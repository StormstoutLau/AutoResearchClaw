"""Baseline-compatible submission layout for orchestration runs (OB-2)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .model import OrchestrationTask


def build_submission(
    workdir: Path,
    task: OrchestrationTask,
    aggregate: dict[str, Any],
    *,
    adapter_id: str,
) -> Path:
    workdir = Path(workdir)
    submission = workdir / "submission"
    (submission / "code").mkdir(parents=True, exist_ok=True)
    (submission / "results").mkdir(parents=True, exist_ok=True)

    (submission / "results" / "metrics.json").write_text(
        json.dumps(
            {"task_id": task.id, "adapter": adapter_id, "aggregate": aggregate},
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    (submission / "README.md").write_text(
        f"# Orchestration run — {task.id}\n\n"
        "The dry-run harness produces structured orchestration artifacts, not paper text.\n",
        encoding="utf-8",
    )
    (submission / "claims.json").write_text(
        json.dumps(
            {"topic_id": task.id, "claims": [], "summary_metrics": {}},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (submission / "reproduce.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# Re-wrap of an orchestration dry run.\n"
        "set -e\n"
        'echo "orchestration-submission" > results/.reproduce.marker\n',
        encoding="utf-8",
    )
    os.chmod(submission / "reproduce.sh", 0o755)
    (submission / "reproduce.log").write_text(
        f"Orchestration adapter {adapter_id} completed task {task.id}.\n",
        encoding="utf-8",
    )
    (submission / "reproduce.log.creation_time").write_text(
        str(int(time.time())), encoding="utf-8"
    )

    (workdir / "pipeline_summary.json").write_text(
        json.dumps(
            {
                "stages_executed": 4,
                "stages_done": 4,
                "stages_failed": 0,
                "degraded": False,
                "adapter": adapter_id,
                "task_id": task.id,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (workdir / "stage-14").mkdir(exist_ok=True)
    (workdir / "stage-14" / "experiment_summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return submission
