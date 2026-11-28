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


class _SeqLLM:
    """One reply per call (P-231 per-file requests)."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        idx = min(len(self.calls), len(self._contents) - 1)
        self.calls.append({"messages": messages, **kwargs})
        return SimpleNamespace(
            content=self._contents[idx],
            truncated=False,
            finish_reason="stop",
            model="fake",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )


TWO_FILE_BLUEPRINT = """files:
  - name: main.py
    generation_order: 1
    symbols: [set_seed]
  - name: data.py
    generation_order: 2
    symbols: [load_data, build_features]
"""

BROKEN_MAIN_ONE = '''def main() -> None:
    print("METRIC_DEF: auroc_delta")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''

FIXED_MAIN_ONE = '''def set_seed(seed: int) -> None:
    import random

    random.seed(seed)


def main() -> None:
    print("METRIC_DEF: auroc_delta")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''

PARTIAL_DATA = "def load_data():\n    return 1\n"

FIXED_DATA = (
    "def load_data():\n"
    "    return 1\n"
    "\n\n"
    "def build_features():\n"
    "    return 2\n"
)


def test_one_request_per_affected_file(tmp_path: Path) -> None:
    """P-231 (D-3): never ask for every affected file in one reply."""
    stage = tmp_path / "stage-10"
    (stage / "experiment").mkdir(parents=True)
    (stage / "architecture_spec.yaml").write_text(
        TWO_FILE_BLUEPRINT, encoding="utf-8",
    )
    llm = _SeqLLM([
        _reply("data.py", FIXED_DATA),
        _reply("main.py", FIXED_MAIN_ONE),
    ])

    out = _ensure_symbol_contract(
        {"main.py": BROKEN_MAIN_ONE, "data.py": PARTIAL_DATA},
        stage_dir=stage,
        exp_dir=stage / "experiment",
        llm=llm,
        pm=_PM(),
        topic="t",
    )

    assert len(llm.calls) == 2
    first_prompt = llm.calls[0]["messages"][0]["content"]
    assert "## Missing in `data.py`" in first_prompt
    assert "```filename:data.py" in first_prompt
    assert "def build_features" in out["data.py"]
    assert "def set_seed" in out["main.py"]
    rows = [r for r in load_repair_trace(stage) if r["phase"] == "symbol_contract"]
    assert {row["file"] for row in rows} == {"data.py", "main.py"}
