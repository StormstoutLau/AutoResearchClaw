"""Transport-agnostic event replay core (G1c / A1-2).

Pure functions only: pagination, gap detection and SSE framing. The HTTP and
WS routes are thin adapters, so this module is fully testable without
FastAPI installed (server deps are optional extras).
"""
from __future__ import annotations

import json
from pathlib import Path

TERMINAL_EVENTS = ("run.completed", "run.failed", "run.paused")
DEFAULT_LIMIT = 500
MAX_LIMIT = 2000
MAX_STREAMS_PER_RUN = 5


class ConnectionLimiter:
    """Per-run cap on live streams (U-2, P-031). Pure and thread-safe."""

    def __init__(self, limit: int = MAX_STREAMS_PER_RUN) -> None:
        import threading
        self.limit = limit
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}

    def acquire(self, key: str) -> bool:
        with self._lock:
            current = self._active.get(key, 0)
            if current >= self.limit:
                return False
            self._active[key] = current + 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            current = self._active.get(key, 0)
            if current <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] = current - 1

    def active(self, key: str) -> int:
        with self._lock:
            return self._active.get(key, 0)


def parse_cursor(last_event_id: str | None, after: int | None) -> int | None:
    """``Last-Event-ID`` wins over the ``after`` query parameter (D-3)."""
    if last_event_id is not None:
        text = str(last_event_id).strip()
        if text.isdigit():
            return int(text)
    if after is not None:
        try:
            return max(0, int(after))
        except (TypeError, ValueError):
            return None
    return None


def _clamp(limit: int | None) -> int:
    if not limit or int(limit) <= 0:
        return DEFAULT_LIMIT
    return min(int(limit), MAX_LIMIT)


def _oldest_seq(events: list[dict]) -> int:
    return int(events[0]["seq"]) if events else 0


def read_page(
    run_dir: str | Path,
    run_id: str,
    *,
    after: int | None = None,
    limit: int | None = None,
) -> dict:
    """One page of events. ``gap`` is true when the cursor predates retention."""
    from researchclaw.runtime.event_log import EventLog

    log = EventLog(run_dir, run_id)
    events = log.read_all()
    oldest = _oldest_seq(events)
    size = _clamp(limit)

    gap = False
    cursor = after
    if cursor is not None and oldest and cursor < oldest - 1:
        gap = True
        cursor = oldest - 1

    selected = [e for e in events if cursor is None or int(e["seq"]) > cursor]
    page = selected[:size]
    has_more = len(selected) > len(page)
    terminal = any(e.get("type") in TERMINAL_EVENTS for e in page)
    return {
        "run_id": run_id,
        "events": page,
        "oldest_seq": oldest,
        "gap": gap,
        "next_after": int(page[-1]["seq"]) if page else cursor,
        "has_more": has_more,
        "terminal": terminal,
    }


def sse_frame(event: dict) -> str:
    """WHATWG event-stream frame: ``id`` / ``event`` / ``data`` + blank line."""
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
    return "id: %s\nevent: %s\ndata: %s\n\n" % (
        event.get("seq", ""), event.get("type", "message"), payload)


def gap_frame(oldest_seq: int) -> str:
    return "event: stream.gap\ndata: %s\n\n" % json.dumps(
        {"oldest_seq": int(oldest_seq)}, ensure_ascii=False, sort_keys=True)


def heartbeat_frame() -> str:
    return ": ping\n\n"
