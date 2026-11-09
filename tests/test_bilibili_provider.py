"""Tests for the B站 (Bilibili LAN cluster) LLM endpoint integration.

Covers: provider presets (OpenAI + Anthropic wires), from_rc_config wiring,
request URL construction, factory dispatch, CLI menu registration, live
smoke tests against the tunnel (skipped unless reachable and opted in).

Endpoint reference: docs/arc-g1-readiness lineage — B 站 halogen
无审查 Qwen3.8 1M, tunnel 127.0.0.1:<TUNNEL_PORT> -> <B_STATION_HOST>:8080.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from researchclaw.llm import PROVIDER_PRESETS, create_llm_client
from researchclaw.llm.client import LLMClient, LLMConfig, LLMResponse


BILI_BASE = "http://127.0.0.1:<TUNNEL_PORT>"
BILI_TUNNEL_HOST = "127.0.0.1"
BILI_TUNNEL_PORT = 18081


def _tunnel_reachable(timeout: float = 1.5) -> bool:
    """Probe the SSH tunnel without sending a request."""
    try:
        with socket.create_connection((BILI_TUNNEL_HOST, BILI_TUNNEL_PORT), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Unit tests — provider presets
# ---------------------------------------------------------------------------


class TestBilibiliPreset:
    def test_bilibili_in_provider_presets(self):
        assert "bilibili" in PROVIDER_PRESETS

    def test_bilibili_openai_wire_base_url(self):
        assert PROVIDER_PRESETS["bilibili"]["base_url"] == f"{BILI_BASE}/v1"

    def test_bilibili_anthropic_wire_preset(self):
        preset = PROVIDER_PRESETS["bilibili-anthropic"]
        assert preset["base_url"] == BILI_BASE
        assert preset.get("adapter") == "anthropic"


# ---------------------------------------------------------------------------
# Unit tests — from_rc_config wiring
# ---------------------------------------------------------------------------


def _rc_llm(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = dict(
        provider="bilibili",
        base_url="",
        wire_api="chat_completions",
        api_key="local-halogen",
        api_key_env="BILI_API_KEY",
        primary_model="qwen3.8-flash-next",
        fallback_models=(),
    )
    defaults.update(overrides)
    return SimpleNamespace(llm=SimpleNamespace(**defaults))


class TestBilibiliFromRCConfig:
    def test_preset_base_url_used_when_unset(self):
        client = LLMClient.from_rc_config(_rc_llm())
        assert client.config.base_url == f"{BILI_BASE}/v1"
        assert client.config.primary_model == "qwen3.8-flash-next"
        assert client._anthropic is None

    def test_anthropic_preset_sets_adapter(self):
        client = LLMClient.from_rc_config(_rc_llm(provider="bilibili-anthropic"))
        assert client.config.base_url == BILI_BASE
        assert client._anthropic is not None

    def test_custom_base_url_overrides_preset(self):
        client = LLMClient.from_rc_config(
            _rc_llm(base_url="http://127.0.0.1:<ALT_TUNNEL_PORT>/v1")
        )
        assert client.config.base_url == "http://127.0.0.1:<ALT_TUNNEL_PORT>/v1"

    def test_placeholder_key_survives_empty_env(self, monkeypatch):
        monkeypatch.delenv("BILI_API_KEY", raising=False)
        client = LLMClient.from_rc_config(_rc_llm())
        assert client.config.api_key == "local-halogen"


# ---------------------------------------------------------------------------
# Unit tests — request URL construction (both wires)
# ---------------------------------------------------------------------------


class _DummyHTTPResponse:
    def __init__(self, payload: Mapping[str, Any]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_DummyHTTPResponse":
        return self

    def __exit__(self, *a: object) -> None:
        return None


class TestBilibiliEndpoints:
    def test_openai_wire_url(self, monkeypatch):
        client = LLMClient.from_rc_config(_rc_llm())
        captured: dict[str, Any] = {}

        def fake_urlopen(req: urllib.request.Request, timeout: int) -> _DummyHTTPResponse:
            captured["url"] = req.full_url
            return _DummyHTTPResponse(
                {
                    "model": "qwen3.8-flash-next",
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        resp = client._raw_call(
            "qwen3.8-flash-next", [{"role": "user", "content": "ping"}], 64, 0.5, False
        )
        assert captured["url"] == f"{BILI_BASE}/v1/chat/completions"
        assert resp.content == "ok"

    def test_anthropic_wire_url(self):
        client = LLMClient.from_rc_config(_rc_llm(provider="bilibili-anthropic"))
        captured: dict[str, Any] = {}

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {
                    "type": "message",
                    "model": "halogen-qwen3.8-flash-next",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }

        class _Client:
            def post(self, url: str, headers: dict, json: dict) -> _Response:
                captured["url"] = url
                return _Response()

        client._anthropic._client = _Client()
        resp = client._raw_call(
            "qwen3.8-flash-next", [{"role": "user", "content": "ping"}], 64, 0.5, False
        )
        # halogen natively serves /v1/messages — matches the doc's curl probe
        assert captured["url"] == f"{BILI_BASE}/v1/messages"
        assert resp.content == "ok"


# ---------------------------------------------------------------------------
# Unit tests — factory + CLI menu
# ---------------------------------------------------------------------------


class TestBilibiliFactoryAndCli:
    def test_factory_dispatch(self):
        client = create_llm_client(_rc_llm())
        assert isinstance(client, LLMClient)
        assert client.config.base_url == f"{BILI_BASE}/v1"

    def test_cli_menu_registration(self):
        from researchclaw.cli import _PROVIDER_CHOICES, _PROVIDER_MODELS, _PROVIDER_URLS

        assert ("bilibili", "BILI_API_KEY") in _PROVIDER_CHOICES.values()
        assert _PROVIDER_URLS["bilibili"] == f"{BILI_BASE}/v1"
        primary, fallbacks = _PROVIDER_MODELS["bilibili"]
        assert primary == "qwen3.8-flash-next"
        assert fallbacks == []

    def test_init_generates_bilibili_config(self, tmp_path, monkeypatch):
        from researchclaw import cli as rc_cli

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})()
        )
        monkeypatch.setattr("builtins.input", lambda _prompt: "11")
        monkeypatch.setattr(rc_cli, "_prompt_opencode_install", lambda: None)

        assert rc_cli.cmd_init(SimpleNamespace(force=False)) == 0
        import yaml

        raw = (tmp_path / "config.arc.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw)
        assert parsed["llm"]["provider"] == "bilibili"
        assert parsed["llm"]["base_url"] == f"{BILI_BASE}/v1"
        assert parsed["llm"]["primary_model"] == "qwen3.8-flash-next"


# ---------------------------------------------------------------------------
# Unit tests — cli_agent env_extra injection (B站 Claude Code path)
# ---------------------------------------------------------------------------


class TestClaudeCodeEnvExtra:
    def _agent(self, env_extra: list[tuple[str, str]]):
        from researchclaw.experiment.code_agent import ClaudeCodeAgent

        return ClaudeCodeAgent(binary_path="claude", env_extra=env_extra)

    def test_env_extra_reaches_subprocess(self, tmp_path):
        import sys

        agent = self._agent([("ARC_BILI_TEST_VAR", "bili-ok")])
        rc, stdout, _, _, _ = agent._run_subprocess(
            [sys.executable, "-c", "import os; print(os.environ.get('ARC_BILI_TEST_VAR', 'MISSING'))"],
            tmp_path,
            30,
        )
        assert rc == 0
        assert "bili-ok" in stdout

    def test_config_parse_env_extra(self):
        from researchclaw.config import _parse_cli_agent_config

        cfg = _parse_cli_agent_config(
            {
                "provider": "claude_code",
                "env_extra": {
                    "ANTHROPIC_BASE_URL": BILI_BASE,
                    "ANTHROPIC_AUTH_TOKEN": "local-halogen",
                },
            }
        )
        assert dict(cfg.env_extra) == {
            "ANTHROPIC_BASE_URL": BILI_BASE,
            "ANTHROPIC_AUTH_TOKEN": "local-halogen",
        }

    def test_config_parse_empty_env_extra(self):
        from researchclaw.config import _parse_cli_agent_config

        assert dict(_parse_cli_agent_config({}).env_extra) == {}


# ---------------------------------------------------------------------------
# Unit tests — thinking-model parsing (halogen Qwen3.8 emits reasoning_content)
# ---------------------------------------------------------------------------


class TestThinkingModelParse:
    """content 为空、reasoning_content 有值时必须回退，不能静默吞掉。"""

    def _client_capture(self, monkeypatch, message: dict) -> LLMResponse:
        client = LLMClient.from_rc_config(_rc_llm())

        def fake_urlopen(req: urllib.request.Request, timeout: int) -> _DummyHTTPResponse:
            return _DummyHTTPResponse(
                {
                    "model": "halogen-qwen3.8-flash-next",
                    "choices": [
                        {
                            "message": message,
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 16, "total_tokens": 17},
                }
            )

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        return client.chat([{"role": "user", "content": "hi"}], max_tokens=16)

    def test_empty_content_falls_back_to_reasoning(self, monkeypatch):
        resp = self._client_capture(
            monkeypatch, {"content": "", "reasoning_content": "推导过程……答案是 2"}
        )
        assert resp.content == "推导过程……答案是 2"
        assert resp.truncated is True

    def test_normal_content_untouched(self, monkeypatch):
        resp = self._client_capture(
            monkeypatch, {"content": "1 + 1 = 2", "reasoning_content": "…"}
        )
        assert resp.content == "1 + 1 = 2"

    def test_both_empty_stays_empty(self, monkeypatch):
        resp = self._client_capture(monkeypatch, {"content": "", "reasoning_content": ""})
        assert resp.content == ""


# ---------------------------------------------------------------------------
# Live smoke tests — tunnel 18081 (skip unless opted in AND reachable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ARC_BILI_LIVE") != "1",
    reason="ARC_BILI_LIVE not set (live B站 smoke tests are opt-in)",
)
@pytest.mark.skipif(
    not _tunnel_reachable(),
    reason="B站 tunnel 127.0.0.1:<TUNNEL_PORT> not reachable",
)
class TestBilibiliLiveAPI:
    """Live smoke against B站 halogen (1M 档，输出上限 16384)."""

    def _openai_client(self) -> LLMClient:
        return LLMClient(
            LLMConfig(
                base_url=f"{BILI_BASE}/v1",
                api_key="local-halogen",
                primary_model="qwen3.8-flash-next",
                fallback_models=[],
                max_tokens=64,
                timeout_sec=120,
            )
        )

    def test_openai_wire_smoke(self):
        resp = self._openai_client().chat(
            [{"role": "user", "content": "只回复：OK"}],
            max_tokens=512,
            temperature=0.1,
        )
        # Qwen3.8 是思考型模型：max_tokens 需给 thinking 留出预算（1M 档上限 16384）
        assert resp.content.strip(), "empty response"

    def test_anthropic_wire_smoke(self):
        client = LLMClient.from_rc_config(
            _rc_llm(provider="bilibili-anthropic", fallback_models=())
        )
        resp = client.chat(
            [{"role": "user", "content": "只回复：OK"}],
            max_tokens=512,
            temperature=0.1,
        )
        assert resp.content.strip(), "empty response"
