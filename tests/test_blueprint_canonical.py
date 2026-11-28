"""P-230 (B-1/B-3): canonical blueprint serialization and JSON twin."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.codegen_evidence import load_blueprint

# Same failure shape as run N: an unquoted ``signature`` value with a colon.
BLUEPRINT = """```yaml
files:
  - name: config.py
    generation_order: 1
  - name: data.py
    generation_order: 2
    functions:
      - name: load
        signature: (config: Config, rng: np.random.Generator) -> dict
```
"""


class _PM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        return SimpleNamespace(system="sys", user="plan", version="test")


class _LLM:
    def __init__(self, content: str):
        self._content = content

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        return SimpleNamespace(
            content=self._content,
            truncated=False,
            finish_reason="stop",
            model="fake",
        )


def test_canonical_blueprint_is_parsable(tmp_path: Path) -> None:
    agent = CodeAgent(
        llm=_LLM(BLUEPRINT),
        prompts=_PM(),
        config=CodeAgentConfig(review_max_rounds=0),
        stage_dir=tmp_path,
    )

    _, blueprint = agent._phase1_blueprint("topic", "plan", "auroc")

    assert blueprint is not None
    reloaded = load_blueprint(tmp_path)
    assert reloaded is not None
    sig = reloaded["files"][1]["functions"][0]["signature"]
    assert "(config: Config" in sig
    assert agent._blueprint_source in {"canonical", "repaired"}
    assert (tmp_path / "architecture_spec.json").is_file()


def test_json_twin_is_used_when_yaml_is_broken(tmp_path: Path) -> None:
    (tmp_path / "architecture_spec.yaml").write_text(
        "files:\n  - name: a.py\n    signature: (x: int) -> str\n",
        encoding="utf-8",
    )
    payload = {"files": [{"name": "a.py", "generation_order": 1}]}
    (tmp_path / "architecture_spec.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )

    loaded = load_blueprint(tmp_path)

    assert loaded == payload


def test_unreadable_blueprint_returns_none(tmp_path: Path) -> None:
    (tmp_path / "architecture_spec.yaml").write_text(
        "files:\n  - name: a.py\n    signature: (x: int) -> str\n",
        encoding="utf-8",
    )
    assert load_blueprint(tmp_path) is None
