"""B-31a: runtime logging configuration and line buffering."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest

from researchclaw.cli import build_parser
from researchclaw.runtime.logging_setup import (
    configure_logging,
    force_line_buffering,
    resolve_log_level,
)


@pytest.fixture(autouse=True)
def _restore_root_logging():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved_handlers:
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


class TestResolveLogLevel:
    def test_case_insensitive(self) -> None:
        assert resolve_log_level("info") == logging.INFO
        assert resolve_log_level("DEBUG") == logging.DEBUG

    def test_default_is_info(self) -> None:
        assert resolve_log_level(None) == logging.INFO

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve_log_level("verbose")


class TestConfigureLogging:
    def test_info_reaches_file(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        configure_logging("INFO", log, stream=io.StringIO())
        logging.getLogger("researchclaw.test").info("stage started")
        assert "stage started" in log.read_text(encoding="utf-8")

    def test_warning_level_drops_info(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        configure_logging("WARNING", log, stream=io.StringIO())
        logger = logging.getLogger("researchclaw.test")
        logger.info("dropped")
        logger.warning("kept")
        text = log.read_text(encoding="utf-8")
        assert "dropped" not in text
        assert "kept" in text

    def test_repeated_calls_do_not_duplicate_handlers(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        configure_logging("INFO", log, stream=io.StringIO())
        configure_logging("DEBUG", log, stream=io.StringIO())
        # one stream handler + one file handler
        assert len(logging.getLogger().handlers) == 2

    def test_root_level_is_applied(self, tmp_path: Path) -> None:
        configure_logging("DEBUG", tmp_path / "run.log", stream=io.StringIO())
        assert logging.getLogger().level == logging.DEBUG


class TestLineBuffering:
    def test_real_text_stream_is_switched(self, tmp_path: Path) -> None:
        path = tmp_path / "stdout.txt"
        stream = path.open("w", encoding="utf-8")
        try:
            assert force_line_buffering(stream) is True
            assert stream.line_buffering is True
        finally:
            stream.close()

    def test_stream_without_reconfigure_is_ignored(self) -> None:
        assert force_line_buffering(io.StringIO()) is False

    def test_log_file_grows_while_stage_runs(self, tmp_path: Path) -> None:
        log = tmp_path / "run.log"
        configure_logging("INFO", log, stream=io.StringIO())
        logger = logging.getLogger("researchclaw.runner")
        logger.info("Stage 10/23 CODE_GENERATION — running...")
        first = log.stat().st_size
        logger.info("Stage 10/23 CODE_GENERATION — done (3471.0s)")
        assert log.stat().st_size > first


class TestRunCliFlags:
    def test_defaults(self) -> None:
        args = build_parser().parse_args(["run"])
        assert args.log_level == "INFO"
        assert args.log_file is None

    def test_level_is_uppercased(self) -> None:
        args = build_parser().parse_args(["run", "--log-level", "debug"])
        assert args.log_level == "DEBUG"

    def test_log_file_accepted(self) -> None:
        args = build_parser().parse_args(["run", "--log-file", "x.log"])
        assert args.log_file == "x.log"
