"""Config snapshot sanitizer for pipeline skills (P-148, option B).

The manifest may carry a *sanitized* config snapshot so a recorded run can be
re-run from the same configuration without leaking credentials or host paths.

Redaction rules (fail-closed, conservative):
- values whose key looks like a credential (``api_key``/``token``/``secret``/
  ``password``/``credential``) are replaced by ``***REDACTED***``;
- ``*_env`` keys are kept: they hold environment-variable *names*, not secrets;
- absolute paths are replaced by ``<REDACTED_PATH>``;
- redacted key paths are returned so the manifest can declare them.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

SNAPSHOT_NAME = "config.sanitized.yaml"
SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|credential|private[_-]?key)", re.I
)
ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|~[\\/]|\\\\)")


class ConfigSanitizeError(ValueError):
    """Config cannot be snapshotted safely."""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _walk(value: Any, key: str, prefix: str, redacted: list[str]) -> Any:
    path = f"{prefix}.{key}" if prefix else str(key)
    if isinstance(value, dict):
        return {k: _walk(v, k, path, redacted) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, str(i), path, redacted) for i, v in enumerate(value)]
    if isinstance(value, str):
        if SECRET_KEY_RE.search(key) and not key.endswith("_env") and value.strip():
            redacted.append(path)
            return "***REDACTED***"
        if ABS_PATH_RE.match(value):
            redacted.append(path)
            return "<REDACTED_PATH>"
    return value


def sanitize_config(data: dict) -> tuple[dict, list[str]]:
    """Return ``(sanitized_copy, redacted_key_paths)``; input is not mutated."""
    if not isinstance(data, dict):
        raise ConfigSanitizeError("config root must be a mapping")
    redacted: list[str] = []
    cleaned = {k: _walk(v, str(k), "", redacted) for k, v in data.items()}
    return cleaned, sorted(set(redacted))


def write_sanitized_snapshot(config_path: str | Path, skill_dir: str | Path) -> dict:
    """Sanitize ``config_path`` into ``skill_dir/config.sanitized.yaml``."""
    source = Path(config_path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigSanitizeError(f"config unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigSanitizeError("config root must be a mapping")
    cleaned, redacted = sanitize_config(data)
    target = Path(skill_dir) / SNAPSHOT_NAME
    text = yaml.safe_dump(cleaned, sort_keys=False, allow_unicode=True)
    _atomic_write(target, text)
    return {
        "pointer": SNAPSHOT_NAME,
        "sha256": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_format": "yaml",
        "redacted_keys": redacted,
    }
