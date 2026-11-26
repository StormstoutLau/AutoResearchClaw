"""B-34 (P-207): module extraction fallback and evidence-gate false positives.

Each class maps to one item of the B-34 scope registered in
``arc-master-roadmap.md`` §3.2:

* ``TestM1aFenceFallback``   — truncated-but-complete responses lost the code
* ``TestM1bExplicitFailure`` — 32768 still truncated / empty must fail loudly
* ``TestF1F5Comments``       — comments must not satisfy the data-source gate
* ``TestF2ConfigSuffix``     — a ``*Config`` class with real methods is compute
* ``TestF3MetricDelimiters`` — names with ``()`` / ``[]`` / ``{}`` keep whole
* ``TestF4BoolLeaf``         — ``bool`` leaves are ignored explicitly
* ``TestF6VersionFallback``  — a silent version fallback becomes observable
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.codegen_evidence import (
    _leaf_strings,
    check_data_source,
    count_compute_units,
    entrypoint_metric_name,
)
from researchclaw.pipeline.step_journal import code_version, load_steps

BLUEPRINT_SOURCE = {
    "files": [{"name": "main.py", "generation_order": 1}],
    "data": {"source": "yfinance"},
}


def _resp(content: str, *, truncated: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        truncated=truncated,
        finish_reason="length" if truncated else "stop",
        model="fake-model",
        total_tokens=0,
    )


class _FakePM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        return SimpleNamespace(system="", user="", version="test")

    def for_stage(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return SimpleNamespace(system="", user="", version="test")

    def system(self, name):  # noqa: ANN001
        return ""


def _agent(tmp_path: Path) -> CodeAgent:
    return CodeAgent(
        llm=None,
        prompts=_FakePM(),
        config=CodeAgentConfig(
            review_max_rounds=0, hard_validation=False, exec_fix_max_iterations=0,
        ),
        stage_dir=tmp_path,
    )


class TestM1aFenceFallback:
    """M1-a: a response that forgot its closing fence is still extractable."""

    def test_unclosed_fence_is_extracted(self) -> None:
        content = "```python\nimport numpy as np\n\nX = np.zeros(3)\n"
        code = CodeAgent._extract_single_file_code(content, "data.py")
        assert code.startswith("import numpy as np")
        assert "X = np.zeros(3)" in code

    def test_closed_fence_is_unchanged(self) -> None:
        content = "```python\nX = 1\n```\n"
        assert CodeAgent._extract_single_file_code(content, "data.py") == "X = 1"

    def test_unfenced_valid_python_is_still_accepted(self) -> None:
        assert CodeAgent._extract_single_file_code("X = 1\n", "data.py") == "X = 1"

    def test_conversational_reply_is_still_rejected(self) -> None:
        assert CodeAgent._extract_single_file_code("Same, no change.\n", "d.py") == ""


class TestM1bExplicitFailure:
    """M1-b: no silent ``continue`` once escalation did not help."""

    def _run(self, agent: CodeAgent, blueprint: dict) -> None:
        from researchclaw.pipeline.code_agent import ModuleExtractionError

        with pytest.raises(ModuleExtractionError):
            agent._phase2_sequential_generate(
                topic="t", exp_plan="p", metric="m",
                pkg_hint="", arch_spec="", blueprint=blueprint,
            )

    def test_still_truncated_after_escalation_fails_fast(
        self, tmp_path: Path,
    ) -> None:
        agent = _agent(tmp_path)
        calls: list[int] = []

        def fake_chat(system, user, max_tokens=8192):  # noqa: ANN001
            calls.append(max_tokens)
            return _resp("```python\nX = 1\n", truncated=True)

        agent._chat = fake_chat  # type: ignore[assignment]
        blueprint = {"files": [
            {"name": "config.py", "generation_order": 1},
            {"name": "data.py", "generation_order": 2},
        ]}
        self._run(agent, blueprint)

        # Fail fast: the second module is never requested.
        assert calls == [8192, 32768]
        steps = load_steps(tmp_path)
        assert [
            (s["step_id"], s["variant"], s["status"]) for s in steps
        ] == [("generate_file", "config.py", "failed")]
        assert steps[0]["truncated"] is True
        assert agent._codegen_diag["module_failures"][0]["file"] == "config.py"

    def test_empty_response_fails_without_escalation(
        self, tmp_path: Path,
    ) -> None:
        agent = _agent(tmp_path)
        calls: list[int] = []

        def fake_chat(system, user, max_tokens=8192):  # noqa: ANN001
            calls.append(max_tokens)
            return _resp("Same, no change.\n")

        agent._chat = fake_chat  # type: ignore[assignment]
        self._run(agent, {"files": [{"name": "data.py", "generation_order": 1}]})
        assert calls == [8192]
        steps = load_steps(tmp_path)
        assert steps[0]["variant"] == "data.py"
        assert steps[0]["truncated"] is False


class TestF1F5Comments:
    """F-1/F-5: comments are not evidence."""

    def test_comment_only_mention_does_not_satisfy_source(self) -> None:
        warnings, synthetic = check_data_source(
            BLUEPRINT_SOURCE, {"data.py": "# yfinance is planned\nX = 1\n"},
        )
        assert warnings
        assert synthetic is False

    def test_string_literal_still_satisfies_source(self) -> None:
        warnings, synthetic = check_data_source(
            BLUEPRINT_SOURCE, {"data.py": 'SOURCE = "yfinance"\n'},
        )
        assert warnings == []
        assert synthetic is False

    def test_comment_random_is_not_synthetic(self) -> None:
        warnings, synthetic = check_data_source(
            BLUEPRINT_SOURCE,
            {"data.py": "# np.random is deliberately avoided\nimport pandas as pd\n"},
        )
        assert warnings
        assert synthetic is False

    def test_real_random_is_synthetic(self) -> None:
        warnings, synthetic = check_data_source(
            BLUEPRINT_SOURCE,
            {"data.py": "import numpy as np\nx = np.random.rand(3)\n"},
        )
        assert warnings
        assert synthetic is True

    def test_unparsable_file_falls_back_to_raw_text(self) -> None:
        # Fail-open on tokenizer errors: no stripping, old behaviour.
        warnings, synthetic = check_data_source(
            BLUEPRINT_SOURCE, {"data.py": "def broken(:\n# yfinance\n"},
        )
        assert warnings == []
        assert synthetic is False


class TestF2ConfigSuffix:
    """F-2: the ``*Config`` suffix must not exempt real behaviour."""

    def test_config_suffix_with_real_method_counts(self) -> None:
        code = "class KernelConfig:\n    def compute(self, x):\n        return x * 2\n"
        assert count_compute_units({"kernel.py": code}) == 1

    def test_declarative_config_still_excluded(self) -> None:
        code = (
            "class RunConfig:\n"
            "    seed: int = 0\n"
            "\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        assert count_compute_units({"config.py": code}) == 0

    def test_docstring_only_method_still_excluded(self) -> None:
        code = (
            "class RunConfig:\n"
            "    def describe(self):\n"
            '        """Return nothing useful."""\n'
        )
        assert count_compute_units({"config.py": code}) == 0

    def test_regular_class_still_counts(self) -> None:
        code = "class Monitor:\n    def score(self, xs):\n        return sum(xs)\n"
        assert count_compute_units({"monitor.py": code}) == 1


class TestF3MetricDelimiters:
    """F-3: names with balanced delimiters must survive the regex."""

    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            ("auroc(delta)", "auroc(delta)"),
            ("hit@k[5]", "hit@k[5]"),
            ("auroc{0.5}", "auroc{0.5}"),
            ("50%-winrate", "50%-winrate"),
            ("auroc_delta", "auroc_delta"),
        ],
    )
    def test_metric_name_is_kept_whole(self, printed: str, expected: str) -> None:
        code = f'print("METRIC_DEF: {printed} | direction=higher")\n'
        assert entrypoint_metric_name(code) == expected

    def test_separator_still_stops_the_capture(self) -> None:
        code = 'print("METRIC_DEF: auroc_delta | direction=higher")\n'
        assert entrypoint_metric_name(code) == "auroc_delta"


class TestF4BoolLeaf:
    """F-4: ``bool`` leaves are flags, not source names."""

    def test_bool_leaf_is_ignored_explicitly(self) -> None:
        assert _leaf_strings(True) == []
        assert _leaf_strings(False) == []

    def test_bool_does_not_hide_sibling_leaves(self) -> None:
        assert _leaf_strings([True, "yfinance"]) == ["yfinance"]


class TestF6VersionFallback:
    """F-6: a missing package version is observable at DEBUG level."""

    def test_code_version_fallback_is_logged(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        import researchclaw

        monkeypatch.delattr(researchclaw, "__version__")
        with caplog.at_level(
            logging.DEBUG, logger="researchclaw.pipeline.step_journal",
        ):
            version = code_version()
        assert version.startswith("0+")
        assert "code_version" in caplog.text
