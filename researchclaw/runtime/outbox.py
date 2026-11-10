"""Effect queue derived from the append-only event log (G1b / A1-10).

The event log *is* the outbox: enqueue is an append, dedupe is a set
difference, and completion is another append. No database transaction is
needed (P-025 §3.1).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable

from researchclaw.runtime.event_log import canonical_json


@dataclass(frozen=True)
class Effect:
    kind: str
    key: str
    payload: dict


def effect_key(kind: str, payload: dict) -> str:
    """Stable idempotency key (Stripe-style client key, DESIGN §4)."""
    return hashlib.sha256((kind + canonical_json(payload)).encode("utf-8")).hexdigest()


def _events(log) -> list[dict]:
    try:
        return log.read_all()
    except (OSError, ValueError):
        return []


def pending(log) -> list[Effect]:
    """queued − done, first occurrence wins, order preserved."""
    ok_done, out = set(), []
    seen = set()
    for e in _events(log):
        payload = e.get("payload") or {}
        if e.get("type") == "effect.done":
            ok_done.add(payload.get("key"))
        elif e.get("type") == "effect.queued":
            key = payload.get("key")
            if key and key not in seen:
                seen.add(key)
                out.append(Effect(kind=payload.get("kind", ""), key=key, payload=payload))
    return [e for e in out if e.key not in ok_done]


def queued_keys(log) -> set:
    return {e.key for e in pending(log)}


def enqueue(log, kind: str, payload: dict, *, stage: int | None = None) -> Effect:
    key = effect_key(kind, payload)
    eff = Effect(kind=kind, key=key, payload={"kind": kind, "key": key, **payload})
    log.append("effect.queued", eff.payload, stage=stage)
    return eff


def mark_started(log, effect: Effect, *, stage: int | None = None) -> None:
    log.append("effect.started", {"kind": effect.kind, "key": effect.key}, stage=stage)


def mark_done(log, effect: Effect, result: str = "ok", *, stage: int | None = None) -> None:
    log.append("effect.done", {"kind": effect.kind, "key": effect.key,
                               "result": result}, stage=stage)


def run_pending(
    log,
    handler: Callable[[Effect], str],
    *,
    kinds: Iterable[str] | None = None,
    stage: int | None = None,
) -> dict:
    """Execute pending effects once each. Returns ``{ok, failed, skipped}``.

    Failures are terminal (``effect.done`` with ``result=error:...``) so a
    crash-loop cannot replay a poisoned effect forever; callers that want a
    retry must enqueue it again explicitly.
    """
    allow = set(kinds) if kinds else None
    ok = failed = skipped = 0
    for eff in pending(log):
        if allow is not None and eff.kind not in allow:
            skipped += 1
            continue
        mark_started(log, eff, stage=stage)
        try:
            result = handler(eff) or "ok"
            mark_done(log, eff, result, stage=stage)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - record, do not propagate
            mark_done(log, eff, "error:%s" % type(exc).__name__, stage=stage)
            failed += 1
    return {"ok": ok, "failed": failed, "skipped": skipped}
