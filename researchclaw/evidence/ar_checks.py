"""AR-01..AR-08: mechanical checks over a ClaimRecord v1 mapping.

Pure functions only: no I/O, no schema dependency, no status mutation.
Severity vocabulary is frozen to R-03 §3.4 (``fail`` / ``warn`` / ``downgrade``).
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SEVERITIES = ("fail", "warn", "downgrade")

# AR-03: phrases that must carry a resolvable citation marker when used.
BANNED_PHRASES = (
    "研究表明",
    "研究显示",
    "已有研究表明",
    "studies show",
    "research shows",
    "it is well known",
)

# AR-03: frozen marker vocabulary; widening it is tracked as U-1 in P-048.
CITATION_RE = re.compile(r"\[(e-[A-Za-z0-9._-]+)\]")

# AR-02/AR-04: four statistical fields plus the section index.
STATS_FIELDS = ("estimator", "sample", "missing_policy", "alpha", "section_index")

# AR-06: statuses that require evidence when consensus is present.
HIGH_STATUSES = ("formally_verified", "partially_formalized", "numerically_verified")


@dataclass(frozen=True)
class Finding:
    """One rule violation. ``cap`` is consumed later by the publish predicates."""

    code: str
    severity: str
    message: str
    field: str
    cap: str | None = None


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _records(claim: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = claim.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def ar01(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-01: claim-evidence binding (A: quote source; B: every step has sources)."""
    claim_class = claim.get("claim_class")
    if claim_class == "A":
        complete = any(
            _text(item.get("source_id")) and _text(item.get("locator")) and _text(item.get("quote"))
            for item in _records(claim, "evidence")
        )
        if not complete:
            return [
                Finding(
                    "AR-01",
                    "downgrade",
                    "A 类主张需至少 1 条证据同时具备 source_id/locator/quote",
                    "evidence",
                )
            ]
    elif claim_class == "B":
        chain = _records(claim, "reasoning_chain")
        if not chain:
            return [
                Finding("AR-01", "downgrade", "B 类主张需非空的 reasoning_chain", "reasoning_chain")
            ]
        for index, step in enumerate(chain):
            if not step.get("source_refs"):
                return [
                    Finding(
                        "AR-01",
                        "downgrade",
                        "B 类推理链每一步都需 source_refs",
                        f"reasoning_chain[{index}].source_refs",
                    )
                ]
    return []


def ar02(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-02: exploratory vs confirmatory; confirmatory needs a full stats protocol."""
    claim_type = claim.get("claim_type")
    if claim_type not in ("exploratory", "confirmatory"):
        return [
            Finding("AR-02", "downgrade", "claim_type 缺失或非法，按 exploratory 处理", "claim_type")
        ]
    if claim_type != "confirmatory":
        return []
    stats = claim.get("stats_protocol")
    if not isinstance(stats, dict):
        return [
            Finding(
                "AR-02",
                "downgrade",
                "确证性主张缺 stats_protocol，降级为 exploratory",
                "stats_protocol",
            )
        ]
    missing = [name for name in STATS_FIELDS if stats.get(name) in (None, "")]
    if missing:
        return [
            Finding(
                "AR-02",
                "downgrade",
                f"确证性主张统计口径缺字段：{missing}",
                "stats_protocol",
            )
        ]
    return []


def ar03(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-03: banned "studies show" phrasing needs a resolvable, located citation."""
    statement = claim.get("statement")
    if not _text(statement):
        return []
    lowered = statement.lower()
    if not any(phrase.lower() in lowered for phrase in BANNED_PHRASES):
        return []
    evidence = {
        item.get("evidence_id"): item
        for item in _records(claim, "evidence")
        if _text(item.get("evidence_id"))
    }
    cited = [evidence[marker] for marker in CITATION_RE.findall(statement) if marker in evidence]
    if not cited:
        return [
            Finding("AR-03", "fail", "禁用表述缺可解析的 [e-xxxx] 引用", "statement")
        ]
    if any(not _text(item.get("locator")) for item in cited):
        return [
            Finding("AR-03", "downgrade", "禁用表述的引用缺 locator", "evidence")
        ]
    return []


def ar04(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-04: statistics protocol must precede results and be complete."""
    stats = claim.get("stats_protocol")
    results = claim.get("results")
    if not isinstance(stats, dict) or not isinstance(results, dict):
        return []
    missing = [name for name in STATS_FIELDS if stats.get(name) in (None, "")]
    if missing:
        return [Finding("AR-04", "fail", f"统计口径缺字段：{missing}", "stats_protocol")]
    stats_section = stats.get("section_index")
    results_section = results.get("section_index")
    if not isinstance(stats_section, int) or not isinstance(results_section, int):
        return [
            Finding(
                "AR-04",
                "fail",
                "stats_protocol/results 的 section_index 必须为整数",
                "stats_protocol.section_index",
            )
        ]
    if stats_section > results_section:
        return [
            Finding(
                "AR-04",
                "fail",
                f"统计口径 §{stats_section} 晚于结果 §{results_section}",
                "stats_protocol.section_index",
            )
        ]
    return []


def ar05(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-05: A/B claims need a falsifier backed by E1/E2 evidence (cap latex)."""
    if claim.get("claim_class") not in ("A", "B"):
        return []
    falsifier = claim.get("falsifier")
    if (
        not isinstance(falsifier, dict)
        or not _text(falsifier.get("condition"))
        or not _text(falsifier.get("test_ref"))
    ):
        return [
            Finding(
                "AR-05",
                "warn",
                "A/B 类缺反例条件或测试引用，状态上限 latex_verified",
                "falsifier",
                cap="latex_verified",
            )
        ]
    evidence = {
        item.get("evidence_id"): item
        for item in _records(claim, "evidence")
        if _text(item.get("evidence_id"))
    }
    target = evidence.get(falsifier["test_ref"])
    if target is None or target.get("tier") not in ("E1", "E2"):
        return [
            Finding(
                "AR-05",
                "warn",
                "反例引用未解析到 E1/E2 证据，状态上限 latex_verified",
                "falsifier.test_ref",
                cap="latex_verified",
            )
        ]
    return []


def ar06(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-06: consensus is only a filter; it can never lift an evidence-free claim."""
    consensus = claim.get("consensus")
    if not isinstance(consensus, dict):
        return []
    problems: list[str] = []
    if consensus.get("used_as") != "filter":
        problems.append("used_as 必须为 filter")
    if not _records(claim, "evidence") and claim.get("status") in HIGH_STATUSES:
        problems.append("无证据时不得授予 numerically_verified 及以上")
    if not problems:
        return []
    return [
        Finding(
            "AR-06",
            "warn",
            "；".join(problems) + "；状态上限 latex_verified",
            "consensus",
            cap="latex_verified",
        )
    ]


def ar07(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-07: A/B claims must be formal or declare the formalization debt."""
    if claim.get("claim_class") not in ("A", "B"):
        return []
    if _text(claim.get("formal_statement")):
        return []
    formality = claim.get("formality")
    if isinstance(formality, dict) and formality.get("status") == "debt":
        if _text(formality.get("reason")):
            return [Finding("AR-07", "warn", "形式化欠账已声明", "formality")]
        return [Finding("AR-07", "fail", "形式化欠账未给出理由", "formality.reason")]
    return [
        Finding(
            "AR-07", "fail", "A/B 类缺 formal_statement 且未声明 debt", "formal_statement"
        )
    ]


def ar08(claim: Mapping[str, Any]) -> list[Finding]:
    """AR-08: execution-plane isolation (pointer/snapshot integrity, inline cap)."""
    findings: list[Finding] = []
    for index, item in enumerate(_records(claim, "evidence")):
        kind = item.get("kind")
        if kind == "pointer" and (
            not _text(item.get("source_id")) or not _text(item.get("digest"))
        ):
            findings.append(
                Finding(
                    "AR-08",
                    "fail",
                    "跨仓 pointer 必须带 source_id+digest",
                    f"evidence[{index}]",
                )
            )
        if kind == "snapshot" and (
            not _text(item.get("digest")) or item.get("readonly") is not True
        ):
            findings.append(
                Finding(
                    "AR-08",
                    "fail",
                    "snapshot 必须带 digest 且 readonly=true",
                    f"evidence[{index}]",
                )
            )
        inline = item.get("inline_copy")
        if isinstance(inline, str) and len(inline) > 500:
            findings.append(
                Finding(
                    "AR-08",
                    "fail",
                    f"inline_copy 超过 500 字符（{len(inline)}）",
                    f"evidence[{index}].inline_copy",
                )
            )
    return findings


CHECKS: dict[str, Callable[[Mapping[str, Any]], list[Finding]]] = {
    "AR-01": ar01,
    "AR-02": ar02,
    "AR-03": ar03,
    "AR-04": ar04,
    "AR-05": ar05,
    "AR-06": ar06,
    "AR-07": ar07,
    "AR-08": ar08,
}


def check_claim(claim: Mapping[str, Any]) -> list[Finding]:
    """Run every registered check. Deterministic order; never raises on missing fields."""
    findings: list[Finding] = []
    for check in CHECKS.values():
        findings.extend(check(claim))
    return sorted(findings, key=lambda item: (item.code, item.field, item.message))
