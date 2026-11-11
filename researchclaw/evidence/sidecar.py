"""M3 sidecar client: file-based JSON contract with the 3.12 Auto_Prover CLI.

The client starts one subprocess per request, waits with a hard timeout, kills
the process tree on expiry, and validates the response envelope before use.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
C4_REQUIRED = (
    "claim_id", "claim_class", "claim_type", "statement", "formal_statement",
    "formality", "assumptions", "evidence", "reasoning_chain", "stats_protocol",
    "falsifier", "verification_depth", "status", "policy_version",
)
STATUSES = {
    "formally_verified", "partially_formalized", "numerically_verified",
    "latex_verified", "falsified", "failed", "speculation",
}
DEPTHS = {"stage1", "stage2", "stage3", "stage3_5"}
CLAIM_ID_RE = re.compile(r"^c-[0-9a-f]{8}$")
THEOREM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_'.]*$")
MAX_CODE_CHARS = 200_000


class SidecarError(RuntimeError):
    """Base error; carries the sidecar response when one exists."""

    def __init__(self, message: str, *, exit_code: int = 0, response: dict | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.response = response or {}


class SidecarRequestError(SidecarError):
    """Exit 65: invalid request."""


class SidecarTimeout(SidecarError):
    """Exit 75: retryable timeout."""


class SidecarConfigError(SidecarError):
    """Exit 78: missing required capability or config."""


@dataclass(frozen=True)
class SidecarConfig:
    python_exe: str
    ap_root: Path
    timeout_s: float = 330.0
    require_lean: bool = True
    env_extra: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SidecarResult:
    exit_code: int
    response: dict
    request_path: Path
    response_path: Path


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _build_env(config: SidecarConfig) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in (
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE",
        # Lean diagnostics are UTF-8; without Python UTF-8 mode the sidecar
        # decodes them with the system code page and loses axiom/sorry lines.
        "PYTHONUTF8", "PYTHONIOENCODING",
    ):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env["PYTHONPATH"] = str(config.ap_root)
    for key in ("ARB_LEAN_PROJECT", "ARB_LEAN_RUN_ROOT", "ARB_LEAN_LAKE"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    env.update({key: str(value) for key, value in config.env_extra.items()})
    return env


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, check=False,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass


def _validate_request(claim: Mapping[str, Any], lean_statement: str, theorem_name: str) -> None:
    if not isinstance(claim, Mapping):
        raise SidecarRequestError("claim must be a mapping", exit_code=65)
    missing = [key for key in C4_REQUIRED if key not in claim]
    if missing:
        raise SidecarRequestError(f"claim missing C4 fields: {missing}", exit_code=65)
    if not CLAIM_ID_RE.match(str(claim.get("claim_id", ""))):
        raise SidecarRequestError("claim_id must match c-<8 hex>", exit_code=65)
    if claim.get("status") not in STATUSES:
        raise SidecarRequestError("claim.status is invalid", exit_code=65)
    if claim.get("verification_depth") not in DEPTHS:
        raise SidecarRequestError("claim.verification_depth is invalid", exit_code=65)
    if not isinstance(lean_statement, str) or not lean_statement.strip():
        raise SidecarRequestError("lean_statement is required", exit_code=65)
    if len(lean_statement) > MAX_CODE_CHARS:
        raise SidecarRequestError("lean_statement is too long", exit_code=65)
    if not THEOREM_RE.match(theorem_name or ""):
        raise SidecarRequestError("theorem_name is invalid", exit_code=65)


def _validate_response(payload: dict[str, Any], request_id: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SidecarError("response schema_version mismatch")
    if payload.get("request_id") != request_id:
        raise SidecarError("response request_id mismatch")
    run = payload.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("exit_code"), int):
        raise SidecarError("response run is invalid")
    claim = payload.get("claim_record")
    if not isinstance(claim, dict):
        raise SidecarError("response claim_record is missing")
    missing = [key for key in C4_REQUIRED if key not in claim]
    if missing:
        raise SidecarError(f"response claim_record missing: {missing}")
    if claim.get("status") not in STATUSES:
        raise SidecarError("response claim_record.status is invalid")
    if claim.get("verification_depth") not in DEPTHS:
        raise SidecarError("response claim_record.verification_depth is invalid")


def _map_exit(exit_code: int, payload: dict[str, Any]) -> None:
    if exit_code == 0:
        return
    if exit_code == 77:
        raise SidecarError("sidecar emitted reserved exit 77", exit_code=77, response=payload)
    if exit_code == 65:
        raise SidecarRequestError("sidecar rejected the request", exit_code=65, response=payload)
    if exit_code == 75:
        raise SidecarTimeout("sidecar timed out", exit_code=75, response=payload)
    if exit_code == 78:
        raise SidecarConfigError("sidecar capability/config missing", exit_code=78, response=payload)
    raise SidecarError(f"sidecar failed with exit {exit_code}", exit_code=exit_code, response=payload)


def run_lean_check(
    claim: Mapping[str, Any],
    lean_statement: str,
    theorem_name: str,
    *,
    config: SidecarConfig,
    run_dir: Path,
    source_project: str | None = None,
    use_per_run_project: bool = True,
    request_id: str | None = None,
) -> SidecarResult:
    _validate_request(claim, lean_statement, theorem_name)
    request_id = request_id or uuid.uuid4().hex
    if not re.match(r"^[A-Za-z0-9._-]+$", request_id):
        raise SidecarRequestError("request_id contains invalid characters", exit_code=65)

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    response_path = run_dir / "response.json"
    request_timeout = max(5.0, float(config.timeout_s) - 30.0)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "mode": "lean_check",
        "require_lean": bool(config.require_lean),
        "claim": dict(claim),
        "lean": {
            "lean_statement": lean_statement,
            "theorem_name": theorem_name,
            "source_project": source_project or "",
            "use_per_run_project": bool(use_per_run_project),
            "timeout_s": request_timeout,
        },
    }
    _write_json_atomic(request_path, payload)

    script = Path(config.ap_root) / "scripts" / "arb_verify.py"
    if not script.is_file():
        raise SidecarConfigError(f"sidecar script not found: {script}", exit_code=78)

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            [config.python_exe, str(script), "--request", str(request_path), "--response", str(response_path)],
            cwd=str(run_dir),
            env=_build_env(config),
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            start_new_session=(os.name != "nt"),
        )
        try:
            exit_code = proc.wait(timeout=float(config.timeout_s))
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            proc.wait(timeout=30)
            response = {
                "schema_version": SCHEMA_VERSION,
                "request_id": request_id,
                "run": {
                    "run_id": request_id,
                    "attempt": 1,
                    "inputs_digest": "sha256:" + "0" * 64,
                    "exit_code": 75,
                    "status": "timeout",
                    "usage": {},
                },
                "claim_record": dict(claim),
                "lean": {"available": False, "tree_origin": None},
                "degraded_reason": "lean_timeout",
                "lean_unavailable_reason": "lean_timeout",
            }
            raise SidecarTimeout("sidecar hard timeout", exit_code=75, response=response)

    if not response_path.is_file():
        raise SidecarError(
            f"sidecar wrote no response (exit {exit_code})",
            exit_code=exit_code,
        )
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SidecarError(f"invalid sidecar response: {exc}", exit_code=exit_code) from exc

    _map_exit(exit_code, response)
    _validate_response(response, request_id)
    return SidecarResult(exit_code=exit_code, response=response,
                         request_path=request_path, response_path=response_path)
