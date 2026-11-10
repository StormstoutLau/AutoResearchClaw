"""Append-only, hash-chained event log (G1a / A1-1, A1-5, A1-6, Q9).

Design authority: ``spec/arc-g1-readiness-research/DESIGN.md`` §2-§5 and
``spec/arc-q5-decision-method/RESEARCH.md`` §8.

Invariants
----------
I-1  ``checkpoint.json`` stays authoritative; the event log is a projection
     that can rebuild it.
I-2  ``seq`` is strictly monotonic per run; ``prev_sha256`` chains every line.
I-3  A durability failure (fsync) is **fatal** and never retried — retrying
     fsync can report success after the kernel dropped the page.
I-4  Payloads carry digests and summaries only, never raw prompts or secrets.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENT_LOG_NAME = "events.jsonl"
SUMMARY_NAME = "events_summary.json"
ZERO_HASH = "0" * 64

DEFAULT_MAX_SEGMENT_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_SEGMENT_EVENTS = 10_000
DEFAULT_MAX_RUN_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_RUN_EVENTS = 200_000

#: 事件类型最小集（DESIGN §2.1）
EVENT_TYPES = frozenset({
    "run.started", "run.completed", "run.failed", "run.paused",
    "stage.started", "stage.completed", "stage.failed", "stage.retried",
    "tool.call", "tool.result", "llm.call", "llm.result",
    "approval.required", "effect.queued", "effect.started", "effect.done",
    "event_log_truncated", "event_log_rolled",
})

_KEY_EVENT_TYPES = ("run.started", "run.completed", "run.failed",
                    "stage.failed", "approval.required")


class EventDurabilityError(RuntimeError):
    """fsync / write failure — must abort the run (never retried)."""


class EventQuotaExceeded(RuntimeError):
    """Single-run event volume cap (A1-6) reached."""


def canonical_json(obj: object) -> str:
    """Deterministic JSON used for both line encoding and payload hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EventEnvelope:
    """One line of ``events.jsonl`` (DESIGN §2)."""

    seq: int
    ts: str
    run_id: str
    type: str
    prev_sha256: str
    payload_sha256: str
    payload: dict = field(default_factory=dict)
    stage: int | None = None
    attempt: int | None = None
    fencing: int = 0

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "run_id": self.run_id,
            "type": self.type,
            "stage": self.stage,
            "attempt": self.attempt,
            "fencing": self.fencing,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
            "prev_sha256": self.prev_sha256,
        }

    def to_line(self) -> str:
        return canonical_json(self.to_dict())


def _parse_segment_name(name: str) -> tuple[int, int] | None:
    """``events.<first>-<last>.jsonl[.gz]`` → (first, last)."""
    if not name.startswith("events.") or not name.endswith(".jsonl") and not name.endswith(".jsonl.gz"):
        return None
    stem = name[len("events."):]
    for suffix in (".jsonl.gz", ".jsonl"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        return None
    parts = stem.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1])


class EventLog:
    """Single-writer append-only log with chaining, rolling and retention."""

    def __init__(
        self,
        run_dir: str | Path,
        run_id: str,
        *,
        max_segment_bytes: int = DEFAULT_MAX_SEGMENT_BYTES,
        max_segment_events: int = DEFAULT_MAX_SEGMENT_EVENTS,
        max_run_bytes: int = DEFAULT_MAX_RUN_BYTES,
        max_run_events: int = DEFAULT_MAX_RUN_EVENTS,
        fsync: bool = True,
        fencing: int = 0,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.max_segment_bytes = max_segment_bytes
        self.max_segment_events = max_segment_events
        self.max_run_bytes = max_run_bytes
        self.max_run_events = max_run_events
        self.fsync = fsync
        self.fencing = fencing
        self.truncated = False
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._last_seq = 0
        self._last_hash = ZERO_HASH
        self._seg_first = None
        self._seg_count = 0
        self._seg_bytes = 0
        self._total_events = 0
        self._total_bytes = 0
        self._refresh()

    # ------------------------------------------------------------ state

    @property
    def path(self) -> Path:
        return self.run_dir / EVENT_LOG_NAME

    def _segments(self) -> list[tuple[tuple[int, int], Path]]:
        out = []
        for p in self.run_dir.iterdir():
            key = _parse_segment_name(p.name)
            if key is not None:
                out.append((key, p))
        return sorted(out, key=lambda kv: kv[0][0])

    def _refresh(self) -> None:
        """Rebuild counters from disk (crash recovery: last complete line wins)."""
        self._total_events = 0
        self._total_bytes = 0
        for _key, p in self._segments():
            self._total_bytes += p.stat().st_size
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8", errors="replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            good = []
            for ln in lines:
                try:
                    json.loads(ln)
                except json.JSONDecodeError:
                    self.truncated = True
                    break
                good.append(ln)
            self._seg_count = len(good)
            self._seg_bytes = self.path.stat().st_size
            self._total_events += len(good)
            self._total_bytes += self._seg_bytes
            if good:
                self._last_hash = _sha256(good[-1])
                try:
                    self._last_seq = int(json.loads(good[-1])["seq"])
                except (KeyError, TypeError, ValueError):
                    self._last_seq = len(good)
                self._seg_first = int(json.loads(good[0]).get("seq", 1))
        else:
            self._seg_count = 0
            self._seg_bytes = 0
            self._seg_first = None

    @property
    def last_seq(self) -> int:
        return self._last_seq

    @property
    def count(self) -> int:
        return self._total_events

    # ------------------------------------------------------------ write

    def _check_quota(self, nbytes: int) -> None:
        if self._total_bytes + nbytes > self.max_run_bytes:
            raise EventQuotaExceeded(
                "event log bytes would exceed cap (%d > %d)"
                % (self._total_bytes + nbytes, self.max_run_bytes))
        if self._total_events + 1 > self.max_run_events:
            raise EventQuotaExceeded(
                "event count would exceed cap (%d > %d)"
                % (self._total_events + 1, self.max_run_events))

    def _roll_if_needed(self, incoming: int) -> None:
        if self._seg_count == 0:
            return
        if (self._seg_bytes + incoming <= self.max_segment_bytes
                and self._seg_count < self.max_segment_events):
            return
        first = self._seg_first if self._seg_first is not None else 1
        last = self._last_seq
        target = self.run_dir / ("events.%d-%d.jsonl" % (first, last))
        os.replace(self.path, target)
        self._seg_count = 0
        self._seg_bytes = 0
        self._seg_first = None

    def append(
        self,
        event_type: str,
        payload: dict | None = None,
        *,
        stage: int | None = None,
        attempt: int | None = None,
        fencing: int | None = None,
        ts: str | None = None,
    ) -> EventEnvelope:
        """Append one event and fsync it. Raises on any durability failure."""
        payload = payload or {}
        payload_text = canonical_json(payload)
        env = EventEnvelope(
            seq=self._last_seq + 1,
            ts=ts or _now_iso(),
            run_id=self.run_id,
            type=event_type,
            prev_sha256=self._last_hash,
            payload_sha256=_sha256(payload_text),
            payload=payload,
            stage=stage,
            attempt=attempt,
            fencing=self.fencing if fencing is None else fencing,
        )
        data = (env.to_line() + "\n").encode("utf-8")
        self._check_quota(len(data))
        self._roll_if_needed(len(data))

        try:
            with self.path.open("ab") as fh:
                written = 0
                while written < len(data):
                    written += fh.write(data[written:])
                fh.flush()
                if self.fsync:
                    os.fsync(fh.fileno())
        except OSError as exc:
            raise EventDurabilityError(
                "event log write/fsync failed at seq %d: %s" % (env.seq, exc)) from exc

        self._last_seq = env.seq
        self._last_hash = _sha256(env.to_line())
        self._seg_count += 1
        self._seg_bytes += len(data)
        self._total_events += 1
        self._total_bytes += len(data)
        if self._seg_first is None:
            self._seg_first = env.seq
        return env

    # ------------------------------------------------------------ read

    def _iter_lines(self):
        for _key, p in self._segments():
            if p.suffix == ".gz":
                with gzip.open(p, "rt", encoding="utf-8", errors="replace") as fh:
                    for ln in fh:
                        if ln.strip():
                            yield ln.strip(), p
            else:
                for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if ln.strip():
                        yield ln.strip(), p
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                if ln.strip():
                    yield ln.strip(), self.path

    def read_all(self) -> list[dict]:
        """All events in order. A torn tail in the active segment is dropped."""
        out: list[dict] = []
        tolerance = 0
        for ln, p in self._iter_lines():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                if p == self.path:
                    self.truncated = True
                    break
                tolerance += 1
                if tolerance > 1:
                    raise ValueError("event log corrupted in archived segment: %s" % p)
        return out

    def read_after(self, seq: int) -> list[dict]:
        """Cursor read for Last-Event-ID style replay (A1-2 storage half)."""
        return [e for e in self.read_all() if int(e.get("seq", 0)) > seq]

    def verify_chain(self) -> tuple[bool, str]:
        """Recompute the hash chain and payload digests. Returns (ok, message).

        Three checks per line: seq continuity, the ``prev_sha256`` pointer, and
        the ``payload_sha256`` digest. The digest check closes the tail-line
        hole of pointer-only chains (nothing follows the last line). When
        ``events_summary.json`` is current, its ``chain_tail`` must also match
        the recomputed tail, which closes non-payload field tampering.

        Note: after ``apply_retention`` deletes the oldest segment the chain is
        only partially verifiable and this reports a seq gap; archive-level
        verification is out of scope (see P-040 O-1).
        """
        prev = ZERO_HASH
        expect_seq = 1
        events = self.read_all()
        for e in events:
            if int(e.get("seq", -1)) != expect_seq:
                return False, "seq gap at %r (expected %d)" % (e.get("seq"), expect_seq)
            if e.get("prev_sha256") != prev:
                return False, "prev_sha256 mismatch at seq %d" % expect_seq
            payload_digest = _sha256(canonical_json(e.get("payload", {})))
            if e.get("payload_sha256") != payload_digest:
                return False, "payload_sha256 mismatch at seq %d" % expect_seq
            prev = _sha256(canonical_json(e))
            expect_seq += 1
        ok, msg = self._verify_summary_tail(events, prev)
        if not ok:
            return False, msg
        return True, "ok (%d events)" % (expect_seq - 1)

    def _verify_summary_tail(self, events: list[dict], tail_hash: str) -> tuple[bool, str]:
        """Compare the recomputed tail with the summary when it is current.

        A summary whose ``last_seq`` predates the live log is stale (written by
        an earlier run segment), so tail closure is not applied — otherwise a
        live run would always look tampered.
        """
        p = self.run_dir / SUMMARY_NAME
        if not p.is_file():
            return True, ""
        try:
            summary = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, "events_summary.json is unreadable"
        if not isinstance(summary, dict):
            return False, "events_summary.json is not an object"
        live_last = int(events[-1].get("seq", 0)) if events else 0
        if int(summary.get("last_seq", 0) or 0) != live_last:
            return True, ""
        if summary.get("chain_tail") != tail_hash:
            return False, "chain_tail mismatch with events_summary.json"
        return True, ""

    # ------------------------------------------------------------ lifecycle

    def apply_retention(
        self,
        retention_days: int = 30,
        archive_days: int = 365,
        now: datetime | None = None,
    ) -> dict:
        """Hot→gzip→delete for **rolled** segments; the active log is never moved."""
        now = now or datetime.now(timezone.utc)
        archived, deleted = [], []
        for _key, p in self._segments():
            age_days = (now - datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)).days
            if p.suffix == ".gz":
                if age_days > archive_days:
                    p.unlink()
                    deleted.append(p.name)
                continue
            if age_days > retention_days:
                gz = p.with_suffix(".jsonl.gz")
                with p.open("rb") as src, gzip.open(gz, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                p.unlink()
                archived.append(gz.name)
        return {"archived": archived, "deleted": deleted}

    def summary(self) -> dict:
        events = self.read_all()
        segments = []
        for _key, p in self._segments():
            segments.append({
                "file": p.name,
                "first": _key[0],
                "last": _key[1],
                "bytes": p.stat().st_size,
                "digest": _sha256(p.name + ":" + str(p.stat().st_size)),
            })
        head = _sha256(canonical_json(events[0])) if events else ZERO_HASH
        tail = _sha256(canonical_json(events[-1])) if events else ZERO_HASH
        key_events = [{"seq": e["seq"], "type": e["type"]}
                      for e in events if e.get("type") in _KEY_EVENT_TYPES][:50]
        return {
            "run_id": self.run_id,
            "first_seq": events[0]["seq"] if events else 0,
            "last_seq": events[-1]["seq"] if events else 0,
            "count": len(events),
            "chain_head": head,
            "chain_tail": tail,
            "bytes": sum(p.stat().st_size for p in self.run_dir.iterdir()
                         if _parse_segment_name(p.name) or p.name == EVENT_LOG_NAME),
            "segments": segments,
            "key_events": key_events,
        }

    def write_summary(self) -> dict:
        data = self.summary()
        target = self.run_dir / SUMMARY_NAME
        tmp = os.path.join(self.run_dir, SUMMARY_NAME + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        return data


def rebuild_checkpoint(events: list[dict]) -> dict | None:
    """Rebuild a checkpoint payload from ``stage.completed`` events (A1-5).

    Returns ``None`` when the log has no completed stage. The result mirrors
    ``_write_checkpoint``'s shape so callers can persist it verbatim.
    """
    last = None
    for e in events:
        if e.get("type") == "stage.completed":
            last = e
    if last is None:
        return None
    payload = last.get("payload") or {}
    return {
        "last_completed_stage": int(payload.get("stage", last.get("stage") or 0)),
        "last_completed_name": payload.get("name", ""),
        "run_id": last.get("run_id", ""),
        "timestamp": last.get("ts", ""),
        "recovered": True,
        "recovered_from_seq": int(last.get("seq", 0)),
    }


def replay_digest(log: EventLog) -> str:
    """Cheap fingerprint of the whole log (used by tests and diagnostics)."""
    return log.verify_chain()[1]


def _utcnow_iso_seconds(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat()


def _mtime_days_ago(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400.0
