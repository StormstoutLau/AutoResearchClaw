"""B-33 L1: stage step journal (append-only, digest-only, pure skip oracle)."""

from __future__ import annotations

from pathlib import Path

import pytest

from researchclaw.pipeline.step_journal import (
    STEP_JOURNAL_NAME,
    StepJournalError,
    append_step,
    code_version,
    hash_text,
    last_done,
    load_steps,
    should_skip,
    step_key,
)


def _append(stage_dir: Path, **kwargs):
    return append_step(stage_dir, **kwargs)


class TestAppendAndLoad:
    def test_seq_is_monotonic(self, tmp_path: Path) -> None:
        a = _append(tmp_path, step_id="blueprint", variant="first")
        b = _append(tmp_path, step_id="gen", variant="config.py")
        assert (a["seq"], b["seq"]) == (1, 2)
        steps = load_steps(tmp_path)
        assert [s["seq"] for s in steps] == [1, 2]

    def test_missing_journal_reads_empty(self, tmp_path: Path) -> None:
        assert load_steps(tmp_path) == []

    def test_payload_has_no_code_body(self, tmp_path: Path) -> None:
        code = "def train():\n    return 1.0\n"
        _append(
            tmp_path,
            step_id="gen",
            variant="train.py",
            outputs={"train.py": hash_text(code)},
        )
        raw = (tmp_path / STEP_JOURNAL_NAME).read_text(encoding="utf-8")
        assert "def train" not in raw
        assert "sha256:" in raw

    def test_torn_tail_is_tolerated(self, tmp_path: Path) -> None:
        _append(tmp_path, step_id="blueprint", variant="first")
        with (tmp_path / STEP_JOURNAL_NAME).open("a", encoding="utf-8") as fh:
            fh.write('{"seq": 2, "step_id": "gen", "trunc')
        steps = load_steps(tmp_path)
        assert len(steps) == 1

    def test_corrupt_middle_raises(self, tmp_path: Path) -> None:
        path = tmp_path / STEP_JOURNAL_NAME
        path.write_text(
            '{"seq": 1, "step_id": "a", "status": "done"}\n'
            "{not json}\n"
            '{"seq": 3, "step_id": "c", "status": "done"}\n',
            encoding="utf-8",
        )
        with pytest.raises(StepJournalError):
            load_steps(tmp_path)


class TestLastDone:
    def test_returns_latest_done(self, tmp_path: Path) -> None:
        _append(tmp_path, step_id="gen", variant="config.py", status="failed")
        _append(tmp_path, step_id="gen", variant="config.py", status="done")
        got = last_done(load_steps(tmp_path), "gen", "config.py")
        assert got is not None and got["status"] == "done"

    def test_ignores_truncated(self, tmp_path: Path) -> None:
        _append(tmp_path, step_id="gen", variant="x.py", truncated=True)
        assert last_done(load_steps(tmp_path), "gen", "x.py") is None

    def test_variant_is_part_of_identity(self, tmp_path: Path) -> None:
        _append(tmp_path, step_id="blueprint", variant="first")
        assert last_done(load_steps(tmp_path), "blueprint", "retry") is None
        assert last_done(load_steps(tmp_path), "blueprint", "first") is not None

    def test_step_key(self) -> None:
        assert step_key("gen", "config.py") == "gen:config.py"
        assert step_key("finalize") == "finalize"


class TestShouldSkip:
    def _done(self, tmp_path: Path, *, outputs: dict[str, str], digest: str = "d1"):
        _append(
            tmp_path,
            step_id="gen",
            variant="config.py",
            inputs_digest=digest,
            outputs=outputs,
            code_version_value="v1",
            prompt_version="p1",
        )
        return last_done(load_steps(tmp_path), "gen", "config.py")

    def test_hit_when_everything_matches(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={"config.py": "h1"},
            code_version_value="v1",
            prompt_version="p1",
        )

    def test_miss_on_input_change(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert not should_skip(
            last,
            inputs_digest="d2",
            files_on_disk={"config.py": "h1"},
            code_version_value="v1",
            prompt_version="p1",
        )

    def test_miss_on_code_version_change(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert not should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={"config.py": "h1"},
            code_version_value="v2",
            prompt_version="p1",
        )

    def test_miss_on_prompt_version_change(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert not should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={"config.py": "h1"},
            code_version_value="v1",
            prompt_version="p2",
        )

    def test_miss_when_output_tampered(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert not should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={"config.py": "tampered"},
            code_version_value="v1",
            prompt_version="p1",
        )

    def test_miss_when_output_deleted(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={"config.py": "h1"})
        assert not should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={},
            code_version_value="v1",
            prompt_version="p1",
        )

    def test_miss_when_no_outputs_recorded(self, tmp_path: Path) -> None:
        last = self._done(tmp_path, outputs={})
        assert not should_skip(
            last,
            inputs_digest="d1",
            files_on_disk={},
            code_version_value="v1",
            prompt_version="p1",
        )

    def test_miss_for_none_entry(self) -> None:
        assert not should_skip(
            None,
            inputs_digest="d1",
            files_on_disk={},
            code_version_value="v1",
            prompt_version="p1",
        )


class TestVersions:
    def test_hash_text_is_deterministic(self) -> None:
        assert hash_text("abc") == hash_text("abc")
        assert hash_text("abc") != hash_text("abd")

    def test_code_version_shape(self) -> None:
        value = code_version()
        assert "+" in value
        prefix, short = value.split("+", 1)
        assert prefix
        assert len(short) == 8

    def test_code_version_reads_package_files(self) -> None:
        """D-5: generator files must be readable via importlib.resources."""
        from researchclaw.pipeline.step_journal import _VERSION_FILES, _read_package_bytes

        for rel in _VERSION_FILES:
            data = _read_package_bytes(rel)
            assert isinstance(data, bytes) and data, rel

    def test_code_version_changes_when_generator_bytes_change(self, monkeypatch) -> None:
        import researchclaw.pipeline.step_journal as journal

        monkeypatch.setattr(journal, "_read_package_bytes", lambda rel: b"alpha")
        first = journal.code_version()
        monkeypatch.setattr(journal, "_read_package_bytes", lambda rel: b"beta")
        assert journal.code_version() != first

    def test_code_version_survives_missing_files(self, monkeypatch) -> None:
        import researchclaw.pipeline.step_journal as journal

        monkeypatch.setattr(journal, "_read_package_bytes", lambda rel: None)
        value = journal.code_version()
        assert "+" in value and len(value.split("+", 1)[1]) == 8
