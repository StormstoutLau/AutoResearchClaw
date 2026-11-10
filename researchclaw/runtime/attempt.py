"""Attempt records and resume notes (G1b / A1-9, A1-11, A1-12).

Attempts are **records**, not state transitions: an attempt never writes
``StageStatus`` (DESIGN §3). Files live at
``<run>/attempts/stage-NN/attempt-<k>.json`` so they never collide with the
PIVOT/REFINE ``stage-NN_v{k}/`` snapshots.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_NOTE_CHARS = 500

#: 已知支持「会话续接」的 backend（U-2）。当前 CLI 代理均未暴露 resume 语义，
#: 因此新 attempt 一律标记 ``context_replayed=True``；将来接入时在此登记即可。
SESSION_RESUME_BACKENDS: frozenset[str] = frozenset()


def session_resume_supported(backend: str | None) -> bool:
    """Whether a retry may continue the prior provider session (A1-9 / U-2)."""
    return (backend or "").strip().lower() in SESSION_RESUME_BACKENDS


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
