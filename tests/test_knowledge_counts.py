"""P-155 T27-T28: knowledge counts single source and mismatch detection."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.knowledge.stats import knowledge_counts

KG = {
    "entities": [
        {"id": f"tb-{i}", "type": "concept", "name": f"Node {i}", "page": i}
        for i in range(15)
    ],
    "relations": [
        {"source": f"tb-{i % 15}", "target": f"tb-{(i + 1) % 15}", "type": "depends_on"}
        for i in range(17)
    ],
}


def _fixtures(tmp_path: Path) -> tuple[Path, Path]:
    index = tmp_path / "papers.jsonl"
    rows = [
        {"paper_id": "p1", "title": "A", "year": 2024,
         "classification_confidence": 0.9, "metadata_confidence": 1.0},
        {"paper_id": "p2", "title": "B", "year": 2023,
         "classification_confidence": 0.8, "metadata_confidence": 1.0},
        {"paper_id": "p3", "title": "a", "year": 2024,
         "classification_confidence": 0.7, "metadata_confidence": 1.0},
    ]
    index.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    kg = tmp_path / "textbook_kg.json"
    kg.write_text(json.dumps(KG), encoding="utf-8")
    return index, kg


class TestKnowledgeCounts:
    def test_knowledge_counts_single_source(self, tmp_path: Path) -> None:
        index, kg = _fixtures(tmp_path)
        first = knowledge_counts(tmp_path, paper_index_path=index, kg_path=kg)
        second = knowledge_counts(tmp_path, paper_index_path=index, kg_path=kg)
        assert first == second
        assert first["paper_count"] == 2
        assert first["paper_duplicates"] == 1
        assert first["kg_nodes"] == 15
        assert first["kg_edges"] == 17
        assert first["illegal_edges"] == 0
        assert first["consistent"] is True

    def test_counts_mismatch_detected(self, tmp_path: Path) -> None:
        index, kg = _fixtures(tmp_path)
        report = knowledge_counts(
            tmp_path,
            paper_index_path=index,
            kg_path=kg,
            doc_counts={"paper_count": 3, "kg_edges": 17},
        )
        assert report["consistent"] is False
        assert report["mismatches"] == ["paper_count"]
