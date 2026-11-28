"""B-36 P0: repair trace is digest-only, append-only and never fatal."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from researchclaw.pipeline.repair_trace import (
    TRACE_NAME,
    digest,
    load,
    record,
)


class TestRecord:
    def test_writes_digests_instead_of_bodies(self, tmp_path: Path) -> None:
        prompt = "SECRET PROMPT BODY"
        response = "```python\nprint('hi')\n```"
        payload = record(
            tmp_path,
            phase="repair_request",
            file="data.py",
            attempt=1,
            max_attempts=5,
            prompt=prompt,
            response=response,
        )
        assert payload is not None
        assert payload["prompt_sha256"] == digest(prompt)
        assert payload["prompt_chars"] == len(prompt)
        assert payload["response_sha256"] == digest(response)
        assert payload["response_chars"] == len(response)

        raw = (tmp_path / TRACE_NAME).read_text(encoding="utf-8")
        assert "SECRET PROMPT BODY" not in raw
        assert "print('hi')" not in raw

    def test_errors_are_structured_and_truncated(self, tmp_path: Path) -> None:
        issue = SimpleNamespace(
            severity="error",
            category="syntax",
            message="x" * 900,
            line=42,
            col=7,
        )
        payload = record(
            tmp_path,
            phase="validation_failed",
            file="data.py",
            error_summary="1 error(s)",
            errors=[issue],
        )
        assert payload is not None
        assert payload["error_summary"] == "1 error(s)"
        entry = payload["errors"][0]
        assert entry["line"] == 42 and entry["col"] == 7
        assert len(entry["message"]) == 300

    def test_appends_in_order(self, tmp_path: Path) -> None:
        record(tmp_path, phase="validation_failed", file="a.py")
        record(tmp_path, phase="repair_rejected", file="a.py", reason="invalid_python")
        record(tmp_path, phase="repair_aborted", file="a.py", reason="unusable_responses")
        phases = [row["phase"] for row in load(tmp_path)]
        assert phases == [
            "validation_failed", "repair_rejected", "repair_aborted",
        ]

    def test_abort_carries_the_counter(self, tmp_path: Path) -> None:
        payload = record(
            tmp_path,
            phase="repair_aborted",
            file="data.py",
            reason="unusable_responses",
            extra={"invalid_returns": 2},
        )
        assert payload is not None
        assert payload["invalid_returns"] == 2

    def test_never_raises_when_path_is_a_file(self, tmp_path: Path) -> None:
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        assert record(blocker, phase="repair_request", file="a.py") is None

    def test_load_skips_malformed_lines(self, tmp_path: Path) -> None:
        record(tmp_path, phase="repair_request", file="a.py")
        with (tmp_path / TRACE_NAME).open("a", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        rows = load(tmp_path)
        assert len(rows) == 1
        assert rows[0]["phase"] == "repair_request"

    def test_missing_trace_loads_empty(self, tmp_path: Path) -> None:
        assert load(tmp_path) == []


class TestAgentRepairTracing:
    """The CodeAgent hard-validation repair is a second repair site."""

    class _PM:
        def system(self, name):  # noqa: ANN001
            return "sys"

    class _LLM:
        def __init__(self, content: str) -> None:
            self._content = content
            self.calls = 0

        def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
            self.calls += 1
            return SimpleNamespace(
                content=self._content, model="fake", truncated=False,
            )

    def _agent(self, tmp_path: Path, content: str):
        from researchclaw.config import CodeAgentConfig
        from researchclaw.pipeline.code_agent import CodeAgent

        return CodeAgent(
            llm=self._LLM(content),
            prompts=self._PM(),
            config=CodeAgentConfig(
                review_max_rounds=0, hard_validation=False,
                exec_fix_max_iterations=0,
            ),
            stage_dir=tmp_path,
        )

    def test_agent_validation_and_repair_are_recorded(
        self, tmp_path: Path,
    ) -> None:
        main = (
            "def main():\n"
            "    print('METRIC_DEF: m')\n"
            "\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        content = (
            f"```filename:main.py\n{main}```\n"
            "```filename:a.py\nx = 1\n```\n"
        )
        agent = self._agent(tmp_path, content)
        expected = sorted(agent._extract_files(content))
        agent._repair_critical_issues(
            {"a.py": "x = 0\n", "main.py": main},
            ["[a.py] boom"], "t", "p", "m", "",
            attempt=1, max_attempts=4,
        )
        rows = load(tmp_path)
        assert [r["phase"] for r in rows] == [
            "agent_validation_failed", "agent_repair",
        ]
        assert rows[0]["attempt"] == 1 and rows[0]["max_attempts"] == 4
        assert rows[0]["issues"] == ["[a.py] boom"]
        assert rows[1]["accepted"] == expected
        assert rows[1]["reason"] == "merged"

    def test_agent_repair_without_files_is_recorded(
        self, tmp_path: Path,
    ) -> None:
        agent = self._agent(tmp_path, "no files here")
        agent._repair_critical_issues(
            {"a.py": "x = 0\n"}, ["[a.py] boom"], "t", "p", "m", "",
        )
        rows = load(tmp_path)
        assert rows[-1]["phase"] == "agent_repair"
        assert rows[-1]["reason"] == "no_extractable_file"
        assert rows[-1]["rejected"] == ["a.py"]


class TestTraceShape:
    def test_required_fields_present(self, tmp_path: Path) -> None:
        payload = record(
            tmp_path,
            phase="repair_accepted",
            file="methods.py",
            attempt=2,
            max_attempts=5,
            accepted=["methods.py"],
            model="fake",
            truncated=False,
        )
        assert payload is not None
        for key in (
            "ts", "stage", "phase", "file", "attempt", "max_attempts",
            "reason", "error_summary", "errors", "prompt_sha256",
            "prompt_chars", "response_sha256", "response_chars",
            "accepted", "rejected", "model", "truncated",
        ):
            assert key in payload
        assert payload["accepted"] == ["methods.py"]
        assert payload["stage"] == tmp_path.name
