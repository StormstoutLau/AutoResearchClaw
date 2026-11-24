"""P-155 T11-T15: KnowledgeStore empty/degraded/fulltext/read-only semantics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from researchclaw.knowledge.store import KnowledgeStore


def _paper_index(tmp_path: Path) -> Path:
    path = tmp_path / "papers.jsonl"
    rows = [
        {"paper_id": "p1", "title": "Alpha robustness", "year": 2024,
         "classification_confidence": 0.9, "metadata_confidence": 1.0,
         "pdf_name": "p1.pdf"},
        {"paper_id": "p2", "title": "Beta calibration", "year": 2023,
         "classification_confidence": 0.8, "metadata_confidence": 1.0,
         "pdf_name": "p2.pdf"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


class TestKnowledgeStore:
    def test_empty_kb_returns_empty(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path / "empty")
        result = store.query("paper", "anything")
        assert result.results == []
        assert result.empty is True
        assert result.count == 0
        assert result.fulltext is False

    def test_missing_index_marks_degraded(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path / "empty")
        result = store.query("paper", "alpha")
        assert result.retrieval_degraded is True
        assert result.backend == "none"

    def test_unknown_kind_raises(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        with pytest.raises(ValueError):
            store.query("unknown", "x")

    def test_query_is_read_only(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        (kb / "questions").mkdir(parents=True)
        (kb / "questions" / "q1.md").write_text("# Alpha question\n", encoding="utf-8")
        index = _paper_index(tmp_path)
        before = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (kb.rglob("*"),)
            for p in p
            if p.is_file()
        }
        before[str(index)] = hashlib.sha256(index.read_bytes()).hexdigest()

        store = KnowledgeStore(kb, paper_index_path=index)
        store.query("kb", "alpha")
        store.query("paper", "alpha")

        after = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (kb.rglob("*"),)
            for p in p
            if p.is_file()
        }
        after[str(index)] = hashlib.sha256(index.read_bytes()).hexdigest()
        assert before == after

    def test_fulltext_false_and_citation_rejected(self, tmp_path: Path) -> None:
        index = _paper_index(tmp_path)
        store = KnowledgeStore(tmp_path, paper_index_path=index)
        result = store.query("paper", "alpha")
        assert result.fulltext is False
        assert store.citation_allowed("abstract") is True
        assert store.citation_allowed("fulltext:p1#3") is False
