"""P-081: P-row tier parsing lives in spec_map (single implementation, I-10)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "spec_map_under_test", ROOT / "scripts" / "spec" / "spec_map.py")
sm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sm
_spec.loader.exec_module(sm)

HEADER = (
    "| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |\n"
    "|---|---|---|---|---|---|\n"
)


def _progress(basis: str, feature: str = "feat-a") -> str:
    return HEADER + (
        f"| P-200 | 事项 | [spec/{feature}/](../spec/{feature}/) {basis} | done | P0 | ok |\n"
    )


def test_parse_rows_keeps_basis_column() -> None:
    rows = sm.parse_progress_rows(_progress("T1：Layer-1 实现"))
    assert "T1" in rows["P-200"]["basis"]
    assert rows["P-200"]["features"] == ("feat-a",)


def test_row_tier_reads_t1_and_t3() -> None:
    rows = sm.parse_progress_rows(_progress("T1：Layer-1 实现"))
    assert sm.row_tier(rows["P-200"]) == "T1"
    rows = sm.parse_progress_rows(_progress("T3：Layer-0 文档订正"))
    assert sm.row_tier(rows["P-200"]) == "T3"


def test_row_tier_missing_or_ambiguous() -> None:
    rows = sm.parse_progress_rows(_progress("Layer-0 文档订正"))
    assert sm.row_tier(rows["P-200"]) is None
    rows = sm.parse_progress_rows(_progress("T10 不是档位"))
    assert sm.row_tier(rows["P-200"]) is None
