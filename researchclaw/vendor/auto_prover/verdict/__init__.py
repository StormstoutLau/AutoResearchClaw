"""W1 / B-52: 判定策略包。"""
from .policy import POLICY_VERSION, VerdictEvidence, decide_citation_label

__all__ = ["POLICY_VERSION", "VerdictEvidence", "decide_citation_label"]
