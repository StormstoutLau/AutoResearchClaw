"""Checkpoint atomic-write retry (P-160)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline import runner


def test_write_checkpoint_retries_permission_error(tmp_path, monkeypatch):
    real_replace = Path.replace
    calls = {"count": 0}

    def flaky_replace(self, target):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise PermissionError(13, "busy", str(target))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    runner._write_checkpoint(tmp_path, runner.Stage.TOPIC_INIT, "run-1")

    assert calls["count"] >= 3
    data = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert data["last_completed_stage"] == 1
    assert not list(tmp_path.glob("checkpoint_*.tmp"))
