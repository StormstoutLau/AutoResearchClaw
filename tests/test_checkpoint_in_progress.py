"""B-33 L0: an interrupted stage must be re-entered, never skipped."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline.runner import (
    _write_checkpoint,
    _write_stage_start,
    read_checkpoint,
)
from researchclaw.pipeline.stages import Stage


def _read(run_dir: Path) -> dict:
    return json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))


class TestReadCheckpoint:
    def test_no_checkpoint_returns_none(self, tmp_path: Path) -> None:
        assert read_checkpoint(tmp_path) is None

    def test_completed_stage_returns_next(self, tmp_path: Path) -> None:
        _write_checkpoint(tmp_path, Stage.RESOURCE_PLANNING, "r1")
        assert read_checkpoint(tmp_path) == Stage.EXPERIMENT_RUN

    def test_in_progress_stage_wins_over_next(self, tmp_path: Path) -> None:
        _write_checkpoint(tmp_path, Stage.RESOURCE_PLANNING, "r1")
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        assert read_checkpoint(tmp_path) == Stage.CODE_GENERATION

    def test_in_progress_wins_over_older_completed(self, tmp_path: Path) -> None:
        _write_checkpoint(tmp_path, Stage.TOPIC_INIT, "r1")
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        # An earlier completion must not mask a later in-progress marker.
        assert read_checkpoint(tmp_path) == Stage.CODE_GENERATION

    def test_in_progress_cleared_for_later_stage(self, tmp_path: Path) -> None:
        _write_checkpoint(tmp_path, Stage.RESOURCE_PLANNING, "r1")
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        # Once the interrupted stage completes, the next stage is scheduled.
        _write_checkpoint(tmp_path, Stage.CODE_GENERATION, "r1")
        assert read_checkpoint(tmp_path) == Stage.RESOURCE_PLANNING


class TestWriteStageStart:
    def test_preserves_last_completed(self, tmp_path: Path) -> None:
        _write_checkpoint(tmp_path, Stage.RESOURCE_PLANNING, "r1")
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        data = _read(tmp_path)
        assert data["last_completed_stage"] == int(Stage.RESOURCE_PLANNING)
        assert data["in_progress_stage"] == int(Stage.CODE_GENERATION)
        assert data["in_progress_name"] == "CODE_GENERATION"
        assert data["run_id"] == "r1"

    def test_works_without_existing_checkpoint(self, tmp_path: Path) -> None:
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        data = _read(tmp_path)
        assert data["in_progress_stage"] == int(Stage.CODE_GENERATION)
        assert "last_completed_stage" not in data

    def test_completion_clears_in_progress(self, tmp_path: Path) -> None:
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        _write_checkpoint(tmp_path, Stage.CODE_GENERATION, "r1")
        data = _read(tmp_path)
        assert "in_progress_stage" not in data
        assert data["last_completed_stage"] == int(Stage.CODE_GENERATION)

    def test_no_temp_files_left(self, tmp_path: Path) -> None:
        _write_stage_start(tmp_path, Stage.CODE_GENERATION, "r1")
        assert not list(tmp_path.glob("checkpoint_*.tmp"))
