"""R-3 统一接缝：接线、回退与传输契约测试（离线）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _cli_cfg(provider: str = "claude_code", **overrides):
    values = dict(
        provider=provider,
        binary_path="",
        model="",
        max_budget_usd=5.0,
        timeout_sec=30,
        extra_args=(),
        env_extra=(),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _config(provider: str = "claude_code"):
    return SimpleNamespace(
        experiment=SimpleNamespace(cli_agent=_cli_cfg(provider)),
        llm=SimpleNamespace(primary_model="test-model", provider="openai", base_url=""),
    )


def _code_result(files: dict[str, str], error: str | None = None):
    from researchclaw.experiment.code_agent import CodeAgentResult

    return CodeAgentResult(
        files=files,
        provider_name="claude_code",
        elapsed_sec=1.0,
        raw_output="ok",
        error=error,
    )


class TestConfigSingleDefinition:
    def test_config_code_agent_single_definition(self):
        from researchclaw.config import CodeAgentConfig as ConfigCAC
        from researchclaw.pipeline.code_agent import CodeAgentConfig as PipelineCAC

        assert ConfigCAC is PipelineCAC


class TestFactoryErrorPath:
    def test_factory_error_points_to_cli_agent_path(self, monkeypatch):
        import researchclaw.experiment.code_agent as mod

        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        with pytest.raises(RuntimeError) as exc:
            mod.create_code_agent(_config("claude_code"))
        assert "experiment.cli_agent.binary_path" in str(exc.value)


class TestStage10Helper:
    def _call(self, tmp_path: Path, config=None, llm=None):
        from researchclaw.pipeline.stage_impls._code_generation import (
            _try_cli_code_agent,
        )

        return _try_cli_code_agent(
            config or _config(),
            llm,
            None,
            stage_dir=tmp_path,
            topic="t",
            exp_plan="p",
            metric="accuracy",
            pkg_hint="",
            compute_budget="",
            extra_guidance="",
        )

    def test_helper_skips_llm_provider(self, tmp_path, monkeypatch):
        import researchclaw.experiment.code_agent as mod

        def _boom(*args, **kwargs):
            raise AssertionError("factory must not be called for provider=llm")

        monkeypatch.setattr(mod, "create_code_agent", _boom)
        assert self._call(tmp_path, _config("llm")) is None

    def test_helper_returns_files_and_writes_log(self, tmp_path, monkeypatch):
        import researchclaw.experiment.code_agent as mod

        fake = SimpleNamespace(generate=lambda **kwargs: _code_result({"main.py": "print(1)"}))
        monkeypatch.setattr(mod, "create_code_agent", lambda *a, **k: fake)
        files = self._call(tmp_path)
        assert files == {"main.py": "print(1)"}
        log = json.loads((tmp_path / "cli_agent_log.json").read_text(encoding="utf-8"))
        assert log["provider"] == "claude_code"
        assert log["ok"] is True
        assert log["files"] == ["main.py"]

    def test_helper_falls_back_on_exception(self, tmp_path, monkeypatch):
        import researchclaw.experiment.code_agent as mod

        def _boom(*args, **kwargs):
            raise RuntimeError("binary exploded")

        monkeypatch.setattr(mod, "create_code_agent", _boom)
        assert self._call(tmp_path) is None

    def test_helper_falls_back_on_failed_result(self, tmp_path, monkeypatch):
        import researchclaw.experiment.code_agent as mod

        fake = SimpleNamespace(
            generate=lambda **kwargs: _code_result({}, error="timeout")
        )
        monkeypatch.setattr(mod, "create_code_agent", lambda *a, **k: fake)
        assert self._call(tmp_path) is None


class TestStage13Helpers:
    def test_refine_helper_uses_agent(self, tmp_path):
        from researchclaw.pipeline.stage_impls._execution import _try_agent_refine

        fake = SimpleNamespace(
            refine=lambda **kwargs: _code_result({"main.py": "print(2)"})
        )
        files = _try_agent_refine(
            fake,
            current_files={"main.py": "print(1)"},
            run_summaries=["run"],
            metric_key="accuracy",
            metric_direction="maximize",
            topic="t",
            extra_hints="",
            workdir=tmp_path,
            timeout_sec=30,
        )
        assert files == {"main.py": "print(2)"}

    def test_refine_helper_falls_back(self, tmp_path):
        from researchclaw.pipeline.stage_impls._execution import _try_agent_refine

        def _boom(**kwargs):
            raise RuntimeError("refine failed")

        files = _try_agent_refine(
            SimpleNamespace(refine=_boom),
            current_files={"main.py": "print(1)"},
            run_summaries=[],
            metric_key="accuracy",
            metric_direction="maximize",
            topic="t",
            extra_hints="",
            workdir=tmp_path,
            timeout_sec=30,
        )
        assert files is None

    def test_repair_helper_uses_agent(self, tmp_path):
        from researchclaw.pipeline.stage_impls._execution import _try_agent_repair

        fake = SimpleNamespace(
            repair=lambda **kwargs: _code_result({"main.py": "print(3)"})
        )
        files = _try_agent_repair(
            fake,
            files={"main.py": "print(1)"},
            issues="syntax error",
            workdir=tmp_path,
            timeout_sec=30,
        )
        assert files == {"main.py": "print(3)"}

    def test_repair_helper_returns_none_without_agent(self, tmp_path):
        from researchclaw.pipeline.stage_impls._execution import _try_agent_repair

        assert (
            _try_agent_repair(
                None,
                files={"main.py": "print(1)"},
                issues="x",
                workdir=tmp_path,
                timeout_sec=30,
            )
            is None
        )


class TestCodexTransport:
    def test_codex_prompt_goes_to_stdin(self, tmp_path, monkeypatch):
        from researchclaw.experiment.code_agent import CodexAgent

        agent = CodexAgent(binary_path="codex", model="m")
        cmd = agent._build_cmd(tmp_path)
        assert cmd[:3] == ["codex", "exec", "-"]
        captured: dict[str, object] = {}

        def fake_run(cmd, workdir, timeout_sec, stdin_text=None):
            captured["cmd"] = cmd
            captured["stdin"] = stdin_text
            return 0, "", "", 0.1, False

        monkeypatch.setattr(agent, "_run_subprocess", fake_run)
        agent.generate(
            exp_plan="PLAN BODY",
            topic="Test topic",
            metric_key="accuracy",
            pkg_hint="",
            compute_budget="",
            extra_guidance="",
            workdir=tmp_path,
        )
        assert "PLAN BODY" in captured["stdin"]
        assert not any("PLAN BODY" in str(part) for part in captured["cmd"])


class TestWiringFitnessFunction:
    def test_wiring_script_passes(self):
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, "scripts/code_agent_wiring_check.py"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_wiring_script_fails_on_unwired_provider(self, tmp_path):
        files = {
            "researchclaw/config.py": 'CLI_AGENT_PROVIDERS = {"llm", "ghost"}\n',
            "researchclaw/experiment/code_agent.py": (
                'if provider == "llm":\n    pass\n'
                "class ClaudeCodeAgent:\n"
                '    def _build_cmd(self):\n        return ["-p"]\n'
                "class CodexAgent:\n"
                '    def _build_cmd(self):\n        return ["exec", "-"]\n'
            ),
            "researchclaw/pipeline/code_agent.py": (
                "from researchclaw.config import CodeAgentConfig\n"
            ),
            "researchclaw/pipeline/stage_impls/_code_generation.py": (
                "_try_cli_code_agent(\n_cli_agent_used = True\ncli_agent\n"
            ),
            "researchclaw/pipeline/stage_impls/_execution.py": (
                "_try_agent_refine(\n_try_agent_repair(\ncli_agent\n"
            ),
        }
        for rel, content in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable,
                "scripts/code_agent_wiring_check.py",
                "--root",
                str(tmp_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 1
        assert "ghost" in proc.stdout


class TestDoctorCliAgent:
    def test_llm_provider_is_pass(self):
        from researchclaw.health import check_cli_agent

        result = check_cli_agent("llm")
        assert result.status == "pass"

    def test_missing_binary_fails(self, monkeypatch):
        import researchclaw.health as health

        monkeypatch.setattr(health.shutil, "which", lambda name: None)
        result = health.check_cli_agent("claude_code")
        assert result.status == "fail"
        assert "experiment.cli_agent.binary_path" in (result.fix or "")

    def test_explicit_binary_passes(self):
        from researchclaw.health import check_cli_agent

        result = check_cli_agent("claude_code", binary_path="C:/tools/claude.exe")
        assert result.status == "pass"
