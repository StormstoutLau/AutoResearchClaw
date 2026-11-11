"""数据类型 — 证明树/搜索状态/合法性"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# Stage 3: Agentic Proving
# ============================================================================

class NodeStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PROVEN = "proven"
    SORRY = "sorry"
    BLOCKED = "blocked"

class ErrorType(Enum):
    """APOLLO 5 类错误 + 扩展"""
    SYNTAX = "syntax"
    TYPE_MISMATCH = "type_mismatch"
    MISSING_LEMMA = "missing_lemma"
    TACTIC_FAILURE = "tactic_failure"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"

@dataclass
class ProofNode:
    """证明树中的节点"""
    id: str
    goal: str
    tier: int = 1
    status: NodeStatus = NodeStatus.PENDING
    tactic: Optional[str] = None
    reflection: Optional[str] = None    # Seed-Prover: 反思性分析
    children: list[ProofNode] = field(default_factory=list)
    parent_id: Optional[str] = None
    model_used: Optional[str] = None
    iterations: int = 0
    errors: list[str] = field(default_factory=list)

@dataclass
class ProofTree:
    """完整证明树"""
    root: ProofNode
    total_subgoals: int = 0
    proven: int = 0
    sorry: int = 0
    blocked: int = 0
    # D093 / F7: 运行期指标（旁路；不进入 snapshot / 序列化输出）。
    run_stats: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "total": self.total_subgoals,
            "proven": self.proven,
            "sorry": self.sorry,
            "blocked": self.blocked,
            "completion": self.proven / max(self.total_subgoals, 1)
        }

@dataclass
class BeamCandidate:
    """Beam Search 候选节点"""
    node: ProofNode
    tactics_applied: list[str] = field(default_factory=list)
    score: float = 0.0
    depth: int = 0

@dataclass
class BeamSearchState:
    """Beam Search 状态"""
    beam: list[BeamCandidate] = field(default_factory=list)
    beam_width: int = 4
    max_depth: int = 10
    current_depth: int = 0
    best_score: float = 0.0
    best_candidate: Optional[BeamCandidate] = None


# ============================================================================
# Stage 3.5: 7-Layer Legality Detection (LongCat)
# ============================================================================

@dataclass
class LegalityCheckResult:
    """单层合法性检测结果"""
    layer: int
    layer_name: str
    passed: bool
    violations: list[str] = field(default_factory=list)
    details: str = ""

@dataclass
class LegalityReport:
    """7 层合法性检测完整报告"""
    checks: list[LegalityCheckResult] = field(default_factory=list)
    overall_pass: bool = True

    @property
    def violation_count(self) -> int:
        return sum(len(c.violations) for c in self.checks if not c.passed)

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  Layer {c.layer} [{c.layer_name}]: {status}")
            for v in c.violations:
                lines.append(f"    - {v}")
        return "\n".join(lines)


# ============================================================================
# 模型调用记录
# ============================================================================

@dataclass
class ModelCallRecord:
    model: str
    stage: str
    task: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    # B-36 (D049): 传输归因的**结构化**承载 (原始事实, 供离线复算)。
    #   为什么在 gateway 侧单点: 全族 LLM 调用**都汇聚**到 `ModelGateway._record`
    #   ⇒ 一处修复覆盖全族 (非逐 Stage 加字段)。默认值 ⇒ 既有构造点零变化。
    finish_reason: Optional[str] = None
    reasoning_chars: int = 0
    diagnosis: Optional[str] = None
