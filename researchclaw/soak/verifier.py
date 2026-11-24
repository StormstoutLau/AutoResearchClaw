"""Read-only soak verification (G7 A7-1/A7-4, P-160).

Design authority: ``spec/arc-g7-soak/DESIGN.md`` §4.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from researchclaw.runtime.event_log import EventLog
from researchclaw.run_state import read_run_state

_COMPLETED = {"done", "completed", "success", "succeeded", "finished"}
_FAILED = {"failed", "error", "cancelled", "canceled"}
_PAUSED = {"paused", "blocked_approval", "rejected", "waiting_human",
           "waiting", "retrying"}
_RUNNING = {"running", "pending", "active", "started"}


@dataclass(frozen=True)
class RunVerification:
    run_id: str
    ok: bool
    problems: tuple[str, ...]
    chain_ok: bool
    chain_message: str
    first_seq: int
    last_seq: int
    event_count: int
    seq_gaps: tuple[int, ...]
    duplicate_seqs: tuple[int, ...]
    run_id_mismatches: tuple[int, ...]
    segments: tuple[dict, ...]
    checkpoint_stage: int
    checkpoint_name: str
    checkpoint_status: str
    max_completed_stage: int
    event_checkpoint_skew: int
    completed_stages: tuple[int, ...]
    terminal_status: str
    convergence_signature: dict
    reference_signature: dict | None
    converged: bool
    retention_limited: bool
    failure_stages: tuple[tuple[int, int], ...]


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in _COMPLETED:
        return "completed"
    if text in _FAILED:
        return "failed"
    if text in _PAUSED:
        return "paused"
    if text in _RUNNING:
        return "running"
    return "unknown"


def _event_stage(event: dict) -> int | None:
    payload = event.get("payload") or {}
    raw = payload.get("stage", event.get("stage"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def event_seq_coverage(events: list[dict]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return ``(gaps, duplicates)`` within ``min(seq)..max(seq)``.

    A missing prefix (retention deletion) is reported separately by
    ``verify_run`` so it is not expanded into thousands of pseudo-gaps.
    """
    seqs: list[int] = []
    for event in events:
        try:
            seqs.append(int(event.get("seq")))
        except (TypeError, ValueError, AttributeError):
            continue
    if not seqs:
        return (), ()
    seen: set[int] = set()
    duplicates: set[int] = set()
    for seq in seqs:
        if seq in seen:
            duplicates.add(seq)
        seen.add(seq)
    gaps = tuple(n for n in range(min(seqs), max(seqs) + 1) if n not in seen)
    return gaps, tuple(sorted(duplicates))


def _completed_stages(events: list[dict]) -> tuple[int, ...]:
    out: list[int] = []
    for event in events:
        if event.get("type") != "stage.completed":
            continue
        stage = _event_stage(event)
        if stage is not None:
            out.append(stage)
    return tuple(out)


def collect_failure_stages(events: list[dict]) -> tuple[tuple[int, int], ...]:
    counts: dict[int, int] = {}
    for event in events:
        if event.get("type") != "stage.failed":
            continue
        stage = _event_stage(event)
        if stage is None:
            continue
        counts[stage] = counts.get(stage, 0) + 1
    return tuple(sorted(counts.items()))


def _segments(run_dir: Path) -> tuple[dict, ...]:
    out = []
    for path in sorted(run_dir.glob("events.*.jsonl*")):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append({"file": path.name, "bytes": size})
    return tuple(out)


def _checkpoint(run_dir: Path) -> tuple[int, str, str]:
    data = _read_json(run_dir / "checkpoint.json") or {}
    try:
        stage = int(data.get("last_completed_stage") or 0)
    except (TypeError, ValueError):
        stage = 0
    name = str(data.get("last_completed_name") or "")
    status = _normalize_status(data.get("status"))
    return stage, name, status


def read_terminal_status(run_dir: str | Path) -> str:
    """Pipeline summary first, then checkpoint, then the shared run-state view."""
    run_dir = Path(run_dir)
    summary = _read_json(run_dir / "pipeline_summary.json") or {}
    status = _normalize_status(summary.get("final_status"))
    if status != "unknown":
        return status
    _stage, _name, checkpoint_status = _checkpoint(run_dir)
    if checkpoint_status != "unknown":
        return checkpoint_status
    try:
        return _normalize_status(read_run_state(run_dir).status.value)
    except Exception:  # noqa: BLE001 - a degraded view must not break verification
        return "unknown"


def convergence_signature(run_dir: str | Path) -> dict:
    """Terminal-state signature (DESIGN v1.1 D-4).

    Volatile fields (timestamps, run_id, retry counts, intermediate event
    sequences) are excluded by construction.
    """
    run_dir = Path(run_dir)
    stage, name, _status = _checkpoint(run_dir)
    return {
        "final_status": read_terminal_status(run_dir),
        "last_completed_stage": stage,
        "last_completed_name": name,
    }


def _reference_is_usable(signature: dict) -> bool:
    return bool(
        signature.get("last_completed_stage")
        or signature.get("last_completed_name")
        or signature.get("final_status") not in ("unknown", "")
    )


def verify_run(
    run_dir: str | Path,
    *,
    expected_run_id: str | None = None,
    reference_run_dir: str | Path | None = None,
    allow_retention_gap: bool = False,
) -> RunVerification:
    run_dir = Path(run_dir)
    run_id = expected_run_id or run_dir.name
    if not run_dir.is_dir():
        signature = {
            "final_status": "unknown",
            "last_completed_stage": 0,
            "last_completed_name": "",
        }
        return RunVerification(
            run_id=run_id, ok=False, problems=("run_dir_missing",),
            chain_ok=False, chain_message="run directory does not exist",
            first_seq=0, last_seq=0, event_count=0, seq_gaps=(),
            duplicate_seqs=(), run_id_mismatches=(), segments=(),
            checkpoint_stage=0, checkpoint_name="", checkpoint_status="unknown",
            max_completed_stage=0, event_checkpoint_skew=0, completed_stages=(),
            terminal_status="unknown", convergence_signature=signature,
            reference_signature=None, converged=False, retention_limited=False,
            failure_stages=(),
        )

    log = EventLog(run_dir, run_id)
    problems: list[str] = []
    try:
        events = log.read_all()
        chain_ok, chain_message = log.verify_chain()
    except (OSError, ValueError) as exc:
        events = []
        chain_ok, chain_message = False, "event log unreadable: %s" % exc
        problems.append("archive_unreadable")

    if not events:
        problems.append("no_events")
    if not chain_ok:
        problems.append("chain:%s" % chain_message)

    seqs = []
    for event in events:
        try:
            seqs.append(int(event.get("seq")))
        except (TypeError, ValueError, AttributeError):
            continue
    first_seq = min(seqs) if seqs else 0
    last_seq = max(seqs) if seqs else 0
    gaps, duplicates = event_seq_coverage(events)
    if gaps:
        problems.append("seq_gaps:%s" % ",".join(str(x) for x in gaps[:20]))
    if duplicates:
        problems.append("duplicate_seqs:%s" % ",".join(str(x) for x in duplicates[:20]))

    mismatches: list[int] = []
    for event in events:
        if event.get("run_id") != run_id:
            try:
                mismatches.append(int(event.get("seq")))
            except (TypeError, ValueError):
                continue
    if mismatches:
        problems.append("run_id_mismatch_at:%s" % ",".join(str(x) for x in mismatches[:20]))

    segments = _segments(run_dir)
    retention_limited = bool(
        first_seq > 1 and not any(seg["file"].startswith("events.1-")
                                 for seg in segments))
    if retention_limited and not allow_retention_gap:
        problems.append("retention_limited")

    # Cursor replay: one probe, not a second full read.
    cursor_mismatch = False
    if last_seq > 0:
        probe = max(1, last_seq // 2)
        try:
            cursor = log.read_after(probe)
            expected = [e for e in events if int(e.get("seq", 0)) > probe]
            cursor_mismatch = cursor != expected
        except (OSError, ValueError):
            cursor_mismatch = True
    if cursor_mismatch:
        problems.append("cursor_mismatch")

    checkpoint_stage, checkpoint_name, checkpoint_status = _checkpoint(run_dir)
    completed_stages = _completed_stages(events)
    max_completed_stage = max(completed_stages) if completed_stages else 0
    skew = checkpoint_stage - max_completed_stage
    if events and checkpoint_stage == 0:
        problems.append("missing_checkpoint")
    if skew < 0:
        problems.append("checkpoint_behind_events")

    terminal_status = read_terminal_status(run_dir)
    signature = {
        "final_status": terminal_status,
        "last_completed_stage": checkpoint_stage,
        "last_completed_name": checkpoint_name,
    }

    reference_signature = None
    integrity_ok = bool(
        chain_ok and not gaps and not duplicates and not mismatches
        and not cursor_mismatch
        and (allow_retention_gap or not retention_limited)
    )
    if reference_run_dir is not None:
        reference_signature = convergence_signature(reference_run_dir)
        if not _reference_is_usable(reference_signature):
            problems.append("reference_invalid")
            converged = False
        else:
            converged = integrity_ok and signature == reference_signature
            if signature != reference_signature:
                for key in ("final_status", "last_completed_stage",
                            "last_completed_name"):
                    if signature.get(key) != reference_signature.get(key):
                        problems.append("signature_mismatch:%s" % key)
    else:
        converged = bool(
            integrity_ok
            and terminal_status == "completed"
            and checkpoint_stage > 0
            and checkpoint_stage >= max_completed_stage
        )

    return RunVerification(
        run_id=run_id,
        ok=not problems,
        problems=tuple(problems),
        chain_ok=chain_ok,
        chain_message=chain_message,
        first_seq=first_seq,
        last_seq=last_seq,
        event_count=len(events),
        seq_gaps=gaps,
        duplicate_seqs=duplicates,
        run_id_mismatches=tuple(mismatches),
        segments=segments,
        checkpoint_stage=checkpoint_stage,
        checkpoint_name=checkpoint_name,
        checkpoint_status=checkpoint_status,
        max_completed_stage=max_completed_stage,
        event_checkpoint_skew=skew,
        completed_stages=completed_stages,
        terminal_status=terminal_status,
        convergence_signature=signature,
        reference_signature=reference_signature,
        converged=converged,
        retention_limited=retention_limited,
        failure_stages=collect_failure_stages(events),
    )
