"""G3 M5 wiring: Stage 22/23 K5 blocking and retrieval notice (A3-4/A3-5)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.pipeline.stages import StageStatus


def _config(kb_root: Path) -> RCConfig:
    return RCConfig.from_dict(
        {
            "project": {"name": "k5-wiring"},
            "research": {"topic": "K5 wiring"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "console"},
            "knowledge_base": {"root": str(kb_root)},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        },
        check_paths=False,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_stage22_blocks_unresolved_k5_ref(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_export_publish,
    )

    run_dir = tmp_path / "run"
    _write(run_dir / "stage-19" / "paper_revised.md", "## Results\n\nSee tb:missing.\n")
    stage22 = run_dir / "stage-22"
    stage22.mkdir(parents=True)
    result = _execute_export_publish(
        stage22, run_dir, _config(tmp_path / "kb"), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.FAILED
    assert "E_K5_UNRESOLVED_REF" in (result.error or "")
    report = json.loads((stage22 / "k5_refs.json").read_text(encoding="utf-8"))
    assert report["unresolved"][0]["ref"] == "tb:missing"


def test_stage22_adds_retrieval_notice(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_export_publish,
    )

    run_dir = tmp_path / "run"
    _write(run_dir / "stage-19" / "paper_revised.md", "## Results\n\nPlain text.\n")
    _write(
        run_dir / "stage-04" / "retrieval_status.json",
        json.dumps({"retrieval_degraded": True}),
    )
    stage22 = run_dir / "stage-22"
    stage22.mkdir(parents=True)
    result = _execute_export_publish(
        stage22, run_dir, _config(tmp_path / "kb"), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.DONE
    paper = (stage22 / "paper_final.md").read_text(encoding="utf-8")
    assert paper.startswith("> **Retrieval note:**")
    assert "retrieval_degraded.json" in result.artifacts


def test_stage23_blocks_unresolved_k5_ref(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_citation_verify,
    )

    run_dir = tmp_path / "run"
    _write(run_dir / "stage-22" / "paper_final.md", "## Results\n\nSee paper:missing.\n")
    stage23 = run_dir / "stage-23"
    stage23.mkdir(parents=True)
    result = _execute_citation_verify(
        stage23, run_dir, _config(tmp_path / "kb"), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.FAILED
    assert "E_K5_UNRESOLVED_REF" in (result.error or "")
    report = json.loads((stage23 / "k5_refs.json").read_text(encoding="utf-8"))
    assert report["unresolved"][0]["ref"] == "paper:missing"
