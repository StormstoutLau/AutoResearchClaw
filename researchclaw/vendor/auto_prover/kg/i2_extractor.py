"""i2_extractor.py — I-2 抽取器 (Phase 5b-S2, Batch 0c)

verdict JSONL → UnifiedCase 的映射层 (D019 降载版, 在统一 schema 上落地)。

核心: 成功案例白名单 + 字段映射 + 去重键 (case_id 来自 normalize_statement)。
设计依据: DESIGN_ATLAS_PHASE_5B_S2.md §3.2/§3.3
关键修正 (Review #2 CRITICAL-1): 白名单必须用 CitationLabel 的 .value(小写) 集合,
因 verdict_writer.py 写入的是 verdict.citation_label.value (小写), 否则 _is_ready 恒假。

P1 扩展 (2026-09-07): 新增 textbook lean4_cases (cases.json) 抽取 —
历史种子案例 (source="textbook") 与 A4 verdict 在新案例时 power 主键上自然去重。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .unified_cases import UnifiedCase, make_case_id
from ..datatypes import CURRENT_POLICY_VERSION

# 白名单: 枚举 .value(小写), 与 datatypes.py CitationLabel 一致
# (formally_verified / partially_formalized / numerically_verified)
_READY_LABELS = {"formally_verified", "partially_formalized", "numerically_verified"}
_FORMAL_LABELS = {"formally_verified", "partially_formalized"}


def _is_ready(record: dict) -> bool:
    """成功案例白名单判定 (DESIGN §3.3)

    guard 1: lean_code 非 None (空/缺 → 弃)
    guard 2: citation_label ∈ 白名单 (小写 value)
    guard 3 (W1 / B-52): 正式标签要求 policy_version ≥ 2；旧记录拒绝入库
    """
    if not record.get("lean_code"):
        return False  # guard 1
    label = record.get("citation_label", "")
    if label not in _READY_LABELS:
        return False  # guard 2
    if label in _FORMAL_LABELS:
        try:
            version = int(record.get("policy_version", 1))
        except (TypeError, ValueError):
            version = 1
        if version < CURRENT_POLICY_VERSION:
            return False  # guard 3
    return True


def parse_verdict(record: dict) -> Optional[UnifiedCase]:
    """单条 verdict → UnifiedCase; 白名单不符 → None

    Args:
        record: verdict JSONL record (verdict_writer._verdict_to_record 产)

    Returns:
        UnifiedCase 或 None (白名单不符 / 字段缺失)
    """
    if not _is_ready(record):
        return None
    assertion = record.get("assertion", "")
    code = record.get("lean_code", "")
    return UnifiedCase(
        case_id=make_case_id(assertion),          # 归一化 MD5 确定性主键
        kind="theorem",                            # verdict 无明确 kind, 默认 theorem
        statement=assertion,
        code=code,
        source="pipeline",
        verdict_id=record.get("verdict_id", ""),
        citation_label=record.get("citation_label", ""),
        timestamp=record.get("timestamp", ""),
    )


def extract_all(verdict_jsonl: str) -> list[UnifiedCase]:
    """全量抽取: 遍历 verdict JSONL, 白名单通过 → UnifiedCase

    Args:
        verdict_jsonl: verdict JSONL 文件路径

    Returns:
        UnifiedCase 列表 (仅白名单通过者)
    """
    cases = []
    path = Path(verdict_jsonl)
    if not path.exists():
        return cases
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            case = parse_verdict(record)
            if case is not None:
                cases.append(case)
    return cases


# ============================================================================
# P1 扩展: textbook Lean4CaseLibrary 历史种子案例 (source="textbook")
# ============================================================================

def parse_lean4_case(d: dict) -> Optional[UnifiedCase]:
    """单条 Lean4Case dict → UnifiedCase (source="textbook", P1 扩展)

    Lean4Case.to_dict() 键名: {id, kind, statement, code} (键 "id", 非 case_id,
    与 A6 Case.to_dict() 的 "case_id" 不同 — 见 lean4_case_library 复刻源)。

    guard: statement 非空 (统一库以 statement 为检索锚点; 空则 case_id 碰撞弃)。

    case_id 用 make_case_id(statement) 而非原始 "id":
      保证与 A4 assertion (make_case_id(assertion)) 在同义文本时自然去重合并;
      integer 目标 ID 语义不同, 两源措辞不同时作为独立 case 并存 (DESIGN §6 已预见)。

    原始 textbook id 存入 tags ("textbook_id:<id>") 供溯源。
    """
    if not d or not isinstance(d, dict):
        return None
    statement = (d.get("statement") or "").strip()
    code = d.get("code") or ""
    if not statement and not code:
        return None  # 双空, 无检索锚点也无证明体 → 弃
    if not statement:
        return None  # 无检索锚点 → 弃 (避免空 statement 的 case_id 全碰撞)
    raw_id = d.get("id", "")
    return UnifiedCase(
        case_id=make_case_id(statement),
        kind=d.get("kind", "theorem") or "theorem",
        statement=statement,
        code=code,
        source="textbook",
        tags=[f"textbook_id:{raw_id}"] if raw_id else [],
    )


def extract_lean4_cases(cases_json: str) -> list[UnifiedCase]:
    """全量抽取 textbook lean4_cases/cases.json (source="textbook", P1 扩展)

    cases.json 为 JSON 数组 (Lean4Case.to_dict() 序列), 非 JSONL。

    Args:
        cases_json: textbook / vendor lean4_cases/cases.json 路径

    Returns:
        UnifiedCase 列表 (仅 statement 非空者)
    """
    cases = []
    path = Path(cases_json)
    if not path.exists():
        return cases
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return cases
    if not isinstance(data, list):
        return cases
    for item in data:
        if not isinstance(item, dict):
            continue
        case = parse_lean4_case(item)
        if case is not None:
            cases.append(case)
    return cases