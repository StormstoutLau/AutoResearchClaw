"""G3 P-089: per-request prompt version context (A3-7).

``PromptManager.for_stage`` sets the version for the current context; every
``LLMClient.chat`` call logs it, so direct calls (debate, code agent, repair)
are covered without threading a parameter through all call sites.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_CURRENT_PROMPT_VERSION: ContextVar[str] = ContextVar(
    "current_prompt_version", default=""
)


def set_prompt_version(version: str) -> None:
    _CURRENT_PROMPT_VERSION.set(version or "")


def get_prompt_version() -> str:
    return _CURRENT_PROMPT_VERSION.get()


def log_prompt_version(model: str = "") -> str:
    """Log the request-time prompt version and return it."""
    version = get_prompt_version()
    logger.info(
        "llm.request prompt_version=%s model=%s", version or "-", model or "-"
    )
    return version
