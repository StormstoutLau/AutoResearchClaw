"""P-155 T01-T06: Paper index selection, dedup and confidence rules."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.knowledge.models import PaperRecord
from researchclaw.knowledge.paper_index import (
    batch_report,
    load_paper_index,
    normalize_confidence,
    normalize_confidence_with_flag,
    select_first_batch,
)


def _rec(
    paper_id: str,
    *,
    title: str = "",
    year: int = 2024,
    doi: str = "",
    confidence: float = 0.9,
    metadata: float = 1.0,
    pdf: str = "",
) -> PaperRecord:
    return PaperRecord(
        paper_id=paper_id,
        title=title or f"Paper {paper_id}",
        year=year,
        doi=doi,
        classification_confidence=confidence,
        metadata_confidence=metadata,
        pdf_name=pdf,
    )


class TestPaperBatch:
    def test_paper_batch_selects_500(self) -> None:
        records = [_rec(f"p{i:04d}", confidence=1.0 - (i % 100) / 100) for i in range(600)]
        selected = select_first_batch(records, limit=500)
        assert len(selected) == 500
        assert len({record.paper_id for record in selected}) == 500
        # Deterministic: the same input gives the same first record.
        again = select_first_batch(records, limit=500)
        assert [r.paper_id for r in selected] == [r.paper_id for r in again]

    def test_duplicate_doi_removed(self) -> None:
        records = [
            _rec("p1", doi="10.1000/ABC"),
            _rec("p2", doi="10.1000/abc"),
            _rec("p3", doi="10.1000/xyz"),
        ]
        selected = select_first_batch(records, limit=10)
        report = batch_report(records, limit=10)
        assert len(selected) == 2
        assert report["duplicates"] == 1

    def test_duplicate_title_year_removed(self) -> None:
        records = [
            _rec("p1", title="A Study of Things!", year=2024),
            _rec("p2", title="a   study of things", year=2024),
            _rec("p3", title="A Study of Things", year=2023),
        ]
        selected = select_first_batch(records, limit=10)
        report = batch_report(records, limit=10)
        assert len(selected) == 2
        assert report["duplicates"] == 1

    def test_confidence_normalized_from_percent(self) -> None:
        assert normalize_confidence(92) == pytest.approx(0.92)
        assert normalize_confidence(0.8) == pytest.approx(0.8)

    def test_confidence_boundary_one(self) -> None:
        value, boundary = normalize_confidence_with_flag(1)
        assert value == 1.0
        assert boundary is True
        value2, boundary2 = normalize_confidence_with_flag(1.0)
        assert value2 == 1.0
        assert boundary2 is True
        value3, _ = normalize_confidence_with_flag(1.01)
        assert value3 == pytest.approx(0.0101)

    def test_corrupt_paper_jsonl_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "papers.jsonl"
        path.write_text('{"paper_id":"p1","title":"ok"}\n{not json}\n', encoding="utf-8")
        with pytest.raises(ValueError):
            load_paper_index(path)
