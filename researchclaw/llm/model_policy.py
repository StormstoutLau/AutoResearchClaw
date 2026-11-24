"""Model policy: deterministic role→tier routing, budget and local-only guards (G6).

The default policy is single-tier: every role resolves to ``balanced`` and every
tier model is empty, so ``resolve_model`` falls back to ``llm.primary_model``.
Layering is opt-in by editing ``model_policy.yaml``.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import yaml

POLICY_SCHEMA_VERSION = 1
MODEL_POLICY_VERSION = 1
ROLES = ("planner", "executor", "reviewer", "subagent")
TIERS = ("fast", "balanced", "hard")
TRIGGERS = ("gate_reject", "two_failures", "context_over_80")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

DEFAULT_POLICY: dict[str, Any] = {
    "version": POLICY_SCHEMA_VERSION,
    "default_tier": "balanced",
    "tiers": {tier: {"model": ""} for tier in TIERS},
    "roles": {role: "balanced" for role in ROLES},
    "escalation": {
        "from": "balanced",
        "to": "hard",
        "triggers": list(TRIGGERS),
    },
}

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "model_policy.yaml"


class ModelPolicyError(ValueError):
    """The policy file is missing, malformed or violates the schema."""


class BudgetExhausted(RuntimeError):
    """A pre-call budget check rejected the request."""


class LocalOnlyViolation(RuntimeError):
    """``local_only`` is set but the endpoint is not loopback."""


def _validate(policy: Mapping[str, Any]) -> dict:
    if not isinstance(policy, Mapping):
        raise ModelPolicyError("model policy must be an object")
    data = copy.deepcopy(dict(policy))
    if data.get("version") != POLICY_SCHEMA_VERSION:
        raise ModelPolicyError(f"policy version must be {POLICY_SCHEMA_VERSION}")
    tiers = data.get("tiers")
    if not isinstance(tiers, Mapping) or not tiers:
        raise ModelPolicyError("tiers must be a non-empty object")
    for tier, spec in tiers.items():
        if tier not in TIERS:
            raise ModelPolicyError(f"unknown tier: {tier!r}")
        if not isinstance(spec, Mapping):
            raise ModelPolicyError(f"tier {tier!r} must be an object")
        model = spec.get("model", "")
        if not isinstance(model, str):
            raise ModelPolicyError(f"tier {tier!r} model must be a string")
    default_tier = data.get("default_tier")
    if default_tier not in tiers:
        raise ModelPolicyError(f"unknown default_tier: {default_tier!r}")
    roles = data.get("roles")
    if not isinstance(roles, Mapping):
        raise ModelPolicyError("roles must be an object")
    for role, tier in roles.items():
        if role not in ROLES:
            raise ModelPolicyError(f"unknown role: {role!r}")
        if tier not in tiers:
            raise ModelPolicyError(f"role {role!r} points to unknown tier: {tier!r}")
    if set(roles) != set(ROLES):
        raise ModelPolicyError("roles must cover planner/executor/reviewer/subagent")
    escalation = data.get("escalation")
    if not isinstance(escalation, Mapping):
        raise ModelPolicyError("escalation must be an object")
    if escalation.get("from") not in tiers or escalation.get("to") not in tiers:
        raise ModelPolicyError("escalation from/to must reference known tiers")
    triggers = escalation.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        raise ModelPolicyError("escalation.triggers must be a non-empty list")
    for trigger in triggers:
        if trigger not in TRIGGERS:
            raise ModelPolicyError(f"unknown escalation trigger: {trigger!r}")
    return data


def load_model_policy(source: str | Path | Mapping[str, Any] | None = None) -> dict:
    """Load and validate a policy; ``None`` returns the built-in single tier."""
    if source is None:
        return copy.deepcopy(DEFAULT_POLICY)
    if isinstance(source, Mapping):
        return _validate(source)
    path = Path(source)
    if not path.is_file():
        raise ModelPolicyError(f"model policy file does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ModelPolicyError(f"cannot read model policy: {exc}") from exc
    return _validate(raw)


def route(
    role: str,
    *,
    stage: int = 0,
    attempts: int = 0,
    gate: str = "",
    budget_left: float | None = None,
    context_ratio: float = 0.0,
    policy: Mapping[str, Any] | None = None,
) -> str:
    """Return the tier for ``role``; escalation only on explicit triggers."""
    data = _validate(policy) if policy is not None else copy.deepcopy(DEFAULT_POLICY)
    roles = data["roles"]
    if role not in roles:
        raise ModelPolicyError(f"unknown role: {role!r}")
    base = str(roles[role])
    if budget_left is not None and float(budget_left) <= 0:
        return base

    escalation = data["escalation"]
    if base != escalation["from"]:
        return base
    triggers = set(escalation["triggers"])
    fired = False
    if gate == "gate_reject" and "gate_reject" in triggers:
        fired = True
    if int(attempts) >= 2 and "two_failures" in triggers:
        fired = True
    if float(context_ratio) >= 0.8 and "context_over_80" in triggers:
        fired = True
    return str(escalation["to"]) if fired else base


def resolve_model(tier: str, policy: Mapping[str, Any], primary_model: str) -> str:
    data = _validate(policy)
    if tier not in data["tiers"]:
        raise ModelPolicyError(f"unknown tier: {tier!r}")
    return str(data["tiers"][tier].get("model") or primary_model)


def policy_digest(policy: Mapping[str, Any]) -> str:
    body = json.dumps(dict(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def pre_call_budget_check(spent_usd: float, budget_usd: float) -> None:
    """Reject before the HTTP call when spend has reached the budget."""
    budget = float(budget_usd or 0.0)
    if budget <= 0:
        return
    if float(spent_usd or 0.0) >= budget:
        raise BudgetExhausted(
            f"budget exhausted: spent ${float(spent_usd):.4f} >= ${budget:.4f}"
        )


def check_local_only(base_url: str, local_only: bool) -> None:
    """Reject non-loopback endpoints before any HTTP call when local_only is on."""
    if not local_only:
        return
    host = (urlparse(str(base_url or "")).hostname or "").strip().lower()
    if host not in _LOCAL_HOSTS:
        raise LocalOnlyViolation(
            f"local_only is set but endpoint host is {host or '<empty>'!r}"
        )


__all__ = [
    "BudgetExhausted",
    "DEFAULT_POLICY",
    "DEFAULT_POLICY_PATH",
    "LocalOnlyViolation",
    "MODEL_POLICY_VERSION",
    "ModelPolicyError",
    "ROLES",
    "TIERS",
    "TRIGGERS",
    "check_local_only",
    "load_model_policy",
    "policy_digest",
    "pre_call_budget_check",
    "resolve_model",
    "route",
]
