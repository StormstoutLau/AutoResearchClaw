"""Event replay endpoints (G1c / A1-2): cursor page, SSE stream, WS subscribe.

Thin adapters over :mod:`researchclaw.runtime.event_stream`; all semantics
(pagination, gap, terminal detection) live in the transport-agnostic core.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from researchclaw.runtime.event_stream import (
    MAX_STREAMS_PER_RUN, ConnectionLimiter, gap_frame, heartbeat_frame,
    parse_cursor, read_page, sse_frame,
)

router = APIRouter(prefix="/api", tags=["events"])

HEARTBEAT_SECONDS = 15.0
POLL_SECONDS = 1.0
_limiter = ConnectionLimiter(MAX_STREAMS_PER_RUN)


def _run_dir(run_id: str) -> Path:
    from researchclaw.server.routes.pipeline import _validated_run_dir
    return _validated_run_dir(run_id)


def _has_event_log(run_dir: Path) -> bool:
    """The log may live only in rolled segments (active file absent)."""
    return (run_dir / "events.jsonl").exists() or bool(
        list(run_dir.glob("events.*.jsonl")))


def _require_event_log(run_id: str) -> Path:
    """404 before any read so ``EventLog`` never mkdirs a bogus run dir (D-3)."""
    run_dir = _run_dir(run_id)
    if not _has_event_log(run_dir):
        raise HTTPException(status_code=404, detail=f"No event log for run {run_id}")
    return run_dir


def _page(run_id: str, after: int | None, limit: int | None) -> dict:
    run_dir = _require_event_log(run_id)
    return read_page(run_dir, run_id, after=after, limit=limit)


@router.get("/runs/{run_id}/events")
async def list_events(run_id: str, request: Request, after: int | None = None,
                      limit: int | None = None) -> dict:
    cursor = parse_cursor(request.headers.get("Last-Event-ID"), after)
    return _page(run_id, cursor, limit)


@router.get("/runs/{run_id}/events/stream")
async def stream_events(run_id: str, request: Request, after: int | None = None,
                        limit: int | None = None):
    cursor = parse_cursor(request.headers.get("Last-Event-ID"), after)
    run_dir = _require_event_log(run_id)
    if not _limiter.acquire(run_id):
        raise HTTPException(status_code=429,
                            detail=f"too many event streams for run {run_id}")

    async def gen():
        nonlocal cursor
        try:
            yield "retry: 3000\n\n"
            idle = 0.0
            while True:
                if await request.is_disconnected():
                    return
                if not _has_event_log(run_dir):
                    return
                page = read_page(run_dir, run_id, after=cursor, limit=limit)
                if page["gap"]:
                    yield gap_frame(page["oldest_seq"])
                    cursor = page["oldest_seq"] - 1
                    continue
                for event in page["events"]:
                    yield sse_frame(event)
                if page["events"]:
                    cursor = page["next_after"]
                    idle = 0.0
                if page["terminal"]:
                    return
                idle += POLL_SECONDS
                if idle >= HEARTBEAT_SECONDS:
                    yield heartbeat_frame()
                    idle = 0.0
                await asyncio.sleep(POLL_SECONDS)
        finally:
            _limiter.release(run_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.websocket("/runs/{run_id}/events/ws")
async def ws_events(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    run_dir = _run_dir(run_id)
    if not _has_event_log(run_dir):
        await websocket.close(code=1008, reason="no event log for run")
        return
    if not _limiter.acquire(run_id):
        await websocket.close(code=1013)      # try again later
        return
    try:
        first = json.loads(await websocket.receive_text())
        if first.get("type") != "subscribe":
            await websocket.close(code=1008)
            return
        cursor = parse_cursor(None, first.get("after"))
        while True:
            if not _has_event_log(run_dir):
                await websocket.close(code=1008, reason="event log removed")
                return
            page = read_page(run_dir, run_id, after=cursor)
            if page["gap"]:
                await websocket.send_text(json.dumps(
                    {"type": "stream.gap", "oldest_seq": page["oldest_seq"]}))
                cursor = page["oldest_seq"] - 1
                continue
            for event in page["events"]:
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            if page["events"]:
                cursor = page["next_after"]
            if page["terminal"]:
                await websocket.close()
                return
            await asyncio.sleep(POLL_SECONDS)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001 - malformed frame closes the socket
        await websocket.close(code=1008)
    finally:
        _limiter.release(run_id)
