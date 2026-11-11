"""W2: 求值隔离与 Lean/REPL 沙箱（B-53 / B-55）。

子模块:
  · :mod:`proof_pipeline.sandbox.evaluator`   —— AST 白名单 + worker + 双超时
  · :mod:`proof_pipeline.sandbox.lean_filter` —— Lean 危险构造过滤
"""
from .limits import DEFAULT_MEMORY_LIMIT_MB
from .evaluator import (
    DEFAULT_BATCH_BUDGET_S,
    DEFAULT_SEARCH_BUDGET_S,
    DEFAULT_TIMEOUT_S,
    MAX_EXPR_CHARS,
    EvaluationError,
    EvaluationTimeout,
    SafeEvaluator,
    UnsafeExpressionError,
    WorkerCrashed,
    validate_expression,
)
from .lean_filter import (
    DANGEROUS_LEAN_TOKENS,
    scan_dangerous_commands,
    strip_comments,
)

__all__ = [
    "DANGEROUS_LEAN_TOKENS",
    "DEFAULT_BATCH_BUDGET_S",
    "DEFAULT_MEMORY_LIMIT_MB",
    "DEFAULT_SEARCH_BUDGET_S",
    "DEFAULT_TIMEOUT_S",
    "MAX_EXPR_CHARS",
    "EvaluationError",
    "EvaluationTimeout",
    "SafeEvaluator",
    "UnsafeExpressionError",
    "WorkerCrashed",
    "scan_dangerous_commands",
    "strip_comments",
    "validate_expression",
]
