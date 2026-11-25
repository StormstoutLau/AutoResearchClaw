"""Experiment-plan contract repair (P-177).

The Stage 9 LLM occasionally returns YAML with only ``baselines/datasets`` and
no ``proposed_methods``. The old code treated that as a parse failure only when
``plan is None``; a dict without methods slipped through and killed the stage
at the consistency check. This module repairs the contract with one bounded
regeneration, then falls back to deterministic names.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

import yaml

_FENCE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)```", re.DOTALL)
_SYSTEM = (
    "You repair an experiment-plan YAML document. "
    "Output ONLY YAML with the required keys. No prose, no fences."
)
_USER_TEMPLATE = (
    "The experiment plan is missing `proposed_methods`.\n"
    "Topic: {topic}\n"
    "Return YAML with at least these keys:\n"
    "proposed_methods: [<method name>, ...]\n"
    "datasets: [<dataset>, ...]\n"
    "metrics: [<metric>, ...]\n"
    "baselines: [<baseline>, ...]\n"
    "Keep any existing content if provided. At most 6 methods."
)


def _has_methods(plan: Mapping[str, Any]) -> bool:
    for key in ("proposed_methods", "ablations"):
        value = plan.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
    return False


def _load_yaml(text: str) -> dict | None:
    candidates = [match.group(1) for match in _FENCE.finditer(text)]
    candidates.append(text)
    for candidate in candidates:
        try:
            parsed = yaml.safe_load(candidate)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, Mapping):
            name = str(item.get("name") or item.get("method") or "").strip()
            if name:
                out.append(name)
    return out


def _method_from_hypotheses(hypotheses: str) -> list[str]:
    names = re.findall(r"\*\*([A-Za-z][\w\- ]{2,40})\*\*", str(hypotheses or ""))
    names += re.findall(r"`([A-Za-z][\w\- ]{2,40})`", str(hypotheses or ""))
    cleaned = [" ".join(name.split()) for name in names]
    unique = list(dict.fromkeys(cleaned))
    return unique[:3]


def _slug(topic: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", str(topic or "")).strip("_").lower()
    return token[:24] or "proposed"


def ensure_methods(
    plan: Mapping[str, Any] | None,
    *,
    llm: Any = None,
    topic: str = "",
    hypotheses: str = "",
    max_repairs: int = 1,
) -> dict:
    """Return a plan whose ``proposed_methods`` is non-empty.

    One bounded regeneration when an LLM is available; deterministic fallback
    names otherwise. Never raises: a degraded plan is better than a failed run,
    and the caller logs the degradation.
    """
    out = dict(plan or {})
    if not out:
        # An empty dict means the model produced nothing usable; the Stage 9
        # schema-deficit guard must still pause instead of fabricating content.
        return out
    if _has_methods(out):
        return out

    for _ in range(max(0, int(max_repairs))):
        if llm is None:
            break
        try:
            response = llm.chat(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _USER_TEMPLATE.format(topic=topic)},
                ],
                max_tokens=1200,
            )
        except Exception:  # noqa: BLE001 - repair must not break the stage
            break
        content = getattr(response, "content", str(response))
        parsed = _load_yaml(str(content))
        if parsed and _has_methods(parsed):
            out["proposed_methods"] = _names(parsed.get("proposed_methods")) or _names(
                parsed.get("ablations")
            )
            for key in ("datasets", "metrics", "baselines"):
                if not _names(out.get(key)) and _names(parsed.get(key)):
                    out[key] = _names(parsed.get(key))
            return out

    methods = _method_from_hypotheses(hypotheses)
    out["proposed_methods"] = methods or [f"{_slug(topic)}_proposed"]
    return out
