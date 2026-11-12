"""Tool invocation pipeline (G4-M3, A4-4/A4-5).

Order is deliberate: schema validation -> approval gate -> ``tool.call`` ->
handler -> ``tool.result``. Rejected calls never emit ``tool.call`` so that
"every call has a result" stays a checkable invariant.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.tools.approvals import is_approved
from researchclaw.tools.registry import Registry, ToolSpec, unfreeze

logger = logging.getLogger(__name__)

E_APPROVAL_REQUIRED = "E_APPROVAL_REQUIRED"
E_INVALID_ARGUMENTS = "E_INVALID_ARGUMENTS"
E_EVENT_LOG_UNAVAILABLE = "E_EVENT_LOG_UNAVAILABLE"

Handler = Callable[[dict], Awaitable[dict]]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(obj: Any) -> str:
    """SHA-256 over canonical JSON; non-JSON values degrade to ``str`` (review
    D-2) so a handler result can never escape ``invoke`` nor orphan its call."""
    return _sha256(canonical_json(_to_jsonable(obj)))


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _args_summary(args: Mapping[str, Any]) -> str:
    """Key names only — values never enter the event log (I-3)."""
    return ",".join(sorted(args))[:200]


def _result_summary(result: Mapping[str, Any]) -> str:
    keys = ",".join(sorted(_to_jsonable(dict(result))))
    return f"success={result.get('success')};keys={keys}"[:200]


def _requires_approval(spec: ToolSpec) -> bool:
    return spec.approval == "always" or (
        spec.approval == "high_only" and spec.risk == "high"
    )


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "error": message}


class ToolInvoker:
    """Run-scoped tool invoker with fail-closed approval and event pairing."""

    def __init__(
        self,
        registry: Registry,
        handlers: Mapping[str, Handler],
        *,
        event_log: EventLog | None = None,
        approvals_path: str | Path | None = None,
    ) -> None:
        self.registry = registry
        self.handlers = handlers
        self.event_log = event_log
        self.approvals_dir = Path(approvals_path).parent if approvals_path else None
        self._validators = {
            spec.name: Draft202012Validator(unfreeze(spec.input_schema))
            for spec in registry.tools
        }

    async def invoke(self, name: str, args: dict | None) -> dict[str, Any]:
        arguments = dict(args or {})
        spec = self.registry.get(name)
        if spec is None:
            return _error("INVALID_TOOL", f"Unknown tool: {name}")

        try:
            self._validators[name].validate(arguments)
        except ValidationError as exc:
            return _error(E_INVALID_ARGUMENTS, exc.message)

        call_id = uuid.uuid4().hex
        if _requires_approval(spec) and not self._approved(name):
            self._emit("approval.required", {
                "tool": name,
                "risk": spec.risk,
                "approval": spec.approval,
                "call_id": call_id,
            })
            return _error(E_APPROVAL_REQUIRED,
                          f"tool '{name}' requires approval")

        if self.event_log is not None:
            try:
                self.event_log.append("tool.call", {
                    "tool": name,
                    "call_id": call_id,
                    "risk": spec.risk,
                    "args_digest": _digest(arguments),
                    "args_summary": _args_summary(arguments),
                })
            except Exception as exc:  # noqa: BLE001 - audit-first
                return _error(E_EVENT_LOG_UNAVAILABLE, str(exc))

        started = time.perf_counter()
        exit_code = 0
        try:
            handler = self.handlers[name]
            result = await handler(arguments)
            if not isinstance(result, dict):
                result = {"success": True, "result": result}
        except ValueError as exc:
            result = _error("INVALID_ARGUMENT", str(exc))
        except Exception as exc:  # noqa: BLE001 - report as tool error
            logger.exception("tool %s failed", name)
            result = _error("INTERNAL_ERROR", str(exc))
        if isinstance(result.get("exit_code"), int):
            exit_code = int(result["exit_code"])

        duration_ms = int((time.perf_counter() - started) * 1000)
        self._emit("tool.result", {
            "tool": name,
            "call_id": call_id,
            "risk": spec.risk,
            "exit_code": exit_code,
            "result_digest": _digest(result),
            "result_summary": _result_summary(result),
            "duration_ms": duration_ms,
        })
        return result

    def _approved(self, name: str) -> bool:
        if self.approvals_dir is None:
            return False
        return is_approved(self.approvals_dir, name)

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_log is None:
            return
        try:
            self.event_log.append(event_type, payload)
        except Exception:  # noqa: BLE001 - execution already happened
            logger.warning("tool event append failed", exc_info=True)


def emit_orphan_markers(event_log: EventLog) -> list[str]:
    """Append ``tool.orphan_call`` for unpaired calls; idempotent per call_id."""
    calls: dict[str, str] = {}
    results: set[str] = set()
    marked: set[str] = set()
    for event in event_log.read_all():
        kind = event.get("type")
        payload = event.get("payload") or {}
        call_id = payload.get("call_id")
        if not call_id:
            continue
        if kind == "tool.call":
            calls[call_id] = str(payload.get("tool", ""))
        elif kind == "tool.result":
            results.add(call_id)
        elif kind == "tool.orphan_call":
            marked.add(call_id)

    added: list[str] = []
    for call_id, tool in calls.items():
        if call_id in results or call_id in marked:
            continue
        event_log.append("tool.orphan_call",
                         {"call_id": call_id, "tool": tool})
        added.append(call_id)
    return added
