"""Textbook knowledge-graph adapter with a strict relation vocabulary (P-155)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.knowledge.graph.relations import RelationType
from researchclaw.knowledge.models import KGEdge, KGNode

TEXTBOOK_ENTITY_TYPES: tuple[str, ...] = (
    "concept",
    "definition",
    "theorem",
    "lemma",
    "corollary",
    "proof",
    "example",
    "exercise",
    "chapter",
    "section",
    "method",
    "model",
    "dataset",
    "metric",
    "application",
)

TEXTBOOK_RELATION_TYPES: tuple[str, ...] = tuple(
    relation.value for relation in RelationType
) + (
    "depends_on",
    "proves",
    "contains",
    "topic_contains",
    "generalizes",
    "applies",
    "prerequisite",
    "example_of",
    "formalized_in",
)

_ENTITY_TYPES = frozenset(TEXTBOOK_ENTITY_TYPES)
_RELATION_TYPES = frozenset(TEXTBOOK_RELATION_TYPES)


def load_textbook_kg(
    path: str | Path,
) -> tuple[list[KGNode], list[KGEdge], list[dict]]:
    """Load the KG; invalid entities/edges are reported and skipped, never stored."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid textbook KG JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("textbook KG must be an object")
    raw_nodes = data.get("entities")
    raw_edges = data.get("relations")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("textbook KG needs entities and relations lists")

    nodes: list[KGNode] = []
    errors: list[dict] = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            errors.append({"code": "E_ENTITY_SHAPE", "index": index})
            continue
        node_type = str(raw.get("type") or "")
        node_id = str(raw.get("id") or "")
        name = str(raw.get("name") or "")
        if not node_id or not name or node_type not in _ENTITY_TYPES:
            errors.append({"code": "E_ENTITY_TYPE", "index": index, "type": node_type})
            continue
        nodes.append(KGNode(
            id=node_id,
            type=node_type,
            name=name,
            page=int(raw.get("page") or 0),
            attributes=dict(raw.get("attributes") or {}),
        ))

    known_ids = {node.id for node in nodes}
    edges: list[KGEdge] = []
    for index, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            errors.append({"code": "E_EDGE_SHAPE", "index": index})
            continue
        relation = str(raw.get("type") or "")
        source = str(raw.get("source") or "")
        target_id = str(raw.get("target") or "")
        if relation not in _RELATION_TYPES:
            errors.append({
                "code": "E_ILLEGAL_RELATION",
                "index": index,
                "type": relation,
            })
            continue
        if source not in known_ids or target_id not in known_ids:
            errors.append({"code": "E_UNKNOWN_ENDPOINT", "index": index})
            continue
        edges.append(KGEdge(
            source=source,
            target=target_id,
            type=relation,
            page=int(raw.get("page") or 0),
        ))
    return nodes, edges, errors


def query_entities(nodes: list[KGNode], text: str, limit: int = 10) -> list[KGNode]:
    needle = (text or "").strip().lower()
    if not needle:
        return []
    hits = [node for node in nodes if needle in node.name.lower()]
    return hits[: max(0, int(limit))]
