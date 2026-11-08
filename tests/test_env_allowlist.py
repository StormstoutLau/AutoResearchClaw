"""H-6: subprocess environment must be allowlisted."""

from __future__ import annotations

import subprocess
import sys

from researchclaw.utils.env import build_subprocess_env


def test_secret_not_forwarded(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    env = build_subprocess_env()
    assert "OPENAI_API_KEY" not in env


def test_path_is_preserved(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    assert build_subprocess_env()["PATH"] == "/usr/bin"


def test_overrides_are_applied() -> None:
    assert build_subprocess_env({"SAFE_FLAG": "1"})["SAFE_FLAG"] == "1"


def test_child_process_cannot_read_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    code = "import os; print(os.environ.get('OPENAI_API_KEY') or 'MISSING')"
    out = subprocess.check_output(
        [sys.executable, "-c", code],
        env=build_subprocess_env(),
        text=True,
    ).strip()
    assert out == "MISSING"
