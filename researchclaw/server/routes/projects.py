"""Project listing / status API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from researchclaw.run_state import read_run_state

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects")
async def list_projects() -> dict[str, Any]:
    """List all project directories (artifacts/rc-*)."""
    artifacts = Path("artifacts")
    projects: list[dict[str, Any]] = []
    if artifacts.exists():
        for d in sorted(artifacts.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("rc-"):
                state = read_run_state(d)
                projects.append(
                    {
                        "id": state.run_id,
                        "path": str(d),
                        "current_stage": state.current_stage,
                        "current_stage_name": state.current_stage_name,
                        "status": state.status.value,
                        "is_active": state.is_active,
                        "topic": state.topic,
                        "start_time": state.start_time,
                        "last_update": state.last_update,
                        "schema_version": state.schema_version,
                    }
                )
    return {"projects": projects}
