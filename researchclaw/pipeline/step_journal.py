"""Stage-level step journal (B-33 / L1).

A stage (notably Stage 10) spends tens of minutes inside a single stage; the
pipeline checkpoint only advances when the stage finishes.  This module records
one line per completed sub-step so a re-entry can skip work whose inputs have
not changed.

Invariants
----------
I-1  ``steps.jsonl`` is append-only; ``seq`` is strictly monotonic.
I-2  Payloads carry digests only — never prompts or generated code (mirrors the
     event-log rule I-4).
I-3  Only ``status == "done"`` entries are reusable; truncated or failed
     attempts must never be replayed.
I-4  ``should_skip`` is a pure function over (journal entry, inputs, disk state).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from researchclaw.runtime.filelock import exclusive_lock
from researchclaw.utils.paths import safe_join

STEP_JOURNAL_NAME = "steps.jsonl"
STEP_LOCK_NAME = ".steps.lock"


class StepJournalError(ValueError):
    """Corrupt ``steps.jsonl`` line (a torn tail is tolerated)."""


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_text(text: str) -> str:
    """Digest used for inputs and single-file outputs."""
    return "sha256:" + hashlib.sha256(str(text).encode("utf-8")).hexdigest()


_VERSION_FILES = ("code_agent.py", "stage_impls/_code_generation.py")


def _read_package_bytes(rel: str) -> bytes | None:
    """Read a generator file from the installed package (zip-safe).

    ``Path(__file__)`` works in a checkout but breaks under zipimport; the
    ``importlib.resources`` path is the portable form.
    """
    try:
        from importlib.resources import files as _files

        target = _files("researchclaw.pipeline")
        for part in rel.split("/"):
            target = target / part
        data = target.read_bytes()
        return data if isinstance(data, bytes) else None
    except Exception:  # noqa: BLE001 - fall through to the path-based read
        pass
    try:
        return (Path(__file__).resolve().parent / rel).read_bytes()
    except OSError:
        return None


def code_version() -> str:
    """Stable identity for the Stage 10 generator code.

    Design decision D-8 (B-33): one algorithm only — package version plus the
    first 8 hex chars of the two generator files, so a change to either file
    invalidates journalled steps without any manual bump.
    """
    try:
        from researchclaw import __version__
    except Exception:  # noqa: BLE001 - version is informational only
        __version__ = "0"
    digest = hashlib.sha256()
    for rel in _VERSION_FILES:
        data = _read_package_bytes(rel)
        if data is not None:
            digest.update(data)
    return f"{__version__}+{digest.hexdigest()[:8]}"


def step_key(step_id: str, variant: str = "") -> str:
    """Composite key: ``<phase>:<subject>`` and an optional variant suffix."""
    return f"{step_id}:{variant}" if variant else step_id


def load_steps(stage_dir: str | Path) -> list[dict[str, Any]]:
    """Read the journal.

    A run of corrupt lines at the tail is dropped (crash recovery, matching
    ``stage_events.load_stage_events``); corruption before the last parseable
    line raises :class:`StepJournalError`.
    """
    path = Path(stage_dir) / STEP_JOURNAL_NAME
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    last_good = -1
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        last_good = index
    steps: list[dict[str, Any]] = []
    for index, line in enumerate(lines[: last_good + 1]):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StepJournalError(f"{path}:{index + 1}: {exc.msg}") from exc
        if isinstance(raw, dict):
            steps.append(raw)
    return steps


def append_step(
    stage_dir: str | Path,
    *,
    step_id: str,
    variant: str = "",
    status: str = "done",
    inputs_digest: str = "",
    outputs: Mapping[str, str] | None = None,
    model: str = "",
    elapsed_sec: float = 0.0,
    truncated: bool = False,
    code_version_value: str | None = None,
    prompt_version: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    """Append one step record under an advisory lock; returns the record."""
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts or _utcnow_iso(),
        "stage": stage_dir.name,
        "step_id": step_id,
        "variant": variant,
        "status": status,
        "inputs_digest": inputs_digest,
        "outputs": dict(outputs or {}),
        "model": model,
        "elapsed_sec": round(float(elapsed_sec), 3),
        "truncated": bool(truncated),
        "code_version": code_version_value
        if code_version_value is not None
        else code_version(),
        "prompt_version": prompt_version,
    }
    with exclusive_lock(stage_dir / STEP_LOCK_NAME):
        existing = load_steps(stage_dir)
        payload["seq"] = (int(existing[-1].get("seq") or 0) + 1) if existing else 1
        with safe_join(stage_dir, STEP_JOURNAL_NAME).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    return payload


def last_done(
    steps: list[dict[str, Any]], step_id: str, variant: str = "",
) -> dict[str, Any] | None:
    """Most recent ``status=done`` entry for ``(step_id, variant)``."""
    for entry in reversed(steps):
        if entry.get("step_id") != step_id:
            continue
        if str(entry.get("variant") or "") != str(variant or ""):
            continue
        if entry.get("status") == "done" and not entry.get("truncated"):
            return entry
    return None


def should_skip(
    last: Mapping[str, Any] | None,
    *,
    inputs_digest: str,
    files_on_disk: Mapping[str, str],
    code_version_value: str | None = None,
    prompt_version: str = "",
) -> bool:
    """Whether a journalled step can be reused as-is.

    A missing file is a cache miss (V-6), never a silent hit.
    """
    if not isinstance(last, Mapping) or not last:
        return False
    if last.get("status") != "done" or last.get("truncated"):
        return False
    if str(last.get("inputs_digest") or "") != str(inputs_digest or ""):
        return False
    if (
        code_version_value is not None
        and str(last.get("code_version") or "") != str(code_version_value)
    ):
        return False
    if (
        prompt_version
        and str(last.get("prompt_version") or "") != str(prompt_version)
    ):
        return False
    outputs = last.get("outputs")
    if not isinstance(outputs, Mapping) or not outputs:
        return False
    for name, expected in outputs.items():
        actual = files_on_disk.get(str(name))
        if actual is None or str(actual) != str(expected):
            return False
    return True
