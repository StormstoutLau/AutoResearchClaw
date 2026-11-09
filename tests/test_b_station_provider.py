"""Tests for the B-station (node B of the A/B/C inference cluster) LLM endpoint.

Covers: provider presets (OpenAI + Anthropic wires), from_rc_config wiring,
request URL construction, factory dispatch, CLI menu registration, live
smoke tests against the tunnel (skipped unless reachable and opted in).

Endpoint reference: B 站 = node B of the three-node RPC cluster (not a video
site). Live tests read the tunnel endpoint from ARC_BSTATION_BASE_URL and are
skipped when it is unset, so no local address is committed.
"""

from __future__ import annotations

import json
import os
import re
import socket
import urllib.request
from types import SimpleNamespace
from typing import Any, Mapping
from urllib.parse import urlparse

import pytest

from researchclaw.llm import PROVIDER_PRESETS, create_llm_client
from researchclaw.llm.client import LLMClient, LLMConfig, LLMResponse


BSTATION_BASE = os.environ.get("ARC_BSTATION_BASE_URL", "").rstrip("/")
# RFC 2606 reserved TLD: safe for offline URL assertions, never a real host.
BSTATION_TEST_BASE = "http://b-station.test"


def _tunnel_reachable(timeout: float = 1.5) -> bool:
    """Probe the configured tunnel without sending an API request."""
    if not BSTATION_BASE:
        return False
    parsed = urlparse(BSTATION_BASE)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Unit tests — provider presets
# ---------------------------------------------------------------------------


class TestBStationPreset:
    def test_b_station_in_provider_presets(self):
        assert "b-station" in PROVIDER_PRESETS

    def test_b_station_openai_wire_has_no_baked_url(self):
        assert PROVIDER_PRESETS["b-station"]["base_url"] is None

    def test_b_station_anthropic_wire_preset(self):
        preset = PROVIDER_PRESETS["b-station-anthropic"]
        assert preset["base_url"] is None
        assert preset.get("adapter") == "anthropic"


# ---------------------------------------------------------------------------
# Unit tests — from_rc_config wiring
# ---------------------------------------------------------------------------


def _rc_llm(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = dict(
        provider="b-station",
        base_url=f"{BSTATION_TEST_BASE}/v1",
        wire_api="chat_completions",
        api_key="local-halogen",
        api_key_env="BSTATION_API_KEY",
        primary_model="qwen3.8-flash-next",
        fallback_models=(),
    )
    defaults.update(overrides)
    return SimpleNamespace(llm=SimpleNamespace(**defaults))


class TestBStationFromRCConfig:
    def test_explicit_base_url_is_used(self):
        client = LLMClient.from_rc_config(_rc_llm())
        assert client.config.base_url == f"{BSTATION_TEST_BASE}/v1"
        assert client.config.primary_model == "qwen3.8-flash-next"
        assert client._anthropic is None

    def test_env_base_url_is_used_when_config_empty(self, monkeypatch):
        monkeypatch.setenv("RESEARCHCLAW_LLM_BASE_URL", f"{BSTATION_TEST_BASE}/v1")
        client = LLMClient.from_rc_config(_rc_llm(base_url=""))
        assert client.config.base_url == f"{BSTATION_TEST_BASE}/v1"

    def test_missing_endpoint_fails_closed(self, monkeypatch):
        monkeypatch.delenv("RESEARCHCLAW_LLM_BASE_URL", raising=False)
        with pytest.raises(ValueError, match="private endpoint"):
            LLMClient.from_rc_config(_rc_llm(base_url=""))

    def test_anthropic_preset_sets_adapter(self):
        client = LLMClient.from_rc_config(
            _rc_llm(provider="b-station-anthropic", base_url=BSTATION_TEST_BASE)
        )
        assert client.config.base_url == BSTATION_TEST_BASE
        assert client._anthropic is not None

    def test_custom_base_url_overrides_preset(self):
        client = LLMClient.from_rc_config(
            _rc_llm(base_url="http://custom.test/v1")
        )
        assert client.config.base_url == "http://custom.test/v1"

    def test_placeholder_key_survives_empty_env(self, monkeypatch):
        monkeypatch.delenv("BSTATION_API_KEY", raising=False)
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


class TestBStationEndpoints:
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
        assert captured["url"] == f"{BSTATION_TEST_BASE}/v1/chat/completions"
        assert resp.content == "ok"

    def test_anthropic_wire_url(self):
        client = LLMClient.from_rc_config(
            _rc_llm(provider="b-station-anthropic", base_url=BSTATION_TEST_BASE)
        )
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
        assert captured["url"] == f"{BSTATION_TEST_BASE}/v1/messages"
        assert resp.content == "ok"


# ---------------------------------------------------------------------------
# Unit tests — factory + CLI menu
# ---------------------------------------------------------------------------


class TestBStationFactoryAndCli:
    def test_factory_dispatch(self):
        client = create_llm_client(_rc_llm())
        assert isinstance(client, LLMClient)
        assert client.config.base_url == f"{BSTATION_TEST_BASE}/v1"

    def test_cli_menu_registration(self):
        from researchclaw.cli import _PROVIDER_CHOICES, _PROVIDER_MODELS

        assert ("b-station", "BSTATION_API_KEY") in _PROVIDER_CHOICES.values()
        primary, fallbacks = _PROVIDER_MODELS["b-station"]
        assert primary == "qwen3.8-flash-next"
        assert fallbacks == []

    def test_init_generates_b_station_config(self, tmp_path, monkeypatch):
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
        assert parsed["llm"]["provider"] == "b-station"
        # Private endpoint must stay blank in the generated template.
        assert parsed["llm"]["base_url"] == ""
        assert parsed["llm"]["primary_model"] == "qwen3.8-flash-next"
        assert "<TUNNEL_PORT>" in raw  # guidance uses placeholders, not real ports


# ---------------------------------------------------------------------------
# Unit tests — cli_agent env_extra injection (B 站 Claude Code path)
# ---------------------------------------------------------------------------


class TestClaudeCodeEnvExtra:
    def _agent(self, env_extra: list[tuple[str, str]]):
        from researchclaw.experiment.code_agent import ClaudeCodeAgent

        return ClaudeCodeAgent(binary_path="claude", env_extra=env_extra)

    def test_env_extra_reaches_subprocess(self, tmp_path):
        import sys

        agent = self._agent([("ARC_BSTATION_TEST_VAR", "bstation-ok")])
        rc, stdout, _, _, _ = agent._run_subprocess(
            [sys.executable, "-c", "import os; print(os.environ.get('ARC_BSTATION_TEST_VAR', 'MISSING'))"],
            tmp_path,
            30,
        )
        assert rc == 0
        assert "bstation-ok" in stdout

    def test_stdin_prompt_preserves_newlines(self, tmp_path):
        """Windows .CMD shims truncate multi-line argv; prompt must go via stdin."""
        import sys

        agent = self._agent([])
        rc, stdout, _, _, _ = agent._run_subprocess(
            [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
            tmp_path,
            30,
            stdin_text="TOPIC: line-one\nINSTRUCTION: line-two",
        )
        assert rc == 0
        assert "line-one" in stdout
        assert "line-two" in stdout

    def test_generate_sends_prompt_via_stdin_not_argv(self, tmp_path, monkeypatch):
        agent = self._agent([])
        captured: dict[str, Any] = {}

        def fake_run(cmd, workdir, timeout_sec, stdin_text=None):
            captured["cmd"] = cmd
            captured["stdin"] = stdin_text
            return 0, "", "", 0.0, False

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
        assert "TOPIC: Test topic" in captured["stdin"]
        assert "PLAN BODY" in captured["stdin"]
        assert not any("PLAN BODY" in part for part in captured["cmd"])

    def test_config_parse_env_extra(self):
        from researchclaw.config import _parse_cli_agent_config

        cfg = _parse_cli_agent_config(
            {
                "provider": "claude_code",
                "env_extra": {
                    "ANTHROPIC_BASE_URL": BSTATION_BASE,
                    "ANTHROPIC_AUTH_TOKEN": "local-halogen",
                },
            }
        )
        assert dict(cfg.env_extra) == {
            "ANTHROPIC_BASE_URL": BSTATION_BASE,
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
# Unit tests — Anthropic cache accounting (halogen returns input_tokens=0)
# ---------------------------------------------------------------------------


class TestAnthropicCacheUsage:
    def test_cached_input_tokens_are_counted_in_prompt_usage(self):
        client = LLMClient.from_rc_config(
            _rc_llm(provider="b-station-anthropic", fallback_models=())
        )

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {
                    "type": "message",
                    "model": "halogen-qwen3.8-flash-next",
                    "content": [{"type": "text", "text": "OK"}],
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 29,
                        "cache_read_input_tokens": 56,
                        "cache_creation_input_tokens": 0,
                    },
                }

        class _Client:
            def post(self, url: str, headers: dict, json: dict) -> _Response:
                return _Response()

        client._anthropic._client = _Client()
        resp = client._raw_call(
            "qwen3.8-flash-next", [{"role": "user", "content": "ping"}], 64, 0.1, False
        )
        assert resp.prompt_tokens == 56
        assert resp.completion_tokens == 29
        assert resp.total_tokens == 85


# ---------------------------------------------------------------------------
# Live smoke tests — configured tunnel (skip unless opted in AND reachable)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ARC_BSTATION_LIVE") != "1",
    reason="ARC_BSTATION_LIVE not set (live B 站 smoke tests are opt-in)",
)
@pytest.mark.skipif(
    not _tunnel_reachable(),
    reason="ARC_BSTATION_BASE_URL not set or unreachable",
)
class TestBStationLiveAPI:
    """Live smoke against B 站 halogen (1M 档，输出上限 16384)."""

    def _openai_client(self, max_tokens: int = 64) -> LLMClient:
        return LLMClient(
            LLMConfig(
                base_url=f"{BSTATION_BASE}/v1",
                api_key="local-halogen",
                primary_model="qwen3.8-flash-next",
                fallback_models=[],
                max_tokens=max_tokens,
                timeout_sec=180,
            )
        )

    def _anthropic_client(self) -> LLMClient:
        return LLMClient.from_rc_config(
            _rc_llm(
                provider="b-station-anthropic",
                base_url=BSTATION_BASE,
                fallback_models=(),
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
        resp = self._anthropic_client().chat(
            [{"role": "user", "content": "只回复：OK"}],
            max_tokens=512,
            temperature=0.1,
        )
        assert resp.content.strip(), "empty response"

    # -- 端点能力 ---------------------------------------------------------

    def test_health_reports_1m_context_and_both_wires(self):
        """1M 能力由 /health 声明，避免用长 prefill 烧时间。"""
        with urllib.request.urlopen(f"{BSTATION_BASE}/health", timeout=30) as r:
            data = json.load(r)
        assert data["status"] == "ok"
        assert "qwen3.8" in data["model"].lower()
        assert data["context"] == 1048576
        assert data["capability_probe"] == "ok"
        assert "/v1/chat/completions" in data["endpoints"]
        assert "/v1/messages" in data["endpoints"]

    def test_json_mode_returns_parseable_json(self):
        client = self._openai_client(max_tokens=512)
        resp = client.chat(
            [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Return {"status":"ok"}.'},
            ],
            max_tokens=512,
            temperature=0.1,
            json_mode=True,
        )
        text = resp.content.strip()
        fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        parsed = json.loads(text)
        assert parsed.get("status") == "ok"

    def test_system_prompt_is_respected(self):
        resp = self._openai_client().chat(
            [{"role": "user", "content": "2 + 2 = ?"}],
            system="You are a calculator. Reply with digits only.",
            max_tokens=512,
            temperature=0,
        )
        assert "4" in resp.content

    def test_multi_turn_context_recall(self):
        resp = self._openai_client().chat(
            [
                {"role": "user", "content": "Remember the number 42."},
                {"role": "assistant", "content": "Noted."},
                {
                    "role": "user",
                    "content": "What number did I ask you to remember? "
                    "Reply with the number only.",
                },
            ],
            max_tokens=512,
            temperature=0,
        )
        assert "42" in resp.content

    def test_token_usage_is_reported(self):
        resp = self._openai_client().chat(
            [{"role": "user", "content": "只回复：OK"}],
            max_tokens=512,
            temperature=0.1,
        )
        assert resp.prompt_tokens > 0
        assert resp.completion_tokens > 0
        assert resp.total_tokens >= resp.completion_tokens
        assert "qwen" in (resp.model or "").lower()

    def test_anthropic_wire_reports_usage(self):
        resp = self._anthropic_client().chat(
            [{"role": "user", "content": "只回复：OK"}],
            max_tokens=512,
            temperature=0.1,
        )
        assert resp.content.strip()
        assert resp.prompt_tokens > 0
        assert resp.completion_tokens > 0

    def test_preflight_reports_ok(self):
        ok, message = self._openai_client().preflight()
        assert ok, message
