"""P-202: hardening of the Stage 10 evidence gates (F-1..F-4 + N-1).

Each class maps to one boundary registered in
``spec/arc-stage10-blueprint-yaml-robust/DESIGN.md`` §5.1.
"""

from __future__ import annotations

from pathlib import Path

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent, _fold_trailing_colon_items
from researchclaw.pipeline.codegen_evidence import (
    check_data_source,
    check_metric_consistency,
    entrypoint_metric_name,
    evaluate_stage10_evidence,
    load_blueprint,
)
from researchclaw.pipeline.step_journal import load_steps
from researchclaw.prompts import PromptManager
from types import SimpleNamespace

BLUEPRINT = """files:
  - name: config.py
    generation_order: 1
  - name: monitor.py
    generation_order: 2
primary_metric: auroc_delta
data:
  source: yfinance
"""

MAIN_OK = '''from config import Config

METRIC = "auroc_delta"


def main() -> None:
    print("METRIC_DEF: auroc_delta | direction=higher | desc=test")
    print("auroc_delta: 0.71")


if __name__ == "__main__":
    main()
'''

CONFIG_PY = '''class RunConfig:
    seed: int = 0
'''

MONITOR_PY = '''class Monitor:
    def score(self, values):
        return sum(values) / len(values)
'''

UNFENCED_REPAIR = """Sure, I fixed the indentation and the quoting.

files:
  - name: config.py
    generation_order: 1
  - name: monitor.py
    generation_order: 2
"""


def _files(**overrides: str) -> dict[str, str]:
    base = {
        "config.py": CONFIG_PY,
        "monitor.py": MONITOR_PY,
        "main.py": MAIN_OK,
        "data.py": "import yfinance as yf\n",
    }
    base.update(overrides)
    return base


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return SimpleNamespace(
            content=self._responses[idx],
            truncated=False,
            finish_reason="stop",
            total_tokens=0,
        )


class TestF1MetricExtraction:
    """F-1: the metric name must come from what is printed, not from prose."""

    def test_comment_is_not_mistaken_for_the_metric(self) -> None:
        code = '# METRIC_DEF: old_metric\nprint("METRIC_DEF: auroc_delta")\n'
        assert entrypoint_metric_name(code) == "auroc_delta"

    def test_docstring_is_not_mistaken_for_the_metric(self) -> None:
        code = ('"""Prints METRIC_DEF: stale_name for legacy runs."""\n'
                'print("METRIC_DEF: auroc_delta")\n')
        assert entrypoint_metric_name(code) == "auroc_delta"

    def test_name_with_percent_and_colon_is_kept_whole(self) -> None:
        code = 'print("METRIC_DEF: 50%-winrate | direction=higher")\n'
        assert entrypoint_metric_name(code) == "50%-winrate"

    def test_fallback_skips_comment_lines(self) -> None:
        code = '# METRIC_DEF: old_metric\nBANNER = "METRIC_DEF: window_f1"\n'
        assert entrypoint_metric_name(code) == "window_f1"

    def test_missing_metric_still_returns_empty(self) -> None:
        assert entrypoint_metric_name('print("hello")\n') == ""

    def test_comment_cannot_hijack_consistency_gate(self) -> None:
        code = ('# METRIC_DEF: window_f1\n'
                'print("METRIC_DEF: auroc_delta")\n')
        failures = check_metric_consistency(
            "auroc_delta", {"main.py": code},
        )
        assert failures == []


class TestF2DataSourceLeaves:
    """F-2: extract leaf strings, never ``str(dict)`` / ``str(list)``."""

    def test_sources_from_list_of_dicts(self, tmp_path: Path) -> None:
        (tmp_path / "architecture_spec.yaml").write_text(
            "files:\n  - name: main.py\n    generation_order: 1\n"
            "data:\n  sources:\n    - provider: yfinance\n",
            encoding="utf-8",
        )
        blueprint = load_blueprint(tmp_path)
        warnings, synthetic = check_data_source(blueprint, _files())
        assert warnings == []
        assert synthetic is False

    def test_sources_from_nested_dict(self, tmp_path: Path) -> None:
        (tmp_path / "architecture_spec.yaml").write_text(
            "files:\n  - name: main.py\n    generation_order: 1\n"
            "data:\n  sources:\n    primary:\n      provider: yfinance\n",
            encoding="utf-8",
        )
        blueprint = load_blueprint(tmp_path)
        warnings, _ = check_data_source(blueprint, _files())
        assert warnings == []

    def test_missing_source_still_warns(self, tmp_path: Path) -> None:
        (tmp_path / "architecture_spec.yaml").write_text(
            "files:\n  - name: main.py\n    generation_order: 1\n"
            "data:\n  source: yfinance\n",
            encoding="utf-8",
        )
        blueprint = load_blueprint(tmp_path)
        files = _files(**{"data.py": "import numpy as np\nx = np.random.rand(3)\n"})
        warnings, synthetic = check_data_source(blueprint, files)
        assert warnings and synthetic is True

    def test_no_repr_artefact_in_warning_text(self, tmp_path: Path) -> None:
        (tmp_path / "architecture_spec.yaml").write_text(
            "files:\n  - name: main.py\n    generation_order: 1\n"
            "data:\n  sources:\n    - provider: yfinance\n",
            encoding="utf-8",
        )
        blueprint = load_blueprint(tmp_path)
        files = _files(**{"data.py": "import numpy as np\n"})
        warnings, _ = check_data_source(blueprint, files)
        assert warnings
        assert "'provider'" not in warnings[0]


class TestF3FoldingGuards:
    """F-3: a mapping is not prose."""

    def test_multiword_key_with_mapping_is_not_folded(self) -> None:
        lines = ["  - some key:", "    nested: value", "    order: 1"]
        assert _fold_trailing_colon_items(lines) == lines

    def test_mapping_value_ending_with_colon_is_not_folded(self) -> None:
        lines = ["  - name: foo bar:"]
        assert _fold_trailing_colon_items(lines) == lines

    def test_prose_still_folds(self) -> None:
        lines = [
            "  - All condition classes are DIFFERENT:",
            "    Monitor A uses tau-KL;",
        ]
        folded = _fold_trailing_colon_items(lines)
        assert folded == ['  - "All condition classes are DIFFERENT: Monitor A uses tau-KL;"']

    def test_folded_prose_parses_as_string(self) -> None:
        import yaml

        lines = _fold_trailing_colon_items(
            ["criteria:", "  - All classes differ:", "    Monitor A uses tau-KL;"]
        )
        data = yaml.safe_load("\n".join(lines))
        assert isinstance(data["criteria"][0], str)
        assert "Monitor A uses tau-KL" in data["criteria"][0]


class TestF4UnfencedRepair:
    """F-4: prose without a trailing colon must not break the repair."""

    def _agent(self, tmp_path: Path, responses: list[str]) -> CodeAgent:
        return CodeAgent(
            llm=_FakeLLM(responses),
            prompts=PromptManager(),
            config=CodeAgentConfig(
                review_max_rounds=0, hard_validation=False,
            ),
            stage_dir=tmp_path,
        )

    def test_unfenced_repair_is_realigned_to_files_key(self, tmp_path: Path) -> None:
        agent = self._agent(tmp_path, ["not yaml at all", UNFENCED_REPAIR])
        arch, blueprint = agent._phase1_blueprint("topic", "plan", "auroc_delta")
        assert blueprint is not None
        assert len(blueprint["files"]) == 2
        steps = [s for s in load_steps(tmp_path) if s["step_id"] == "blueprint"]
        assert [s["variant"] for s in steps] == ["first", "yaml_repair"]
        assert "Sure, I fixed" not in arch

    def test_fenced_repair_is_unchanged(self, tmp_path: Path) -> None:
        fenced = "```yaml\nfiles:\n  - name: a.py\n    generation_order: 1\n" \
                 "  - name: b.py\n    generation_order: 2\n```"
        agent = self._agent(tmp_path, ["not yaml", fenced])
        _, blueprint = agent._phase1_blueprint("topic", "plan", "m")
        assert blueprint is not None
        assert [f["name"] for f in blueprint["files"]] == ["a.py", "b.py"]


class TestN1DeliveredFromDisk:
    """N-1: the gate must judge what is actually written to ``experiment/``."""

    def test_disk_main_py_is_used_when_absent_from_the_mapping(
        self, tmp_path: Path,
    ) -> None:
        stage_dir = tmp_path / "stage-10"
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True)
        (stage_dir / "architecture_spec.yaml").write_text(BLUEPRINT, encoding="utf-8")
        (exp_dir / "main.py").write_text(MAIN_OK, encoding="utf-8")
        (exp_dir / "config.py").write_text(CONFIG_PY, encoding="utf-8")
        (exp_dir / "monitor.py").write_text(MONITOR_PY, encoding="utf-8")
        (exp_dir / "data.py").write_text("import yfinance as yf\n", encoding="utf-8")

        report = evaluate_stage10_evidence(
            stage_dir=stage_dir,
            files={},
            metric="auroc_delta",
            delivered_dir=exp_dir,
        )
        codes = [f.code for f in report.failures]
        assert "metric_not_printed" not in codes
        assert "blueprint_files_missing" not in codes
        assert "no_compute_unit" not in codes

    def test_mapping_still_used_without_delivered_dir(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        stage_dir.mkdir()
        (stage_dir / "architecture_spec.yaml").write_text(BLUEPRINT, encoding="utf-8")
        report = evaluate_stage10_evidence(
            stage_dir=stage_dir, files=_files(), metric="auroc_delta",
        )
        assert report.ok

    def test_disk_wins_over_stale_mapping(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True)
        (stage_dir / "architecture_spec.yaml").write_text(BLUEPRINT, encoding="utf-8")
        (exp_dir / "main.py").write_text(MAIN_OK, encoding="utf-8")
        (exp_dir / "config.py").write_text(CONFIG_PY, encoding="utf-8")
        (exp_dir / "monitor.py").write_text(MONITOR_PY, encoding="utf-8")
        (exp_dir / "data.py").write_text("import yfinance as yf\n", encoding="utf-8")

        stale = {"main.py": 'print("no metric here")\n'}
        report = evaluate_stage10_evidence(
            stage_dir=stage_dir, files=stale, metric="auroc_delta",
            delivered_dir=exp_dir,
        )
        assert report.ok
