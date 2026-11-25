"""Deterministic drift guard (failure guard A, FA-1..FA-3).

Reads only existing stage artifacts plus an optional scope-change approval.
No network, no LLM: the default backend is lexical TF-IDF; a semantic
embedding function can be injected by tests or future callers.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

SCHEMA_DRIFT = "arc-drift-report/1"
SCHEMA_SCOPE_APPROVAL = "arc-scope-change-approval/1"

_STOPWORDS = frozenset(
    "the a an and or of to in on for with by is are was were be been this that "
    "these those it its as at from into than then we our their there here can "
    "may might will would should could not no do does did has have had".split()
)
_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")
_SECTION_RE = re.compile(r"(?m)^(#{1,6})\s+(.+)$")
_P_ONLY_RE = re.compile(
    r"\bp\s*[<>=]\s*0?\.\d+|\bsignificant(?:ly)?\b|显著性", re.IGNORECASE
)
_EFFECT_RE = re.compile(
    r"effect size|cohen|odds ratio|hazard ratio|confidence interval|\bCI\b|%|"
    r"β|r2|r²|eta squared",
    re.IGNORECASE,
)
_CONCLUSION_HEADINGS = (
    "conclusion", "discussion", "results", "findings",
    "结论", "讨论", "结果", "发现",
)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", name, raw)
        return default
    if not 0.0 <= value <= 1.0:
        logger.warning("Ignoring out-of-range %s=%r", name, raw)
        return default
    return value


@dataclass(frozen=True)
class DriftThresholds:
    rq_warn: float = 0.45
    rq_pause: float = 0.35
    unsupported_pause: float = 0.40
    p_only_warn: float = 0.50
    lexical_pause: float = 0.20

    @classmethod
    def from_env(cls) -> "DriftThresholds":
        return cls(
            rq_warn=_env_float("ARC_DRIFT_RQ_WARN", cls.rq_warn),
            rq_pause=_env_float("ARC_DRIFT_RQ_PAUSE", cls.rq_pause),
            unsupported_pause=_env_float(
                "ARC_DRIFT_UNSUPPORTED_PAUSE", cls.unsupported_pause
            ),
            p_only_warn=_env_float("ARC_DRIFT_P_ONLY_WARN", cls.p_only_warn),
            lexical_pause=_env_float("ARC_DRIFT_LEXICAL_PAUSE", cls.lexical_pause),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "rq_warn": self.rq_warn,
            "rq_pause": self.rq_pause,
            "unsupported_pause": self.unsupported_pause,
            "p_only_warn": self.p_only_warn,
            "lexical_pause": self.lexical_pause,
        }


@dataclass(frozen=True)
class DriftReport:
    schema: str = SCHEMA_DRIFT
    run_id: str = ""
    decision: str = ""
    action: str = "pass"
    rq_cos: float | None = None
    unsupported_ratio: float | None = None
    p_only_ratio: float | None = None
    backend: str = "lexical_tfidf"
    thresholds: dict[str, float] | None = None
    reasons: tuple[str, ...] = ()
    signals: dict[str, Any] | None = None
    generated: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "decision": self.decision,
            "action": self.action,
            "rq_cos": self.rq_cos,
            "unsupported_ratio": self.unsupported_ratio,
            "p_only_ratio": self.p_only_ratio,
            "backend": self.backend,
            "thresholds": dict(self.thresholds or {}),
            "reasons": list(self.reasons),
            "signals": dict(self.signals or {}),
            "generated": self.generated,
        }


def tokenize(text: str) -> list[str]:
    words = [word for word in _TOKEN_RE.findall((text or "").lower())
             if word not in _STOPWORDS]
    bigrams = [f"{left}_{right}" for left, right in zip(words, words[1:])]
    return words + bigrams


def lexical_cosine(a: str, b: str) -> float:
    docs = [tokenize(a), tokenize(b)]
    if not docs[0] or not docs[1]:
        return 0.0
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc))
    vectors: list[dict[str, float]] = []
    norms: list[float] = []
    for doc in docs:
        tf = Counter(doc)
        vector = {
            term: (count / len(doc)) * (math.log(3.0 / (1.0 + df[term])) + 1.0)
            for term, count in tf.items()
        }
        vectors.append(vector)
        norms.append(math.sqrt(sum(value * value for value in vector.values())))
    left, right = vectors
    if norms[0] == 0.0 or norms[1] == 0.0:
        return 0.0
    dot = sum(value * right.get(term, 0.0) for term, value in left.items())
    return round(max(0.0, min(1.0, dot / (norms[0] * norms[1]))), 6)


def extract_conclusion(text: str) -> str:
    text = text or ""
    matches = list(_SECTION_RE.finditer(text))
    selected: list[str] = []
    for index, match in enumerate(matches):
        title = match.group(2).strip().lower()
        if not any(keyword in title for keyword in _CONCLUSION_HEADINGS):
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        selected.append(text[start:end].strip())
    if selected:
        return "\n".join(part for part in selected if part)
    tail = max(400, int(len(text) * 0.4))
    return text[-tail:]


def p_only_ratio(text: str) -> float:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text or "") if s.strip()]
    candidates = [s for s in sentences if _P_ONLY_RE.search(s)]
    if not candidates:
        return 0.0
    p_only = [s for s in candidates if not _EFFECT_RE.search(s)]
    return round(len(p_only) / len(candidates), 4)


def claim_support(run_dir: Path, text: str) -> tuple[float | None, int]:
    try:
        from researchclaw.hitl.claim_verifier import ClaimVerifier

        report = ClaimVerifier(Path(run_dir)).verify_text(text)
    except Exception:  # noqa: BLE001 - a broken claim verifier must not block Stage 15
        logger.warning("Drift guard: claim verification failed", exc_info=True)
        return None, 0
    checked = report.grounded_claims + report.ungrounded_claims
    if checked == 0:
        return None, 0
    return round(report.ungrounded_claims / checked, 4), checked


def read_scope_change_approval(stage_dir: Path) -> dict[str, Any] | None:
    path = Path(stage_dir) / "scope_change_approval.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    schema = payload.get("schema")
    if schema is not None and schema != SCHEMA_SCOPE_APPROVAL:
        return None
    if not isinstance(payload.get("approved"), bool):
        return None
    return payload


def write_scope_change_approval(
    stage_dir: Path,
    *,
    approved: bool,
    reason: str,
    approved_by: str = "hitl",
) -> Path:
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_SCOPE_APPROVAL,
        "approved": bool(approved),
        "reason": reason,
        "approved_by": approved_by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    path = stage_dir / "scope_change_approval.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _read_prior(run_dir: Path, filename: str) -> str:
    try:
        from researchclaw.pipeline._helpers import _read_prior_artifact

        return _read_prior_artifact(Path(run_dir), filename) or ""
    except Exception:  # noqa: BLE001
        return ""


def _cosine_from_embedding(
    goal: str, outcome: str, embed_fn: Callable[[str], list[float]]
) -> float | None:
    try:
        left = [float(x) for x in embed_fn(goal)]
        right = [float(x) for x in embed_fn(outcome)]
    except Exception:  # noqa: BLE001
        logger.warning("Drift guard: embedding backend failed", exc_info=True)
        return None
    if len(left) != len(right) or not left:
        return None
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norm == 0.0:
        return None
    return round(max(0.0, min(1.0, dot / norm)), 6)


def assess_drift(
    run_dir: Path,
    stage_dir: Path,
    decision: str,
    decision_md: str,
    analysis: str,
    *,
    embed_fn: Callable[[str], list[float]] | None = None,
    thresholds: DriftThresholds | None = None,
) -> DriftReport:
    run_dir = Path(run_dir)
    stage_dir = Path(stage_dir)
    limits = thresholds or DriftThresholds.from_env()

    goal = "\n".join(
        part for part in (
            _read_prior(run_dir, "goal.md"),
            _read_prior(run_dir, "hypotheses.md"),
        ) if part
    )
    conclusion = extract_conclusion(analysis or "")
    outcome = "\n".join(part for part in (conclusion, decision_md or "") if part)

    reasons: list[str] = []
    backend = "injected" if embed_fn is not None else "lexical_tfidf"
    if embed_fn is not None:
        rq_cos = _cosine_from_embedding(goal, outcome, embed_fn)
    else:
        rq_cos = lexical_cosine(goal, outcome)
    if rq_cos is None:
        reasons.append("rq_cos_unavailable")

    unsupported, claims_checked = claim_support(run_dir, outcome)
    p_only = p_only_ratio(outcome)
    approval = read_scope_change_approval(stage_dir)
    approved_pivot = (
        str(decision).upper() == "PIVOT"
        and approval is not None
        and approval.get("approved") is True
    )

    if approved_pivot:
        action = "exempt"
        reasons.append("approved_scope_change")
    elif len(goal.strip()) < 40 or len(outcome.strip()) < 40:
        action = "warn"
        reasons.append("insufficient_inputs")
    else:
        pause_limit = limits.rq_pause if backend == "injected" else limits.lexical_pause
        if (
            rq_cos is not None
            and rq_cos < pause_limit
            and unsupported is not None
            and unsupported > limits.unsupported_pause
        ):
            action = "pause"
            reasons.extend(("rq_cos_below_pause", "unsupported_above_pause"))
        elif rq_cos is None:
            action = "warn"
        elif rq_cos < limits.rq_warn:
            action = "warn"
            reasons.append("rq_cos_below_warn")
        elif p_only > limits.p_only_warn:
            action = "warn"
            reasons.append("p_only_above_warn")
        else:
            action = "pass"

    return DriftReport(
        run_id=run_dir.name,
        decision=str(decision),
        action=action,
        rq_cos=rq_cos,
        unsupported_ratio=unsupported,
        p_only_ratio=p_only,
        backend=backend,
        thresholds=limits.to_dict(),
        reasons=tuple(reasons),
        signals={
            "goal_chars": len(goal),
            "outcome_chars": len(outcome),
            "claims_checked": claims_checked,
            "scope_approved": bool(approval and approval.get("approved") is True),
        },
        generated=datetime.now(timezone.utc).isoformat(),
    )


def write_drift_report(stage_dir: Path, report: DriftReport) -> Path:
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    path = stage_dir / "drift_report.json"
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8"
    )
    return path


def format_reanchor_section(report: DriftReport) -> str:
    return (
        "\n\n## Drift Guard — RQ Re-anchoring Required\n\n"
        f"- action: `{report.action}`\n"
        f"- rq_cos: `{report.rq_cos}`\n"
        f"- unsupported_ratio: `{report.unsupported_ratio}`\n"
        f"- reasons: `{', '.join(report.reasons)}`\n\n"
        "Re-anchor the analysis to the original goal and hypotheses. If the "
        "pivot is legitimate, write `stage-15/scope_change_approval.json` with "
        "`approved: true` and a reason before resuming.\n"
    )
