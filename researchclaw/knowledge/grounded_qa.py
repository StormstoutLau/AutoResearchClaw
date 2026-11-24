"""Grounded QA contract with a null implementation and explicit degradation (P-155)."""
from __future__ import annotations

from typing import Any, Iterable

from researchclaw.knowledge.models import Citation


def stage20_contradiction_gate(result: dict, policy: str = "warn") -> dict:
    """Stage 20 helper: block only when policy is ``block`` and contradictions exist."""
    contradictions = list(result.get("contradictions") or [])
    blocked = policy == "block" and bool(contradictions)
    return {
        "blocked": blocked,
        "code": "E20_GQ_CONTRADICTION" if blocked else "",
    }


class NullGroundedQA:
    """Default-off implementation: no retrieval, no files, always insufficient."""

    def answer(self, question: str = "", policy: str = "warn") -> dict[str, Any]:
        return {
            "citations": [],
            "status": "insufficient",
            "retrieval_degraded": False,
            "backend": "none",
            "contradictions": [],
            "blocked": False,
        }


class GroundedQA:
    """Answer with citations from a KnowledgeStore.

    ``enabled=False`` delegates to :class:`NullGroundedQA`, so a disabled run
    produces no files and is byte-identical to the baseline (GQ-1).
    """

    def __init__(
        self,
        store: Any,
        *,
        enabled: bool = False,
        fail_backend: bool = False,
        contradictions: Iterable[str] = (),
    ) -> None:
        self.store = store
        self.enabled = bool(enabled)
        self.fail_backend = bool(fail_backend)
        self.contradictions = list(contradictions)

    def answer(self, question: str, policy: str = "warn") -> dict[str, Any]:
        if not self.enabled:
            return NullGroundedQA().answer(question, policy)
        if self.fail_backend:
            return {
                "citations": [],
                "status": "insufficient",
                "retrieval_degraded": True,
                "backend": "none",
                "contradictions": list(self.contradictions),
                "blocked": False,
            }

        result = self.store.query("paper", question)
        citations: list[dict[str, str]] = []
        for row in result.results[:3]:
            quote = str(row.get("abstract") or row.get("title") or "").strip()
            if not quote:
                continue
            citation = Citation.from_quote(
                source=f"paper:{row.get('paper_id', '')}",
                locator="abstract",
                quote=quote,
            )
            citations.append(citation.to_dict())

        blocked = policy == "block" and bool(self.contradictions)
        output: dict[str, Any] = {
            "citations": citations,
            "status": "answered" if citations else "insufficient",
            "retrieval_degraded": bool(result.retrieval_degraded),
            "backend": result.backend,
            "contradictions": list(self.contradictions),
            "blocked": blocked,
        }
        if blocked:
            output["code"] = "E20_GQ_CONTRADICTION"
        return output
