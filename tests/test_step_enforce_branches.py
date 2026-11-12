"""step_enforce 两分支 feature 门槛一致性（P-024 / R-5）。

被测面：`resolve()` 的 batch（有 spec 文档改动）与 batch-registration（仅 PROGRESS 改动）
两条路径必须对同一 `(pid, features)` 给出**相同**的 feature 绑定判定。

隔离：`_sessions_for_pid` / `_check_sessions` 被 monkeypatch，不触文件系统与子进程。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "step_enforce_under_test", ROOT / "scripts" / "spec" / "step_enforce.py")
se = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = se          # dataclass 需要模块已注册
_spec.loader.exec_module(se)

HEADER = (
    "| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |\n"
    "|---|---|---|---|---|---|\n"
)


def progress(*rows: str) -> str:
    return HEADER + "".join(r + "\n" for r in rows)


def row(pid: str, feature: str | None, tier: str | None = "T3") -> str:
    parts = []
    if feature:
        parts.append("[spec/%s/](../spec/%s/)" % (feature, feature))
    if tier:
        parts.append(tier)
    dep = " ".join(parts) or "—"
    return "| %s | 事项 | %s | done | P0 | ok |" % (pid, dep)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """隔离 session 查询与完整性校验。"""
    monkeypatch.setattr(se, "_sessions_for_pid", lambda pid: ["specwf-ok"])
    monkeypatch.setattr(se, "_check_sessions", lambda sids, require_complete: ([sids[0]], []))


def _batch_resolve(old: str, new: str):
    """有 spec 文档改动 → _resolve_declared 路径。"""
    return se.resolve(["spec/feat-a/RESEARCH.md"], [], True, old, new, "main", False)


def _registration_resolve(old: str, new: str):
    """仅 PROGRESS 改动 → batch-registration 路径。"""
    return se.resolve([], [], True, old, new, "main", False)


# ---------------------------------------------------------------- T-1 回归

def test_mixed_batch_t3_row_without_feature_is_allowed():
    """T1 + T3 同提交（P-022/P-023 场景）：T3 行无 feature 不应报错。"""
    old = progress()
    new = progress(row("P-024", "feat-a"), row("P-025", None))
    d = _batch_resolve(old, new)
    assert d.mode == "batch"
    assert not [e for e in d.errors if "未声明任何 spec" in e], d.errors
    assert d.features == {"feat-a"}


# ---------------------------------------------------------------- T-2 高编号仍严格

def test_high_pid_without_feature_still_errors():
    """≥ BATCH_BINDING_MIN_P 的批次无 feature 仍必须红。"""
    pid = "P-%03d" % se.BATCH_BINDING_MIN_P
    old = progress()
    new = progress(row(pid, None))
    d = _batch_resolve(old, new)
    assert any("未声明任何 spec" in e for e in d.errors), d.errors


# ---------------------------------------------------------------- T-3 两分支一致

@pytest.mark.parametrize("pid,feature,should_error", [
    ("P-024", None, False),
    ("P-024", "feat-a", False),
    ("P-200", None, True),
    ("P-200", "feat-a", False),
])
def test_two_branches_agree(pid, feature, should_error):
    """同一 (pid, features) 在两分支下的 feature 判定必须一致。"""
    old = progress()
    new = progress(row(pid, feature))
    batch = _batch_resolve(old, new)
    reg = _registration_resolve(old, new)
    assert reg.mode == "batch-registration"
    assert batch.mode == "batch"
    b_err = any("未声明任何 spec" in e for e in batch.errors)
    r_err = any("未声明任何 spec" in e for e in reg.errors)
    assert b_err == r_err == should_error, (batch.errors, reg.errors)


# ---------------------------------------------------------------- T-4 覆盖不放宽

def test_coverage_check_not_relaxed():
    """声明 P 只绑定 feat-a，但改动了 feat-b → 仍必须红。"""
    old = progress()
    new = progress(row("P-024", "feat-a"), row("P-025", None))
    d = se.resolve(["spec/feat-b/RESEARCH.md"], [], True, old, new, "main", False)
    assert any("未被声明 P 覆盖" in e for e in d.errors), d.errors


# ---------------------------------------------------------------- T-5 session 不放宽

def test_session_completeness_not_relaxed(monkeypatch):
    """声明 P 无 session → 仍必须红（T3 行也不例外）。"""
    monkeypatch.setattr(se, "_sessions_for_pid", lambda pid: [])
    old = progress()
    new = progress(row("P-024", "feat-a"), row("P-025", None))
    d = _batch_resolve(old, new)
    assert any("无 session" in e for e in d.errors), d.errors


# ---------------------------------------------------------------- T-6 四文档齐全（P-081）

def test_t1_missing_doc_errors(monkeypatch):
    """T1 批次缺任一四文档 → 红。"""
    monkeypatch.setattr(se, "_missing_docs", lambda feat: ["CHECKLIST.md"])
    old = progress()
    new = progress(row("P-200", "feat-a", "T1"))
    d = _batch_resolve(old, new)
    assert any("四文档不全" in e for e in d.errors), d.errors


def test_t1_complete_docs_passes(monkeypatch):
    monkeypatch.setattr(se, "_missing_docs", lambda feat: [])
    old = progress()
    new = progress(row("P-200", "feat-a", "T1"))
    d = _batch_resolve(old, new)
    assert not [e for e in d.errors if "四文档" in e], d.errors


def test_t3_skips_doc_completeness(monkeypatch):
    """T3 轻批合法无四文档：缺文件也不得报错。"""
    monkeypatch.setattr(se, "_missing_docs", lambda feat: ["RESEARCH.md"])
    old = progress()
    new = progress(row("P-200", "feat-a", "T3"))
    d = _batch_resolve(old, new)
    assert not [e for e in d.errors if "四文档" in e], d.errors


def test_missing_tier_errors(monkeypatch):
    """P ≥ 阈值但依据列无 T1/T3 → 红（不默认 T1 以免历史大面积误报）。"""
    monkeypatch.setattr(se, "_missing_docs", lambda feat: [])
    old = progress()
    new = progress(row("P-200", "feat-a", None))
    d = _batch_resolve(old, new)
    assert any("缺批次档位" in e for e in d.errors), d.errors


def test_low_pid_is_not_gated(monkeypatch):
    """低于阈值的 P 行不受四文档/档位约束（棘轮不回溯）。"""
    monkeypatch.setattr(se, "_missing_docs", lambda feat: ["RESEARCH.md"])
    old = progress()
    new = progress(row("P-024", "feat-a", None))
    d = _batch_resolve(old, new)
    assert not [e for e in d.errors if "四文档" in e or "缺批次档位" in e], d.errors
