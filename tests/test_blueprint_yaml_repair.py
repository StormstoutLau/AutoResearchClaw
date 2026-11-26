"""B-32 M1: blueprint YAML robustness (trailing-colon folding + repair retry)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent, _fold_trailing_colon_items
from researchclaw.pipeline.step_journal import load_steps
from researchclaw.prompts import PromptManager

# Verbatim shape of the B-site failure: a natural-language list item ends
# with a colon and the continuation lines are more indented.
SITE_BODY = """files:
  - name: config.py
    generation_order: 1
  - name: monitor.py
    generation_order: 2
verification_criteria:
  - All condition classes have DIFFERENT core method implementations:
    HiddenStateTauKLMonitor overrides score with tau-rescaled KL;
    FrechetAdjointMonitor overrides score with adjoint C(t) and Frechet distance;
"""

# Unparsable in a way neither the sanitizer nor the folding pass can repair.
UNPARSABLE_BODY = """files:
  - name: config.py
    generation_order: 1
  - name: monitor.py
    generation_order: 2
matrix: [a, b
"""

GOOD_BLUEPRINT = """```yaml
files:
  - name: config.py
    generation_order: 1
  - name: monitor.py
    generation_order: 2
```"""

CODE = '```filename:main.py\nprint("metric: 1.0")\n```'


def _fenced(body: str) -> str:
    return "```yaml\n" + body + "```"


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


def _agent(tmp_path: Path, responses: list[str], **cfg) -> CodeAgent:
    return CodeAgent(
        llm=_FakeLLM(responses),
        prompts=PromptManager(),
        config=CodeAgentConfig(
            review_max_rounds=0, hard_validation=False, **cfg,
        ),
        stage_dir=tmp_path,
    )


class TestFolding:
    def test_trailing_colon_item_is_folded_and_parses(self) -> None:
        lines = [
            "verification_criteria:",
            "  - All condition classes are different:",
            "    Monitor A uses tau-KL;",
            "    Monitor B uses Frechet distance;",
            "  - unrelated plain item",
        ]
        folded = _fold_trailing_colon_items(lines)
        assert folded[1].strip().startswith('- "All condition classes are different:')
        assert "Monitor A uses tau-KL;" in folded[1]
        data = yaml.safe_load("\n".join(folded))
        value = data["verification_criteria"][0]
        assert value.startswith("All condition classes are different:")
        assert "Frechet distance;" in value
        assert data["verification_criteria"][1] == "unrelated plain item"

    def test_trailing_colon_without_continuation(self) -> None:
        folded = _fold_trailing_colon_items(["  - Only a title:"])
        assert folded == ['  - "Only a title:"']

    def test_top_level_mapping_key_is_untouched(self) -> None:
        lines = ["verification_criteria:", "  - ok"]
        assert _fold_trailing_colon_items(lines) == lines

    def test_nested_sequence_is_untouched(self) -> None:
        lines = ["  - item:", "    - sub"]
        assert _fold_trailing_colon_items(lines) == lines

    def test_single_token_key_with_mapping_is_untouched(self) -> None:
        lines = ["  - interface:", "    name: value", "    order: 1"]
        assert _fold_trailing_colon_items(lines) == lines

    def test_sibling_item_stops_folding(self) -> None:
        lines = ["  - first sentence:", "  - second"]
        assert _fold_trailing_colon_items(lines) == ['  - "first sentence:"', "  - second"]


class TestParseBlueprint:
    def test_real_site_snippet_now_parses(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [GOOD_BLUEPRINT])
        blueprint = agent._parse_blueprint(SITE_BODY)
        assert blueprint is not None
        assert len(blueprint["files"]) == 2
        criteria = blueprint["verification_criteria"]
        assert "HiddenStateTauKLMonitor" in criteria[0]


class TestRepairRetry:
    def test_repair_success_replaces_blueprint(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, [_fenced(UNPARSABLE_BODY), GOOD_BLUEPRINT],
        )
        arch, blueprint = agent._phase1_blueprint("topic", "plan", "auroc")
        assert blueprint is not None
        steps = [s for s in load_steps(tmp_path) if s["step_id"] == "blueprint"]
        assert [s["variant"] for s in steps] == ["first", "yaml_repair"]
        on_disk = (tmp_path / "architecture_spec.yaml").read_text(encoding="utf-8")
        assert on_disk == arch
        assert "generation_order" in on_disk

    def test_repair_failure_keeps_first_version(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, [_fenced(UNPARSABLE_BODY), "still not yaml"],
        )
        arch, blueprint = agent._phase1_blueprint("topic", "plan", "auroc")
        assert blueprint is None
        on_disk = (tmp_path / "architecture_spec.yaml").read_text(encoding="utf-8")
        assert on_disk == arch
        assert "matrix: [a, b" in on_disk
        steps = [s for s in load_steps(tmp_path) if s["step_id"] == "blueprint"]
        assert [s["variant"] for s in steps] == ["first"]
        assert agent._codegen_diag["yaml_repair_attempted"] is True


class TestFallbackDecision:
    def test_unparsable_writes_decision_file(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path,
            [_fenced(UNPARSABLE_BODY), "still not yaml", CODE],
        )
        result = agent.generate("topic", "plan", "auroc", "numpy")
        assert result.files
        payload = json.loads(
            (tmp_path / "codegen_decision.json").read_text(encoding="utf-8")
        )
        assert payload["fallback"] == "single_shot"
        assert payload["reason"] == "blueprint_unparsable"
        assert payload["yaml_repair_attempted"] is True
        assert payload["blueprint_chars"] > 0
        assert "at" in payload

    def test_structure_invalid_reason(self, tmp_path: Path) -> None:
        thin = "```yaml\nfiles:\n  - name: config.py\n```"
        agent = _agent(tmp_path, [thin, CODE])
        agent.generate("topic", "plan", "auroc", "numpy")
        payload = json.loads(
            (tmp_path / "codegen_decision.json").read_text(encoding="utf-8")
        )
        assert payload["reason"] == "blueprint_structure_invalid"
        assert payload["yaml_repair_attempted"] is False

    def test_no_decision_when_planning_disabled(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, [CODE], architecture_planning=False,
        )
        agent.generate("topic", "plan", "auroc", "numpy")
        assert not (tmp_path / "codegen_decision.json").exists()
