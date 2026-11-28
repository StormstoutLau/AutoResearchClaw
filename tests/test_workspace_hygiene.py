"""P-227 (F-1/F-3): experiment workspace hygiene helpers."""

from __future__ import annotations

from pathlib import Path

from researchclaw.pipeline.stage_impls._code_generation import (
    _blueprint_file_names,
    _quarantine_stale,
)


class TestQuarantineStale:
    def test_moves_orphan_and_keeps_declared(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True)
        (exp_dir / "data.py").write_text("X = 1\n", encoding="utf-8")
        (exp_dir / "data_generator.py").write_text("Y = 2\n", encoding="utf-8")

        moved = _quarantine_stale(
            exp_dir, stage_dir, keep={"data.py"}, tag="pre-attempt",
        )

        assert moved == ["data_generator.py"]
        assert (exp_dir / "data.py").is_file()
        assert not (exp_dir / "data_generator.py").exists()
        quarantined = stage_dir / "quarantine" / "pre-attempt" / "data_generator.py"
        assert quarantined.read_text(encoding="utf-8") == "Y = 2\n"

    def test_missing_directory_is_a_noop(self, tmp_path: Path) -> None:
        assert _quarantine_stale(
            tmp_path / "nope", tmp_path, keep=set(), tag="x",
        ) == []

    def test_keeps_non_python_files(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True)
        (exp_dir / "notes.txt").write_text("keep\n", encoding="utf-8")

        moved = _quarantine_stale(exp_dir, stage_dir, keep=set(), tag="x")

        assert moved == []
        assert (exp_dir / "notes.txt").is_file()


class TestBlueprintFileNames:
    def test_list_form_and_basename(self) -> None:
        blueprint = {
            "files": [
                {"name": "src/data.py"},
                {"path": "methods.py"},
                {"filename": "main.py", "generation_order": 3},
                {"no_name": True},
                "not-a-dict",
            ]
        }
        assert _blueprint_file_names(blueprint) == {
            "data.py", "methods.py", "main.py",
        }

    def test_missing_or_invalid_blueprint(self) -> None:
        assert _blueprint_file_names(None) == set()
        assert _blueprint_file_names({}) == set()
        assert _blueprint_file_names({"files": {"a": 1}}) == set()
