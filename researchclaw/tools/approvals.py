"""Run-scoped tool approvals (G4-M3, A4-5).

``approvals.json`` is the only release source (M0 §5). Reads are fail-closed:
a missing, unreadable or malformed file means "not approved". Writes are
atomic and serialised with the repo's cross-platform advisory lock.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from researchclaw.runtime.filelock import exclusive_lock

APPROVALS_NAME = "approvals.json"


def _path(run_dir: str | Path) -> Path:
    return Path(run_dir) / APPROVALS_NAME


def read_approvals(run_dir: str | Path) -> dict[str, dict]:
    """Return the approval table; any read/parse/shape problem yields ``{}``."""
    path = _path(run_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(key): value
        for key, value in data.items()
        if isinstance(value, dict)
    }


def is_approved(run_dir: str | Path, tool: str) -> bool:
    entry = read_approvals(run_dir).get(str(tool))
    return isinstance(entry, dict) and entry.get("approved") is True


def grant(run_dir: str | Path, tool: str, *, by: str) -> Path:
    """Atomically record an approval for ``tool`` under ``run_dir``."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = _path(run_dir)
    lock = run_dir / ".locks" / "approvals.lock"
    with exclusive_lock(lock):
        data = read_approvals(run_dir)
        data[str(tool)] = {
            "approved": True,
            "by": str(by),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        fd, tmp_name = tempfile.mkstemp(dir=str(run_dir), prefix=".approvals.",
                                        suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    return path
