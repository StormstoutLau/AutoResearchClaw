"""ResearchPlan v1: constrained task graph on top of the 23 stages (G8a / P-152)."""
from .decompose import (
    DecomposeError,
    decompose_node,
    should_decompose,
)
from .derive import (
    add_experiment_nodes,
    add_hypothesis_nodes,
    add_synthesis_gaps,
    build_initial_plan,
    check_experiment_plan_consistency,
    mark_analysis_done,
)
from .exp_plan import ensure_methods
from .ledger import compute_ledger, read_ledger, write_ledger
from .rebuild import rebuild_plan
from .replan import (
    ReplanError,
    apply_replan,
    plan_diff,
    replan,
    request_replan,
)
from .schema import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FANOUT,
    MAX_NODES,
    NODE_STATUSES,
    NODE_TYPES,
    SCHEMA_ID,
    Violation,
    plan_digest,
    seal_plan,
    validate_plan,
)
from .search import search_experiment_candidates
from .store import (
    PLAN_DIR,
    PLAN_NAME,
    append_event,
    load_plan,
    plan_filename,
    read_events,
    read_index,
    update_from_stage,
    update_plan,
    write_plan,
    write_replan,
)

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_FANOUT",
    "MAX_NODES",
    "NODE_STATUSES",
    "NODE_TYPES",
    "PLAN_DIR",
    "PLAN_NAME",
    "SCHEMA_ID",
    "Violation",
    "DecomposeError",
    "ReplanError",
    "add_experiment_nodes",
    "add_hypothesis_nodes",
    "add_synthesis_gaps",
    "append_event",
    "apply_replan",
    "build_initial_plan",
    "check_experiment_plan_consistency",
    "compute_ledger",
    "decompose_node",
    "ensure_methods",
    "load_plan",
    "mark_analysis_done",
    "plan_diff",
    "plan_digest",
    "plan_filename",
    "read_events",
    "read_index",
    "read_ledger",
    "rebuild_plan",
    "replan",
    "request_replan",
    "search_experiment_candidates",
    "seal_plan",
    "should_decompose",
    "update_from_stage",
    "update_plan",
    "validate_plan",
    "write_ledger",
    "write_plan",
    "write_replan",
]
