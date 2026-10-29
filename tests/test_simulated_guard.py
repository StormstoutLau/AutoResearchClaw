"""PR-4 contract tests: default sandbox mode, simulated-paper escape hatch,
and agent-mode dispatch (SIM-01..04, AG-01..08)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from researchclaw.config import RCConfig, validate_config
from researchclaw.experiment.sandbox import SandboxResult


def _minimal(**overrides) -> dict:
    data: dict = {
        "project": {"name": "demo"},
        "research": {"topic": "Test topic"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "docs/kb"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "api_key_env": "OPENAI_API_KEY",
        },
    }
    for dotted, value in overrides.items():
        section, _, key = dotted.partition(".")
        data.setdefault(section, {})[key] = value
    return data


def _config(**overrides) -> RCConfig:
    return RCConfig.from_dict(_minimal(**overrides), check_paths=False)


# ── SIM-01: default experiment mode ──────────────────────────────


def test_sim01a_missing_mode_defaults_to_sandbox_with_warning() -> None:
    data = _minimal()
    result = validate_config(data, check_paths=False)
    assert result.ok
    assert any("experiment.mode not set" in w for w in result.warnings)

    config = RCConfig.from_dict(data, check_paths=False)
    assert config.experiment.mode == "sandbox"


def test_sim01b_explicit_simulated_is_preserved_without_warning() -> None:
    data = _minimal(**{"experiment.mode": "simulated"})
    result = validate_config(data, check_paths=False)
    assert result.ok
    assert not any("experiment.mode not set" in w for w in result.warnings)

    config = RCConfig.from_dict(data, check_paths=False)
    assert config.experiment.mode == "simulated"


def test_sim01c_invalid_mode_is_rejected() -> None:
    result = validate_config(_minimal(**{"experiment.mode": "kubernetes"}), check_paths=False)
    assert not result.ok
    assert any("Invalid experiment.mode" in e for e in result.errors)


def test_allow_simulated_paper_defaults_false() -> None:
    assert _config().research.allow_simulated_paper is False
    assert _config(**{"research.allow_simulated_paper": True}).research.allow_simulated_paper


# ── SIM-02: data_origin detection ────────────────────────────────


def _write_run(run_dir: Path, status: str, *, stage: str = "stage-12") -> None:
    runs = run_dir / stage / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "run-1.json").write_text(json.dumps({"status": status}), encoding="utf-8")


def test_sim02_simulated_mode_reports_simulated_origin(tmp_path: Path) -> None:
    from researchclaw.pipeline._helpers import detect_data_origin

    config = _config(**{"experiment.mode": "simulated"})
    assert detect_data_origin(tmp_path, config) == "simulated"


def test_sim02_real_run_reports_real_origin(tmp_path: Path) -> None:
    from researchclaw.pipeline._helpers import detect_data_origin

    _write_run(tmp_path, "completed")
    assert detect_data_origin(tmp_path, _config()) == "real"


def test_sim02_simulated_run_status_without_mode(tmp_path: Path) -> None:
    from researchclaw.pipeline._helpers import detect_data_origin

    _write_run(tmp_path, "simulated")
    assert detect_data_origin(tmp_path, _config()) == "simulated"


def test_sim02_missing_artifacts_is_unknown(tmp_path: Path) -> None:
    from researchclaw.pipeline._helpers import detect_data_origin

    assert detect_data_origin(tmp_path, _config()) == "unknown"


# ── SIM-03: Stage 20 blocks simulated papers ─────────────────────


def _prepare_stage20(tmp_path: Path, *, mode: str, allow: bool) -> tuple:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_quality_gate,
    )

    stage_dir = tmp_path / "stage-20"
    stage_dir.mkdir(parents=True)
    stage_19 = tmp_path / "stage-19"
    stage_19.mkdir()
    (stage_19 / "paper_revised.md").write_text("# Paper\n\nbody", encoding="utf-8")
    if mode == "simulated":
        _write_run(tmp_path, "simulated")

    config = _config(
        **{"experiment.mode": mode, "research.allow_simulated_paper": allow}
    )
    return _execute_quality_gate, stage_dir, config


def test_sim03_simulated_paper_is_blocked(tmp_path: Path) -> None:
    gate, stage_dir, config = _prepare_stage20(
        tmp_path, mode="simulated", allow=False
    )
    result = gate(stage_dir, tmp_path, config, object(), llm=None)
    assert result.status.name == "FAILED"
    assert "E20_SIMULATED_DATA" in (result.error or "")
    assert (stage_dir / "quality_warning.txt").is_file()


def test_sim03_real_mode_is_not_blocked(tmp_path: Path) -> None:
    gate, stage_dir, config = _prepare_stage20(
        tmp_path, mode="sandbox", allow=False
    )
    _write_run(tmp_path, "completed")
    result = gate(stage_dir, tmp_path, config, object(), llm=None)
    # Real data still has to satisfy the pre-existing VerifiedRegistry guard,
    # but it must never trip the simulated-specific block.
    assert "E20_SIMULATED_DATA" not in (result.error or "")
    assert not (stage_dir / "quality_warning.txt").exists()


# ── SIM-04: watermark when explicitly allowed ────────────────────


def test_sim04_markdown_watermark_is_prefixed() -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _apply_simulated_watermark,
    )

    marked = _apply_simulated_watermark("# Title\n\nbody")
    assert marked.startswith("> **SIMULATED DATA — NOT FOR SUBMISSION**")
    assert "# Title" in marked
    # Idempotent.
    assert _apply_simulated_watermark(marked) == marked


def test_sim04_latex_notice_is_injected() -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _add_simulated_latex_notice,
    )

    tex = "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n"
    marked = _add_simulated_latex_notice(tex)
    assert "SIMULATED DATA --- NOT FOR SUBMISSION" in marked
    assert marked.index("SIMULATED DATA") > marked.index("\\begin{document}")
    # Idempotent: a second pass must not duplicate the banner.
    assert _add_simulated_latex_notice(marked).count("SIMULATED DATA ---") == 1


def test_sim04_latex_notice_falls_back_without_document_env() -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _add_simulated_latex_notice,
    )

    marked = _add_simulated_latex_notice("no document env here")
    assert marked.startswith("\\begin{center}")
    assert "no document env here" in marked


# ── AG: agent-mode dispatch ──────────────────────────────────────


def _stage10_setup(tmp_path: Path, mode: str) -> tuple[Path, Path, RCConfig]:
    stage_dir = tmp_path / "stage-10"
    stage_dir.mkdir(parents=True)
    stage_09 = tmp_path / "stage-09"
    stage_09.mkdir()
    (stage_09 / "exp_plan.yaml").write_text("metric: accuracy\n", encoding="utf-8")
    config = _config(**{"experiment.mode": mode})
    return stage_dir, tmp_path, config


@pytest.mark.parametrize(
    ("mode", "plan_file", "meta_file"),
    [
        ("biology_agent", "biology_plan.md", "biology_meta.json"),
        ("stat_agent", "stat_plan.md", "stat_meta.json"),
        ("agentic", "agent_plan.md", "agent_meta.json"),
    ],
)
def test_ag02_stage10_writes_agent_plan(
    tmp_path: Path, mode: str, plan_file: str, meta_file: str
) -> None:
    from researchclaw.pipeline.stage_impls._code_generation import (
        _execute_code_generation,
    )

    stage_dir, run_dir, config = _stage10_setup(tmp_path, mode)
    result = _execute_code_generation(stage_dir, run_dir, config, object(), llm=None)

    assert result.status.name == "DONE"
    assert plan_file in result.artifacts
    assert (stage_dir / plan_file).is_file()
    assert (stage_dir / meta_file).is_file()
    assert (stage_dir / "experiment_spec.md").is_file()
    assert (stage_dir / "experiment" / plan_file).is_file()
    # No Python project is generated for agent modes.
    assert not any((stage_dir / "experiment").glob("*.py"))


@pytest.mark.parametrize(
    ("mode", "plan_file", "workspace"),
    [
        ("biology_agent", "biology_plan.md", "biology"),
        ("stat_agent", "stat_plan.md", "stat"),
    ],
)
def test_ag02_stage12_runs_agent_and_writes_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    plan_file: str,
    workspace: str,
) -> None:
    import researchclaw.experiment.factory as factory

    captured: dict = {}

    class FakeSandbox:
        def run(self, prompt_text: str, *, timeout_sec: int | None = None):
            captured["prompt"] = prompt_text
            captured["timeout"] = timeout_sec
            return SandboxResult(
                returncode=0,
                stdout="ok",
                stderr="",
                elapsed_sec=3.5,
                metrics={"growth_rate": 0.81},
                timed_out=False,
            )

    monkeypatch.setattr(factory, "create_sandbox", lambda cfg, wd: FakeSandbox())

    from researchclaw.pipeline.stage_impls._execution import _execute_experiment_run

    stage_dir = tmp_path / "stage-12"
    stage_dir.mkdir()
    stage_10 = tmp_path / "stage-10"
    stage_10.mkdir()
    (stage_10 / plan_file).write_text("# plan\n\nsteps", encoding="utf-8")
    config = _config(**{"experiment.mode": mode})

    result = _execute_experiment_run(
        stage_dir, tmp_path, config, object(), llm=None
    )

    assert result.status.name == "DONE"
    assert captured["prompt"].startswith("# plan")
    run_payload = json.loads((stage_dir / "runs" / "run-1.json").read_text())
    assert run_payload["mode"] == mode
    assert run_payload["status"] == "completed"
    assert run_payload["metrics"] == {"growth_rate": 0.81}
    assert run_payload["workspace"] == f"runs/{workspace}"
    assert run_payload["schema_version"] == 1
    results = json.loads((stage_dir / "runs" / "results.json").read_text())
    assert results["metrics"] == {"growth_rate": 0.81}


def test_ag04_plan_text_is_passed_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan must never be treated as Python source (the old G7 bug)."""
    import researchclaw.experiment.factory as factory

    captured: dict = {}

    class FakeSandbox:
        def run(self, prompt_text: str, *, timeout_sec: int | None = None):
            captured["prompt"] = prompt_text
            return SandboxResult(
                returncode=0,
                stdout="",
                stderr="",
                elapsed_sec=1.0,
                metrics={"p": 0.1},
                timed_out=False,
            )

    monkeypatch.setattr(factory, "create_sandbox", lambda cfg, wd: FakeSandbox())

    from researchclaw.pipeline.stage_impls._execution import _execute_experiment_run

    plan = "# 1. Target\n\nEstimate growth.\n\ndef main():\n    pass\n"
    stage_dir = tmp_path / "stage-12"
    stage_dir.mkdir()
    (tmp_path / "stage-10").mkdir()
    (tmp_path / "stage-10" / "biology_plan.md").write_text(plan, encoding="utf-8")

    config = _config(**{"experiment.mode": "biology_agent"})
    _execute_experiment_run(stage_dir, tmp_path, config, object(), llm=None)

    assert captured["prompt"] == plan


def test_ag03_timeout_without_metrics_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import researchclaw.experiment.factory as factory

    class FakeSandbox:
        def run(self, prompt_text: str, *, timeout_sec: int | None = None):
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr="timed out",
                elapsed_sec=60.0,
                metrics={},
                timed_out=True,
            )

    monkeypatch.setattr(factory, "create_sandbox", lambda cfg, wd: FakeSandbox())

    from researchclaw.pipeline.stage_impls._execution import _execute_experiment_run

    stage_dir = tmp_path / "stage-12"
    stage_dir.mkdir()
    (tmp_path / "stage-10").mkdir()
    (tmp_path / "stage-10" / "stat_plan.md").write_text("# plan", encoding="utf-8")

    config = _config(**{"experiment.mode": "stat_agent"})
    result = _execute_experiment_run(stage_dir, tmp_path, config, object(), llm=None)

    assert result.status.name == "FAILED"
    assert "no usable metrics" in (result.error or "")
    payload = json.loads((stage_dir / "runs" / "run-1.json").read_text())
    assert payload["status"] == "timed_out"
    assert payload["metrics"] == {}


def test_ag03_missing_plan_blocks_upstream(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._execution import _execute_experiment_run

    stage_dir = tmp_path / "stage-12"
    stage_dir.mkdir()
    config = _config(**{"experiment.mode": "biology_agent"})

    result = _execute_experiment_run(stage_dir, tmp_path, config, object(), llm=None)

    assert result.status.name == "FAILED"
    assert result.decision == "upstream_blocked"


def test_ag01_factory_supports_agent_modes(tmp_path: Path) -> None:
    """create_sandbox must not raise Unsupported for biology/stat agents."""
    from researchclaw.experiment.factory import create_sandbox

    for mode in ("biology_agent", "stat_agent"):
        config = _config(**{"experiment.mode": mode})
        sandbox = create_sandbox(config.experiment, tmp_path / mode)
        assert sandbox is not None


def test_ag07_stage13_skips_refine_for_agentic(
    tmp_path: Path,
) -> None:
    from researchclaw.pipeline.stage_impls._execution import _execute_iterative_refine

    stage_dir = tmp_path / "stage-13"
    stage_dir.mkdir()
    stage_12 = tmp_path / "stage-12" / "runs"
    stage_12.mkdir(parents=True)
    (stage_12 / "results.json").write_text("{}", encoding="utf-8")

    config = _config(**{"experiment.mode": "agentic"})
    result = _execute_iterative_refine(
        stage_dir, tmp_path, config, object(), llm=None
    )

    assert result.status.name == "DONE"
    log = json.loads((stage_dir / "refinement_log.json").read_text())
    assert log["skipped"] is True
    assert log["mode"] == "agentic"
    assert (stage_dir / "experiment_final").is_dir()
