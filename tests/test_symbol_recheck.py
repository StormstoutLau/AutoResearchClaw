"""P-229: symbol contract re-check after late entrypoint/alignment rewrites."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from researchclaw.pipeline.repair_trace import load as load_repair_trace
from researchclaw.pipeline.stage_impls._code_generation import (
    _ensure_symbol_contract,
)

BLUEPRINT = """files:
  - name: main.py
    generation_order: 1
    symbols: [set_seed, train_model]
  - name: data.py
    generation_order: 2
    symbols: [load_data]
"""

BROKEN_MAIN = '''def main() -> None:
    print("METRIC_DEF: auroc_delta")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''

FIXED_MAIN = '''def set_seed(seed: int) -> None:
    import random

    random.seed(seed)


def train_model() -> None:
    return None


def main() -> None:
    print("METRIC_DEF: auroc_delta")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''

DATA = "def load_data():\n    return 1\n"


class _PM:
    def system(self, name):  # noqa: ANN001
        return "sys"


class _LLM:
    def __init__(self, content: str, truncated: bool = False):
        self._content = content
        self._truncated = truncated
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        return SimpleNamespace(
            content=self._content,
            truncated=self._truncated,
            finish_reason="length" if self._truncated else "stop",
            model="fake",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )


def _stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage-10"
    (stage / "experiment").mkdir(parents=True)
    (stage / "architecture_spec.yaml").write_text(BLUEPRINT, encoding="utf-8")
    return stage


def _reply(name: str, code: str) -> str:
    return f"```filename:{name}\n{code}```\n"


def test_recheck_repairs_missing_symbols(tmp_path: Path) -> None:
    stage = _stage(tmp_path)
    llm = _LLM(_reply("main.py", FIXED_MAIN))

    out = _ensure_symbol_contract(
        {"main.py": BROKEN_MAIN, "data.py": DATA},
        stage_dir=stage,
        exp_dir=stage / "experiment",
        llm=llm,
        pm=_PM(),
        topic="t",
    )

    assert "def set_seed" in out["main.py"]
    assert "def train_model" in out["main.py"]
    assert out["data.py"] == DATA
    written = (stage / "experiment" / "main.py").read_text(encoding="utf-8")
    assert written.strip() == FIXED_MAIN.strip()
    row = load_repair_trace(stage)[-1]
    assert row["phase"] == "symbol_contract"
    assert row["reason"] == "repaired"
    assert row["accepted"] == ["main.py"]


def test_recheck_keeps_original_when_repair_fails(tmp_path: Path) -> None:
    stage = _stage(tmp_path)
    llm = _LLM(_reply("main.py", BROKEN_MAIN))
    files = {"main.py": BROKEN_MAIN, "data.py": DATA}

    out = _ensure_symbol_contract(
        dict(files),
        stage_dir=stage,
        exp_dir=stage / "experiment",
        llm=llm,
        pm=_PM(),
        topic="t",
    )

    assert out == files
    assert load_repair_trace(stage)[-1]["reason"] == "still_missing"
    assert not (stage / "experiment" / "main.py").exists()


def test_no_blueprint_is_a_noop(tmp_path: Path) -> None:
    stage = tmp_path / "stage-10"
    stage.mkdir()
    llm = _LLM(_reply("main.py", FIXED_MAIN))

    out = _ensure_symbol_contract(
        {"main.py": BROKEN_MAIN},
        stage_dir=stage,
        exp_dir=stage / "experiment",
        llm=llm,
        pm=_PM(),
        topic="t",
    )

    assert out == {"main.py": BROKEN_MAIN}
    assert llm.calls == []


def test_truncated_reply_escalates_budget(tmp_path: Path) -> None:
    stage = _stage(tmp_path)
    llm = _LLM(_reply("main.py", FIXED_MAIN), truncated=True)

    _ensure_symbol_contract(
        {"main.py": BROKEN_MAIN, "data.py": DATA},
        stage_dir=stage,
        exp_dir=stage / "experiment",
        llm=llm,
        pm=_PM(),
        topic="t",
    )

    assert [c["max_tokens"] for c in llm.calls] == [16384, 32768]
