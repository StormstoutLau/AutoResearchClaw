"""T01 — orchestration task corpus shape, sources and validation (P-162)."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.tasks import (  # noqa: E402
    TASK_ORDER,
    load_task,
    load_tasks,
    validate_task,
)


def test_corpus_shape() -> None:
    tasks = load_tasks()
    assert [t.id for t in tasks] == list(TASK_ORDER)
    assert Counter(t.cls for t in tasks) == Counter({"D": 4, "L": 4, "A": 4, "C": 3})
    assert len({t.id for t in tasks}) == 15


def test_sources_exist_and_validate_clean() -> None:
    for task in load_tasks():
        assert (REPO_ROOT / task.source_manifest).is_file(), task.id
        assert validate_task(task) == [], task.id
        assert len(task.subgoals) >= 2, task.id
        if task.cls != "C":
            assert len(task.subgoals) >= 3, task.id


def test_public_prompt_does_not_leak_split_strategy() -> None:
    banned = ("split into", "sub-agent", "worker", "parallel")
    for task in load_tasks():
        if task.cls == "C":
            continue
        lowered = task.prompt.lower()
        for token in banned:
            assert token not in lowered, (task.id, token)


def test_bad_json_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "D1.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_task("D1", tasks_dir=tmp_path)


def test_unknown_task_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_task("Z9", tasks_dir=tmp_path)
