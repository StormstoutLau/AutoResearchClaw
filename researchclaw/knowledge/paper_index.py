"""Paper index loading, first-batch selection and confidence normalization (P-155)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from researchclaw.knowledge.models import PaperRecord

DEFAULT_BATCH = 500
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize_confidence(value: object) -> float:
    return normalize_confidence_with_flag(value)[0]


def normalize_confidence_with_flag(value: object) -> tuple[float, bool]:
    """Normalize to 0..1; ``value == 1`` is treated as an already-normalized 1.0."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0, False
    boundary = number == 1
    if number > 1:
        number = number / 100.0
    if number < 0:
        number = 0.0
    if number > 1:
        number = 1.0
    return number, boundary


def normalize_title(title: str) -> str:
    lower = (title or "").lower()
    cleaned = _PUNCT.sub("", lower)
    return _SPACE.sub(" ", cleaned).strip()


def dedup_key(record: PaperRecord) -> str:
    if record.doi.strip():
        return "doi:" + record.doi.strip().lower()
    return f"title:{normalize_title(record.title)}|{record.year}"


def load_paper_index(path: str | Path) -> list[PaperRecord]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    records: list[PaperRecord] = []
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid paper JSONL at line {lineno}: {exc}") from exc
        if not isinstance(raw, dict) or not raw.get("paper_id") or not raw.get("title"):
            raise ValueError(f"paper record at line {lineno} needs paper_id and title")
        confidence, _boundary = normalize_confidence_with_flag(
            raw.get("classification_confidence", 0)
        )
        try:
            year = int(raw.get("year") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"paper record at line {lineno}: invalid year: {raw.get('year')!r}"
            ) from exc
        try:
            metadata_value = float(raw.get("metadata_confidence") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "paper record at line "
                f"{lineno}: invalid metadata_confidence: {raw.get('metadata_confidence')!r}"
            ) from exc
        if not 0.0 <= metadata_value <= 1.0:
            raise ValueError(
                f"paper record at line {lineno}: metadata_confidence "
                f"out of 0-1 range: {metadata_value}"
            )
        records.append(PaperRecord(
            paper_id=str(raw["paper_id"]),
            title=str(raw["title"]),
            year=year,
            venue=str(raw.get("venue") or ""),
            doi=str(raw.get("doi") or ""),
            abstract=str(raw.get("abstract") or ""),
            classification_confidence=confidence,
            metadata_confidence=metadata_value,
            pdf_name=str(raw.get("pdf_name") or ""),
            source=str(raw.get("source") or ""),
        ))
    return records


def _sort_key(record: PaperRecord) -> tuple:
    metadata_first = 0 if record.metadata_confidence == 1.0 else 1
    has_pdf = 0 if record.pdf_name else 1
    return (metadata_first, -record.classification_confidence, has_pdf, record.paper_id)


def _select(records: Iterable[PaperRecord], limit: int) -> tuple[list[PaperRecord], dict]:
    ordered = sorted(records, key=_sort_key)
    seen: set[str] = set()
    selected: list[PaperRecord] = []
    duplicates = 0
    for record in ordered:
        key = dedup_key(record)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if len(selected) < limit:
            selected.append(record)
    rejected = max(len(ordered) - duplicates - len(selected), 0)
    report = {
        "selected": len(selected),
        "duplicates": duplicates,
        "rejected": rejected,
        "limit": limit,
    }
    return selected, report


def select_first_batch(
    records: Iterable[PaperRecord],
    limit: int = DEFAULT_BATCH,
    *,
    report_path: str | Path | None = None,
) -> list[PaperRecord]:
    selected, report = _select(records, limit)
    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return selected


def batch_report(records: Iterable[PaperRecord], limit: int = DEFAULT_BATCH) -> dict:
    return _select(records, limit)[1]
