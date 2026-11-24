"""Data models for G5 knowledge access and Grounded QA (P-155)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    year: int = 0
    venue: str = ""
    doi: str = ""
    abstract: str = ""
    classification_confidence: float = 0.0
    metadata_confidence: float = 0.0
    pdf_name: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "abstract": self.abstract,
            "classification_confidence": self.classification_confidence,
            "metadata_confidence": self.metadata_confidence,
            "pdf_name": self.pdf_name,
            "source": self.source,
        }


@dataclass(frozen=True)
class KGNode:
    id: str
    type: str
    name: str
    page: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "page": self.page,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class KGEdge:
    source: str
    target: str
    type: str
    page: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "page": self.page,
        }


@dataclass
class QueryResult:
    results: list[Any] = field(default_factory=list)
    empty: bool = True
    retrieval_degraded: bool = False
    backend: str = "none"
    fulltext: bool = False
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": list(self.results),
            "empty": self.empty,
            "retrieval_degraded": self.retrieval_degraded,
            "backend": self.backend,
            "fulltext": self.fulltext,
            "count": self.count,
        }


@dataclass(frozen=True)
class SkillPackInfo:
    id: str
    path: str
    version: str
    digest: str
    signature: str


@dataclass(frozen=True)
class Citation:
    source: str
    locator: str
    quote: str
    digest: str

    @classmethod
    def from_quote(cls, source: str, locator: str, quote: str) -> "Citation":
        digest = "sha256:" + hashlib.sha256(quote.encode("utf-8")).hexdigest()
        return cls(source=source, locator=locator, quote=quote, digest=digest)

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "locator": self.locator,
            "quote": self.quote,
            "digest": self.digest,
        }
