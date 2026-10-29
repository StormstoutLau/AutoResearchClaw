"""Pipeline core — 23-stage research pipeline.

Public API::

    from researchclaw.pipeline import execute_pipeline

    results = execute_pipeline(
        run_dir=Path("artifacts/rc-..."),
        run_id="rc-...",
        config=config,
        adapters=AdapterBundle(),
    )
"""

from researchclaw.pipeline._helpers import StageResult
from researchclaw.pipeline.contracts import CONTRACTS, StageContract
from researchclaw.pipeline.runner import execute_pipeline, execute_iterative_pipeline
from researchclaw.pipeline.stages import STAGE_SEQUENCE, Stage, StageStatus

__all__ = [
    "CONTRACTS",
    "STAGE_SEQUENCE",
    "Stage",
    "StageContract",
    "StageResult",
    "StageStatus",
    "execute_iterative_pipeline",
    "execute_pipeline",
]
