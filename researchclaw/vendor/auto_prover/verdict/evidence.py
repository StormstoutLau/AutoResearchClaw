"""W1 / B-54: 编译证据解析（纯函数，零 I/O）。"""
from __future__ import annotations

import re

# Lean 官方 Reference《Validating a Lean Proof》§Printing Axioms:
# 标准公理 = propext / Classical.choice / Quot.sound。
STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}

_SORRY_RE = re.compile(r"declaration uses ['\"]sorry['\"]", re.IGNORECASE)
_ERROR_RE = re.compile(r"\berror:", re.IGNORECASE)
_NO_AXIOM_RE = re.compile(r"does not depend on any axioms", re.IGNORECASE)
_AXIOM_LIST_RE = re.compile(r"depends on axioms:\s*\[([^\]]*)\]", re.DOTALL)


def parse_sorry_warnings(diagnostics: str) -> list[str]:
    """提取 `declaration uses 'sorry'` 警告行。"""
    return [
        line.strip()
        for line in (diagnostics or "").splitlines()
        if _SORRY_RE.search(line)
    ]


def parse_compile_errors(diagnostics: str) -> list[str]:
    """提取 Lean/Lake `error:` 诊断行（保留完整行）。"""
    return [
        line.strip()
        for line in (diagnostics or "").splitlines()
        if _ERROR_RE.search(line)
    ]


def parse_axiom_output(diagnostics: str) -> tuple[list[str], str]:
    """解析 `#print axioms` 输出。

    Returns:
        (axioms, check) —— check ∈ passed / failed / skipped
    """
    text = diagnostics or ""
    if _NO_AXIOM_RE.search(text):
        return [], "passed"

    matches = _AXIOM_LIST_RE.findall(text)
    if not matches:
        return [], "skipped"

    raw = matches[-1]
    axioms = [item.strip().strip("'\"") for item in raw.split(",")]
    axioms = [item for item in axioms if item]
    check = "passed" if set(axioms).issubset(STANDARD_AXIOMS) else "failed"
    return axioms, check
