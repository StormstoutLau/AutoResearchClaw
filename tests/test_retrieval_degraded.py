"""H-4: retrieval degradation must be explicit."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline.stage_impls._literature import _write_retrieval_status


def test_degraded_marker_true(tmp_path: Path) -> None:
    name = _write_retrieval_status(tmp_path, real_search_succeeded=False)
    data = json.loads((tmp_path / name).read_text(encoding="utf-8"))
    assert data["retrieval_degraded"] is True
    assert data["degraded_reason"] == ["academic_api_search_failed"]
    assert data["real_search_succeeded"] is False


def test_degraded_marker_false(tmp_path: Path) -> None:
    name = _write_retrieval_status(tmp_path, real_search_succeeded=True)
    data = json.loads((tmp_path / name).read_text(encoding="utf-8"))
    assert data["retrieval_degraded"] is False
    assert data["degraded_reason"] == []
