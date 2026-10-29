"""Reusable peer-review core shared by Stage 18 and the MCP server."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from researchclaw.config import RCConfig
from researchclaw.pipeline._helpers import (
    _chat_with_prompt,
    _get_evolution_overlay,
    _read_prior_artifact,
    _safe_json_loads,
)
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


class ReviewConfigError(RuntimeError):
    """Raised when no usable LLM configuration is available for review."""


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of a single peer-review generation."""

    review_markdown: str
    model: str
    independent: bool
    tokens: int


def has_llm_config(config: RCConfig | None) -> bool:
    """Return True when *config* carries enough information to call an LLM."""
    if config is None:
        return False
    llm = getattr(config, "llm", None)
    if llm is None:
        return False
    if getattr(llm, "provider", "") == "acp":
        return True

    base_url = str(getattr(llm, "base_url", "") or "")
    if not base_url:
        try:
            from researchclaw.llm import PROVIDER_PRESETS

            preset = PROVIDER_PRESETS.get(getattr(llm, "provider", ""), {})
            base_url = str(preset.get("base_url") or "")
        except Exception:  # noqa: BLE001 - preset table is optional
            base_url = ""

    api_key = str(getattr(llm, "api_key", "") or "")
    if not api_key:
        api_key = os.environ.get(str(getattr(llm, "api_key_env", "") or ""), "")
    return bool(base_url and api_key)


def collect_experiment_evidence(run_dir: Path) -> str:
    """Collect actual experiment parameters and results for peer review."""
    evidence_parts: list[str] = []

    # 1. Read experiment code to find actual trial count, methods used
    exp_dir = _read_prior_artifact(run_dir, "experiment/")
    if exp_dir and Path(exp_dir).is_dir():
        main_py = Path(exp_dir) / "main.py"
        if main_py.exists():
            code = main_py.read_text(encoding="utf-8")
            evidence_parts.append(
                f"### Actual Experiment Code (main.py)\n```python\n{code[:3000]}\n```"
            )

    # 2. Read sandbox run results (actual metrics, runtime, stderr)
    runs_text = _read_prior_artifact(run_dir, "runs/")
    if runs_text and Path(runs_text).is_dir():
        for run_file in sorted(Path(runs_text).glob("*.json"))[:5]:
            payload = _safe_json_loads(run_file.read_text(encoding="utf-8"), {})
            if isinstance(payload, dict):
                summary = {
                    "metrics": payload.get("metrics"),
                    "elapsed_sec": payload.get("elapsed_sec"),
                    "timed_out": payload.get("timed_out"),
                }
                stderr = payload.get("stderr", "")
                if stderr:
                    summary["stderr_excerpt"] = stderr[:500]
                evidence_parts.append(
                    f"### Run Result: {run_file.name}\n```json\n"
                    f"{json.dumps(summary, indent=2)}\n```"
                )

    # 3. Read refinement log for actual iteration count
    refine_log_text = _read_prior_artifact(run_dir, "refinement_log.json")
    if refine_log_text:
        try:
            rlog = json.loads(refine_log_text)
            summary = {
                "iterations_executed": len(rlog.get("iterations", [])),
                "converged": rlog.get("converged"),
                "stop_reason": rlog.get("stop_reason"),
                "best_metric": rlog.get("best_metric"),
            }
            evidence_parts.append(
                f"### Refinement Summary\n```json\n{json.dumps(summary, indent=2)}\n```"
            )
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Count actual number of experiment runs
    actual_run_count = 0
    for stage_subdir in sorted(run_dir.glob("stage-*/runs")):
        for rf in stage_subdir.glob("*.json"):
            if rf.name != "results.json":
                actual_run_count += 1
    if actual_run_count > 0:
        evidence_parts.append(
            f"### Actual Trial Count\n"
            f"**The experiment was executed {actual_run_count} time(s).** "
            "If the paper claims a different number of trials, this is a CRITICAL discrepancy."
        )

    if not evidence_parts:
        return ""

    return (
        "\n\n## Actual Experiment Evidence\n"
        "Use the evidence below to verify the paper's methodology claims.\n\n"
        + "\n\n".join(evidence_parts)
    )


def review_paper_text(
    paper_text: str,
    *,
    config: RCConfig | None,
    llm: Any | None,
    prompts: PromptManager | None = None,
    run_dir: Path | None = None,
    topic: str = "",
    experiment_evidence: str | None = None,
    quality_warnings: Sequence[str] = (),
    author_model: str = "",
    judge_model: str = "",
) -> ReviewResult:
    """Run the Stage 18 peer-review prompt over arbitrary paper text.

    Raises:
        ReviewConfigError: when *llm* or *config* is missing.
    """
    if llm is None or config is None:
        raise ReviewConfigError(
            "LLM configuration is required for paper review "
            "(set llm.base_url and the API key environment variable)"
        )

    if experiment_evidence is None:
        experiment_evidence = (
            collect_experiment_evidence(run_dir) if run_dir is not None else ""
        )

    suffix = ""
    if quality_warnings:
        suffix = (
            "\n\nAUTOMATED QUALITY ISSUES (flag these in your review):\n"
            + "\n".join(f"- {warning}" for warning in quality_warnings)
            + "\n"
        )

    prompt_manager = prompts or PromptManager()
    overlay = _get_evolution_overlay(run_dir, "peer_review") if run_dir else ""
    rendered = prompt_manager.for_stage(
        "peer_review",
        evolution_overlay=overlay,
        topic=topic or config.research.topic,
        draft=paper_text,
        experiment_evidence=experiment_evidence,
    )

    response = _chat_with_prompt(
        llm,
        rendered.system,
        rendered.user + suffix,
        json_mode=rendered.json_mode,
        max_tokens=rendered.max_tokens,
    )

    resolved_judge = (
        judge_model
        or getattr(getattr(llm, "config", None), "primary_model", "")
        or ""
    )
    independent = bool(author_model and resolved_judge and author_model != resolved_judge)

    return ReviewResult(
        review_markdown=str(getattr(response, "content", "") or ""),
        model=str(getattr(response, "model", "") or resolved_judge),
        independent=independent,
        tokens=int(getattr(response, "total_tokens", 0) or 0),
    )
