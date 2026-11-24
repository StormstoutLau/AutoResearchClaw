"""Read-position persistence for literature sources (P-155 / A5-9)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _key(kind: str, instance: str) -> str:
    return f"{kind}:{instance}"


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_position(path: str | Path, kind: str, instance: str, position: int) -> None:
    target = Path(path)
    data = _read(target)
    data[_key(kind, instance)] = {
        "position": int(position),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(target, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_position(path: str | Path, kind: str, instance: str) -> int:
    entry = _read(Path(path)).get(_key(kind, instance))
    if not isinstance(entry, dict):
        return 0
    try:
        return int(entry.get("position", 0))
    except (TypeError, ValueError):
        return 0
