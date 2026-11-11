"""数据类型 — LaTeX 状态与依赖图"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# Stage 1: NL → LaTeX 形式化 (多 LLM 验证 + 依赖检查)
# ============================================================================

class LaTeXStatus(Enum):
    SUCCESS = "success"                 # 多 LLM 共识 + 依赖无错误
    DEPENDENCY_ERROR = "dependency_error"  # 依赖未定义
    LLM_DISAGREEMENT = "llm_disagreement"  # 多 LLM 未达成共识
    MAX_RETRIES = "max_retries"

@dataclass
class DependencyCheck:
    """依赖检查结果"""
    referenced_symbols: list[str] = field(default_factory=list)  # LaTeX 中引用的符号
    undefined_symbols: list[str] = field(default_factory=list)   # 未定义的符号
    missing_hypotheses: list[str] = field(default_factory=list)  # 缺失的前提条件
    external_references: list[str] = field(default_factory=list) # 引用的外部论文/定理
    resolved_by_kg: list[str] = field(default_factory=list)      # 由知识库解析的符号
    resolved_by_paper_search: list[str] = field(default_factory=list)  # 由论文检索解析的符号
    all_dependencies_defined: bool = False
# 依赖链追踪 (Dependency Chain Tracking) — 传递闭包 + DAG
# ============================================================================

@dataclass
class DependencyNode:
    """依赖图中的一个节点"""
    name: str                               # 符号/定理/引理名称
    kind: str = "unknown"                   # "symbol" | "theorem" | "lemma" | "definition" | "paper"
    source: str = ""                        # 来源：KG / mathlib / paper / external
    defined: bool = True                    # 是否已在 KG 中定义
    statement: str = ""                     # 定义/陈述
    depth: int = 0                          # 距离根断言的深度
    children: list[str] = field(default_factory=list)  # 子依赖（传递依赖）

@dataclass
class DependencyGraph:
    """断言依赖关系图（DAG）"""
    root_assertion: str = ""                # 根断言名称
    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (from, to)
    max_depth: int = 0                      # 依赖链最大深度
    total_nodes: int = 0
    undefined_nodes: list[str] = field(default_factory=list)    # 未定义的节点
    cycle_detected: bool = False
    cycles: list[list[str]] = field(default_factory=list)       # 检测到的循环
    external_count: int = 0                 # 外部（非 KG）依赖数量
    kg_coverage: float = 0.0                # KG 覆盖率

    def transitive_dependencies(self, node_name: str) -> set[str]:
        """计算传递闭包（所有直接和间接依赖）"""
        result = set()
        visited = set()
        def dfs(name):
            if name in visited:
                return
            visited.add(name)
            if name in self.nodes:
                for child in self.nodes[name].children:
                    result.add(child)
                    dfs(child)
        dfs(node_name)
        return result

    def dependency_path(self, target: str) -> list[str]:
        """从根断言到目标节点的最短依赖路径"""
        from collections import deque
        if self.root_assertion not in self.nodes:
            return []
        queue = deque([(self.root_assertion, [self.root_assertion])])
        visited = {self.root_assertion}
        while queue:
            current, path = queue.popleft()
            if current == target:
                return path
            if current in self.nodes:
                for child in self.nodes[current].children:
                    if child not in visited:
                        visited.add(child)
                        queue.append((child, path + [child]))
        return []

    def summary(self) -> str:
        return (
            f"DependencyGraph: {self.total_nodes} nodes, "
            f"max_depth={self.max_depth}, "
            f"undefined={len(self.undefined_nodes)}, "
            f"external={self.external_count}, "
            f"kg_coverage={self.kg_coverage:.0%}, "
            f"cycles={'DETECTED' if self.cycle_detected else 'none'}"
        )
