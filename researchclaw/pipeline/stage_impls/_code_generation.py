"""Stage 10: Code generation."""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.experiment.validator import (
    CodeValidation,
    format_issues_for_llm,
    validate_code,
)
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._domain import _detect_domain
from researchclaw.pipeline.codegen_evidence import (
    check_symbol_contract,
    declared_symbols,
    evaluate_stage10_evidence,
    load_blueprint,
    resolve_metric,
    write_evidence_report,
)
from researchclaw.pipeline.repair_trace import (
    digest as _repair_digest,
    record as _record_repair_trace,
)
from researchclaw.pipeline.step_journal import (
    append_step as _append_progress_step,
    hash_text as _progress_digest,
)
from researchclaw.pipeline._helpers import (
    StageResult,
    _chat_with_prompt,
    _ensure_sandbox_deps,
    _extract_code_block,
    _extract_multi_file_blocks,
    _extract_yaml_block,
    _get_evolution_overlay,
    _load_hardware_profile,
    _read_prior_artifact,
    _safe_json_loads,
    _utcnow_iso,
)
from researchclaw.pipeline.entrypoint_contract import (
    ENTRYPOINT_MAX_TOKENS,
    ENTRYPOINT_RETRY_MAX_TOKENS,
    build_entrypoint_prompt,
    entrypoint_issues as _entrypoint_issues,
    synthesize_entrypoint,
)
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager
from researchclaw.utils.paths import safe_join

logger = logging.getLogger(__name__)


def _quarantine_stale(
    exp_dir: Path, stage_dir: Path, *, keep: set[str], tag: str,
) -> list[str]:
    """P-227 (F-1): move delivered-code leftovers out of ``experiment/``.

    Attempts share one directory.  Without this, a module produced by a failed
    attempt (run L: ``data_generator.py`` from attempt 1) survived into the
    final deliverable and was not declared by the blueprint.  Files are moved
    to ``stage-10/quarantine/<tag>/`` instead of deleted, so the evidence
    trail stays auditable.
    """
    if not exp_dir.is_dir():
        return []
    dest = stage_dir / "quarantine" / tag
    moved: list[str] = []
    for path in sorted(exp_dir.iterdir()):
        if not path.is_file() or path.suffix != ".py":
            continue
        if path.name in keep:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / path.name
        if target.exists():
            target = dest / f"{path.stem}.{int(path.stat().st_mtime)}{path.suffix}"
        path.replace(target)
        moved.append(path.name)
    if moved:
        logger.warning(
            "Stage 10: quarantined stale file(s) from experiment/: %s",
            ", ".join(moved),
        )
    return moved


def _blueprint_file_names(blueprint: Any) -> set[str]:
    """Basenames declared by the blueprint (P-227 F-3)."""
    entries = (blueprint or {}).get("files") if isinstance(blueprint, dict) else None
    if not isinstance(entries, list):
        return set()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("path") or entry.get("filename")
        if name:
            names.add(str(name).replace("\\", "/").rsplit("/", 1)[-1])
    return names


def _is_parseable(code: str) -> bool:
    """B-29: reject syntax-broken repair output before it overwrites a file."""
    try:
        ast.parse(str(code or ""))
    except SyntaxError:
        return False
    return True


def _blocked_validation_report(
    repair_counts: dict[str, int],
    max_repair: int,
    validation_log: list[str],
) -> str:
    """Render the BLOCKED report with the repairs that actually ran.

    The header used to print ``max_repair`` (the per-file limit), so an early
    abort after two unusable replies was reported as "after 5 repairs" — the
    same contradiction the run-I postmortem flagged for the log lines.
    """
    performed = sum(int(n) for n in repair_counts.values())
    lines = [
        "# Code Validation Report",
        "",
        f"**Status**: BLOCKED — critical issues remain after {performed} "
        f"repair attempt(s) (limit {max_repair}/file)",
        "",
    ]
    if repair_counts:
        lines.append("Repairs performed per file:")
        lines.extend(
            f"- {name}: {count}"
            for name, count in sorted(repair_counts.items())
        )
        lines.append("")
    lines.extend(f"- {entry}" for entry in validation_log)
    return "\n".join(lines)


def _journal_alignment(
    stage_dir: Path, variant: str, status: str, text: str,
) -> None:
    """Record one alignment decision as a progress-only step (B-31b/B-33).

    Alignment is not reusable work, so ``outputs`` is empty and
    ``should_skip`` can never suppress a later run.
    """
    try:
        _append_progress_step(
            stage_dir,
            step_id="alignment",
            variant=variant,
            status=status,
            inputs_digest=_progress_digest(text),
        )
    except Exception:  # noqa: BLE001 - journal is best-effort
        logger.debug("could not journal alignment step", exc_info=True)


def _extract_valid_repair_files(
    content: str, known_files: set[str],
) -> dict[str, str]:
    """B-28: accept only complete, syntactically valid files from a repair reply.

    A truncated repair response often ends mid-string. ``ast.parse`` rejects
    that fragment, so the caller keeps the last known-good file instead of
    overwriting it. Unknown filenames are ignored to avoid surprise files.
    """
    raw = _extract_multi_file_blocks(content)
    allowed = set(known_files) | {"main.py"}
    accepted: dict[str, str] = {}
    for name, code in raw.items():
        if name not in allowed:
            logger.warning("Stage 10 repair: ignoring unknown file %s", name)
            continue
        if not isinstance(code, str) or not code.strip():
            continue
        try:
            ast.parse(code)
        except SyntaxError as exc:
            logger.warning(
                "Stage 10 repair: ignoring syntax-invalid %s (%s)", name, exc,
            )
            continue
        if name == "main.py":
            issues = _entrypoint_issues(code)
            if issues:
                logger.warning(
                    "Stage 10 repair: ignoring main.py that breaks the entrypoint "
                    "contract (%s)", "; ".join(issues),
                )
                continue
        accepted[name] = code
    return accepted


def _merge_repair_files(
    original: dict[str, str], repaired: dict[str, str],
) -> dict[str, str]:
    """B-28: merge repaired files; never drop files the model did not return."""
    merged = dict(original)
    merged.update(repaired)
    return merged


def _request_repair_response(
    llm: LLMClient, system: str, user: str, *, max_tokens: int,
):
    """B-28: repair/fix calls retry once when the model output is truncated."""
    resp = _chat_with_prompt(llm, system, user, max_tokens=max_tokens)
    truncated = bool(getattr(resp, "truncated", False)) or (
        getattr(resp, "finish_reason", "") == "length"
    )
    if truncated:
        logger.warning("Stage 10 repair: response truncated — retrying with 32768")
        resp = _chat_with_prompt(
            llm, system, user, max_tokens=max(32768, int(max_tokens)),
        )
    return resp


def _generate_entrypoint(
    llm: LLMClient,
    pm: PromptManager,
    *,
    topic: str,
    metric: str,
    files: dict[str, str],
    exp_plan: str = "",
    max_attempts: int = 2,
) -> str:
    """B-29: ask for one complete ``main.py`` that satisfies the contract.

    Returns "" when every attempt fails.  The prompt lists the other modules so
    the entrypoint imports them instead of re-implementing their logic.
    """
    system = pm.system("code_generation")
    issues: list[str] | None = None
    for attempt in range(1, max_attempts + 1):
        budget = (
            ENTRYPOINT_MAX_TOKENS if attempt == 1
            else ENTRYPOINT_RETRY_MAX_TOKENS
        )
        user = build_entrypoint_prompt(
            topic=topic,
            metric=metric,
            files=files,
            exp_plan=exp_plan,
            previous_issues=issues,
        )
        resp = _chat_with_prompt(llm, system, user, max_tokens=budget)
        truncated = bool(getattr(resp, "truncated", False)) or (
            getattr(resp, "finish_reason", "") == "length"
        )
        if truncated and budget < ENTRYPOINT_RETRY_MAX_TOKENS:
            logger.warning(
                "Stage 10: entrypoint attempt %d truncated — escalating to %d",
                attempt, ENTRYPOINT_RETRY_MAX_TOKENS,
            )
            resp = _chat_with_prompt(
                llm, system, user, max_tokens=ENTRYPOINT_RETRY_MAX_TOKENS,
            )
        code = _extract_code_block(resp.content)
        issues = _entrypoint_issues(code)
        if code.strip() and not issues:
            logger.info(
                "Stage 10: entrypoint generated on attempt %d (%d chars)",
                attempt, len(code),
            )
            return code
        logger.warning(
            "Stage 10: entrypoint attempt %d rejected: %s",
            attempt, "; ".join(issues) or "empty output",
        )
    return ""


def _ensure_entrypoint(
    files: dict[str, str],
    *,
    llm: LLMClient | None,
    pm: PromptManager,
    topic: str,
    metric: str,
    exp_dir: Path,
    exp_plan: str = "",
) -> dict[str, str]:
    """B-29: regenerate ``main.py`` when it cannot run as the entrypoint.

    A truncated-but-parseable ``main.py`` (no ``__main__`` guard, no
    ``METRIC_DEF``) would otherwise only be caught by the exit gate, after the
    whole stage has already spent hours.  Fixing it here keeps the failure
    cheap and gives Stage 12 a runnable file.
    """
    if llm is None:
        return files
    issues = _entrypoint_issues(files.get("main.py", ""))
    if not issues:
        return files

    logger.warning(
        "Stage 10: entrypoint contract unmet (%s); generating main.py",
        "; ".join(issues),
    )
    code = _generate_entrypoint(
        llm, pm, topic=topic, metric=metric, files=files, exp_plan=exp_plan,
    )
    if not code:
        # B-30: last resort — a thin driver over an existing entry function.
        code = synthesize_entrypoint(files, metric) or ""
        if code:
            logger.warning(
                "Stage 10: using auto-generated entrypoint driver over "
                "existing modules"
            )
        else:
            logger.error(
                "Stage 10: dedicated entrypoint generation failed and no "
                "module exposes an entry function (%s)",
                "; ".join(_entrypoint_issues(files.get("main.py", ""))),
            )
            return files

    files["main.py"] = code
    try:
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text(code, encoding="utf-8")
    except OSError as exc:
        logger.warning("Stage 10: could not write generated main.py: %s", exc)
    try:
        _append_progress_step(
            exp_dir.parent,
            step_id="entrypoint",
            variant="stage",
            status="done",
            inputs_digest=_progress_digest(topic + "\n---\n" + metric),
            outputs={"main.py": _progress_digest(code)},
        )
    except Exception:  # noqa: BLE001 - journal is best-effort
        logger.debug("could not journal stage entrypoint", exc_info=True)
    return files


def _missing_symbols_by_file(
    failures: list[Any],
) -> dict[str, list[str]]:
    """Turn symbol-contract failures into ``{file: [symbol, ...]}``."""
    missing: dict[str, list[str]] = {}
    for failure in failures:
        detail = str(getattr(failure, "detail", "") or "")
        for item in detail.split(":", 1)[-1].split(","):
            name, _, symbol = item.strip().partition(":")
            if name.strip() and symbol.strip():
                missing.setdefault(name.strip(), []).append(symbol.strip())
    return missing


def _ensure_symbol_contract(
    files: dict[str, str],
    *,
    stage_dir: Path,
    exp_dir: Path,
    llm: LLMClient | None,
    pm: PromptManager,
    topic: str,
) -> dict[str, str]:
    """P-229: re-check the symbol contract after late entrypoint rewrites.

    ``_ensure_entrypoint`` and the alignment regen run *after* the earlier
    symbol checks, so run M shipped a main.py missing four declared symbols
    and only the exit gate noticed.  One targeted repair is attempted here;
    a second failure is deliberately left to the exit gate.
    """
    if llm is None:
        return files
    blueprint = load_blueprint(stage_dir)
    if not blueprint:
        return files
    failures = check_symbol_contract(blueprint, files)
    if not failures:
        return files

    missing = _missing_symbols_by_file(failures)
    if not missing:
        return files
    logger.warning(
        "Stage 10: symbol contract broken after late rewrite: %s",
        "; ".join(
            f"{name}: {', '.join(symbols)}" for name, symbols in missing.items()
        ),
    )
    affected = {name for name in missing if name in files}
    code_ctx = "\n\n".join(
        f"```filename:{name}\n{files[name]}\n```" for name in sorted(affected)
    )
    wanted = "\n".join(
        f"- {name}: {', '.join(symbols)}"
        for name, symbols in sorted(missing.items())
    )
    prompt = (
        "The delivered code is missing symbols declared in the architecture "
        "blueprint.\n\n"
        "## Missing symbols\n"
        f"{wanted}\n\n"
        "## Current files\n"
        f"{code_ctx}\n\n"
        "## Rules\n"
        "1. Add every missing symbol with a real implementation\n"
        "2. Keep all existing classes/functions unchanged\n"
        "3. Output the complete corrected file(s) as ```filename:xxx.py```\n"
    )
    resp = _chat_with_prompt(
        llm, pm.system("code_generation"), prompt, max_tokens=16384,
    )
    truncated = bool(getattr(resp, "truncated", False)) or (
        getattr(resp, "finish_reason", "") == "length"
    )
    if truncated:
        logger.warning(
            "Stage 10: symbol repair truncated — retrying with 32768"
        )
        resp = _chat_with_prompt(
            llm, pm.system("code_generation"), prompt, max_tokens=32768,
        )
    repaired = _extract_valid_repair_files(resp.content, set(files))
    merged = _merge_repair_files(files, repaired)
    remaining = check_symbol_contract(blueprint, merged)
    try:
        _record_repair_trace(
            stage_dir,
            phase="symbol_contract",
            prompt=prompt,
            response=resp.content,
            model=str(getattr(resp, "model", "") or ""),
            truncated=getattr(resp, "truncated", None),
            accepted=sorted(repaired),
            rejected=sorted(set(affected) - set(repaired)),
            reason="repaired" if not remaining else "still_missing",
            extra={
                "missing": missing,
                "remaining": [
                    str(getattr(item, "detail", "")) for item in remaining
                ],
            },
        )
    except Exception:  # noqa: BLE001 - trace is best-effort
        logger.debug("could not record symbol repair", exc_info=True)
    if remaining:
        logger.error(
            "Stage 10: symbol contract still broken after one repair: %s",
            "; ".join(str(getattr(item, "detail", "")) for item in remaining),
        )
        return files
    for name, code in repaired.items():
        try:
            exp_dir.mkdir(parents=True, exist_ok=True)
            safe_join(exp_dir, name).write_text(code, encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Stage 10: could not write symbol repair for %s: %s", name, exc,
            )
    logger.info(
        "Stage 10: symbol contract restored by targeted repair (%s)",
        ", ".join(sorted(repaired)),
    )
    return merged


# Improvement G: Continuous-action environments that are incompatible with DQN
_CONTINUOUS_ENVS = {
    "pendulum", "halfcheetah", "hopper", "walker2d", "ant", "humanoid",
    "swimmer", "reacher", "invertedpendulum", "inverteddoublependulum",
    "mountaincarcontinuous", "lunarlander-continuous",
}

# Deep-validation warnings that block delivery (P-220).  Kept in one place so
# the "before" and "after repair" counts cannot drift apart.
_DEEP_CRITICAL_KEYWORDS = (
    "UnboundLocalError", "unregistered", "does not exist",
    "empty or trivial subclass", "does NOT override",
    "Import-usage mismatch", "NameError",
    "was removed", "ptp()",
    "copy-paste", "identical method signatures",
    "identical AST", "NOT a real ablation",
    "shadows stdlib/pip",
)


def _critical_deep(warnings: list[str]) -> list[str]:
    """Subset of deep-validation warnings that must be repaired."""
    return [
        w for w in warnings
        if any(keyword in w for keyword in _DEEP_CRITICAL_KEYWORDS)
    ]


def _deep_repair_counts(
    before: list[str], after: list[str],
) -> tuple[int, int]:
    """``(fixed, remaining)`` after one deep-repair cycle.

    A repair can *introduce* warnings (the model rewrites a file and trips a
    new check), so ``len(before) - len(after)`` went negative in run J
    (``fixed -14/3``).  ``fixed`` is clamped at 0 and ``remaining`` is
    reported separately instead of pretending the delta is a success count.
    """
    before_critical = _critical_deep(before)
    remaining = len(_critical_deep(after))
    fixed = max(0, len(before_critical) - remaining)
    return fixed, remaining


def _execute_collider_plan_generation(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Stage 10 (collider_agent mode): generate a ColliderAgent physics prompt.

    Reads the experiment design plan from Stage 9 and uses the LLM to
    translate it into a detailed ColliderAgent-compatible Markdown prompt
    (similar to ``paper-reproduction/*/prompt_figure_N.md``).

    The generated prompt is saved as ``collider_plan.md`` in the stage
    directory.  Stage 12 reads this file and invokes Claude Code with the
    ColliderAgent skills to execute the full physics pipeline.
    """
    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    hypothesis = _read_prior_artifact(run_dir, "hypotheses.json") or ""
    topic = config.research.topic

    # System prompt: instruct LLM to produce a ColliderAgent-style prompt
    system_prompt = (
        "You are a particle physics expert generating a detailed execution plan for "
        "the ColliderAgent framework. ColliderAgent uses Claude Code to orchestrate "
        "the full collider phenomenology pipeline:\n"
        "  1. FeynRules model generation from a Lagrangian\n"
        "  2. UFO export for MadGraph5\n"
        "  3. MadGraph5 event generation with Pythia8/Delphes\n"
        "  4. MadAnalysis5 analysis\n"
        "  5. Numerical post-processing and figure generation\n\n"
        "The execution plan must follow this Markdown structure:\n"
        "  # 1. Target\n"
        "  (what figure/result to produce)\n"
        "  # 2. Model\n"
        "  ## 2.1 Lagrangian\n"
        "  ## 2.2 Parameters\n"
        "  ## 2.3 Particles\n"
        "  # 3. Collider Process\n"
        "  ## 3.1 Signal Process\n"
        "  ## 3.2 Background Process (if any)\n"
        "  # 4. Numerical Analysis\n"
        "  (step-by-step procedure)\n\n"
        "Be as precise as possible with formulas, parameter values, and analysis steps. "
        "If the topic does not have a defined Lagrangian or specific HEP process, "
        "generate an equivalent phenomenological study appropriate for the topic. "
        "If MadGraph/Monte Carlo is not needed (pure numerical analysis), skip those steps "
        "and describe only the post-processing steps."
    )
    user_prompt = (
        f"Research topic: {topic}\n\n"
        f"Experiment design plan:\n{exp_plan}\n\n"
        f"Hypotheses:\n{hypothesis}\n\n"
        "Generate a detailed ColliderAgent execution plan as a Markdown document."
    )

    collider_plan: str
    if llm is not None:
        try:
            resp = _chat_with_prompt(llm, system_prompt, user_prompt, max_tokens=4096)
            collider_plan = resp.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stage 10 (collider_agent): LLM call failed (%s) — using fallback plan", exc)
            collider_plan = _fallback_collider_plan(topic, exp_plan)
    else:
        collider_plan = _fallback_collider_plan(topic, exp_plan)

    # Write the plan
    plan_path = stage_dir / "collider_plan.md"
    plan_path.write_text(collider_plan, encoding="utf-8")
    logger.info("Stage 10 (collider_agent): wrote physics prompt to %s", plan_path)

    # Also write a metadata file
    import json as _json
    meta = {
        "generated": _utcnow_iso(),
        "mode": "collider_agent",
        "topic": topic,
        "plan_file": "collider_plan.md",
        "plan_length_chars": len(collider_plan),
    }
    (stage_dir / "collider_meta.json").write_text(
        _json.dumps(meta, indent=2), encoding="utf-8"
    )

    # Satisfy Stage 10 contract (output_files requires "experiment/" and
    # "experiment_spec.md").  In collider_agent mode there is no Python
    # experiment; instead we place the ColliderAgent prompt inside the
    # experiment/ directory so downstream contract validation passes.
    exp_dir = stage_dir / "experiment"
    exp_dir.mkdir(exist_ok=True)
    (exp_dir / "collider_plan.md").write_text(collider_plan, encoding="utf-8")

    spec_md = (
        f"# Experiment Specification (collider_agent mode)\n\n"
        f"**Topic:** {topic}\n\n"
        f"**Backend:** ColliderAgent — full HEP pipeline via Claude Code\n\n"
        f"**Physics plan:** `collider_plan.md`\n\n"
        f"Stage 12 will invoke the Claude Code CLI with the ColliderAgent skills\n"
        f"to execute the Lagrangian → FeynRules → UFO → MadGraph5 → Delphes →\n"
        f"MadAnalysis5 pipeline and produce publication-quality figures.\n"
    )
    (stage_dir / "experiment_spec.md").write_text(spec_md, encoding="utf-8")

    return StageResult(
        stage=Stage.CODE_GENERATION,
        status=StageStatus.DONE,
        artifacts=("collider_plan.md", "collider_meta.json", "experiment/", "experiment_spec.md"),
        evidence_refs=("stage-10/collider_plan.md",),
    )


def _fallback_collider_plan(topic: str, exp_plan: str) -> str:
    """Generate a minimal fallback ColliderAgent prompt when LLM is unavailable."""
    return f"""# 1. Target

Investigate the following physics topic using the ColliderAgent pipeline:
**{topic}**

{exp_plan or "Execute the relevant collider phenomenology analysis and generate exclusion contours or kinematic distributions as appropriate."}

---

# 2. Model

## 2.1 Lagrangian

Use the Standard Model as baseline. For beyond-SM contributions,
refer to the experiment design plan above.

## 2.2 Parameters

Use SM parameters. Scan over new-physics parameters as described in the plan.

## 2.3 Particles

Use standard SM particles.

---

# 3. Collider Process

## 3.1 Signal Process

Run the relevant signal processes at the LHC (√s = 13 TeV).

---

# 4. Numerical Analysis

## Step 1: Execute the phenomenology pipeline
Follow the experiment design plan to produce the required figures and results.

## Step 2: Generate output figures
Save all figures to output/figures/ in PDF and PNG format.
"""


def _check_rl_compatibility(code: str) -> list[str]:
    """Detect DQN + continuous-action environment mismatches.

    Returns a list of error strings if incompatible combinations are found.
    """
    errors: list[str] = []
    code_lower = code.lower()
    has_dqn = "dqn" in code_lower
    if not has_dqn:
        return errors

    for env_name in _CONTINUOUS_ENVS:
        if env_name in code_lower:
            errors.append(
                f"RL COMPATIBILITY ERROR: DQN is used with continuous-action "
                f"environment '{env_name}'. DQN only works with DISCRETE action "
                f"spaces. Use SAC, TD3, or PPO instead."
            )
    return errors


_AGENT_PLAN_SPECS: dict[str, dict[str, str]] = {
    "biology_agent": {
        "plan_file": "biology_plan.md",
        "meta_file": "biology_meta.json",
        "label": "Biology-Agent",
        "structure": (
            "# 1. Target\n(metabolic phenotype / knockout effect to quantify)\n"
            "# 2. Organism and Model\n(GEM identifier, medium, constraints)\n"
            "# 3. Perturbations\n(gene/reaction knockouts, media swaps)\n"
            "# 4. Analysis\n(FBA / pFBA / FVA / production envelope steps)\n"
            "# 5. Outputs\n(results.json schema and figures)\n"
        ),
    },
    "stat_agent": {
        "plan_file": "stat_plan.md",
        "meta_file": "stat_meta.json",
        "label": "stat_research_agent",
        "structure": (
            "# 1. Target\n(estimand / hypothesis to test)\n"
            "# 2. Data\n(dataset, variables, sample size, cleaning rules)\n"
            "# 3. Model\n(statistical test or regression specification)\n"
            "# 4. Diagnostics\n(assumption checks, sensitivity analyses)\n"
            "# 5. Outputs\n(results.json schema and tables/figures)\n"
        ),
    },
    "agentic": {
        "plan_file": "agent_plan.md",
        "meta_file": "agent_meta.json",
        "label": "coding agent",
        "structure": (
            "# 1. Target\n(metric to optimise and acceptance threshold)\n"
            "# 2. Environment\n(image, dependencies, data, hardware)\n"
            "# 3. Procedure\n(ordered steps the agent should execute)\n"
            "# 4. Deliverables\n(code, logs, results.json schema)\n"
        ),
    },
}


def _execute_agent_plan_generation(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    mode: str,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    """Stage 10 for agent-backed experiment modes.

    These modes execute an end-to-end agent session in Stage 12 instead of
    running generated Python, so Stage 10 only has to produce a precise
    natural-language plan. No Python project is generated.
    """
    spec = _AGENT_PLAN_SPECS[mode]
    plan_file = spec["plan_file"]
    label = spec["label"]

    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    hypotheses = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    topic = config.research.topic

    system_prompt = (
        f"You are an expert research engineer writing an execution plan for the "
        f"{label}. The agent runs the full experiment end to end, so the plan "
        f"must be self-contained and operational.\n\n"
        f"Use exactly this Markdown structure:\n{spec['structure']}\n"
        "Be concrete about parameters, datasets, and expected outputs. "
        "The agent must write all numerical results to results.json in the "
        "workspace root."
    )
    user_prompt = (
        f"Research topic: {topic}\n\n"
        f"Experiment design plan:\n{exp_plan}\n\n"
        f"Hypotheses:\n{hypotheses}\n\n"
        f"Write the {label} execution plan."
    )

    plan_text = ""
    if llm is not None:
        try:
            resp = _chat_with_prompt(llm, system_prompt, user_prompt, max_tokens=4096)
            plan_text = resp.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Stage 10 (%s): LLM call failed (%s) — using fallback plan",
                mode,
                exc,
            )
    if not plan_text:
        plan_text = (
            f"# 1. Target\n\nExecute the following research topic end to end:\n"
            f"**{topic}**\n\n{exp_plan}\n\n"
            f"# Execution\n\nFollow the experiment design plan above, run the "
            f"analysis with the {label}, and write all numerical results to "
            f"`results.json` in the workspace root.\n"
        )

    safe_join(stage_dir, plan_file).write_text(plan_text, encoding="utf-8")
    safe_join(stage_dir, spec["meta_file"]).write_text(
        json.dumps(
            {
                "generated": _utcnow_iso(),
                "mode": mode,
                "topic": topic,
                "plan_file": plan_file,
                "plan_length_chars": len(plan_text),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Stage 10's contract requires experiment/ + experiment_spec.md even when
    # no Python project exists; mirror the collider_agent convention.
    exp_dir = stage_dir / "experiment"
    exp_dir.mkdir(exist_ok=True)
    safe_join(exp_dir, plan_file).write_text(plan_text, encoding="utf-8")

    (stage_dir / "experiment_spec.md").write_text(
        f"# Experiment Specification ({mode} mode)\n\n"
        f"**Topic:** {topic}\n\n"
        f"**Backend:** {label} — full session executed in Stage 12\n\n"
        f"**Plan:** `{plan_file}`\n\n"
        "Stage 12 passes this plan to the agent sandbox, which writes "
        "`results.json` in its workspace. No Python source is generated here.\n",
        encoding="utf-8",
    )

    return StageResult(
        stage=Stage.CODE_GENERATION,
        status=StageStatus.DONE,
        artifacts=(plan_file, spec["meta_file"], "experiment/", "experiment_spec.md"),
        evidence_refs=(f"stage-10/{plan_file}",),
    )


def _try_cli_code_agent(
    config: RCConfig,
    llm: Any | None,
    prompts: Any | None,
    *,
    stage_dir: Path,
    run_dir: Path,
    topic: str,
    exp_plan: str,
    metric: str,
    pkg_hint: str,
    compute_budget: str,
    extra_guidance: str,
) -> dict[str, str] | None:
    """Run the explicitly configured CLI code agent, or return None.

    ``provider == "llm"`` keeps the existing pipeline untouched. Any failure
    is logged to ``cli_agent_log.json`` and returns None so the caller can
    fall back to Beast Mode / multi-phase CodeAgent / legacy single-shot.
    """
    agent_cfg = getattr(config.experiment, "cli_agent", None)
    provider = (getattr(agent_cfg, "provider", "") or "llm").strip().lower()
    if provider == "llm":
        return None

    from researchclaw.experiment.code_agent import create_code_agent

    log: dict[str, Any] = {
        "provider": provider,
        "ok": False,
        "files": [],
        "elapsed_sec": 0.0,
        "error": None,
        "generated": _utcnow_iso(),
        # A1-9：回填本次实际使用的 provider 会话（id / resumed）。
        "session": None,
    }

    def _write_log() -> None:
        (stage_dir / "cli_agent_log.json").write_text(
            json.dumps(log, indent=2), encoding="utf-8"
        )

    try:
        agent = create_code_agent(
            config, llm=llm, prompts=prompts,
            session_ctx=(run_dir, int(Stage.CODE_GENERATION)),
        )
        result = agent.generate(
            exp_plan=exp_plan,
            topic=topic,
            metric_key=metric,
            pkg_hint=pkg_hint,
            compute_budget=compute_budget,
            extra_guidance=extra_guidance,
            workdir=stage_dir / "cli_agent_workspace",
            timeout_sec=int(getattr(agent_cfg, "timeout_sec", 600) or 600),
        )
    except Exception as exc:  # noqa: BLE001 - optional backend must not abort Stage 10
        logger.warning(
            "CLI code agent (%s) failed: %s; falling back to LLM path",
            provider,
            exc,
        )
        log["error"] = str(exc)
        _write_log()
        return None

    log.update(
        {
            "ok": bool(result.ok) and bool(result.files),
            "files": sorted(result.files),
            "elapsed_sec": round(result.elapsed_sec, 2),
            "error": result.error,
            "raw_output_tail": (result.raw_output or "")[-1000:],
            "session": getattr(result, "session_info", None),
        }
    )
    _write_log()

    if not result.ok or not result.files:
        logger.warning(
            "CLI code agent (%s) produced no usable files (%s); falling back",
            provider,
            result.error or "empty files",
        )
        return None

    logger.info(
        "CLI code agent (%s): %d files in %.1fs",
        provider,
        len(result.files),
        result.elapsed_sec,
    )
    return dict(result.files)


def _execute_code_generation(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    # ── ColliderAgent mode: generate a physics prompt instead of Python code ─
    if config.experiment.mode == "collider_agent":
        return _execute_collider_plan_generation(
            stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts
        )
    # ── End ColliderAgent bypass ──────────────────────────────────────────────

    # ── Other agent-backed modes: generate an execution plan, not Python ─────
    if config.experiment.mode in _AGENT_PLAN_SPECS:
        return _execute_agent_plan_generation(
            stage_dir,
            run_dir,
            config,
            adapters,
            mode=config.experiment.mode,
            llm=llm,
            prompts=prompts,
        )
    # ── End agent plan bypass ─────────────────────────────────────────────────

    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    metric = config.experiment.metric_key
    max_repair = 5  # BUG-14: Increased from 3 to give more chances for critical bugs
    files: dict[str, str] = {}
    validation_log: list[str] = []

    # --- Detect available packages for sandbox ---
    _pm = prompts or PromptManager()

    # --- Hardware-aware package hint ---
    hw_profile = _load_hardware_profile(run_dir)
    if config.experiment.mode in ("sandbox", "docker"):
        if config.experiment.mode == "docker":
            pkg_prefix = "docker mode"
            _net_policy = config.experiment.docker.network_policy
            _base_pkgs = (
                ", torchvision, torchaudio, matplotlib, seaborn, scipy, "
                "tqdm, torchdiffeq, gymnasium, networkx, PyYAML, Pillow, "
                "transformers, datasets, accelerate, peft, bitsandbytes, "
                "timm, einops, torchmetrics, h5py"
            )
            if _net_policy == "none":
                pkg_extras = _base_pkgs + " (ONLY pre-installed packages — NO pip install available)"
            elif _net_policy in ("setup_only", "pip_only"):
                pkg_extras = _base_pkgs + ", and additional pip-installable packages via requirements.txt"
            else:
                pkg_extras = _base_pkgs + ", and additional pip-installable packages (auto-detected from imports)"
        else:
            pkg_prefix = "sandbox mode"
            pkg_extras = ""
        if hw_profile and hw_profile.get("has_gpu"):
            gpu_type = hw_profile.get("gpu_type", "cuda")
            gpu_name = hw_profile.get("gpu_name", "GPU")
            tier = hw_profile.get("tier", "limited")
            if tier == "high":
                device_hint = f"torch.device('{gpu_type}')"
                pkg_hint = (
                    f"\nAVAILABLE PACKAGES ({pkg_prefix}): Python stdlib, numpy, torch, sklearn, scipy, pandas{pkg_extras}.\n"
                    f"GPU: {gpu_name} ({gpu_type}). You MAY use PyTorch with GPU acceleration.\n"
                    f"Use `device = {device_hint}` for tensor operations.\n"
                )
            else:  # limited (low VRAM NVIDIA or MPS)
                device_hint = f"torch.device('{gpu_type}')"
                pkg_hint = (
                    f"\nAVAILABLE PACKAGES ({pkg_prefix}): Python stdlib, numpy, torch, sklearn, scipy, pandas{pkg_extras}.\n"
                    f"GPU: {gpu_name} ({gpu_type}) — LIMITED performance.\n"
                    f"Use `device = {device_hint}` but design LIGHTWEIGHT experiments:\n"
                    f"- Small models (<1M parameters)\n"
                    f"- Few epochs (<=20)\n"
                    f"- Small datasets (<=10K samples)\n"
                    f"- Avoid large batch sizes\n"
                )
        else:
            pkg_hint = _pm.block("pkg_hint_sandbox")
    else:
        pkg_hint = ""

    # --- Compute budget hint ---
    time_budget_sec = config.experiment.time_budget_sec
    try:
        compute_budget = _pm.block("compute_budget").replace(
            "{time_budget_sec}", str(time_budget_sec)
        )
    except Exception:  # noqa: BLE001
        compute_budget = (
            f"\n## Compute Budget Constraint\n"
            f"- Total execution time limit: {time_budget_sec} seconds\n"
            f"- Design experiments that complete within this budget\n"
            f"- Implement a time guard: stop gracefully at 80% of budget\n"
        )

    # --- Dataset guidance + setup script + HP reporting (docker/sandbox modes) ---
    extra_guidance = ""
    _net_policy = getattr(getattr(config, "docker", None), "network_policy", "setup_only")
    if config.experiment.mode in ("sandbox", "docker"):
        _net_policy = (
            config.experiment.docker.network_policy
            if config.experiment.mode == "docker"
            else "none"  # sandbox mode has no network
        )
        if _net_policy == "none":
            # Network disabled: inject strict offline-only guidance
            try:
                extra_guidance += _pm.block("network_disabled_guidance")
            except Exception:  # noqa: BLE001
                pass
        elif _net_policy == "full":
            try:
                extra_guidance += _pm.block("dataset_guidance")
                extra_guidance += _pm.block("network_full_guidance")
            except Exception:  # noqa: BLE001
                pass
        else:
            # setup_only or pip_only — existing behavior
            try:
                extra_guidance += _pm.block("dataset_guidance")
            except Exception:  # noqa: BLE001
                pass
            if config.experiment.mode == "docker":
                try:
                    extra_guidance += _pm.block("setup_script_guidance")
                except Exception:  # noqa: BLE001
                    pass
        try:
            extra_guidance += _pm.block("hp_reporting")
        except Exception:  # noqa: BLE001
            pass
        # I-06: Multi-seed enforcement for all experiments
        try:
            extra_guidance += _pm.block("multi_seed_enforcement")
        except Exception:  # noqa: BLE001
            pass

    # --- BA: Inject BenchmarkAgent plan from Stage 9 ---
    _bp_path = None
    for _s9_dir in sorted(run_dir.glob("stage-09*"), reverse=True):
        _candidate = _s9_dir / "benchmark_plan.json"
        if _candidate.exists():
            _bp_path = _candidate
            break
    if _bp_path is not None:
        try:
            import json as _json_bp
            _bp_data = _json_bp.loads(_bp_path.read_text(encoding="utf-8"))
            # Reconstruct the prompt block
            from researchclaw.agents.benchmark_agent.orchestrator import BenchmarkPlan
            _bp = BenchmarkPlan(
                selected_benchmarks=_bp_data.get("selected_benchmarks", []),
                selected_baselines=_bp_data.get("selected_baselines", []),
                data_loader_code=_bp_data.get("data_loader_code", ""),
                baseline_code=_bp_data.get("baseline_code", ""),
                experiment_notes=_bp_data.get("experiment_notes", ""),
            )
            _bp_block = _bp.to_prompt_block()
            if _bp_block:
                extra_guidance += (
                    "\n\n## BenchmarkAgent Selections (USE THESE)\n"
                    "The following datasets, baselines, and code snippets were "
                    "automatically selected and validated by the BenchmarkAgent. "
                    "You MUST use these selections in your experiment code.\n\n"
                    + _bp_block
                )
                logger.info(
                    "BA: Injected benchmark plan (%d benchmarks, %d baselines)",
                    len(_bp.selected_benchmarks), len(_bp.selected_baselines),
                )
        except Exception as _bp_exc:
            logger.debug("BA: Failed to load benchmark plan: %s", _bp_exc)

    # --- P2.2+P2.3: LLM training topic detection and guidance ---
    _llm_keywords = (
        "language model", "llm", "fine-tun", "lora", "qlora", "peft",
        "instruction tun", "rlhf", "dpo", "sft", "alignment",
        "transformer train", "causal lm", "chat model", "qwen", "llama",
        "mistral", "phi-", "gemma", "pretraining", "tokeniz",
    )
    topic_lower = config.research.topic.lower()
    is_llm_topic = any(kw in topic_lower for kw in _llm_keywords)

    # --- I-08: RL topic detection and step guidance ---
    _rl_keywords = (
        "reinforcement learning", "policy gradient", "ppo", "sac", "td3",
        "ddpg", "dqn", "a2c", "a3c", "mujoco", "locomotion", "continuous control",
        "reward shaping", "exploration", "multi-agent rl", "marl", "curriculum rl",
        "imitation learning", "inverse rl", "offline rl", "model-based rl",
        "actor-critic", "reinforce", "gym", "gymnasium",
    )
    is_rl_topic = any(kw in topic_lower for kw in _rl_keywords)
    if is_rl_topic:
        try:
            extra_guidance += _pm.block("rl_step_guidance")
        except Exception:  # noqa: BLE001
            pass

    # --- F-01: Framework API doc injection (auto-detected) ---
    try:
        from researchclaw.data import detect_frameworks, load_framework_docs
        _hypothesis_text = _read_prior_artifact(run_dir, "hypotheses.md") or ""
        _fw_ids = detect_frameworks(
            config.research.topic, _hypothesis_text, exp_plan or ""
        )
        if _fw_ids:
            _fw_docs = load_framework_docs(_fw_ids, max_chars=8000)
            if _fw_docs:
                extra_guidance += _fw_docs
                logger.info("F-01: Injected framework docs for: %s", _fw_ids)
    except Exception:  # noqa: BLE001
        logger.debug("F-01: Framework doc injection skipped", exc_info=True)

    if is_llm_topic and config.experiment.mode == "docker":
        try:
            extra_guidance += _pm.block("llm_training_guidance")
        except Exception:  # noqa: BLE001
            pass
        try:
            extra_guidance += _pm.block("llm_eval_guidance")
        except Exception:  # noqa: BLE001
            pass
        # P2.3: Warn if time budget is too short for LLM training
        if time_budget_sec < 3600:
            extra_guidance += (
                "\n## COMPUTE BUDGET WARNING\n"
                f"Current time_budget_sec={time_budget_sec} is likely TOO SHORT "
                f"for LLM fine-tuning. Typical LoRA training needs 1-4 hours. "
                f"Design a LIGHTWEIGHT experiment:\n"
                f"- Use a small dataset (<=5000 samples)\n"
                f"- Train for 1-3 epochs only\n"
                f"- Use small batch size (1-2) with gradient accumulation\n"
                f"- Use 4-bit quantization (QLoRA) to minimize memory\n"
                f"- Limit max_seq_length to 512-1024\n"
                f"- If possible, use a smaller model (<=7B parameters)\n"
            )

    # --- Domain-specific guidance injection for non-ML domains ---
    try:
        from researchclaw.domains.detector import detect_domain as _dd_s10, is_ml_domain as _is_ml_s10
        _dp = _dd_s10(topic=config.research.topic)
        if not _is_ml_s10(_dp):
            from researchclaw.domains.prompt_adapter import get_adapter as _ga
            _adapter = _ga(_dp)
            _blocks = _adapter.get_code_generation_blocks({})
            if _blocks.compute_budget:
                compute_budget = _blocks.compute_budget
            if _blocks.dataset_guidance:
                extra_guidance = _blocks.dataset_guidance + "\n" + extra_guidance
            if _blocks.code_generation_hints:
                extra_guidance += "\n" + _blocks.code_generation_hints
            if _blocks.output_format_guidance:
                extra_guidance += "\n" + _blocks.output_format_guidance
            logger.info("Injected domain-specific guidance for %s", _dp.domain_id)
    except Exception:  # noqa: BLE001
        logger.debug("Domain guidance injection skipped", exc_info=True)

    # BUG-R6-01: Add explicit implementation constraints to prevent LLM
    # from substituting unrelated DL models for lightweight algorithms.
    extra_guidance += (
        "\n\nIMPLEMENTATION CONSTRAINTS (MUST FOLLOW):\n"
        "- Implement EXACTLY the algorithm/method described in the topic.\n"
        "- Do NOT replace the stated method with a deep-learning proxy "
        "(e.g. ResNet, BERT, GPT, Gymnasium+SB3) unless the topic "
        "EXPLICITLY requires deep learning.\n"
        "- Prefer lightweight CPU-friendly libraries (numpy, scipy, "
        "sklearn, pandas) unless deep learning is inherent to the topic.\n"
        "- The experiment MUST be self-contained and runnable without GPU.\n"
    )

    # --- Code generation: explicit CLI provider → Beast Mode → CodeAgent → Legacy ---
    _code_agent_active = False
    _beast_mode_used = False
    _cli_agent_used = False
    _code_max_tokens = 8192

    # ── Explicit CLI code agent (opt-in via experiment.cli_agent.provider) ──
    _cli_files = _try_cli_code_agent(
        config,
        llm,
        prompts,
        stage_dir=stage_dir,
        run_dir=run_dir,
        topic=config.research.topic,
        exp_plan=exp_plan,
        metric=metric,
        pkg_hint=pkg_hint,
        compute_budget=compute_budget,
        extra_guidance=extra_guidance,
    )
    if _cli_files:
        files = _cli_files
        _cli_agent_used = True
        _code_agent_active = True  # Phase-5 review is LLM-specific; skip it

    # ── Beast Mode: OpenCode external agent (optional) ─────────────────
    _oc_cfg = config.experiment.opencode
    if not _cli_agent_used and _oc_cfg.enabled:
        from researchclaw.pipeline.opencode_bridge import (
            OpenCodeBridge,
            OpenCodeResult,
            count_historical_failures,
            score_complexity,
        )

        _hist_failures = count_historical_failures(run_dir)
        _cplx = score_complexity(
            exp_plan=exp_plan,
            topic=config.research.topic,
            historical_failures=_hist_failures,
            threshold=_oc_cfg.complexity_threshold,
        )

        # Persist complexity analysis
        (stage_dir / "complexity_analysis.json").write_text(
            json.dumps(
                {
                    "score": _cplx.score,
                    "signals": _cplx.signals,
                    "recommendation": _cplx.recommendation,
                    "reason": _cplx.reason,
                    "threshold": _oc_cfg.complexity_threshold,
                    "historical_failures": _hist_failures,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if _cplx.recommendation == "beast_mode":
            _proceed = _oc_cfg.auto
            if not _proceed:
                # Non-auto mode: check for HITL adapter
                if adapters.hitl is not None:
                    try:
                        _proceed = adapters.hitl.confirm(
                            f"Beast Mode: complexity={_cplx.score:.2f} "
                            f"(threshold={_oc_cfg.complexity_threshold}). "
                            f"Route to OpenCode?"
                        )
                    except Exception:  # noqa: BLE001
                        logger.info(
                            "Beast mode: HITL adapter unavailable, skipping "
                            "(set opencode.auto=true for non-interactive runs)"
                        )
                else:
                    logger.info(
                        "Beast mode: no HITL adapter, skipping "
                        "(set opencode.auto=true for non-interactive runs)"
                    )

            if _proceed:
                _oc_model = _oc_cfg.model or config.llm.primary_model
                _bridge = OpenCodeBridge(
                    model=_oc_model,
                    llm_base_url=config.llm.base_url,
                    api_key_env=config.llm.api_key_env,
                    llm_provider=config.llm.provider,
                    timeout_sec=_oc_cfg.timeout_sec,
                    max_retries=_oc_cfg.max_retries,
                    workspace_cleanup=_oc_cfg.workspace_cleanup,
                )

                logger.info(
                    "Beast mode: ENGAGED (complexity=%.2f, model=%s)",
                    _cplx.score,
                    _oc_model,
                )

                _oc_result: OpenCodeResult = _bridge.generate(
                    stage_dir=stage_dir,
                    topic=config.research.topic,
                    exp_plan=exp_plan,
                    metric=metric,
                    pkg_hint=pkg_hint + "\n" + compute_budget,
                    extra_guidance=extra_guidance,
                    time_budget_sec=config.experiment.time_budget_sec,
                )

                # Persist beast mode log
                (stage_dir / "beast_mode_log.json").write_text(
                    json.dumps(
                        {
                            "success": _oc_result.success,
                            "elapsed_sec": _oc_result.elapsed_sec,
                            "files": list(_oc_result.files.keys()),
                            "error": _oc_result.error,
                            "complexity_score": _cplx.score,
                            "model": _oc_model,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                if _oc_result.success and _oc_result.files:
                    files = _oc_result.files
                    _beast_mode_used = True
                    _code_agent_active = True  # skip legacy path
                    logger.info(
                        "Beast mode: SUCCESS — %d files in %.1fs",
                        len(files),
                        _oc_result.elapsed_sec,
                    )
                else:
                    logger.warning(
                        "Beast mode: FAILED (%s) — falling back to CodeAgent",
                        _oc_result.error or "unknown error",
                    )
        else:
            logger.info(
                "Beast mode: complexity=%.2f (threshold=%.2f), not triggered",
                _cplx.score,
                _oc_cfg.complexity_threshold,
            )

    if (
        not _cli_agent_used
        and not _beast_mode_used
        and config.experiment.code_agent.enabled
        and llm is not None
    ):
        # ── F-02: Advanced Code Agent path ────────────────────────────────
        from researchclaw.pipeline.code_agent import CodeAgent as _CodeAgent

        _ca_cfg = config.experiment.code_agent
        # Ensure we have a proper config object
        if not hasattr(_ca_cfg, "enabled"):
            from researchclaw.pipeline.code_agent import (
                CodeAgentConfig as _CAConfig,
            )
            _ca_cfg = _CAConfig()

        # Sandbox factory (only for sandbox/docker modes)
        _sandbox_factory = None
        if config.experiment.mode in ("sandbox", "docker"):
            from researchclaw.experiment.factory import (
                create_sandbox as _csb,
            )
            _sandbox_factory = _csb

        if any(
            config.llm.primary_model.startswith(p)
            for p in ("gpt-5", "o3", "o4")
        ):
            _code_max_tokens = 16384

        # ── Domain detection + Code Search for non-ML domains ──────────
        _domain_profile = None
        _code_search_result = None
        try:
            from researchclaw.domains.detector import detect_domain as _dd
            from researchclaw.domains.detector import is_ml_domain as _is_ml
            _domain_profile = _dd(topic=config.research.topic)
            logger.info(
                "CodeAgent: domain=%s (%s)",
                _domain_profile.display_name,
                _domain_profile.domain_id,
            )
            # Run code search for non-ML domains (ML has enough built-in knowledge)
            if not _is_ml(_domain_profile):
                try:
                    from researchclaw.agents.code_searcher import CodeSearchAgent
                    _cs_agent = CodeSearchAgent(llm=llm)
                    _code_search_result = _cs_agent.search(
                        topic=config.research.topic,
                        domain=_domain_profile,
                    )
                    if _code_search_result and _code_search_result.patterns.has_content:
                        logger.info(
                            "Code search: %d patterns, %d repos found",
                            len(_code_search_result.patterns.api_patterns),
                            len(_code_search_result.repos_found),
                        )
                except Exception:  # noqa: BLE001
                    logger.debug("Code search unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.debug("Domain detection unavailable", exc_info=True)

        _agent = _CodeAgent(
            llm=llm,
            prompts=_pm,
            config=_ca_cfg,
            stage_dir=stage_dir,
            sandbox_factory=_sandbox_factory,
            experiment_config=config.experiment,
            domain_profile=_domain_profile,
            code_search_result=_code_search_result,
        )
        _agent_result = _agent.generate(
            topic=config.research.topic,
            exp_plan=exp_plan,
            metric=metric,
            pkg_hint=pkg_hint + "\n" + compute_budget + "\n" + extra_guidance,
            max_tokens=_code_max_tokens,
        )
        files = _agent_result.files
        _code_agent_active = True

        # Write agent artifacts
        (stage_dir / "code_agent_log.json").write_text(
            json.dumps(
                {
                    "log": _agent_result.validation_log,
                    "llm_calls": _agent_result.total_llm_calls,
                    "sandbox_runs": _agent_result.total_sandbox_runs,
                    "best_score": _agent_result.best_score,
                    "tree_nodes_explored": _agent_result.tree_nodes_explored,
                    "review_rounds": _agent_result.review_rounds,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        # P-230 (B-1): never overwrite the canonical blueprint with the raw
        # transport copy — run N's raw YAML failed to parse at the gate.
        if _agent_result.architecture_spec and load_blueprint(stage_dir) is None:
            (stage_dir / "architecture_spec.yaml").write_text(
                _agent_result.architecture_spec, encoding="utf-8",
            )
        logger.info(
            "CodeAgent: %d LLM calls, %d sandbox runs, score=%.2f",
            _agent_result.total_llm_calls,
            _agent_result.total_sandbox_runs,
            _agent_result.best_score,
        )
    elif not _cli_agent_used and not _beast_mode_used and llm is not None:
        # ── Legacy single-shot generation ─────────────────────────────────
        topic = config.research.topic
        _md = config.experiment.metric_direction
        _md_hint = (
            f"`{_md}` — use direction={'lower' if _md == 'minimize' else 'higher'} "
            f"in METRIC_DEF. You MUST NOT use the opposite direction."
        )
        _overlay = _get_evolution_overlay(run_dir, "code_generation")
        sp = _pm.for_stage(
            "code_generation",
            evolution_overlay=_overlay,
            topic=topic,
            metric=metric,
            pkg_hint=pkg_hint + "\n" + compute_budget + "\n" + extra_guidance,
            exp_plan=exp_plan,
            metric_direction_hint=_md_hint,
        )
        # R13-3: Use higher max_tokens for reasoning models (they consume tokens
        # for internal chain-of-thought). Retry once with even higher limit on empty.
        _code_max_tokens = sp.max_tokens or 8192
        if any(config.llm.primary_model.startswith(p) for p in ("gpt-5", "o3", "o4")):
            _code_max_tokens = max(_code_max_tokens, 16384)

        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=_code_max_tokens,
        )
        files = _extract_multi_file_blocks(resp.content)
        if not files and not resp.content.strip():
            # Empty response — retry with higher token limit
            logger.warning(
                "R13-3: Empty LLM response for code_generation (len=%d, "
                "finish_reason=%s, tokens=%d). Retrying with 32768 tokens.",
                len(resp.content),
                resp.finish_reason,
                resp.total_tokens,
            )
            resp = _chat_with_prompt(
                llm,
                sp.system,
                sp.user,
                json_mode=sp.json_mode,
                max_tokens=32768,
            )
            files = _extract_multi_file_blocks(resp.content)
        if not files:
            logger.warning(
                "R13-2: _extract_multi_file_blocks returned empty. "
                "LLM response length=%d, first 300 chars: %s",
                len(resp.content),
                resp.content[:300],
            )

    # --- Fallback: generic numerical experiment ---
    if not files:
        files = {
            "main.py": (
                "import numpy as np\n"
                "\n"
                "np.random.seed(42)\n"
                "\n"
                "# Fallback experiment: parameter sweep on a synthetic objective\n"
                "# This runs when LLM code generation fails to produce valid code.\n"
                "dim = 10\n"
                "n_conditions = 3\n"
                "results = {}\n"
                "\n"
                "for cond_idx in range(n_conditions):\n"
                "    cond_name = f'condition_{cond_idx}'\n"
                "    scores = []\n"
                "    for seed in range(3):\n"
                "        rng = np.random.RandomState(seed + cond_idx * 100)\n"
                "        x = rng.randn(dim)\n"
                "        score = float(1.0 / (1.0 + np.sum(x ** 2)))\n"
                "        scores.append(score)\n"
                "    mean_score = float(np.mean(scores))\n"
                "    results[cond_name] = mean_score\n"
                f"    print(f'condition={{cond_name}} {metric}: {{mean_score:.6f}}')\n"
                "\n"
                "best = max(results, key=results.get)\n"
                f"print(f'{metric}: {{results[best]:.6f}}')\n"
            )
        }

    # --- B-29: guarantee a runnable entrypoint before validating files ---
    # B-34 M6: the blueprint's metric is what the exit gate checks; prompting
    # the entrypoint with config.experiment.metric_key produced
    # ``metric_mismatch`` in run J.
    metric = resolve_metric(stage_dir, metric)
    files = _ensure_entrypoint(
        files,
        llm=llm,
        pm=_pm,
        topic=config.research.topic,
        metric=metric,
        exp_dir=stage_dir / "experiment",
        exp_plan=exp_plan,
    )
    # P-229: the entrypoint rewrite may drop declared symbols.
    files = _ensure_symbol_contract(
        files,
        stage_dir=stage_dir,
        exp_dir=stage_dir / "experiment",
        llm=llm,
        pm=_pm,
        topic=config.research.topic,
    )

    # --- Validate each file + auto-repair loop ---
    all_valid = True
    attempt = 0
    # Actual repairs performed per file; ``max_repair`` is only the limit.
    # The report used to print the limit, so an early abort (2 unusable
    # responses) was reported as "after 5 repairs".
    repair_counts: dict[str, int] = {}
    for fname, code in list(files.items()):
        # Skip non-Python files (requirements.txt, setup.py, etc.)
        if not fname.endswith(".py"):
            continue
        validation = validate_code(code)
        repair_attempt = 0
        # B-30: give up early when the model keeps returning unparseable code
        # instead of burning every repair slot on the same failure.
        invalid_returns = 0
        while not validation.ok and llm is not None and repair_attempt < max_repair:
            repair_attempt += 1
            attempt += 1
            repair_counts[fname] = repair_attempt
            # Only send errors to the LLM — warnings don't block validation
            # and confuse the LLM into over-correcting (e.g. removing runtime imports)
            errors_only = type(validation)(
                issues=[i for i in validation.issues if i.severity == "error"]
            )
            issues_text = format_issues_for_llm(errors_only)
            validation_log.append(
                f"File {fname} attempt {repair_attempt}: {validation.summary()}"
            )
            logger.info(
                "Code validation failed for %s (attempt %d/%d): %s",
                fname,
                repair_attempt,
                max_repair,
                validation.summary(),
            )
            _record_repair_trace(
                stage_dir,
                phase="validation_failed",
                file=fname,
                attempt=repair_attempt,
                max_attempts=max_repair,
                error_summary=validation.summary(),
                errors=validation.issues,
            )
            all_files_ctx = "\n\n".join(
                f"```filename:{f}\n{c}\n```" for f, c in files.items()
            )
            rp = _pm.sub_prompt(
                "code_repair",
                fname=fname,
                issues_text=issues_text,
                all_files_ctx=all_files_ctx,
            )
            resp = _chat_with_prompt(llm, rp.system, rp.user)
            _repaired = _extract_code_block(resp.content)
            _record_repair_trace(
                stage_dir,
                phase="repair_request",
                file=fname,
                attempt=repair_attempt,
                max_attempts=max_repair,
                prompt=rp.user,
                response=resp.content,
                model=str(getattr(resp, "model", "") or ""),
                truncated=getattr(resp, "truncated", None),
                extra={
                    "issues_text_sha256": _repair_digest(issues_text),
                    "issues_text_chars": len(issues_text),
                },
            )
            if _repaired.strip() and _is_parseable(_repaired):
                files[fname] = _repaired
                invalid_returns = 0
                _record_repair_trace(
                    stage_dir,
                    phase="repair_accepted",
                    file=fname,
                    attempt=repair_attempt,
                    max_attempts=max_repair,
                    accepted=[fname],
                )
            elif _repaired.strip():
                invalid_returns += 1
                logger.warning(
                    "Repair attempt returned invalid Python for %s, keeping original",
                    fname,
                )
                _record_repair_trace(
                    stage_dir,
                    phase="repair_rejected",
                    file=fname,
                    attempt=repair_attempt,
                    max_attempts=max_repair,
                    reason=(
                        "truncated"
                        if getattr(resp, "truncated", False)
                        else "invalid_python"
                    ),
                    rejected=[fname],
                )
            else:
                invalid_returns += 1
                logger.warning("Repair attempt returned empty code, keeping original")
                _record_repair_trace(
                    stage_dir,
                    phase="repair_rejected",
                    file=fname,
                    attempt=repair_attempt,
                    max_attempts=max_repair,
                    reason="empty",
                    rejected=[fname],
                )
            if invalid_returns >= 2:
                logger.error(
                    "Repair aborted for %s after %d unusable response(s)",
                    fname, invalid_returns,
                )
                _record_repair_trace(
                    stage_dir,
                    phase="repair_aborted",
                    file=fname,
                    attempt=repair_attempt,
                    max_attempts=max_repair,
                    reason="unusable_responses",
                    extra={"invalid_returns": invalid_returns},
                )
                validation_log.append(
                    f"File {fname}: repair aborted after {invalid_returns} "
                    "unusable responses"
                )
                break
            validation = validate_code(files[fname])
        if not validation.ok:
            all_valid = False
            # BUG-14: Log remaining issues prominently.  Report the repairs
            # that actually ran for this file, not the configured limit.
            logger.warning(
                "Code validation FAILED for %s after %d repair attempt(s): %s",
                fname, repair_counts.get(fname, 0), validation.summary(),
            )

    # Improvement G: RL algorithm-environment compatibility check
    for fname, code in list(files.items()):
        if not fname.endswith(".py"):
            continue
        _rl_errors = _check_rl_compatibility(code)
        if _rl_errors:
            for _rl_err in _rl_errors:
                logger.error("Stage 10: %s (in %s)", _rl_err, fname)
                validation_log.append(f"RL_COMPAT: {fname}: {_rl_err}")
            all_valid = False

    # BUG-14: Block on critical validation failures (syntax/import errors)
    if not all_valid:
        _has_critical = False
        for fname, code in files.items():
            _v = validate_code(code)
            if not _v.ok:
                for issue in _v.issues:
                    if issue.severity == "error" and issue.category in (
                        "syntax", "import",
                    ):
                        _has_critical = True
        if _has_critical:
            _performed = sum(repair_counts.values())
            logger.error(
                "Stage 10: CRITICAL validation issues remain after %d repair "
                "attempt(s) (limit %d/file). Blocking stage.",
                _performed, max_repair,
            )
            (stage_dir / "validation_report.md").write_text(
                _blocked_validation_report(repair_counts, max_repair, validation_log),
                encoding="utf-8",
            )
            return StageResult(
                stage=Stage.CODE_GENERATION,
                status=StageStatus.FAILED,
                artifacts=("validation_report.md",),
                evidence_refs=(),
            )

    # --- BUG-184: Cross-import validation — warn if a .py file imports a
    # local module that doesn't exist in the files dict.  This catches the
    # case where Beast Mode/CodeAgent produced an intermediate file that
    # got lost during repair iterations.
    _known_modules = {
        f.replace(".py", "") for f in files if f.endswith(".py")
    }
    _stdlib_and_common = {
        "os", "sys", "json", "math", "time", "copy", "re", "random",
        "pathlib", "argparse", "logging", "collections", "functools",
        "itertools", "abc", "typing", "dataclasses", "enum", "io",
        "csv", "pickle", "glob", "shutil", "subprocess", "datetime",
        "numpy", "np", "torch", "torchvision", "gymnasium", "gym",
        "sklearn", "scipy", "pandas", "matplotlib", "PIL", "tqdm",
        "einops", "timm", "transformers", "datasets", "peft",
        "stable_baselines3",
    }
    for fname, code in list(files.items()):
        if not fname.endswith(".py"):
            continue
        for _m in re.findall(
            r"^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            code, re.MULTILINE,
        ):
            if (_m not in _known_modules
                    and _m not in _stdlib_and_common
                    and not _m.startswith("_")):
                logger.warning(
                    "BUG-184: %s imports '%s' which is not in generated "
                    "files — experiment may crash on import",
                    fname, _m,
                )

    # --- Write experiment directory ---
    exp_dir = stage_dir / "experiment"
    exp_dir.mkdir(parents=True, exist_ok=True)
    # P-227 (F-1): a failed attempt must not leak modules into the delivery.
    _quarantine_stale(exp_dir, stage_dir, keep=set(files), tag="pre-attempt")
    for fname, code in files.items():
        safe_join(exp_dir, fname).write_text(code, encoding="utf-8")

    # --- Write validation report ---
    if validation_log or not all_valid:
        report_lines = ["# Code Validation Report\n"]
        if all_valid:
            report_lines.append(f"**Status**: PASSED after {attempt} total repair(s)\n")
        else:
            report_lines.append(
                f"**Status**: FAILED after {attempt} total repair attempt(s)\n"
            )
        for entry in validation_log:
            report_lines.append(f"- {entry}")
        (stage_dir / "validation_report.md").write_text(
            "\n".join(report_lines), encoding="utf-8"
        )

    # --- R10-Fix6: Code complexity and quality check ---
    from researchclaw.experiment.validator import (
        auto_fix_unbound_locals,
        check_code_complexity,
        deep_validate_files,
    )

    # --- BUG-3 fix: Programmatic auto-fix for UnboundLocalError patterns ---
    _total_ub_fixes = 0
    for fname, code in list(files.items()):
        if fname.endswith(".py"):
            fixed_code, n_fixes = auto_fix_unbound_locals(code)
            if n_fixes > 0:
                files[fname] = fixed_code
                safe_join(exp_dir, fname).write_text(fixed_code, encoding="utf-8")
                _total_ub_fixes += n_fixes
                logger.info(
                    "Stage 10: auto-fixed %d UnboundLocalError risk(s) in %s",
                    n_fixes, fname,
                )
    if _total_ub_fixes:
        logger.info(
            "Stage 10: auto-fixed %d total UnboundLocalError risks", _total_ub_fixes
        )

    complexity_warnings: list[str] = []
    for fname, code in files.items():
        if fname.endswith(".py"):
            cw = check_code_complexity(code)
            for w in cw:
                complexity_warnings.append(f"[{fname}] {w}")
                logger.warning("Stage 10 code quality: [%s] %s", fname, w)

    # --- P1.1+P1.2: Deep quality analysis (class quality, scoping, API) ---
    deep_warnings = deep_validate_files(files)
    for w in deep_warnings:
        logger.warning("Stage 10 deep quality: %s", w)
    complexity_warnings.extend(deep_warnings)

    # --- P1.2: If critical deep issues found, attempt one repair cycle ---
    critical_deep = _critical_deep(deep_warnings)
    # P-227 (F-2): check the symbol contract here instead of waiting for the
    # exit gate.  Run L attempt 2 lost 7 of 9 data.py symbols during repair
    # and only failed 153 minutes later at blueprint_symbols_missing.
    blueprint_for_symbols = load_blueprint(stage_dir) or {}
    for failure in check_symbol_contract(blueprint_for_symbols, files):
        critical_deep.append(f"[symbols] {failure.detail}")
    if critical_deep and llm is not None:
        logger.info(
            "Stage 10: %d critical code issues found — triggering repair cycle",
            len(critical_deep),
        )
        _issues = list(critical_deep)
        _baseline = deep_warnings
        for _round in range(1, 3):
            repair_issues = "\n".join(f"- {w}" for w in _issues)
            # P-228 (G-1): cap the stage-level repair context as well; every
            # file stays present but oversized ones keep head+tail only.
            from researchclaw.pipeline.code_agent import (
                CodeAgent as _ContextAgent,
            )
            all_code_ctx = _ContextAgent._format_files(
                files, keep_full=set(files), budget=80000,
            )
            _prev_note = (
                f"STILL NOT FIXED (previous round):\n{repair_issues}\n\n"
                if _round > 1 else ""
            )
            repair_prompt = (
                f"{_prev_note}"
                f"CRITICAL CODE QUALITY ISSUES FOUND:\n{repair_issues}\n\n"
                f"Fix ALL these issues in the code below. Return the complete "
                f"corrected files using ```filename:xxx.py format.\n\n"
                f"RULES:\n"
                f"- Preserve every declared symbol (class/function); never remove "
                f"or rename one\n"
                f"- nn.Linear/nn.Conv must be created in __init__(), not forward()\n"
                f"- Variables used after if/else must be defined before the branch\n"
                f"- Use scipy.special.erf, not np.erf\n"
                f"- Ablation/variant classes must have genuinely different logic\n"
                f"- Every class must have a real implementation, not just `pass`\n"
                f"- Ablation classes MUST override the parent method that implements "
                f"the component being ablated (e.g., if ablating attention, override "
                f"the attention method with a simpler alternative like mean pooling)\n"
                f"- IMPORT CONSISTENCY: if you write `from X import Y`, call `Y()` "
                f"directly — NOT `X.Y()`. Mixing styles causes NameError.\n"
                f"- NumPy 2.0: ndarray.ptp() was removed — use arr.max()-arr.min()\n"
                f"- NumPy 2.0: np.bool/np.int/np.float removed — use builtins\n"
                f"- Pretrained models (EfficientNet, ResNet, ViT) expect 224×224 input "
                f"— add `transforms.Resize(224)` when using CIFAR (32×32) or similar\n"
                f"- Copy-paste ablation: if two classes have identical bodies, REWRITE "
                f"the ablation to genuinely remove/reduce a component (e.g., zero out "
                f"attention weights, halve hidden dimensions, remove a loss term)\n"
                f"- KD: teacher must be frozen, add projection layers if teacher_dim != "
                f"student_dim, use temperature T=4 for soft targets\n"
                f"- FILENAME COLLISIONS: If a file like config.py shadows a pip/stdlib "
                f"package, rename it (e.g., config.py → experiment_config.py) and update "
                f"ALL imports referencing it\n\n"
                f"Current code:\n{all_code_ctx}\n"
            )
            try:
                repair_resp = _request_repair_response(
                    llm,
                    _pm.system("code_generation"),
                    repair_prompt,
                    max_tokens=_code_max_tokens,
                )
                repaired = _extract_valid_repair_files(
                    repair_resp.content, set(files),
                )
                _record_repair_trace(
                    stage_dir,
                    phase="project_repair",
                    prompt=repair_prompt,
                    response=repair_resp.content,
                    model=str(getattr(repair_resp, "model", "") or ""),
                    truncated=getattr(repair_resp, "truncated", None),
                    accepted=sorted(repaired),
                    rejected=sorted(set(files) - set(repaired)),
                    reason="merged" if repaired else "no_valid_file",
                    extra={"usage": {
                        "prompt_tokens": int(
                            getattr(repair_resp, "prompt_tokens", 0) or 0
                        ),
                        "completion_tokens": int(
                            getattr(repair_resp, "completion_tokens", 0) or 0
                        ),
                        "total_tokens": int(
                            getattr(repair_resp, "total_tokens", 0) or 0
                        ),
                        "finish_reason": str(
                            getattr(repair_resp, "finish_reason", "") or ""
                        ),
                    }},
                )
                if not repaired:
                    break
                files = _merge_repair_files(files, repaired)
                for fname, code in files.items():
                    safe_join(exp_dir, fname).write_text(code, encoding="utf-8")
                logger.info(
                    "Stage 10 repair: merged %d file(s), preserved %d",
                    len(repaired), len(files) - len(repaired),
                )
                # Re-check after repair
                deep_warnings_after = deep_validate_files(files)
                fixed, remaining = _deep_repair_counts(
                    _baseline, deep_warnings_after,
                )
                logger.info(
                    "Stage 10: Deep repair fixed %d of %d critical issues "
                    "(%d remain)",
                    fixed, len(critical_deep), remaining,
                )
                complexity_warnings.append(
                    f"[REPAIR] Deep repair fixed {fixed}/{len(critical_deep)} "
                    f"critical issues ({remaining} remain)"
                )
                # P-227 (F-4): feed whatever is still broken into the next
                # round; stop early when a round made no progress (Self-Refine
                # converges to the same output without new information).
                _issues = _critical_deep(deep_warnings_after)
                for failure in check_symbol_contract(
                    blueprint_for_symbols, files,
                ):
                    _issues.append(f"[symbols] {failure.detail}")
                if not _issues or fixed == 0:
                    break
            except Exception as exc:
                logger.debug("Deep repair failed: %s", exc)
                break

    if complexity_warnings:
        health: dict[str, Any] = {}
        health["code_complexity_warnings"] = complexity_warnings
        (stage_dir / "code_complexity.json").write_text(
            json.dumps(health, indent=2), encoding="utf-8"
        )

    # --- P1.4: LLM Code Review (Stage 10.5) ---
    # Skip when CodeAgent is active — Phase 4 review already covers this.
    if llm is not None and not _code_agent_active:
        all_code_review = "\n\n".join(
            f"# --- {fname} ---\n{code}" for fname, code in files.items()
        )
        if len(all_code_review) > 12000:
            all_code_review = all_code_review[:12000] + "\n... [truncated]"
        review_prompt = (
            f"You are a senior researcher reviewing experiment code for a "
            f"research submission.\n\n"
            f"TOPIC: {config.research.topic}\n"
            f"EXPERIMENT PLAN:\n{exp_plan[:3000]}\n\n"
            f"CODE:\n```python\n{all_code_review}\n```\n\n"
            f"Review the code and return JSON with this EXACT structure:\n"
            f'{{"score": <1-10>, "issues": ['
            f'{{"severity": "critical|major|minor", '
            f'"description": "...", "fix": "..."}}], '
            f'"verdict": "pass|needs_fix"}}\n\n'
            f"Check specifically:\n"
            f"1. Does each algorithm/method have a DISTINCT implementation? "
            f"(Not just renamed copies)\n"
            f"2. Are ablation conditions genuinely different from the main method?\n"
            f"3. Are loss functions / training loops mathematically correct?\n"
            f"4. Will the code actually run without errors? Check variable scoping, "
            f"API usage, tensor shape compatibility.\n"
            f"5. Is the code complex enough for a research paper? (Not trivial)\n"
            f"6. Are experimental conditions fairly compared (same seeds, data)?\n"
            f"7. If using pretrained models (EfficientNet, ResNet, ViT), are input "
            f"images resized to the model's expected size (e.g., 224x224)? CIFAR "
            f"images are 32x32 and MUST be resized for pretrained models.\n"
            f"8. Are imports consistent? `from X import Y` must use `Y()`, not `X.Y()`.\n"
        )
        try:
            review_resp = llm.chat(
                [{"role": "user", "content": review_prompt}],
                system="You are a meticulous ML code reviewer. Be strict.",
                max_tokens=2048,
            )
            # Extract JSON from LLM response (may be wrapped in markdown fences)
            _review_text = review_resp.content if hasattr(review_resp, "content") else str(review_resp)
            # Strip markdown JSON fences if present
            _review_text = _review_text.strip()
            if _review_text.startswith("```"):
                _lines = _review_text.splitlines()
                _start = 1 if _lines[0].strip().startswith("```") else 0
                _end = len(_lines) - 1 if _lines[-1].strip() == "```" else len(_lines)
                _review_text = "\n".join(_lines[_start:_end])
            review_data = _safe_json_loads(_review_text, {})
            if isinstance(review_data, dict):
                review_score = review_data.get("score", 0)
                review_verdict = review_data.get("verdict", "unknown")
                review_issues = review_data.get("issues", [])

                # Write review report
                review_report = {
                    "score": review_score,
                    "verdict": review_verdict,
                    "issues": review_issues,
                    "timestamp": _utcnow_iso(),
                }
                (stage_dir / "code_review.json").write_text(
                    json.dumps(review_report, indent=2), encoding="utf-8"
                )

                # If critical issues found and score low, attempt fix
                critical_issues = [
                    i for i in review_issues
                    if isinstance(i, dict)
                    and i.get("severity") == "critical"
                ]
                if critical_issues and review_score <= 4:
                    logger.warning(
                        "Stage 10 code review: score=%d, %d critical issues — "
                        "attempting fix",
                        review_score, len(critical_issues),
                    )
                    fix_descriptions = "\n".join(
                        f"- [{i.get('severity', '?')}] {i.get('description', '?')}: "
                        f"{i.get('fix', 'no fix suggested')}"
                        for i in critical_issues
                    )
                    fix_prompt = (
                        f"Code review found {len(critical_issues)} CRITICAL issues "
                        f"(score: {review_score}/10):\n{fix_descriptions}\n\n"
                        f"Fix ALL critical issues. Return complete corrected files "
                        f"using ```filename:xxx.py format.\n\n"
                        f"Current code:\n"
                        + "\n\n".join(
                            f"```filename:{f}\n{c}\n```" for f, c in files.items()
                        )
                    )
                    try:
                        fix_resp = _request_repair_response(
                            llm,
                            _pm.system("code_generation"),
                            fix_prompt,
                            max_tokens=_code_max_tokens,
                        )
                        fixed_files = _extract_valid_repair_files(
                            fix_resp.content, set(files),
                        )
                        if fixed_files:
                            files = _merge_repair_files(files, fixed_files)
                            for fname, code in files.items():
                                safe_join(exp_dir, fname).write_text(code, encoding="utf-8")
                            logger.info(
                                "Stage 10 fix: merged %d file(s), preserved %d",
                                len(fixed_files), len(files) - len(fixed_files),
                            )
                            logger.info(
                                "Stage 10: Code fixed after review "
                                "(was %d/10, %d critical issues)",
                                review_score, len(critical_issues),
                            )
                    except Exception as exc:
                        logger.debug("Review-fix failed: %s", exc)
        except Exception as exc:
            logger.debug("Code review failed: %s", exc)

    # --- FIX-3: Topic-experiment alignment check ---
    # BUG-171: Previous 8000-char truncation caused false-positive misalignment
    # for multi-file experiments (30-90K chars). LLM saw "[truncated]" and
    # concluded code was incomplete. Fix: build a structured summary that
    # includes file inventory + full main.py + per-file function/class headers.
    alignment_ok = True
    alignment_note = ""
    if llm is not None:
        # Build structured code summary for alignment check
        _file_inventory = []
        for _fn, _cd in files.items():
            _lines = _cd.count("\n") + 1
            _file_inventory.append(f"  {_fn}: {_lines} lines, {len(_cd)} chars")
        _inventory_block = "FILES GENERATED:\n" + "\n".join(_file_inventory)

        # BUG-179: Beast Mode may use a different entry point (e.g.
        # run_experiment.py).  Detect the actual entry point by scanning
        # for ``if __name__ == "__main__"`` in all files, preferring main.py.
        _entry_file = "main.py"
        if "main.py" not in files or not files.get("main.py", "").strip():
            for _fn, _cd in files.items():
                if 'if __name__' in _cd and '__main__' in _cd:
                    _entry_file = _fn
                    break
        elif files.get("main.py", ""):
            # main.py exists but may be a stub — if another file has the
            # real orchestration (more lines + __main__ guard), prefer it
            _main_lines = files["main.py"].count("\n")
            for _fn, _cd in files.items():
                if _fn == "main.py":
                    continue
                if ('if __name__' in _cd and '__main__' in _cd
                        and _cd.count("\n") > _main_lines * 1.5):
                    _entry_file = _fn
                    break

        _main_code = files.get(_entry_file, files.get("main.py", ""))
        _main_block = f"# --- {_entry_file} (FULL — entry point) ---\n{_main_code}"
        # Cap main.py at 12000 chars to stay within token budget
        if len(_main_block) > 12000:
            _main_block = _main_block[:12000] + "\n... [main.py truncated at 12000 chars]"

        # For other files, include imports + function/class signatures
        _other_summaries = []
        for _fn, _cd in files.items():
            if _fn == _entry_file:
                continue
            _sig_lines = []
            for _line in _cd.split("\n"):
                _stripped = _line.strip()
                if (_stripped.startswith("def ") or _stripped.startswith("class ")
                        or _stripped.startswith("async def ")
                        # BUG-209: Include import lines — they reveal which
                        # techniques/libraries are used (e.g. CosineAnnealingLR)
                        or _stripped.startswith("import ")
                        or _stripped.startswith("from ")):
                    _sig_lines.append(_line)
            if _sig_lines:
                _other_summaries.append(
                    f"# --- {_fn} (imports + signatures) ---\n"
                    + "\n".join(_sig_lines)
                )
            else:
                # Small file — include first 800 chars
                _preview = _cd[:800]
                if len(_cd) > 800:
                    _preview += f"\n... [{len(_cd) - 800} more chars]"
                _other_summaries.append(f"# --- {_fn} (preview) ---\n{_preview}")
        _other_block = "\n\n".join(_other_summaries)
        # Cap other summaries
        if len(_other_block) > 6000:
            _other_block = _other_block[:6000] + "\n... [other files truncated]"

        all_code_for_check = (
            f"{_inventory_block}\n\n{_main_block}\n\n{_other_block}"
        )
        align_prompt = (
            f"Research topic: {config.research.topic}\n\n"
            f"Experiment code:\n```python\n{all_code_for_check}\n```\n\n"
            "TASK: Evaluate whether this experiment code actually tests the "
            "stated research topic. Answer with JSON:\n"
            '{"aligned": true/false, "reason": "...", "suggestions": "..."}\n\n'
            "IMPORTANT: The code spans MULTIPLE files. The file inventory above "
            "shows ALL generated files. Only main.py is shown in full; other "
            "files show function/class signatures. Do NOT mark as misaligned "
            "just because helper files are summarized — they contain full "
            "implementations.\n\n"
            "Check specifically:\n"
            "- Does main.py orchestrate an experiment matching the topic?\n"
            "- Do the helper file signatures indicate relevant models/methods?\n"
            "- If the topic mentions a specific technique, is there evidence of "
            "its implementation (function names, class names, imports)?\n"
            "- Are the experimental conditions meaningfully different from each other?\n"
        )
        try:
            align_resp = llm.chat(
                [{"role": "user", "content": align_prompt}],
                system="You are a scientific code reviewer checking topic-experiment alignment.",
                max_tokens=1024,
            )
            align_data = _safe_json_loads(align_resp.content, {})
            if isinstance(align_data, dict) and not align_data.get("aligned", True):
                alignment_ok = False
                alignment_note = align_data.get("reason", "Misaligned")
                suggestions = align_data.get("suggestions", "")
                _journal_alignment(stage_dir, "initial", "misaligned",
                                   all_code_for_check)
                logger.warning(
                    "Stage 10: Topic-experiment MISALIGNMENT detected: %s",
                    alignment_note,
                )
                # BUG-R6-01: Allow up to 2 regeneration attempts with re-check.
                _max_regen = 2
                for _regen_attempt in range(1, _max_regen + 1):
                    logger.info(
                        "Stage 10: Alignment regen attempt %d/%d",
                        _regen_attempt, _max_regen,
                    )
                    # P-227 (F-3): anchor the regeneration to the blueprint so
                    # the model cannot replace the project with a generic
                    # harness (run L attempt 1) or drop declared symbols.
                    _bp = load_blueprint(stage_dir) or {}
                    _bp_names = _blueprint_file_names(_bp)
                    _bp_block = "\n".join(
                        f"- {name}: "
                        + (", ".join(declared_symbols(_bp, name))
                           or "(no declared symbols)")
                        for name in sorted(_bp_names)
                    ) or "- (blueprint unavailable)"
                    regen_prompt = (
                        f"The experiment code you previously generated does NOT align "
                        f"with the research topic.\n\n"
                        f"TOPIC: {config.research.topic}\n"
                        f"MISALIGNMENT: {alignment_note}\n"
                        f"SUGGESTIONS: {suggestions}\n\n"
                        f"REGENERATE the experiment code to DIRECTLY test the stated "
                        f"topic. The code MUST implement the core technique described "
                        f"in the topic, not a generic proxy.\n\n"
                        f"BLUEPRINT FILES (the complete set — do not add or remove):\n"
                        f"{_bp_block}\n\n"
                        f"CRITICAL CONSTRAINTS:\n"
                        f"- You MUST implement the EXACT algorithm/method from the topic.\n"
                        f"- Do NOT substitute a deep-learning proxy (ResNet, BERT, etc.) "
                        f"when the topic describes a tabular, bandit, or game-theoretic method.\n"
                        f"- Use ONLY lightweight CPU-friendly libraries (numpy, scipy, "
                        f"sklearn) unless the topic EXPLICITLY requires deep learning.\n"
                        f"- The experiment must be self-contained and runnable without GPU.\n"
                        f"- Keep every declared symbol with the same name; do not drop "
                        f"or rename modules.\n\n"
                        f"{pkg_hint}\n{compute_budget}\n"
                        f"PLAN:\n{exp_plan}\n\n"
                        f"Return multiple files using ```filename:xxx.py format."
                    )
                    regen_resp = _chat_with_prompt(
                        llm,
                        system=_pm.system("code_generation"),
                        user=regen_prompt,
                        max_tokens=_code_max_tokens,
                    )
                    regen_files = _extract_multi_file_blocks(regen_resp.content)
                    if not regen_files or "main.py" not in regen_files:
                        logger.warning(
                            "Stage 10: Regen attempt %d produced no main.py",
                            _regen_attempt,
                        )
                        continue
                    # P-227 (F-3): keep the blueprint's file set.  Unknown
                    # modules are dropped, and a file the regen omitted keeps
                    # its previous version instead of disappearing.
                    _allowed = _bp_names | {"main.py"}
                    _kept = {
                        name: code for name, code in regen_files.items()
                        if Path(name).name in _allowed
                    }
                    files = {**files, **_kept}
                    _quarantine_stale(
                        exp_dir, stage_dir, keep=set(files),
                        tag=f"regen-{_regen_attempt}",
                    )
                    for fname, code in files.items():
                        safe_join(exp_dir, fname).write_text(code, encoding="utf-8")
                    # P-229: regen may drop declared symbols from any module.
                    files = _ensure_symbol_contract(
                        files,
                        stage_dir=stage_dir,
                        exp_dir=exp_dir,
                        llm=llm,
                        pm=_pm,
                        topic=config.research.topic,
                    )
                    # Re-check alignment on regenerated code (BUG-171 fix)
                    _rc_inv = []
                    for _fn, _cd in files.items():
                        _rc_inv.append(f"  {_fn}: {_cd.count(chr(10))+1} lines")
                    _rc_main = files.get("main.py", "")
                    if len(_rc_main) > 12000:
                        _rc_main = _rc_main[:12000] + "\n... [truncated]"
                    _rc_sigs = []
                    for _fn, _cd in files.items():
                        if _fn == "main.py":
                            continue
                        # BUG-209: Include imports alongside signatures
                        _slines = [l for l in _cd.split("\n")
                                   if l.strip().startswith((
                                       "def ", "class ", "async def ",
                                       "import ", "from ",
                                   ))]
                        if _slines:
                            _rc_sigs.append(f"# {_fn} imports+signatures:\n" + "\n".join(_slines))
                    recheck_code = (
                        "FILES:\n" + "\n".join(_rc_inv) + "\n\n"
                        f"# main.py (FULL):\n{_rc_main}\n\n"
                        + "\n".join(_rc_sigs)
                    )
                    recheck_resp = llm.chat(
                        [{"role": "user", "content": (
                            f"Research topic: {config.research.topic}\n\n"
                            f"Experiment code:\n```python\n{recheck_code}\n```\n\n"
                            "TASK: Evaluate whether this experiment code actually tests "
                            "the stated research topic. Only main.py is shown in full; "
                            "other files show signatures only. Answer with JSON:\n"
                            '{"aligned": true/false, "reason": "...", "suggestions": "..."}\n'
                        )}],
                        system="You are a scientific code reviewer checking topic-experiment alignment.",
                        max_tokens=1024,
                    )
                    recheck_data = _safe_json_loads(recheck_resp.content, {})
                    if isinstance(recheck_data, dict) and recheck_data.get("aligned", False):
                        alignment_ok = True
                        alignment_note = f"Regenerated after alignment check (attempt {_regen_attempt})"
                        _journal_alignment(
                            stage_dir, f"regen-{_regen_attempt}", "done",
                            recheck_code,
                        )
                        logger.info(
                            "Stage 10: Code aligned after regen attempt %d",
                            _regen_attempt,
                        )
                        break
                    else:
                        alignment_note = recheck_data.get("reason", alignment_note)
                        suggestions = recheck_data.get("suggestions", suggestions)
                        _journal_alignment(
                            stage_dir, f"regen-{_regen_attempt}", "misaligned",
                            recheck_code,
                        )
                        logger.warning(
                            "Stage 10: Regen attempt %d still misaligned: %s",
                            _regen_attempt, alignment_note,
                        )
        except Exception as exc:
            logger.debug("Alignment check failed: %s", exc)
        if alignment_ok and not alignment_note:
            _journal_alignment(stage_dir, "initial", "done", all_code_for_check)

    # --- FIX-7: Ablation distinctness check ---
    main_code = files.get("main.py", "")
    if llm is not None and main_code and "condition" in main_code.lower():
        try:
            ablation_prompt = (
                f"Examine this experiment code:\n```python\n{main_code[:6000]}\n```\n\n"
                "Check if any experimental conditions (methods/ablations) have "
                "IDENTICAL configurations (same hyperparameters, same code paths). "
                "Answer JSON: "
                '{"has_duplicates": true/false, "details": "which conditions are identical"}'
            )
            abl_resp = llm.chat(
                [{"role": "user", "content": ablation_prompt}],
                system="You are a code reviewer checking experimental conditions.",
                max_tokens=512,
            )
            abl_data = _safe_json_loads(abl_resp.content, {})
            if isinstance(abl_data, dict) and abl_data.get("has_duplicates"):
                logger.warning(
                    "Stage 10: Duplicate ablation conditions detected: %s",
                    abl_data.get("details", ""),
                )
                (stage_dir / "ablation_warning.json").write_text(
                    json.dumps(abl_data, indent=2), encoding="utf-8"
                )
                # --- Attempt ablation repair ---
                all_code_ctx = "\n\n".join(
                    f"```filename:{f}\n{c}\n```" for f, c in files.items()
                )
                dup_details = abl_data.get("details", "unknown")
                abl_repair_prompt = (
                    f"ABLATION REPAIR REQUIRED — duplicate conditions detected:\n"
                    f"{dup_details}\n\n"
                    f"Rewrite the ablation/variant conditions so each one is "
                    f"GENUINELY DIFFERENT. Concrete strategies:\n"
                    f"- 'no_<component>': REMOVE the component entirely "
                    f"(e.g., replace attention with mean pooling, remove a loss term)\n"
                    f"- 'reduced_capacity': HALVE hidden dimensions or layers\n"
                    f"- Different conditions MUST produce different outputs on the "
                    f"same input. Add a startup assertion that runs one forward pass "
                    f"per condition on identical input and prints:\n"
                    f"  ABLATION_CHECK: <cond1> vs <cond2> outputs_differ=True\n\n"
                    f"Return ALL files using ```filename:xxx.py format.\n\n"
                    f"Current code:\n{all_code_ctx}\n"
                )
                try:
                    abl_repair_resp = _chat_with_prompt(
                        llm,
                        _pm.system("code_generation"),
                        abl_repair_prompt,
                        max_tokens=_code_max_tokens,
                    )
                    repaired_files = _extract_multi_file_blocks(
                        abl_repair_resp.content
                    )
                    if repaired_files and "main.py" in repaired_files:
                        files = repaired_files
                        for fname, code in files.items():
                            safe_join(exp_dir, fname).write_text(code, encoding="utf-8")
                        logger.info(
                            "Stage 10: Ablation repair applied — "
                            "rewrote duplicate conditions"
                        )
                except Exception as exc:
                    logger.debug("Ablation repair failed: %s", exc)
        except Exception as exc:
            logger.debug("Ablation validation skipped: %s", exc)

    # --- Write spec ---
    file_list = ", ".join(f"`{f}`" for f in sorted(files.keys()))
    main_validation = validate_code(files.get("main.py", ""))
    _align_status = "ALIGNED" if alignment_ok else f"MISALIGNED: {alignment_note}"
    spec = f"""# Experiment Specification

## Topic
{config.research.topic}

## Project Structure
Multi-file experiment project with {len(files)} file(s): {file_list}

## Entry Point
`main.py` \u2014 executed directly via sandbox

## Outputs
- `main.py` emits metric lines in `name: value` format
- Primary metric key: `{metric}`

## Topic-Experiment Alignment
{_align_status}

## Constraints
- Time budget per run: {config.experiment.time_budget_sec}s
- Max iterations: {config.experiment.max_iterations}
- Self-contained execution (no external data, no network)
- Validated: {main_validation.summary()}

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "experiment_spec.md").write_text(spec, encoding="utf-8")

    artifacts = ["experiment/", "experiment_spec.md"]
    if (stage_dir / "validation_report.md").exists():
        artifacts.append("validation_report.md")

    # BUG-R6-01: Fail stage if alignment check detected persistent mismatch
    # after all regen attempts, instead of silently proceeding.
    if not alignment_ok:
        logger.error(
            "Stage 10: Persistent topic-experiment misalignment after all "
            "regen attempts. Failing stage. Reason: %s",
            alignment_note,
        )
        return StageResult(
            stage=Stage.CODE_GENERATION,
            status=StageStatus.FAILED,
            artifacts=tuple(artifacts),
            evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
            error=f"Topic-experiment misalignment: {alignment_note}",
        )

    # B-29: repair loops can still degrade main.py; regenerate before the gate.
    metric = resolve_metric(stage_dir, metric)
    files = _ensure_entrypoint(
        files,
        llm=llm,
        pm=_pm,
        topic=config.research.topic,
        metric=metric,
        exp_dir=exp_dir,
        exp_plan=exp_plan,
    )
    # P-229: re-check after the final entrypoint regeneration (run M lost
    # evaluate_monitor/run_condition/set_seed/train_model here).
    files = _ensure_symbol_contract(
        files,
        stage_dir=stage_dir,
        exp_dir=exp_dir,
        llm=llm,
        pm=_pm,
        topic=config.research.topic,
    )

    # P-178: refuse to ship a non-runnable entrypoint (config-only main.py etc.)
    _main_code = files.get("main.py", "") if isinstance(files, dict) else ""
    if not _main_code:
        _main_path = exp_dir / "main.py"
        if _main_path.is_file():
            try:
                _main_code = _main_path.read_text(encoding="utf-8")
            except OSError:
                _main_code = ""
    _entry_issues = _entrypoint_issues(_main_code)
    if _entry_issues:
        logger.error(
            "Stage 10: generated entrypoint is not runnable: %s", _entry_issues
        )
        return StageResult(
            stage=Stage.CODE_GENERATION,
            status=StageStatus.FAILED,
            artifacts=tuple(artifacts),
            evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
            error="generated entrypoint is not runnable: "
            + "; ".join(_entry_issues[:5]),
        )

    # B-32 M2: a runnable entrypoint is not enough — the delivery must also
    # match what the blueprint promised.  Failures are recorded, never repaired.
    # P-202 (N-1): judge what is actually on disk under experiment/, since that
    # is what Stage 12 runs; the in-memory mapping is only a fallback.
    _evidence = evaluate_stage10_evidence(
        stage_dir=stage_dir,
        files=files,
        metric=metric,
        delivered_dir=exp_dir,
    )
    write_evidence_report(stage_dir, _evidence)
    if _evidence.failures:
        logger.error(
            "Stage 10: evidence gate failed: %s",
            "; ".join(f"{f.code}: {f.detail}" for f in _evidence.failures),
        )
        return StageResult(
            stage=Stage.CODE_GENERATION,
            status=StageStatus.FAILED,
            artifacts=tuple(artifacts) + ("codegen_evidence.json",),
            evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
            error="codegen evidence gate failed: "
            + "; ".join(f.code for f in _evidence.failures),
        )
    for _warning in _evidence.warnings:
        logger.warning("Stage 10 evidence warning: %s", _warning)

    return StageResult(
        stage=Stage.CODE_GENERATION,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts) + ("codegen_evidence.json",),
        evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
    )

