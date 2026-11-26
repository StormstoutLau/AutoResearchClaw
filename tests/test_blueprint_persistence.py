"""B-33 N-1: the blueprint is persisted (and journalled) before Phase 2 runs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.step_journal import load_steps
from researchclaw.prompts import PromptManager

BLUEPRINT = """```yaml
files:
  - name: config.py
    generation_order: 1
  - name: train.py
    generation_order: 2
```"""

NOT_YAML = "This is a prose answer, not a blueprint."


class _FakeLLM:
    def __init__(self, responses: list[tuple[str, bool]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        content, truncated = self._responses[idx]
        return SimpleNamespace(
            content=content,
            truncated=truncated,
            finish_reason="length" if truncated else "stop",
            total_tokens=0,
        )


def _agent(tmp_path: Path, responses: list[tuple[str, bool]]) -> CodeAgent:
    return CodeAgent(
        llm=_FakeLLM(responses),
        prompts=PromptManager(),
        config=CodeAgentConfig(),
        stage_dir=tmp_path,
    )


class TestBlueprintPersistence:
    def test_artifact_written_on_success(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(BLUEPRINT, False)])
        arch, blueprint = agent._phase1_blueprint("topic", "plan", "accuracy")
        assert blueprint is not None
        assert (tmp_path / "architecture_spec.yaml").is_file()
        on_disk = (tmp_path / "architecture_spec.yaml").read_text(encoding="utf-8")
        assert on_disk == arch

    def test_artifact_written_even_when_yaml_is_bad(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(NOT_YAML, False)])
        arch, blueprint = agent._phase1_blueprint("topic", "plan", "accuracy")
        assert blueprint is None
        assert (tmp_path / "architecture_spec.yaml").read_text(
            encoding="utf-8"
        ) == arch

    def test_step_is_journalled_with_variant_first(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(BLUEPRINT, False)])
        agent._phase1_blueprint("topic", "plan", "accuracy")
        steps = [s for s in load_steps(tmp_path) if s["step_id"] == "blueprint"]
        assert len(steps) == 1
        assert steps[0]["variant"] == "first"
        assert steps[0]["status"] == "done"
        assert "architecture_spec.yaml" in steps[0]["outputs"]

    def test_truncated_retry_is_tagged(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(BLUEPRINT, True), (BLUEPRINT, False)])
        agent._phase1_blueprint("topic", "plan", "accuracy")
        steps = [s for s in load_steps(tmp_path) if s["step_id"] == "blueprint"]
        assert [s["variant"] for s in steps] == ["retry"]
        assert len(agent._llm.calls) == 2

    def test_no_temp_file_left(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(BLUEPRINT, False)])
        agent._phase1_blueprint("topic", "plan", "accuracy")
        assert not list(tmp_path.glob("architecture_spec.yaml.tmp"))

    def test_journal_body_contains_no_spec_text(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, [(BLUEPRINT, False)])
        agent._phase1_blueprint("topic", "plan", "accuracy")
        raw = (tmp_path / "steps.jsonl").read_text(encoding="utf-8")
        assert "generation_order" not in raw
