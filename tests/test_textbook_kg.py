"""P-155 T07-T10: Textbook KG counts, relation validation and queries."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.knowledge.textbook_kg import (
    TEXTBOOK_ENTITY_TYPES,
    TEXTBOOK_RELATION_TYPES,
    load_textbook_kg,
    query_entities,
)


def _kg_payload() -> dict:
    entities = []
    for group, prefix in enumerate(("Alpha", "Beta", "Gamma")):
        for index in range(5):
            entities.append({
                "id": f"tb-{group}-{index}",
                "type": TEXTBOOK_ENTITY_TYPES[index % len(TEXTBOOK_ENTITY_TYPES)],
                "name": f"{prefix} Concept {index}",
                "page": 10 + index,
                "attributes": {},
            })
    relations = []
    for index in range(17):
        relations.append({
            "source": entities[index % len(entities)]["id"],
            "target": entities[(index + 1) % len(entities)]["id"],
            "type": TEXTBOOK_RELATION_TYPES[index % len(TEXTBOOK_RELATION_TYPES)],
            "page": 20 + index,
        })
    return {"entities": entities, "relations": relations}


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "textbook_kg.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestTextbookKG:
    def test_textbook_kg_counts_15_17(self, tmp_path: Path) -> None:
        nodes, edges, errors = load_textbook_kg(_write(tmp_path, _kg_payload()))
        assert len(nodes) == 15
        assert len(edges) == 17
        assert errors == []
        assert len(TEXTBOOK_ENTITY_TYPES) == 15
        assert len(TEXTBOOK_RELATION_TYPES) == 17

    def test_illegal_relation_rejected(self, tmp_path: Path) -> None:
        payload = _kg_payload()
        payload["relations"].append({
            "source": payload["entities"][0]["id"],
            "target": payload["entities"][1]["id"],
            "type": "not_a_relation",
            "page": 99,
        })
        nodes, edges, errors = load_textbook_kg(_write(tmp_path, payload))
        assert len(nodes) == 15
        assert len(edges) == 17
        assert len(errors) == 1
        assert errors[0]["code"] == "E_ILLEGAL_RELATION"

    def test_sample_queries_return_three_with_page(self, tmp_path: Path) -> None:
        nodes, _edges, _errors = load_textbook_kg(_write(tmp_path, _kg_payload()))
        for query in ("alpha", "BETA", "Gamma"):
            hits = query_entities(nodes, query, limit=5)
            assert len(hits) >= 3
            assert all(hit.page for hit in hits)

    def test_corrupt_kg_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            load_textbook_kg(path)
