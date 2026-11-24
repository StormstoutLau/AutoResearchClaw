"""Single-source knowledge counts (P-155 / K5)."""
from __future__ import annotations

from pathlib import Path

from researchclaw.knowledge.paper_index import batch_report, load_paper_index, select_first_batch
from researchclaw.knowledge.textbook_kg import load_textbook_kg

_INDEX_DIR = "index"


def knowledge_counts(
    kb_root: str | Path,
    *,
    paper_index_path: str | Path | None = None,
    kg_path: str | Path | None = None,
    doc_counts: dict | None = None,
) -> dict:
    root = Path(kb_root)
    index_dir = root / _INDEX_DIR
    paper_path = Path(paper_index_path) if paper_index_path else index_dir / "paper_entities.jsonl"
    kg_file = Path(kg_path) if kg_path else index_dir / "textbook_kg.json"

    paper_count = 0
    paper_duplicates = 0
    if paper_path.is_file():
        records = load_paper_index(paper_path)
        paper_count = len(select_first_batch(records))
        paper_duplicates = int(batch_report(records)["duplicates"])

    kg_nodes = 0
    kg_edges = 0
    illegal_edges = 0
    if kg_file.is_file():
        nodes, edges, errors = load_textbook_kg(kg_file)
        kg_nodes = len(nodes)
        kg_edges = len(edges)
        illegal_edges = sum(
            1 for error in errors if error.get("code") == "E_ILLEGAL_RELATION"
        )

    counts = {
        "paper_count": paper_count,
        "paper_duplicates": paper_duplicates,
        "kg_nodes": kg_nodes,
        "kg_edges": kg_edges,
        "illegal_edges": illegal_edges,
    }
    mismatches: list[str] = []
    if doc_counts:
        for key, expected in doc_counts.items():
            if key in counts and counts[key] != expected:
                mismatches.append(key)
    counts["consistent"] = not mismatches
    counts["mismatches"] = mismatches
    return counts
