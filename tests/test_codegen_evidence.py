"""B-32 M2: Stage 10 blueprint/artifact evidence gates."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline.codegen_evidence import (
    check_compute_presence,
    check_data_source,
    check_declared_files,
    check_metric_consistency,
    check_symbol_contract,
    count_compute_units,
    declared_symbols,
    evaluate_stage10_evidence,
    load_blueprint,
    symbol_contract_block,
    write_evidence_report,
)

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

CONFIG_PY = '''from dataclasses import dataclass


@dataclass
class RunConfig:
    seed: int = 0
'''

MONITOR_PY = '''class Monitor:
    def score(self, values):
        return sum(values) / len(values)
'''

CONFIG_ONLY_MAIN = '''from config import RunConfig

METRIC = "auroc_delta"


def main() -> None:
    cfg = RunConfig()
    print("METRIC_DEF: auroc_delta | direction=higher")
    print(f"config dims: {cfg.seed}")


if __name__ == "__main__":
    main()
'''


def _write_blueprint(stage_dir: Path, text: str = BLUEPRINT) -> None:
    (stage_dir / "architecture_spec.yaml").write_text(text, encoding="utf-8")


def _files(**overrides: str) -> dict[str, str]:
    base = {
        "config.py": CONFIG_PY,
        "monitor.py": MONITOR_PY,
        "main.py": MAIN_OK,
    }
    base.update(overrides)
    return base


class TestDeclaredFiles:
    def test_all_present(self, tmp_path: Path) -> None:
        assert check_declared_files(load_blueprint(_bp(tmp_path)), _files()) == []

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        files = {"config.py": CONFIG_PY, "main.py": MAIN_OK}
        failures = check_declared_files(load_blueprint(_bp(tmp_path)), files)
        assert [f.code for f in failures] == ["blueprint_files_missing"]
        assert "monitor.py" in failures[0].detail

    def test_optional_file_may_be_missing(self, tmp_path: Path) -> None:
        text = BLUEPRINT.replace(
            "  - name: monitor.py\n    generation_order: 2",
            "  - name: monitor.py\n    generation_order: 2\n    optional: true",
        )
        blueprint = load_blueprint(_bp(tmp_path, text))
        files = {"config.py": CONFIG_PY, "main.py": MAIN_OK}
        assert check_declared_files(blueprint, files) == []

    def test_files_as_mapping(self, tmp_path: Path) -> None:
        text = "files:\n  config.py:\n    generation_order: 1\n"
        blueprint = load_blueprint(_bp(tmp_path, text))
        assert check_declared_files(blueprint, {"config.py": CONFIG_PY}) == []


class TestMetricGate:
    def test_match(self) -> None:
        assert check_metric_consistency("auroc_delta", _files()) == []

    def test_mismatch(self) -> None:
        failures = check_metric_consistency("auroc_delta", _files())
        assert failures == []
        bad = _files(**{"main.py": MAIN_OK.replace("auroc_delta", "window_f1")})
        codes = [f.code for f in check_metric_consistency("auroc_delta", bad)]
        assert codes == ["metric_mismatch"]

    def test_missing_metric_def(self) -> None:
        bad = _files(**{"main.py": "print('hello')\n"})
        codes = [f.code for f in check_metric_consistency("auroc_delta", bad)]
        assert codes == ["metric_not_printed"]

    def test_no_declared_metric_is_skipped(self) -> None:
        assert check_metric_consistency("", _files()) == []


class TestDataSourceGate:
    def test_source_present(self, tmp_path: Path) -> None:
        files = _files(**{"data.py": "import yfinance as yf\n"})
        warnings, synthetic = check_data_source(load_blueprint(_bp(tmp_path)), files)
        assert warnings == [] and synthetic is False

    def test_source_missing_with_synthetic_data(self, tmp_path: Path) -> None:
        files = _files(**{"data.py": "import numpy as np\nx = np.random.default_rng(0)\n"})
        warnings, synthetic = check_data_source(load_blueprint(_bp(tmp_path)), files)
        assert warnings and synthetic is True


class TestComputeGate:
    def test_monitor_counts(self) -> None:
        assert count_compute_units(_files()) >= 1
        assert check_compute_presence(_files()) == []

    def test_config_only_fails(self) -> None:
        files = {"config.py": CONFIG_PY, "main.py": CONFIG_ONLY_MAIN}
        assert count_compute_units(files) == 0
        assert [f.code for f in check_compute_presence(files)] == ["no_compute_unit"]


class TestEvaluate:
    def test_all_green(self, tmp_path: Path) -> None:
        report = evaluate_stage10_evidence(
            stage_dir=_bp(tmp_path),
            files=_files(**{"data.py": "import yfinance as yf\n"}),
            metric="auroc_delta",
        )
        assert report.ok
        assert report.warnings == [] and report.synthetic_data is False

    def test_config_only_delivery_fails(self, tmp_path: Path) -> None:
        report = evaluate_stage10_evidence(
            stage_dir=_bp(tmp_path),
            files={"config.py": CONFIG_PY, "main.py": CONFIG_ONLY_MAIN},
            metric="auroc_delta",
        )
        assert not report.ok
        codes = {f.code for f in report.failures}
        assert "no_compute_unit" in codes
        assert "blueprint_files_missing" in codes

    def test_missing_blueprint_fails_closed(self, tmp_path: Path) -> None:
        report = evaluate_stage10_evidence(
            stage_dir=tmp_path,
            files={"config.py": CONFIG_PY, "main.py": CONFIG_ONLY_MAIN},
            metric="auroc_delta",
        )
        codes = [f.code for f in report.failures]
        assert "blueprint_unavailable" in codes
        assert "no_compute_unit" in codes
        assert not report.ok

    def test_stage_metric_is_used_when_blueprint_has_none(self, tmp_path: Path) -> None:
        _write_blueprint(tmp_path, "files:\n  - name: main.py\n    generation_order: 1\n")
        report = evaluate_stage10_evidence(
            stage_dir=tmp_path, files=_files(), metric="window_f1",
        )
        codes = [f.code for f in report.failures]
        assert "metric_mismatch" in codes

    def test_report_is_written(self, tmp_path: Path) -> None:
        _bp(tmp_path)
        report = evaluate_stage10_evidence(
            stage_dir=tmp_path, files=_files(), metric="auroc_delta",
        )
        path = write_evidence_report(tmp_path, report)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["ok"] is True
        assert payload["failures"] == []
        assert "at" in payload


def _bp(stage_dir: Path, text: str = BLUEPRINT) -> Path:
    _write_blueprint(stage_dir, text)
    return stage_dir


class TestDeclaredSymbolIdentifiers:
    """P-232: only identifiers can be symbols (guard block is not one)."""

    BP = {
        "files": [{
            "name": "main.py",
            "generation_order": 1,
            "functions": [
                {"name": "main", "signature": "() -> None"},
                {"name": 'if __name__ == "__main__"', "signature": "()"},
            ],
        }],
    }

    def test_pseudo_symbol_is_ignored(self) -> None:
        assert declared_symbols(self.BP, "main.py") == ["main"]

    def test_contract_does_not_require_guard_block(self) -> None:
        code = (
            "def main() -> None:\n"
            "    print('METRIC_DEF: auroc')\n"
            "\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        assert check_symbol_contract(self.BP, {"main.py": code}) == []

    def test_block_lists_only_identifiers(self) -> None:
        block = symbol_contract_block(self.BP)
        assert "main" in block
        assert "__main__" not in block


class TestSymbolContractBlock:
    """P-231 (D-2): the prompt block names what each file must define."""

    BP = {
        "files": [
            {"name": "data.py", "generation_order": 1,
             "symbols": ["load", "build"]},
            {"name": "main.py", "generation_order": 2, "symbols": ["main"]},
        ],
    }

    def test_marks_defined_and_missing(self) -> None:
        block = symbol_contract_block(
            self.BP, {"data.py": "def load():\n    return 1\n"},
        )
        assert "load (defined)" in block
        assert "build (MISSING)" in block

    def test_limit_files(self) -> None:
        block = symbol_contract_block(self.BP, limit_files={"main.py"})
        assert "main.py" in block
        assert "data.py" not in block

    def test_without_files_lists_names_only(self) -> None:
        block = symbol_contract_block(self.BP)
        assert "- main.py: main" in block
        assert "MISSING" not in block

    def test_char_budget_truncates(self) -> None:
        block = symbol_contract_block(self.BP, max_chars=10)
        assert "truncated" in block

    def test_no_blueprint_is_empty(self) -> None:
        assert symbol_contract_block(None) == ""
