"""G3 M4: run mandate, stage handback and prompt versioning.

The mandate is written once per run and never mutated afterwards. Handbacks are
validated against the mandate's scope so a paused stage cannot silently widen
what the run is allowed to do. ``prompt_version`` gives every rendered prompt a
deterministic identity for claim traceability.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

MANDATE_NAME = "run_mandate.json"
HANDBACK_NAME = "handback.json"
DEFAULT_SCOPE = ("stage:1-23", "tool:literature")
DEFAULT_STRENGTH = "write"
E_HANDBACK_SCOPE = "E_HANDBACK_SCOPE"


class MandateError(RuntimeError):
    """The persisted mandate cannot be reused for this run."""


class HandbackScopeError(RuntimeError):
    """A handback asks for scope outside the run mandate."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RunMandate:
    policy_version: int
    scope: tuple[str, ...]
    strength: str
    requester: str
    created_at: str
    run_id: str

    def as_dict(self) -> dict:
        return {
            "policy_version": self.policy_version,
            "scope": list(self.scope),
            "strength": self.strength,
            "requester": self.requester,
            "created_at": self.created_at,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunMandate":
        scope = raw.get("scope") or ()
        if not isinstance(scope, (list, tuple)):
            raise MandateError("run mandate scope is not a list")
        return cls(
            policy_version=int(raw.get("policy_version", 1)),
            scope=tuple(str(item) for item in scope),
            strength=str(raw.get("strength", DEFAULT_STRENGTH)),
            requester=str(raw.get("requester", "")),
            created_at=str(raw.get("created_at", "")),
            run_id=str(raw.get("run_id", "")),
        )


def ensure_run_mandate(
    run_dir: Path,
    *,
    run_id: str,
    requester: str = "user:local",
    scope: Iterable[str] = DEFAULT_SCOPE,
    strength: str = DEFAULT_STRENGTH,
    policy_version: int = 2,
    created_at: str | None = None,
) -> RunMandate:
    """Load the run mandate or write it once. Existing mandates are immutable."""
    run_dir = Path(run_dir)
    path = run_dir / MANDATE_NAME
    if path.is_file():
        mandate = RunMandate.from_dict(_read_json(path))
        if mandate.run_id != run_id:
            raise MandateError(
                f"run mandate belongs to {mandate.run_id!r}, requested {run_id!r}"
            )
        return mandate
    mandate = RunMandate(
        policy_version=int(policy_version),
        scope=tuple(dict.fromkeys(str(item) for item in scope)),
        strength=str(strength),
        requester=str(requester),
        created_at=created_at or _now(),
        run_id=run_id,
    )
    _atomic_write_text(
        path, json.dumps(mandate.as_dict(), ensure_ascii=False, indent=2) + "\n"
    )
    return mandate


@dataclass(frozen=True)
class StageHandback:
    reason: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    requested_scope: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "reason": self.reason,
            "evidence": list(self.evidence),
            "requested_scope": list(self.requested_scope),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "StageHandback":
        evidence = raw.get("evidence") or ()
        scope = raw.get("requested_scope") or ()
        return cls(
            reason=str(raw.get("reason", "")),
            evidence=tuple(str(item) for item in evidence),
            requested_scope=tuple(str(item) for item in scope),
        )


def validate_handback(handback: StageHandback, mandate: RunMandate) -> None:
    """Reject a handback that requests scope outside the mandate."""
    if not handback.reason.strip():
        raise HandbackScopeError("handback reason is empty")
    allowed = set(mandate.scope)
    out_of_scope = [item for item in handback.requested_scope if item not in allowed]
    if out_of_scope:
        raise HandbackScopeError(
            f"{E_HANDBACK_SCOPE}: requested scope outside mandate: {out_of_scope}"
        )


def write_handback(
    stage_dir: Path, handback: StageHandback, mandate: RunMandate
) -> Path:
    """Validate and persist a stage handback."""
    validate_handback(handback, mandate)
    path = Path(stage_dir) / HANDBACK_NAME
    _atomic_write_text(
        path, json.dumps(handback.as_dict(), ensure_ascii=False, indent=2) + "\n"
    )
    return path


def read_handback(stage_dir: Path) -> StageHandback | None:
    path = Path(stage_dir) / HANDBACK_NAME
    if not path.is_file():
        return None
    return StageHandback.from_dict(_read_json(path))


def prompt_version(
    *,
    system: str,
    user_template: str,
    model_role: str,
    prompt_bank_version: str,
) -> str:
    """Deterministic prompt identity: sha256 over the rendered templates."""
    payload = {
        "system": system,
        "user_template": user_template,
        "model_role": model_role,
        "prompt_bank_version": prompt_bank_version,
    }
    return "sha256:" + hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()
