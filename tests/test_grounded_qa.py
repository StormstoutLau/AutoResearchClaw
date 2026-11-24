"""P-155 T20-T24: Grounded QA contract, citations and degradation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from researchclaw.knowledge.grounded_qa import (
    GroundedQA,
    NullGroundedQA,
    stage20_contradiction_gate,
)
from researchclaw.knowledge.models import QueryResult


class _StubStore:
    def __init__(self, results: list[dict]) -> None:
        self._results = results

    def query(self, kind: str, text: str = "", limit: int = 10) -> QueryResult:
        rows = self._results[:limit]
        return QueryResult(
            results=rows,
            empty=not rows,
            retrieval_degraded=False,
            backend="lexical",
            fulltext=False,
            count=len(rows),
        )


def _paper_result() -> list[dict]:
    return [{
        "paper_id": "p1",
        "title": "Alpha robustness",
        "abstract": "Evidence text about alpha robustness.",
    }]


class TestGroundedQA:
    def test_gq_disabled_writes_nothing(self, tmp_path: Path) -> None:
        qa = GroundedQA(_StubStore(_paper_result()), enabled=False)
        result = qa.answer("alpha")
        assert result["status"] == "insufficient"
        assert list(tmp_path.rglob("*")) == []
        assert NullGroundedQA().answer("alpha")["status"] == "insufficient"

    def test_citation_four_fields_digest_recomputes(self) -> None:
        qa = GroundedQA(_StubStore(_paper_result()), enabled=True)
        result = qa.answer("alpha")
        assert result["status"] == "answered"
        citation = result["citations"][0]
        assert set(citation) == {"source", "locator", "quote", "digest"}
        expected = "sha256:" + hashlib.sha256(citation["quote"].encode("utf-8")).hexdigest()
        assert citation["digest"] == expected

    def test_insufficient_without_evidence(self) -> None:
        qa = GroundedQA(_StubStore([]), enabled=True)
        result = qa.answer("alpha")
        assert result["status"] == "insufficient"
        assert result["citations"] == []

    def test_dependency_failure_degrades_not_fails(self) -> None:
        qa = GroundedQA(_StubStore([]), enabled=True, fail_backend=True)
        result = qa.answer("alpha")
        assert result["retrieval_degraded"] is True
        assert result["status"] == "insufficient"

    def test_contradiction_warn_and_block(self) -> None:
        qa = GroundedQA(
            _StubStore(_paper_result()),
            enabled=True,
            contradictions=["source A says 0.9; source B says 0.7"],
        )
        warn = qa.answer("alpha")
        assert warn["contradictions"]
        assert warn["blocked"] is False
        blocked = qa.answer("alpha", policy="block")
        assert blocked["blocked"] is True
        assert blocked["code"] == "E20_GQ_CONTRADICTION"
        gate = stage20_contradiction_gate(blocked, policy="block")
        assert gate["blocked"] is True
        assert gate["code"] == "E20_GQ_CONTRADICTION"


# ---------------------------------------------------------------------------
# GQ-5 wiring: Stage 20 reads grounded_qa/result.json and honours the policy.
# ---------------------------------------------------------------------------

def _config(policy: str):
    from researchclaw.config import RCConfig

    return RCConfig.from_dict(
        {
            "project": {"name": "demo"},
            "research": {"topic": "Test topic"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "console"},
            "knowledge_base": {"root": "docs/kb", "grounded_qa_policy": policy},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        check_paths=False,
    )


def _stage20_run(tmp_path: Path, contradictions: list[str]) -> tuple[Path, Path]:
    stage_dir = tmp_path / "stage-20"
    stage_dir.mkdir(parents=True)
    stage_19 = tmp_path / "stage-19"
    stage_19.mkdir()
    (stage_19 / "paper_revised.md").write_text("# Paper\n\nbody", encoding="utf-8")
    gq_dir = tmp_path / "grounded_qa"
    gq_dir.mkdir()
    (gq_dir / "result.json").write_text(
        json.dumps({"status": "answered", "contradictions": contradictions}),
        encoding="utf-8",
    )
    return stage_dir, tmp_path


def test_stage20_blocks_on_gq_contradiction(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_quality_gate,
    )

    stage_dir, run_dir = _stage20_run(tmp_path, ["A says 0.9; B says 0.7"])
    result = _execute_quality_gate(
        stage_dir, run_dir, _config("block"), object(), llm=None
    )
    assert result.status.name == "FAILED"
    assert "E20_GQ_CONTRADICTION" in (result.error or "")


def test_stage20_warn_policy_does_not_block(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_quality_gate,
    )

    stage_dir, run_dir = _stage20_run(tmp_path, ["A says 0.9; B says 0.7"])
    result = _execute_quality_gate(
        stage_dir, run_dir, _config("warn"), object(), llm=None
    )
    assert "E20_GQ_CONTRADICTION" not in (result.error or "")
