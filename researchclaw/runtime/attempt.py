"""Attempt records and resume notes (G1b / A1-9, A1-11, A1-12).

Attempts are **records**, not state transitions: an attempt never writes
``StageStatus`` (DESIGN §3). Files live at
``<run>/attempts/stage-NN/attempt-<k>.json`` so they never collide with the
PIVOT/REFINE ``stage-NN_v{k}/`` snapshots.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_NOTE_CHARS = 500

#: 已知支持「会话续接」的 backend。
#: 本批实测：主控站 / A 站 NEX / B 站 GTR-Pro 三端的 claude CLI 均通过
#: `--session-id` + `--resume` 验证（同一会话文件行数增长且语义回忆正确）。
#: C 站 seaviv 未测（按用户要求不动）。
SESSION_RESUME_BACKENDS: frozenset[str] = frozenset({"claude_code"})

_SESSION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://researchclaw/session/v1")


def session_resume_supported(backend: str | None) -> bool:
    """Whether a retry may continue the prior provider session (A1-9 / U-2)."""
    return (backend or "").strip().lower() in SESSION_RESUME_BACKENDS


def session_scope(run_dir: str | Path) -> str:
    """Canonical run identity for provider sessions.

    The CLI session store is machine-local (P-035 §3), so the run directory —
    not ``run_id`` — is the identity both the stage implementation and the
    attempt recorder can agree on. A run copied to another path starts a new
    session instead of silently resuming a foreign conversation.
    """
    return str(Path(run_dir).resolve())


def stage_session_id(run_dir: str | Path, stage: int) -> str:
    """Deterministic per-(run, stage) session id, stable across attempts."""
    return str(uuid.uuid5(_SESSION_NAMESPACE,
                          "%s:%d" % (session_scope(run_dir), int(stage))))


def read_session_telemetry(
    stage_dir: str | Path, since: str | None = None,
) -> tuple[str | None, bool]:
    """Read ``(session_id, resumed)`` from the stage's own CLI agent log.

    Stage 10 writes ``cli_agent_log.json``; Stage 13 writes
    ``refinement_log.json["cli_agent"]``. ``since`` (ISO-8601) rejects a log
    left over from an earlier attempt, so an attempt never claims to have
    resumed a session it did not use.
    """
    d = Path(stage_dir)
    candidates = (
        ("cli_agent_log.json", ("session",)),
        ("refinement_log.json", ("cli_agent", "session")),
    )
    for name, path in candidates:
        p = d / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if since and str(data.get("generated") or "") < since:
            continue
        for key in path:
            data = data.get(key) if isinstance(data, dict) else None
            if not isinstance(data, dict):
                break
        if not isinstance(data, dict):
            continue
        sid = data.get("id")
        return (str(sid) if sid else None), bool(data.get("resumed"))
    return None, False


@dataclass(frozen=True)
class AttemptRecord:
    stage: int
    stage_name: str
    attempt: int
    started_at: str
    ended_at: str
    exit_class: str
    exit_code: int
    session_id: str | None = None
    context_replayed: bool = True
    resume_note: str = ""
    artifacts: tuple[str, ...] = field(default_factory=tuple)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def attempts_dir(run_dir: str | Path, stage: int) -> Path:
    return Path(run_dir) / "attempts" / ("stage-%02d" % int(stage))


def next_attempt_number(run_dir: str | Path, stage: int) -> int:
    d = attempts_dir(run_dir, stage)
    if not d.is_dir():
        return 1
    nums = [int(p.stem.split("-")[1]) for p in d.glob("attempt-*.json")
            if p.stem.startswith("attempt-") and p.stem.split("-")[1].isdigit()]
    return (max(nums) + 1) if nums else 1


def list_artifacts(stage_dir: str | Path, limit: int = 8) -> tuple[str, ...]:
    """Cheap artifact inventory used by the resume note (names + sizes)."""
    d = Path(stage_dir)
    if not d.is_dir():
        return ()
    out = []
    try:
        for p in sorted(d.iterdir()):
            if p.is_file():
                out.append("%s (%dB)" % (p.name, p.stat().st_size))
            elif p.is_dir() and p.name not in ("__pycache__",):
                out.append("%s/ (%d files)" % (p.name, sum(1 for _ in p.iterdir())))
            if len(out) >= limit:
                break
    except OSError:
        return ()
    return tuple(out)


def build_resume_note(*, stage: int, stage_name: str, attempt: int,
                      last_error: str | None, artifacts: tuple[str, ...],
                      exit_code: int = 0) -> str:
    """≤500 char note telling the next attempt what to check first (A1-12)."""
    head = "[attempt %d] 上次失败：Stage %d (%s)" % (attempt, int(stage), stage_name)
    if exit_code:
        head += "，退出码 %d" % exit_code
    if last_error:
        head += "，错误：%s" % last_error.strip().splitlines()[0][:160]
    head += "。"
    if artifacts:
        body = "已存在产物：%s。" % "、".join(artifacts)
    else:
        body = "未发现可复用产物。"
    tail = "恢复要求：先校验上述产物与上游 spec 是否一致；一致则跳过付费重跑，不一致再重跑。禁止无条件重复外部付费调用。"
    note = head + body + tail
    return note[:MAX_NOTE_CHARS]


def write_attempt(run_dir: str | Path, record: AttemptRecord) -> Path:
    d = attempts_dir(run_dir, record.stage)
    d.mkdir(parents=True, exist_ok=True)
    target = d / ("attempt-%d.json" % record.attempt)
    tmp = target.with_suffix(".json.tmp")
    payload = asdict(record)
    payload["artifacts"] = list(record.artifacts)
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, indent=2, ensure_ascii=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    return target


def read_attempt(run_dir: str | Path, stage: int, attempt: int) -> dict | None:
    p = attempts_dir(run_dir, stage) / ("attempt-%d.json" % attempt)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def latest_attempt(run_dir: str | Path, stage: int) -> dict | None:
    """Historical runs (no attempt files) read as an attempt-1 read-only view."""
    d = attempts_dir(run_dir, stage)
    if not d.is_dir():
        return None
    files = sorted(d.glob("attempt-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
