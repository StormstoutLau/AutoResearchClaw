"""P-158 T10-T15: config parsing, LLM client guards and policy audit fields."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.config import RCConfig
from researchclaw.llm.client import LLMClient, LLMConfig, LLMResponse
from researchclaw.llm.model_policy import BudgetExhausted, LocalOnlyViolation


def _config_data(**model_policy) -> dict:
    data = {
        "project": {"name": "g6"},
        "research": {"topic": "G6"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "docs/kb"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "https://api.example.com/v1",
            "api_key_env": "RC_TEST_KEY",
            "api_key": "inline",
            "primary_model": "primary-model",
        },
    }
    if model_policy:
        data["model_policy"] = model_policy
    return data


class TestModelPolicyConfig:
    def test_config_defaults(self) -> None:
        config = RCConfig.from_dict(_config_data(), check_paths=False)
        assert config.model_policy.enabled is False
        assert config.model_policy.run_budget_usd == 0.0
        assert config.model_policy.local_only is False

    def test_config_parses_fields(self) -> None:
        config = RCConfig.from_dict(
            _config_data(enabled=True, run_budget_usd=2.5, local_only=True),
            check_paths=False,
        )
        assert config.model_policy.enabled is True
        assert config.model_policy.run_budget_usd == 2.5
        assert config.model_policy.local_only is True


class TestClientGuards:
    def test_local_only_blocks_remote_before_http(self, monkeypatch) -> None:
        client = LLMClient(
            LLMConfig(base_url="https://api.example.com/v1", api_key="k", local_only=True)
        )

        def _boom(*args, **kwargs):
            raise AssertionError("HTTP must not be called")

        monkeypatch.setattr(client, "_call_with_retry", _boom)
        with pytest.raises(LocalOnlyViolation):
            client.chat([{"role": "user", "content": "hi"}])

    def test_budget_blocks_before_http_and_emits_event(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from researchclaw.cost_tracker import get_global_tracker

        tracker = get_global_tracker()
        tracker.reset()
        tracker.begin_run(run_dir=tmp_path, run_id="g6-run")
        tracker.record_llm_call(model="m", provider_cost=1.0)

        client = LLMClient(
            LLMConfig(base_url="http://localhost:8000/v1", api_key="k", run_budget_usd=1.0)
        )

        def _boom(*args, **kwargs):
            raise AssertionError("HTTP must not be called")

        monkeypatch.setattr(client, "_call_with_retry", _boom)
        with pytest.raises(BudgetExhausted):
            client.chat([{"role": "user", "content": "hi"}])
        events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
        assert "budget_exhausted" in events
        tracker.reset()

    def test_cost_record_has_policy_version(self, tmp_path: Path) -> None:
        from researchclaw.cost_tracker import get_global_tracker

        tracker = get_global_tracker()
        tracker.reset()
        tracker.begin_run(run_dir=tmp_path, run_id="g6-run")
        client = LLMClient(
            LLMConfig(base_url="http://localhost:8000/v1", api_key="k")
        )
        resp = LLMResponse(
            content="ok",
            model="routed-model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            raw={"usage": {"cost": 0.01}},
        )
        client._record_cost(resp, policy_version=1)
        line = json.loads(
            (tmp_path / "cost_log.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        assert line["model"] == "routed-model"
        assert line["policy_version"] == 1
        tracker.reset()

    def test_enabled_policy_routes_to_tier_model(self) -> None:
        client = LLMClient(
            LLMConfig(
                base_url="http://localhost:8000/v1",
                api_key="k",
                primary_model="primary-model",
                model_policy_enabled=True,
                model_policy={
                    "version": 1,
                    "default_tier": "balanced",
                    "tiers": {
                        "fast": {"model": ""},
                        "balanced": {"model": ""},
                        "hard": {"model": "hard-model"},
                    },
                    "roles": {
                        "planner": "balanced",
                        "executor": "balanced",
                        "reviewer": "balanced",
                        "subagent": "balanced",
                    },
                    "escalation": {
                        "from": "balanced",
                        "to": "hard",
                        "triggers": ["gate_reject", "two_failures", "context_over_80"],
                    },
                },
            )
        )
        assert client._model_chain_for("executor")[0] == "primary-model"
        escalated = client._model_chain_for("executor", gate="gate_reject")
        assert escalated[0] == "hard-model"
