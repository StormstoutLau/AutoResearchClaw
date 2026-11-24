"""Knowledge management — base, adapters, and the G5 read-only facade (P-155)."""

from researchclaw.knowledge.grounded_qa import (
    GroundedQA,
    NullGroundedQA,
    stage20_contradiction_gate,
)
from researchclaw.knowledge.models import (
    Citation,
    KGEdge,
    KGNode,
    PaperRecord,
    QueryResult,
    SkillPackInfo,
)
from researchclaw.knowledge.paper_index import (
    batch_report,
    load_paper_index,
    normalize_confidence,
    normalize_title,
    select_first_batch,
)
from researchclaw.knowledge.read_position import load_position, save_position
from researchclaw.knowledge.skillpack import load_skillpacks
from researchclaw.knowledge.stats import knowledge_counts
from researchclaw.knowledge.store import KnowledgeStore
from researchclaw.knowledge.textbook_kg import load_textbook_kg, query_entities

__all__ = [
    "Citation",
    "GroundedQA",
    "KGEdge",
    "KGNode",
    "KnowledgeStore",
    "NullGroundedQA",
    "PaperRecord",
    "QueryResult",
    "SkillPackInfo",
    "batch_report",
    "knowledge_counts",
    "load_paper_index",
    "load_position",
    "load_skillpacks",
    "load_textbook_kg",
    "normalize_confidence",
    "normalize_title",
    "query_entities",
    "save_position",
    "select_first_batch",
    "stage20_contradiction_gate",
]
