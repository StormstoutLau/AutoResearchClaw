"""Read-only knowledge query facade (P-155)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.knowledge.models import QueryResult
from researchclaw.knowledge.paper_index import load_paper_index
from researchclaw.knowledge.textbook_kg import load_textbook_kg, query_entities

_INDEX_DIR = "index"
_PAPER_INDEX = "paper_entities.jsonl"
_KG_INDEX = "textbook_kg.json"


class KnowledgeStore:
    """Read-only queries over KB markdown, the paper index and the textbook KG.

    Missing indexes are reported as ``retrieval_degraded`` plus ``empty``; no
    placeholder entries are ever fabricated.
    """

    def __init__(
        self,
        kb_root: str | Path,
        paper_index_path: str | Path | None = None,
        kg_path: str | Path | None = None,
    ) -> None:
        self.kb_root = Path(kb_root)
        index_dir = self.kb_root / _INDEX_DIR
        self.paper_index_path = (
            Path(paper_index_path) if paper_index_path is not None
            else index_dir / _PAPER_INDEX
        )
        self.kg_path = (
            Path(kg_path) if kg_path is not None else index_dir / _KG_INDEX
        )

    def query(self, kind: str, text: str = "", limit: int = 10) -> QueryResult:
        if kind not in ("kb", "paper", "kg"):
            raise ValueError(f"unknown query kind: {kind!r}")
        if kind == "kb":
            return self._query_kb(text, limit)
        if kind == "paper":
            return self._query_paper(text, limit)
        return self._query_kg(text, limit)

    def counts(self) -> dict:
        from researchclaw.knowledge.stats import knowledge_counts

        return knowledge_counts(
            self.kb_root,
            paper_index_path=self.paper_index_path,
            kg_path=self.kg_path,
        )

    @staticmethod
    def citation_allowed(locator: str) -> bool:
        """Fulltext is not available until Paper Phase 2; reject its locators."""
        return not (locator or "").strip().lower().startswith("fulltext")

    def _query_kb(self, text: str, limit: int) -> QueryResult:
        if not self.kb_root.is_dir():
            return QueryResult(empty=True, backend="none", count=0)
        needle = (text or "").strip().lower()
        rows: list[dict] = []
        for path in sorted(self.kb_root.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if needle and needle not in content.lower():
                continue
            title = ""
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            rows.append({
                "path": path.relative_to(self.kb_root).as_posix(),
                "title": title or path.stem,
                "excerpt": " ".join(content.split())[:200],
            })
            if len(rows) >= max(0, int(limit)):
                break
        return QueryResult(
            results=rows,
            empty=not rows,
            retrieval_degraded=False,
            backend="markdown" if rows else "none",
            fulltext=False,
            count=len(rows),
        )

    def _query_paper(self, text: str, limit: int) -> QueryResult:
        if not self.paper_index_path.is_file():
            return QueryResult(
                results=[],
                empty=True,
                retrieval_degraded=True,
                backend="none",
                fulltext=False,
                count=0,
            )
        records = load_paper_index(self.paper_index_path)
        needle = (text or "").strip().lower()
        rows = [
            record.to_dict()
            for record in records
            if not needle
            or needle in record.title.lower()
            or needle in record.abstract.lower()
        ][: max(0, int(limit))]
        return QueryResult(
            results=rows,
            empty=not rows,
            retrieval_degraded=False,
            backend="tfidf",
            fulltext=False,
            count=len(rows),
        )

    def _query_kg(self, text: str, limit: int) -> QueryResult:
        if not self.kg_path.is_file():
            return QueryResult(
                results=[],
                empty=True,
                retrieval_degraded=True,
                backend="none",
                fulltext=False,
                count=0,
            )
        nodes, _edges, _errors = load_textbook_kg(self.kg_path)
        hits = query_entities(nodes, text, limit=limit)
        rows = [node.to_dict() for node in hits]
        return QueryResult(
            results=rows,
            empty=not rows,
            retrieval_degraded=False,
            backend="kg",
            fulltext=False,
            count=len(rows),
        )


def load_json(path: str | Path) -> dict:
    """Small helper for tests and callers that need a JSON object."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
