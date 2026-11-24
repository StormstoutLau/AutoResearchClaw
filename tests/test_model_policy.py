"""P-158 T01-T09: model policy loading, deterministic routing and pre-call guards."""
from __future__ import annotations

import pytest

from researchclaw.llm.model_policy import (
    BudgetExhausted,
    LocalOnlyViolation,
    ModelPolicyError,
    check_local_only,
    load_model_policy,
    policy_digest,
    pre_call_budget_check,
    resolve_model,
    route,
)


class TestModelPolicy:
    def test_default_policy_is_single_tier(self) -> None:
        policy = load_model_policy()
        assert policy["version"] == 1
        assert set(policy["roles"]) == {"planner", "executor", "reviewer", "subagent"}
        assert set(policy["roles"].values()) == {"balanced"}
        assert all(
            not policy["tiers"][tier]["model"] for tier in ("fast", "balanced", "hard")
        )

    def test_route_is_deterministic(self) -> None:
        policy = load_model_policy()
        first = route("executor", stage=7, attempts=0, gate="", policy=policy)
        second = route("executor", stage=7, attempts=0, gate="", policy=policy)
        assert first == second == "balanced"

    def test_route_uses_role_table(self) -> None:
        policy = load_model_policy()
        policy["roles"]["planner"] = "fast"
        policy["roles"]["executor"] = "balanced"
        policy["roles"]["reviewer"] = "hard"
        policy["roles"]["subagent"] = "fast"
        assert route("planner", policy=policy) == "fast"
        assert route("executor", policy=policy) == "balanced"
        assert route("reviewer", policy=policy) == "hard"
        assert route("subagent", policy=policy) == "fast"

    def test_escalation_requires_trigger(self) -> None:
        policy = load_model_policy()
        assert route("executor", policy=policy) == "balanced"
        assert route("executor", gate="gate_reject", policy=policy) == "hard"
        assert route("executor", attempts=2, policy=policy) == "hard"
        assert route("executor", gate="gate_reject", policy=policy, budget_left=0) == "balanced"

    def test_no_escalation_without_budget(self) -> None:
        policy = load_model_policy()
        assert route("executor", attempts=5, budget_left=0, policy=policy) == "balanced"
        assert route("executor", attempts=5, budget_left=0.5, policy=policy) == "hard"

    def test_invalid_policy_rejected(self) -> None:
        policy = load_model_policy()
        bad_role = {**policy, "roles": {**policy["roles"], "unknown": "balanced"}}
        with pytest.raises(ModelPolicyError):
            route("executor", policy=bad_role)
        bad_tier = {**policy, "roles": {**policy["roles"], "executor": "turbo"}}
        with pytest.raises(ModelPolicyError):
            route("executor", policy=bad_tier)
        bad_trigger = {
            **policy,
            "escalation": {**policy["escalation"], "triggers": ["timeout"]},
        }
        with pytest.raises(ModelPolicyError):
            route("executor", policy=bad_trigger)

    def test_resolve_model_falls_back_to_primary(self) -> None:
        policy = load_model_policy()
        assert resolve_model("balanced", policy, "primary-model") == "primary-model"
        policy["tiers"]["hard"]["model"] = "hard-model"
        assert resolve_model("hard", policy, "primary-model") == "hard-model"

    def test_policy_digest_deterministic(self) -> None:
        policy = load_model_policy()
        assert policy_digest(policy) == policy_digest(policy)
        policy["tiers"]["hard"]["model"] = "hard-model"
        assert policy_digest(policy) != policy_digest(load_model_policy())

    def test_pre_call_budget_check(self) -> None:
        pre_call_budget_check(0.0, 0.0)
        pre_call_budget_check(0.9, 1.0)
        with pytest.raises(BudgetExhausted):
            pre_call_budget_check(1.0, 1.0)
        with pytest.raises(BudgetExhausted):
            pre_call_budget_check(1.5, 1.0)


class TestLocalOnly:
    def test_local_only_allows_loopback(self) -> None:
        check_local_only("http://localhost:8000/v1", True)
        check_local_only("http://127.0.0.1:8000/v1", True)
        check_local_only("http://[::1]:8000/v1", True)

    def test_local_only_rejects_remote(self) -> None:
        with pytest.raises(LocalOnlyViolation):
            check_local_only("https://api.example.com/v1", True)
        check_local_only("https://api.example.com/v1", False)
