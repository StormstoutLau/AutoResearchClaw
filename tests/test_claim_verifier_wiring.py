"""H-3: ClaimVerifier must be wired into the publication gates."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline.stage_impls._review_publish import _write_claim_verification


def test_writes_claim_report(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-20"
    stage_dir.mkdir()
    name = _write_claim_verification(
        stage_dir,
        tmp_path,
        "The method achieves accuracy 95% on the benchmark [Smith, 2024].",
    )
    assert name == "claim_verification.json"
    report = json.loads((stage_dir / name).read_text(encoding="utf-8"))
    assert report["total_claims"] >= 1
    assert "score" in report
    assert "claims" in report


def test_empty_text_still_writes_report(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-23"
    stage_dir.mkdir()
    name = _write_claim_verification(stage_dir, tmp_path, "")
    report = json.loads((stage_dir / name).read_text(encoding="utf-8"))
    assert report["total_claims"] == 0
    assert report["score"] == 1.0
