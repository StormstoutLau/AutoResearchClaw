"""Advanced multi-phase code generation agent.

Phases
------
1. **Blueprint Planning** — produce deep implementation blueprint with
   per-file pseudocode, tensor shapes, and generation ordering.
2. **Sequential File Generation** — generate files one-by-one following
   the dependency order from the blueprint, with CodeMem summaries.
   Falls back to single-shot generation if blueprint parsing fails.
3. **Execution-in-the-Loop** — run in sandbox, feed errors back for repair.
4. **Solution Tree Search** — explore multiple candidate implementations,
   evaluate via sandbox, select the best (optional, higher cost).
5. **Multi-Agent Review** — coder-reviewer dialog for quality assurance.

Integration
-----------
``CodeAgent`` is instantiated inside ``_execute_code_generation`` in
``executor.py`` when ``config.experiment.code_agent.enabled`` is True.
It receives the same inputs (topic, exp_plan, metric, pkg_hint) and
returns ``CodeAgentResult`` with the generated files.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline._helpers import _close_unterminated_fence
from researchclaw.pipeline.repair_trace import record as _record_repair_trace
from researchclaw.pipeline.entrypoint_contract import (
    ENTRYPOINT_MAX_TOKENS,
    ENTRYPOINT_RETRY_MAX_TOKENS,
    build_entrypoint_prompt,
    entrypoint_issues,
)

logger = logging.getLogger(__name__)


class ModuleExtractionError(RuntimeError):
    """A blueprint module could not be extracted after the 32768 escalation.

    B-34 M1-b: the previous code logged a WARNING and ``continue``d, so Stage
    10 kept generating the remaining modules, ran validation and review, and
    only failed at the evidence gate — up to hours later.  Raising here fails
    at the module that broke.
    """

    def __init__(self, *, file_name: str, reason: str) -> None:
        self.file_name = file_name
        self.reason = reason  # "truncated" | "empty"
        super().__init__(
            f"{file_name}: module extraction failed ({reason}) — refusing to "
            "continue with a missing or partial module"
        )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _blueprint_inputs_digest(topic: str, exp_plan: str, metric: str) -> str:
    """Inputs that determine the blueprint (B-33 L2 minimal set)."""
    from researchclaw.pipeline.step_journal import hash_text

    return hash_text("\n---\n".join([str(topic), str(metric), str(exp_plan or "")]))


# B-32 M1: a block-sequence item whose natural-language value ends with a
# colon is read by YAML as a mapping key with an empty value, so the
# following more-indented continuation lines fail with "could not find
# expected ':'".  Folding them into one quoted scalar keeps the text and
# makes the document parseable.
_TRAILING_COLON_ITEM = re.compile(r"^(?P<indent> *)-[ \t]+(?P<text>.*\S):[ \t]*$")
# A continuation line shaped like ``key: value`` / ``key:`` means the list item
# is a mapping, not prose (P-202 F-3).
_MAPPING_CONTINUATION_RE = re.compile(r"^[^\s:#][^:]*:(?:\s|$)")

_YAML_REPAIR_SUFFIX = (
    "\n\n---\n"
    "Your previous answer could not be parsed as YAML. Re-emit the SAME "
    "blueprint as valid YAML only.\n"
    "Rules:\n"
    "- Output exactly one ```yaml fenced block and nothing else.\n"
    "- Quote every list-item value that ends with ':' or contains ': '.\n"
    "- Keep the same keys, file names and generation_order values.\n"
)

# B-34 M4: modules whose job is wiring/formatting rather than algorithm
# design.  These get a lower thinking effort so the budget goes to code.
_MECHANICAL_FILE_HINTS = (
    "config",
    "settings",
    "constants",
    "schema",
    "types",
    "utils",
    "util",
    "cli",
    "io",
    "loader",
)


def _fold_trailing_colon_items(lines: list[str]) -> list[str]:
    """Fold list items whose natural-language value ends with a colon."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _TRAILING_COLON_ITEM.match(line)
        if match is None:
            out.append(line)
            i += 1
            continue
        indent = match.group("indent")
        text = match.group("text").strip()
        if text.startswith(('"', "'")):
            out.append(line)
            i += 1
            continue
        if " " not in text:
            # A single token like ``- interface:`` is a mapping key, not prose;
            # folding it would swallow the nested mapping into a string.
            out.append(line)
            i += 1
            continue
        if ": " in text:
            # ``- name: foo bar:`` is already a ``key: value`` pair whose value
            # ends with a colon (P-202 F-3); folding would turn it into a
            # string and lose the mapping.
            out.append(line)
            i += 1
            continue

        # Collect continuation lines that belong to this item.  ``text``
        # excludes the trailing colon (the regex consumes it), so re-add it.
        j = i + 1
        folded: list[str] = [text + ":"]
        nested_sequence = False
        nested_mapping = False
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip():
                j += 1
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip(" "))
            if nxt_indent <= len(indent):
                break
            body = nxt.strip()
            if body.startswith("- "):
                # A nested list is a legitimate mapping value, not prose.
                nested_sequence = True
                break
            if _MAPPING_CONTINUATION_RE.match(body):
                # ``- some key:`` followed by ``nested: value`` is a mapping
                # (P-202 F-3); folding it would destroy the structure.
                nested_mapping = True
                break
            folded.append(body)
            j += 1

        if nested_sequence or nested_mapping:
            out.append(line)
            i += 1
            continue

        escaped = " ".join(part for part in folded if part).replace('"', '\\"')
        out.append(f'{indent}- "{escaped}"')
        i = j
    return out


@dataclass
class SolutionNode:
    """One candidate solution in the search tree."""

    node_id: str
    files: dict[str, str]
    parent_id: str | None = None
    depth: int = 0
    # Evaluation
    runs_ok: bool = False
    returncode: int = -1
    evaluated: bool = False
    stdout: str = ""
    stderr: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    generation_method: str = "initial"


@dataclass
class CodeAgentResult:
    """Final output from the code agent."""

    files: dict[str, str]
    architecture_spec: str = ""
    validation_log: list[str] = field(default_factory=list)
    total_llm_calls: int = 0
    total_sandbox_runs: int = 0
    best_score: float = 0.0
    tree_nodes_explored: int = 0
    review_rounds: int = 0


# ---------------------------------------------------------------------------
# Sandbox protocol (structural typing — no import dependency)
# ---------------------------------------------------------------------------


class _SandboxResult(Protocol):  # pragma: no cover
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float
    metrics: dict[str, object]
    timed_out: bool


class _SandboxLike(Protocol):  # pragma: no cover
    def run_project(
        self,
        project_dir: Path,
        *,
        entry_point: str = "main.py",
        timeout_sec: int = 300,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# CodeAgent
# ---------------------------------------------------------------------------


class CodeAgent:
    """Multi-phase code generation agent.

    Parameters
    ----------
    llm : LLMClient
        The language model client to use for code generation.
    prompts : PromptManager
        Manages prompt templates.
    config : CodeAgentConfig
        Agent configuration (toggles, limits, timeouts).
    stage_dir : Path
        Working directory for this stage (e.g. ``run_dir/stage-10``).
    sandbox_factory : callable, optional
        ``(ExperimentConfig, Path) -> SandboxLike``.  Required for
        Phases 2 and 3.
    experiment_config : ExperimentConfig, optional
        Passed to ``sandbox_factory`` when creating sandboxes.
    """

    def __init__(
        self,
        llm: Any,
        prompts: Any,
        config: CodeAgentConfig,
        stage_dir: Path,
        sandbox_factory: Any | None = None,
        experiment_config: Any | None = None,
        domain_profile: Any | None = None,
        code_search_result: Any | None = None,
    ) -> None:
        self._llm = llm
        self._pm = prompts
        self._cfg = config
        self._stage_dir = stage_dir
        self._sandbox_factory = sandbox_factory
        self._exp_config = experiment_config
        self._domain_profile = domain_profile
        self._code_search_result = code_search_result
        self._calls = 0
        self._runs = 0
        self._log: list[str] = []
        self._sandbox: _SandboxLike | None = None
        # B-32 M1: diagnostics for the single-shot fallback record.
        self._codegen_diag: dict[str, Any] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def generate(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        max_tokens: int = 8192,
    ) -> CodeAgentResult:
        """Execute all enabled phases and return generated files."""
        from researchclaw.pipeline.step_journal import hash_text

        t0 = time.time()
        self._log_event("CodeAgent.generate() started")

        # Phase 1: Blueprint planning
        arch_spec = ""
        blueprint = None
        if self._cfg.architecture_planning:
            arch_spec, blueprint = self._phase1_blueprint(
                topic, exp_plan, metric,
            )

        # Phase 2: Code generation
        nodes_explored = 0
        if self._cfg.tree_search_enabled and self._sandbox_factory:
            best, nodes_explored = self._phase3_tree_search(
                topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
            )
        elif (
            self._cfg.sequential_generation
            and blueprint is not None
            and self._is_valid_blueprint(blueprint)
        ):
            # Sequential file generation following blueprint
            files = self._phase2_sequential_generate(
                topic, exp_plan, metric, pkg_hint, arch_spec, blueprint,
            )
            # Hard validation gates (E-03)
            if self._cfg.hard_validation:
                files = self._hard_validate_and_repair(
                    files, topic, exp_plan, metric, pkg_hint, arch_spec,
                )
            # Exec-fix loop
            files = self._exec_fix_loop(files)
            best = SolutionNode(
                node_id="sequential", files=files, runs_ok=True, score=1.0,
            )
        else:
            # Fallback: single-shot generation
            if self._cfg.sequential_generation and self._cfg.architecture_planning:
                # B-32 M1 D-7: distinguish "unparsable" from "parsed but too
                # thin".  Both used to be a single INFO line that the default
                # WARNING root level swallowed.
                reason = (
                    "blueprint_unparsable"
                    if blueprint is None
                    else "blueprint_structure_invalid"
                )
                logger.warning(
                    "Sequential generation requested but blueprint unusable "
                    "(%s) — falling back to single-shot",
                    reason,
                )
                self._log_event(
                    "  Sequential generation requested but blueprint "
                    f"unusable ({reason}) — falling back to single-shot"
                )
                self._record_codegen_decision(
                    fallback="single_shot",
                    reason=reason,
                    blueprint_chars=len(arch_spec),
                )
            files = self._phase2_generate_and_fix(
                topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
            )
            if files:
                self._journal_progress_step(
                    "generate_project",
                    variant="single",
                    status="done",
                    inputs_digest=_blueprint_inputs_digest(topic, exp_plan, metric),
                    outputs={
                        name: hash_text(code) for name, code in files.items()
                    },
                )
            # Hard validation gates (E-03) for single-shot too
            if self._cfg.hard_validation and files:
                files = self._hard_validate_and_repair(
                    files, topic, exp_plan, metric, pkg_hint, arch_spec,
                )
            best = SolutionNode(
                node_id="single", files=files,
                runs_ok=bool(files), score=1.0 if files else 0.0,
            )

        # Phase 5: Review dialog (P-178: never review an empty project)
        review_rounds = 0
        if self._cfg.review_max_rounds > 0 and best.files:
            before_review = dict(best.files)
            best.files, review_rounds = self._phase4_review(
                best.files, topic, exp_plan, metric,
            )
            if best.files != before_review:
                # A review that rewrites files must not bypass the hard gates.
                self._log_event("  Review changed files — revalidating")
                if self._cfg.hard_validation:
                    best.files = self._hard_validate_and_repair(
                        best.files, topic, exp_plan, metric, pkg_hint, arch_spec,
                    )
                best.files = self._exec_fix_loop(best.files)
                best.score = 1.0 if best.files else 0.0

        elapsed = time.time() - t0
        self._log_event(
            f"CodeAgent.generate() done in {elapsed:.1f}s — "
            f"{self._calls} LLM calls, {self._runs} sandbox runs"
        )

        return CodeAgentResult(
            files=best.files,
            architecture_spec=arch_spec,
            validation_log=list(self._log),
            total_llm_calls=self._calls,
            total_sandbox_runs=self._runs,
            best_score=best.score,
            tree_nodes_explored=nodes_explored,
            review_rounds=review_rounds,
        )

    # ── Phase 1: Blueprint Planning ──────────────────────────────────────

    def _phase1_blueprint(
        self, topic: str, exp_plan: str, metric: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Generate a deep implementation blueprint.

        Returns (raw_yaml_str, parsed_blueprint_dict_or_None).
        """
        self._log_event("Phase 1: Blueprint planning")

        sp = self._pm.sub_prompt(
            "architecture_planning",
            topic=topic,
            exp_plan=exp_plan,
            metric=metric,
        )

        # Inject domain context and code search results into blueprint prompt
        domain_context = self._build_domain_context()
        if domain_context:
            sp = type(sp)(
                system=sp.system,
                user=sp.user + "\n\n" + domain_context,
                version=getattr(sp, "version", ""),
            )
            self._log_event("  Injected domain context into blueprint prompt")

        variant = "first"
        resp = self._chat(sp.system, sp.user, max_tokens=8192)
        if getattr(resp, "truncated", False):
            self._log_event(
                "  Blueprint truncated (finish_reason=length) — retrying with 32768"
            )
            variant = "retry"
            resp = self._chat(sp.system, sp.user, max_tokens=32768)

        # Extract YAML block from response (tolerate an unclosed fence)
        arch_spec = resp.content
        yaml_match = re.search(r"```ya?ml\s*\n(.*?)(?:```|\Z)", arch_spec, re.DOTALL)
        if yaml_match:
            arch_spec = yaml_match.group(1).strip()

        self._log_event(f"  Blueprint spec: {len(arch_spec)} chars")

        # B-33 N-1: persist the blueprint the moment it exists.  Waiting until
        # generate() returns means a crash during Phase 2 leaves no blueprint
        # on disk, so the step journal would have no output to validate.
        self._persist_blueprint(
            arch_spec,
            variant=variant,
            inputs_digest=_blueprint_inputs_digest(topic, exp_plan, metric),
            prompt_version=getattr(sp, "version", ""),
        )

        # Parse YAML into structured blueprint
        blueprint = self._parse_blueprint(arch_spec)
        if blueprint is None:
            # B-32 M1 D-5: one narrow "YAML only" retry before giving up on
            # the sequential path (LangChain OutputFixingParser uses
            # max_retries=1 for the same reason).
            repaired, blueprint = self._repair_blueprint_yaml(
                sp.system,
                sp.user,
                variant="yaml_repair",
                inputs_digest=_blueprint_inputs_digest(topic, exp_plan, metric),
                prompt_version=getattr(sp, "version", ""),
            )
            if blueprint is not None:
                arch_spec = repaired
        if blueprint:
            n_files = len(blueprint.get("files", []))
            self._log_event(f"  Parsed blueprint: {n_files} files")
        else:
            self._log_event("  WARNING: Could not parse blueprint YAML")

        return arch_spec, blueprint

    def _repair_blueprint_yaml(
        self,
        system: str,
        user: str,
        *,
        variant: str,
        inputs_digest: str,
        prompt_version: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Ask the model to re-emit the blueprint as valid YAML (B-32 M1).

        Returns ``("", None)`` when the repair call fails or still does not
        parse, so the caller can fall back to single-shot with evidence.
        """
        self._codegen_diag["yaml_repair_attempted"] = True
        self._log_event("  Blueprint YAML invalid — requesting a YAML-only repair")
        try:
            resp = self._chat(system, user + _YAML_REPAIR_SUFFIX, max_tokens=32768)
        except Exception as exc:  # noqa: BLE001 - repair is best-effort
            logger.warning("Blueprint YAML repair call failed: %s", exc)
            return "", None

        text = str(getattr(resp, "content", "") or "")
        match = re.search(r"```ya?ml\s*\n(.*?)(?:```|\Z)", text, re.DOTALL)
        if match:
            repaired = match.group(1).strip()
        else:
            # P-202 (F-4): without a fence the model often prefixes prose
            # ("Sure, I fixed it."), which YAML reads as a root-level scalar
            # and rejects.  Start at the first top-level ``files:`` key.
            repaired = text.strip()
            anchor = re.search(r"^files:[ \t]*$", repaired, re.MULTILINE)
            if anchor:
                repaired = repaired[anchor.start():].strip()
        if not repaired:
            return "", None
        blueprint = self._parse_blueprint(repaired)
        if blueprint is None:
            self._log_event("  YAML repair still did not parse")
            return "", None

        self._persist_blueprint(
            repaired,
            variant=variant,
            inputs_digest=inputs_digest,
            prompt_version=prompt_version,
        )
        self._log_event("  YAML repair parsed successfully")
        return repaired, blueprint

    def _record_codegen_decision(
        self,
        *,
        fallback: str,
        reason: str,
        blueprint_chars: int,
    ) -> None:
        """Persist the fallback decision next to the blueprint (B-32 M1 D-4).

        Deliberately not ``decision.json``: ``_write_stage_meta`` rewrites that
        file when the stage ends, which would erase this evidence.
        """
        payload = {
            "fallback": fallback,
            "reason": reason,
            "blueprint_chars": blueprint_chars,
            "yaml_repair_attempted": bool(
                self._codegen_diag.get("yaml_repair_attempted")
            ),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._stage_dir.mkdir(parents=True, exist_ok=True)
            path = self._stage_dir / "codegen_decision.json"
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError as exc:  # noqa: BLE001 - observability must not break codegen
            logger.warning("could not record codegen decision: %s", exc)

    def _record_module_failure(
        self,
        *,
        file_name: str,
        reason: str,
        truncated: bool,
        file_spec_str: str,
        dep_code: str,
        prompt_version: str,
        model: str,
    ) -> None:
        """Journal a failed module generation (B-34 M1-b).

        Only digests are stored (I-2); the entry is ``status="failed"`` so a
        re-entry never reuses it (I-3).  Best-effort: an unwritable journal
        must not mask the real failure.
        """
        from researchclaw.pipeline.step_journal import append_step, hash_text

        self._log_event(f"  {file_name}: journalling failed module ({reason})")
        try:
            append_step(
                self._stage_dir,
                step_id="generate_file",
                variant=file_name,
                status="failed",
                inputs_digest=hash_text(file_spec_str + "\n---\n" + dep_code),
                outputs={},
                model=model,
                truncated=truncated,
                prompt_version=prompt_version,
            )
        except Exception as exc:  # noqa: BLE001 - journal is best-effort
            logger.warning(
                "could not journal failed module %s: %s", file_name, exc,
            )

    def _journal_progress_step(
        self,
        step_id: str,
        *,
        variant: str = "",
        status: str = "done",
        inputs_digest: str = "",
        outputs: dict[str, str] | None = None,
        model: str = "",
        elapsed_sec: float = 0.0,
        prompt_version: str = "",
    ) -> None:
        """Append a progress row to ``steps.jsonl`` (B-33 ledger).

        Progress rows without outputs are intentionally not reusable
        (``should_skip`` requires a non-empty output map), so recording a
        validation round can never make a later run skip real work.
        """
        from researchclaw.pipeline.step_journal import append_step

        try:
            append_step(
                self._stage_dir,
                step_id=step_id,
                variant=variant,
                status=status,
                inputs_digest=inputs_digest,
                outputs=outputs or {},
                model=model,
                elapsed_sec=elapsed_sec,
                prompt_version=prompt_version,
            )
        except Exception as exc:  # noqa: BLE001 - journal is best-effort
            self._log_event(f"  WARNING: could not journal {step_id}: {exc}")

    @staticmethod
    def _files_digest(files: dict[str, str]) -> str:
        from researchclaw.pipeline.step_journal import hash_text

        joined = "\n---\n".join(
            f"{name}:{hash_text(code)}" for name, code in sorted(files.items())
        )
        return hash_text(joined)

    def _persist_blueprint(
        self,
        arch_spec: str,
        *,
        variant: str,
        inputs_digest: str,
        prompt_version: str,
    ) -> None:
        """Atomically persist the blueprint and journal the step (B-33 N-1).

        The raw spec is written even when YAML parsing fails, so a crash during
        Phase 2 still leaves a recoverable artifact; the journal entry carries
        digests only (never the spec body), per I-4.
        """
        from researchclaw.pipeline.step_journal import append_step, hash_text

        path = self._stage_dir / "architecture_spec.yaml"
        try:
            self._stage_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(arch_spec, encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:  # noqa: BLE001 - persistence must not break codegen
            self._log_event(f"  WARNING: could not persist blueprint: {exc}")
            return
        try:
            append_step(
                self._stage_dir,
                step_id="blueprint",
                variant=variant,
                status="done",
                inputs_digest=inputs_digest,
                outputs={"architecture_spec.yaml": hash_text(arch_spec)},
                prompt_version=prompt_version,
            )
        except Exception:  # noqa: BLE001 - journal is best-effort
            self._log_event("  WARNING: could not append blueprint step record")

    def _build_domain_context(self) -> str:
        """Build domain-specific context for injection into prompts.

        Includes:
        - Domain profile hints (file structure, libraries, evaluation)
        - Code search results (API patterns, reference code)
        """
        parts: list[str] = []

        # Domain profile context
        if self._domain_profile is not None:
            try:
                from researchclaw.domains.prompt_adapter import get_adapter
                adapter = get_adapter(self._domain_profile)
                blueprint_ctx = adapter.get_blueprint_context()
                if blueprint_ctx:
                    parts.append(
                        "# Domain-Specific Guidance\n" + blueprint_ctx
                    )
            except Exception:
                logger.debug("Failed to get domain context", exc_info=True)

        # Code search results
        if self._code_search_result is not None:
            try:
                prompt_ctx = self._code_search_result.to_prompt_context()
                if prompt_ctx:
                    parts.append(
                        "# Reference Code from GitHub\n"
                        "The following patterns were found in relevant open-source projects. "
                        "Use them as reference for API usage and project structure.\n\n"
                        + prompt_ctx
                    )
            except Exception:
                logger.debug("Failed to get code search context", exc_info=True)

        return "\n\n".join(parts)

    def _parse_blueprint(self, yaml_text: str) -> dict[str, Any] | None:
        """Parse blueprint YAML into a structured dict.

        BUG-178: LLM often includes Python type annotations in signature
        values (e.g. ``signature: (self, name: str) -> Config``).  The
        bare ``:`` breaks YAML parsing.  We quote unquoted signature
        values before parsing.
        """
        import yaml

        # P-178: strip a leading/trailing fence left by truncated output.
        cleaned = str(yaml_text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[A-Za-z]*[ \t]*\n?", "", cleaned, count=1)
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
        yaml_text = cleaned

        # B-32 M1: fold list items whose prose value ends with a colon.
        yaml_text = "\n".join(_fold_trailing_colon_items(yaml_text.split("\n")))

        # Pre-process: sanitize values that contain Python type annotations,
        # unclosed quotes, or other patterns that break YAML parsing.
        import re as _bp_re
        sanitized_lines = []
        for line in yaml_text.split("\n"):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                sanitized_lines.append(line)
                continue

            # Skip lines that are pure list markers or block scalars
            if stripped.startswith(("- ", "---", "...")):
                # For list items like `- key: value`, extract after `- `
                if stripped.startswith("- ") and ":" in stripped[2:]:
                    inner = stripped[2:]
                else:
                    sanitized_lines.append(line)
                    continue
            elif ":" in stripped:
                inner = stripped
            else:
                sanitized_lines.append(line)
                continue

            # Find the YAML key separator (first `:` followed by space or EOL)
            m = _bp_re.search(r":\s", inner)
            if not m:
                sanitized_lines.append(line)
                continue

            val_part = inner[m.end():].strip()
            if not val_part:
                sanitized_lines.append(line)
                continue

            # Already properly quoted — skip
            if val_part.startswith(("'", "|", ">")):
                sanitized_lines.append(line)
                continue

            # Check if value needs quoting:
            # 1) Contains `:` or `->` (type annotations)
            # 2) Starts with `"` but doesn't end with `"` (unclosed quote)
            # 3) Contains `[` with `:` (e.g. dict[str, float])
            needs_quoting = False
            if val_part.startswith('"'):
                # Already quoted — check if properly closed
                if not val_part.endswith('"') or val_part.count('"') % 2 != 0:
                    needs_quoting = True  # unclosed or malformed quote
                else:
                    sanitized_lines.append(line)
                    continue
            elif ":" in val_part or "->" in val_part:
                needs_quoting = True

            if needs_quoting:
                # Strip any existing partial quotes, escape internal quotes
                clean = val_part.strip('"').replace('"', '\\"')
                # Remove inline comments (# ...) to avoid YAML issues
                comment_idx = clean.find("  #")
                if comment_idx >= 0:
                    clean = clean[:comment_idx].rstrip()
                indent = line[:len(line) - len(stripped)]
                prefix = stripped[:len(stripped) - len(inner)]  # e.g. "- "
                key_sep = inner[:m.end()]
                sanitized_lines.append(
                    f'{indent}{prefix}{key_sep}"{clean}"'
                )
            else:
                sanitized_lines.append(line)
        sanitized = "\n".join(sanitized_lines)

        for attempt_text in (sanitized, yaml_text):
            try:
                data = yaml.safe_load(attempt_text)
                if isinstance(data, dict) and "files" in data:
                    return data
            except Exception as exc:
                self._log_event(f"  Blueprint YAML parse error: {exc}")
        return None

    @staticmethod
    def _is_valid_blueprint(blueprint: dict[str, Any]) -> bool:
        """Check if a blueprint has the minimum required structure."""
        files = blueprint.get("files", [])
        if not files or not isinstance(files, list):
            return False
        # Need at least 2 files with generation_order
        has_order = sum(
            1 for f in files
            if isinstance(f, dict) and "generation_order" in f
        )
        return has_order >= 2

    # ── Phase 2a: Sequential File Generation ─────────────────────────────

    @staticmethod
    def _is_mechanical_module(file_name: str) -> bool:
        """Wiring/formatting modules need less reasoning than algorithms."""
        stem = file_name.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        return any(hint in stem for hint in _MECHANICAL_FILE_HINTS)

    def _module_line_budget(self, file_spec: dict[str, Any]) -> int:
        """Line budget for one module: blueprint value, else config default."""
        raw = file_spec.get("max_lines")
        try:
            value = int(raw) if raw is not None else int(self._cfg.file_max_lines)
        except (TypeError, ValueError):
            value = int(self._cfg.file_max_lines)
        return max(40, value)

    def _thinking_extra(self, file_name: str) -> dict[str, Any]:
        """Per-module thinking controls (B-34 M4).

        Returns ``{}`` unless ``thinking_policy == "tiered"``, so the default
        stays byte-identical for providers that reject unknown body keys.
        """
        policy = str(getattr(self._cfg, "thinking_policy", "off") or "off")
        if policy != "tiered":
            return {}
        if self._is_mechanical_module(file_name):
            effort = str(
                getattr(self._cfg, "thinking_mechanical_effort", "") or ""
            )
            return {"reasoning_effort": effort} if effort else {}
        limit = int(getattr(self._cfg, "thinking_core_max_tokens", 0) or 0)
        return {"reasoning": {"max_tokens": limit}} if limit > 0 else {}

    def _phase2_sequential_generate(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        blueprint: dict[str, Any],
    ) -> dict[str, str]:
        """Generate files one-by-one following blueprint dependency order."""
        self._log_event("Phase 2: Sequential generation (blueprint-guided)")

        generated_files: dict[str, str] = {}
        code_memory: dict[str, dict[str, Any]] = {}  # CodeMem summaries

        from researchclaw.pipeline.step_journal import hash_text

        # Sort files by generation_order
        file_specs = blueprint.get("files", [])
        file_specs = [f for f in file_specs if isinstance(f, dict)]

        # Ensure generation_order exists; default to list position
        for i, fs in enumerate(file_specs):
            if "generation_order" not in fs:
                fs["generation_order"] = i + 1

        file_specs.sort(key=lambda f: f.get("generation_order", 99))

        for file_spec in file_specs:
            file_name = file_spec.get("name", "")
            if not file_name:
                continue

            self._log_event(
                f"  Generating {file_name} "
                f"(order={file_spec.get('generation_order')})"
            )
            file_t0 = time.time()

            # Build dependency context
            deps = file_spec.get("dependencies", [])
            dep_summaries = ""
            dep_code = ""

            for dep in deps:
                if isinstance(dep, str):
                    if dep in code_memory:
                        dep_summaries += (
                            f"\n### {dep} (summary)\n"
                            + json.dumps(code_memory[dep], indent=2)
                            + "\n"
                        )
                    if dep in generated_files:
                        dep_code += (
                            f"\n### {dep}\n```python\n"
                            + generated_files[dep]
                            + "\n```\n"
                        )

            if not dep_summaries:
                dep_summaries = "(no dependencies yet)"
            if not dep_code:
                dep_code = "(no dependencies yet)"

            # Generate this file via LLM
            file_spec_str = json.dumps(file_spec, indent=2, default=str)
            sp = self._pm.sub_prompt(
                "generate_single_file",
                file_name=file_name,
                file_spec=file_spec_str,
                blueprint=arch_spec,
                dependency_summaries=dep_summaries,
                dependency_code=dep_code,
                topic=topic,
                exp_plan=exp_plan[:4000],  # Truncate to avoid token overflow
                pkg_hint=pkg_hint,
            )
            # B-34 M4: advertise a line budget and pick a thinking tier.
            _line_budget = self._module_line_budget(file_spec)
            _budget_note = (
                f"\n\nBUDGET: keep this file at or under {_line_budget} lines. "
                "If the design needs more, stop at a coherent, runnable "
                "subset rather than truncating mid-statement."
            )
            sp = type(sp)(
                system=sp.system,
                user=sp.user + _budget_note,
                version=getattr(sp, "version", ""),
            )
            _extra_body = self._thinking_extra(file_name)
            _extra_kwargs = {"extra_body": _extra_body} if _extra_body else {}
            if _extra_body:
                self._log_event(
                    f"  {file_name}: thinking tier {_extra_body}"
                )
            resp = self._chat(
                sp.system, sp.user, max_tokens=8192, **_extra_kwargs,
            )
            budget = 8192
            if getattr(resp, "truncated", False):
                self._log_event(
                    f"  {file_name}: truncated — retrying with 32768"
                )
                resp = self._chat(
                    sp.system, sp.user, max_tokens=32768, **_extra_kwargs,
                )
                budget = 32768

            # Extract code from response.  M1-a closes an unterminated fence
            # before the patterns run; otherwise a complete answer that just
            # forgot the closing fence is discarded as empty.
            truncated = bool(getattr(resp, "truncated", False))
            code = self._extract_single_file_code(resp.content, file_name)
            if truncated or not code:
                # B-34 M1-b: never continue silently.  A truncated 32768
                # response is incomplete code, and an empty extraction means
                # the module does not exist — either way the remaining work
                # would end in an evidence-gate failure hours later.
                reason = "truncated" if truncated else "empty"
                self._codegen_diag.setdefault("module_failures", []).append({
                    "file": file_name,
                    "reason": reason,
                    "budget_tokens": budget,
                    "response_chars": len(str(getattr(resp, "content", "") or "")),
                })
                self._record_module_failure(
                    file_name=file_name,
                    reason=reason,
                    truncated=truncated,
                    file_spec_str=file_spec_str,
                    dep_code=dep_code,
                    prompt_version=getattr(sp, "version", ""),
                    model=str(getattr(resp, "model", "") or ""),
                )
                if truncated:
                    message = (
                        f"{file_name}: response still truncated at {budget} "
                        "tokens (finish_reason=length)"
                    )
                else:
                    message = (
                        f"{file_name}: no code could be extracted from the "
                        "response"
                    )
                self._log_event(f"  ERROR: {message}")
                logger.error("Stage 10 module generation failed: %s", message)
                raise ModuleExtractionError(file_name=file_name, reason=reason)

            generated_files[file_name] = code

            # B-33 L1 extension: a successful module used to be invisible in
            # steps.jsonl (only failures were journalled), so a 40-minute
            # Phase 2 looked identical to a dead run.  Progress rows carry
            # digests only (I-2).
            self._journal_progress_step(
                "generate_file",
                variant=file_name,
                status="done",
                inputs_digest=hash_text(file_spec_str + "\n---\n" + dep_code),
                outputs={file_name: hash_text(code)},
                model=str(getattr(resp, "model", "") or ""),
                elapsed_sec=time.time() - file_t0,
                prompt_version=getattr(sp, "version", ""),
            )

            # Build CodeMem summary via AST
            code_memory[file_name] = self._build_code_summary(
                file_name, code,
            )

            self._log_event(
                f"  {file_name}: {len(code.split(chr(10)))} lines, "
                f"{len(code_memory[file_name].get('classes', []))} classes"
            )

        # Verify we have main.py
        # B-29: never promote another file to main.py — renaming config.py
        # removed the module other files import, and left Stage 12 with a
        # config-only entrypoint. Request a real entrypoint instead.
        if "main.py" not in generated_files:
            self._log_event(
                "  WARNING: No main.py generated — requesting dedicated entrypoint"
            )
            entry_t0 = time.time()
            entry = self._generate_entrypoint_file(
                topic, exp_plan, metric, generated_files,
            )
            if entry:
                generated_files["main.py"] = entry
                self._journal_progress_step(
                    "entrypoint",
                    variant="dedicated",
                    status="done",
                    inputs_digest=hash_text(topic + "\n---\n" + metric),
                    outputs={"main.py": hash_text(entry)},
                    elapsed_sec=time.time() - entry_t0,
                )
                self._log_event(
                    f"  Dedicated entrypoint generated: "
                    f"{len(entry.split(chr(10)))} lines"
                )
            else:
                self._log_event(
                    "  WARNING: dedicated entrypoint generation failed"
                )

        self._log_event(
            f"  Sequential generation complete: {len(generated_files)} files"
        )
        return generated_files

    def _generate_entrypoint_file(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        files: dict[str, str],
        max_attempts: int = 2,
    ) -> str:
        """B-29: generate ``main.py`` when sequential generation skipped it."""
        issues: list[str] | None = None
        system = self._pm.system("code_generation")
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
            resp = self._chat(system, user, max_tokens=budget)
            if (
                getattr(resp, "truncated", False)
                and budget < ENTRYPOINT_RETRY_MAX_TOKENS
            ):
                self._log_event(
                    f"  entrypoint attempt {attempt}: truncated — escalating"
                )
                resp = self._chat(
                    system, user, max_tokens=ENTRYPOINT_RETRY_MAX_TOKENS,
                )
            code = self._extract_single_file_code(resp.content, "main.py")
            issues = entrypoint_issues(code)
            if code.strip() and not issues:
                return code
            self._log_event(
                f"  entrypoint attempt {attempt} rejected: "
                + ("; ".join(issues) or "empty output")
            )
        return ""

    @staticmethod
    def _extract_single_file_code(content: str, expected_name: str) -> str:
        """Extract Python code from LLM response for a single file."""
        # B-34 M1-a (same fix as P-178): a complete answer may omit the
        # closing fence.  Without this, every fenced pattern below misses,
        # the raw-text fallback fails ``ast.parse``, and the module is
        # silently dropped.
        content = _close_unterminated_fence(content)

        # Try to extract from ```python``` block
        m = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
        if m and m.group(1).strip():
            return m.group(1).strip()

        # Try ```filename:xxx.py block
        m = re.search(
            rf"```(?:filename:)?{re.escape(expected_name)}\s*\n(.*?)```",
            content, re.DOTALL,
        )
        if m and m.group(1).strip():
            return m.group(1).strip()

        # Any other fenced block — e.g. a plain ``` with no language tag,
        # which models commonly emit even when told to skip fences entirely.
        m = re.search(r"```[^\n`]*\n(.*?)```", content, re.DOTALL)
        if m and m.group(1).strip():
            return m.group(1).strip()

        # No fence found — only trust the raw response as code if it
        # actually parses as valid Python. Without this check, a
        # conversational reply (e.g. "Same, no change.") gets accepted
        # verbatim and silently corrupts the file.
        stripped = content.strip()
        if stripped:
            try:
                ast.parse(stripped)
            except SyntaxError:
                return ""
            return stripped

        return ""

    @staticmethod
    def _build_code_summary(
        filename: str, code: str,
    ) -> dict[str, Any]:
        """Build a CodeMem-style compressed summary via AST analysis."""
        summary: dict[str, Any] = {
            "filename": filename,
            "classes": [],
            "functions": [],
            "imports": [],
        }

        try:
            tree = ast.parse(code)
        except SyntaxError:
            summary["parse_error"] = True
            return summary

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for n in node.body:
                    if isinstance(n, ast.FunctionDef):
                        args = [a.arg for a in n.args.args if a.arg != "self"]
                        methods.append({
                            "name": n.name,
                            "args": args,
                        })
                summary["classes"].append({
                    "name": node.name,
                    "bases": [ast.unparse(b) for b in node.bases],
                    "methods": methods,
                })
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                args = [a.arg for a in node.args.args]
                summary["functions"].append({
                    "name": node.name,
                    "args": args,
                })
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                try:
                    summary["imports"].append(ast.unparse(node))
                except Exception:
                    pass

        return summary

    # ── Phase 2.5: Hard Validation Gates (E-03) ─────────────────────────

    def _hard_validate_and_repair(
        self,
        files: dict[str, str],
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
    ) -> dict[str, str]:
        """Run AST-based hard validation and repair critical issues.

        Critical issues trigger targeted file regeneration.  Non-critical
        issues are logged as warnings only.
        """
        self._log_event("Phase 2.5: Hard validation gates")

        for attempt in range(self._cfg.hard_validation_max_repairs + 1):
            round_t0 = time.time()
            critical, warnings = self._hard_validate(files)
            # Progress-only row: the validation round completed (status reflects
            # whether critical issues remain).  Empty outputs keep it out of
            # should_skip, so it can never suppress real work.
            self._journal_progress_step(
                "hard_validation",
                variant=f"attempt-{attempt}",
                status="done" if not critical else "failed",
                inputs_digest=self._files_digest(files),
                elapsed_sec=time.time() - round_t0,
            )

            # Log warnings
            for w in warnings:
                self._log_event(f"  WARNING: {w}")

            if not critical:
                self._log_event(
                    f"  Hard validation passed "
                    f"({len(warnings)} warning(s), attempt {attempt})"
                )
                return files

            self._log_event(
                f"  Hard validation found {len(critical)} CRITICAL issue(s) "
                f"(attempt {attempt}/{self._cfg.hard_validation_max_repairs})"
            )
            for c in critical:
                self._log_event(f"  CRITICAL: {c}")

            if attempt >= self._cfg.hard_validation_max_repairs:
                self._log_event(
                    "  Max repair attempts reached — proceeding with warnings"
                )
                return files

            # Targeted repair: ask LLM to fix specific critical issues
            files = self._repair_critical_issues(
                files, critical, topic, exp_plan, metric, arch_spec,
                attempt=attempt,
                max_attempts=self._cfg.hard_validation_max_repairs,
            )

        return files

    def _hard_validate(
        self, files: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        """Run AST-based checks and classify as CRITICAL or WARNING.

        Returns (critical_issues, warning_issues).
        """
        critical: list[str] = []
        warnings: list[str] = []

        from researchclaw.experiment.validator import (
            check_class_quality,
            check_code_complexity,
            check_api_correctness,
            check_variable_scoping,
            validate_syntax,
        )

        # 1. Syntax check — always critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            syn = validate_syntax(code)
            if not syn.ok:
                for issue in syn.errors:
                    critical.append(
                        f"[{fname}] Syntax error: {issue.message} "
                        f"(line {issue.line})"
                    )

        # 2. Class quality — some are critical
        class_warns = check_class_quality(files)
        for w in class_warns:
            if "identical AST to parent" in w:
                critical.append(w)
            elif "NOT a real ablation" in w:
                critical.append(w)
            elif "creates nn.Module" in w and "inside forward()" in w:
                critical.append(w)
            elif "empty or trivial subclass" in w:
                # Critical: ablation classes must have real implementations
                critical.append(w)
            else:
                warnings.append(w)

        # 3. Code complexity — hardcoded metrics are critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            complexity_warns = check_code_complexity(code)
            for w in complexity_warns:
                if "hardcoded metric" in w.lower():
                    critical.append(f"[{fname}] {w}")
                elif "trivial computation" in w.lower():
                    critical.append(f"[{fname}] {w}")
                else:
                    warnings.append(f"[{fname}] {w}")

        # 4. API correctness — NameError-causing issues are critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            api_warns = check_api_correctness(code, fname)
            for w in api_warns:
                if "NameError" in w or "Import-usage mismatch" in w:
                    critical.append(w)
                elif "does not exist" in w:
                    critical.append(w)
                else:
                    warnings.append(w)

        # 5. Variable scoping — UnboundLocalError is critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            scope_warns = check_variable_scoping(code, fname)
            for w in scope_warns:
                if "UnboundLocalError" in w:
                    critical.append(w)
                else:
                    warnings.append(w)

        # 6. Cross-file import consistency — check local imports resolve
        known_modules = {
            fname.replace(".py", "")
            for fname in files
            if fname.endswith(".py")
        }
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod_top = node.module.split(".")[0]
                    # Check if importing from a local module that exists
                    if mod_top in known_modules:
                        # Verify imported names exist in target file
                        target_file = f"{mod_top}.py"
                        if target_file in files and node.names:
                            target_code = files[target_file]
                            try:
                                target_tree = ast.parse(target_code)
                            except SyntaxError:
                                continue
                            exported = set()
                            for tnode in ast.walk(target_tree):
                                if isinstance(tnode, ast.ClassDef):
                                    exported.add(tnode.name)
                                elif isinstance(tnode, ast.FunctionDef):
                                    exported.add(tnode.name)
                                elif isinstance(tnode, ast.Assign):
                                    for t in tnode.targets:
                                        if isinstance(t, ast.Name):
                                            exported.add(t.id)
                            for alias in node.names:
                                name = alias.name
                                if name != "*" and name not in exported:
                                    critical.append(
                                        f"[{fname}] ImportError: "
                                        f"'{name}' not defined in "
                                        f"'{target_file}' — will crash"
                                    )

        # 7. BUG-R41-04: main.py MUST have an `if __name__ == "__main__"` block
        #    and must call a training/experiment function — otherwise Docker runs
        #    the file and exits 0 with no output.
        main_code = files.get("main.py", "")
        if main_code:
            try:
                main_tree = ast.parse(main_code)
                has_main_guard = False
                for node in ast.walk(main_tree):
                    if isinstance(node, ast.If):
                        # Check for `if __name__ == "__main__"` pattern
                        test = node.test
                        if isinstance(test, ast.Compare):
                            left = test.left
                            if (
                                isinstance(left, ast.Name)
                                and left.id == "__name__"
                                and len(test.comparators) == 1
                            ):
                                comp = test.comparators[0]
                                if (
                                    isinstance(comp, ast.Constant)
                                    and comp.value == "__main__"
                                ):
                                    has_main_guard = True
                                    break
                if not has_main_guard:
                    critical.append(
                        "[main.py] Missing `if __name__ == \"__main__\":` block — "
                        "script will define functions/classes but never execute "
                        "training. Add a main guard that calls the experiment entry "
                        "point."
                    )
            except SyntaxError:
                pass  # Already caught by syntax check above

        return critical, warnings

    def _repair_critical_issues(
        self,
        files: dict[str, str],
        critical_issues: list[str],
        topic: str,
        exp_plan: str,
        metric: str,
        arch_spec: str,
        *,
        attempt: int = 0,
        max_attempts: int = 0,
    ) -> dict[str, str]:
        """Ask LLM to fix critical validation issues."""
        self._log_event("  Targeted repair for critical issues")
        _record_repair_trace(
            self._stage_dir,
            phase="agent_validation_failed",
            attempt=attempt,
            max_attempts=max_attempts,
            error_summary=f"{len(critical_issues)} CRITICAL issue(s)",
            extra={"issues": [str(i)[:300] for i in critical_issues[:20]]},
        )

        # Identify which files need repair
        affected_files: set[str] = set()
        for issue in critical_issues:
            # Extract filename from issue string: [filename.py] ...
            m = re.match(r"\[([^\]]+\.py)\]", issue)
            if m:
                affected_files.add(m.group(1))
            else:
                # If no filename found, assume all files affected
                affected_files.update(
                    f for f in files if f.endswith(".py")
                )

        if not affected_files:
            affected_files.update(f for f in files if f.endswith(".py"))

        files_ctx = self._format_files(files)
        issues_text = "\n".join(f"- {issue}" for issue in critical_issues)

        prompt = (
            "Your generated code has CRITICAL issues that will cause "
            "runtime failures or produce invalid results. Fix ALL of them.\n\n"
            "## Critical Issues Found\n"
            f"{issues_text}\n\n"
            "## Architecture Blueprint\n"
            f"{arch_spec[:4000]}\n\n"
            "## Current Code\n"
            f"{files_ctx}\n\n"
            "## Rules\n"
            "1. Fix every critical issue listed above\n"
            "2. Ablation/variant classes MUST have different implementations "
            "from their parent — change the forward() or core method\n"
            "3. Never hardcode metric values — compute them from actual data\n"
            "4. nn.Module layers must be created in __init__(), not forward()\n"
            "5. All cross-file imports must reference names that actually exist\n"
            "6. Output ALL files in ```filename:xxx.py``` format\n"
        )

        sys_prompt = self._pm.system("code_generation")
        resp = self._chat(sys_prompt, prompt, max_tokens=16384)

        fixed = self._extract_files(resp.content)
        _record_repair_trace(
            self._stage_dir,
            phase="agent_repair",
            attempt=attempt,
            max_attempts=max_attempts,
            prompt=prompt,
            response=resp.content,
            model=str(getattr(resp, "model", "") or ""),
            truncated=getattr(resp, "truncated", None),
            accepted=sorted(fixed),
            rejected=sorted(set(files) - set(fixed)),
            reason="merged" if fixed else "no_extractable_file",
        )
        if fixed:
            merged = dict(files)
            merged.update(fixed)
            self._log_event(
                f"  Repair updated {len(fixed)} file(s): "
                f"{', '.join(sorted(fixed))}"
            )
            return merged

        self._log_event("  WARNING: Repair produced no extractable files")
        return files

    # ── Phase 2b: Single-Shot Generate + Exec-Fix (legacy) ───────────────

    def _phase2_generate_and_fix(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> dict[str, str]:
        """Generate code in single shot, then iteratively fix via sandbox."""
        self._log_event("Phase 2: Single-shot generate + exec-fix")

        # Initial generation (uses the existing code_generation prompt)
        files = self._generate_code(
            topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
        )
        if not files:
            self._log_event("  WARNING: empty generation, returning fallback")
            return files

        return self._exec_fix_loop(files)

    def _exec_fix_loop(self, files: dict[str, str]) -> dict[str, str]:
        """Run exec-fix loop if sandbox is available."""
        if not self._sandbox_factory or self._cfg.exec_fix_max_iterations <= 0:
            return files

        for i in range(self._cfg.exec_fix_max_iterations):
            result = self._run_in_sandbox(files)
            if result.returncode == 0:
                self._log_event(f"  Exec-fix iter {i}: code runs OK")
                break

            self._log_event(
                f"  Exec-fix iter {i}: crashed (rc={result.returncode}), "
                f"stderr={len(result.stderr or '')} chars"
            )
            files = self._fix_runtime_error(files, result)

        return files

    def _generate_code(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> dict[str, str]:
        """Single code generation call with architecture spec injected."""
        # Inject architecture specification into the pkg_hint slot
        hint = pkg_hint
        if arch_spec:
            hint = (
                f"{pkg_hint}\n\n"
                "## ARCHITECTURE SPECIFICATION (follow this file and class structure)\n"
                f"{arch_spec}\n"
            )

        # BUG-004: Inject numerical stability requirements
        hint += (
            "\n\n## NUMERICAL STABILITY (MANDATORY)\n"
            "- Add gradient clipping: `torch.nn.utils.clip_grad_norm_(params, 1.0)`\n"
            "- After each optimizer step, check for NaN loss:\n"
            "  `if torch.isnan(loss): print('FAIL: NaN detected'); break`\n"
            "- When logging metrics, guard against NaN/Inf:\n"
            "  `v = float(val); v = 0.0 if (math.isnan(v) or math.isinf(v)) else v`\n"
            "- For RL: clip rewards to [-10, 10], use reward normalization\n"
        )

        sp = self._pm.for_stage(
            "code_generation",
            topic=topic,
            metric=metric,
            pkg_hint=hint,
            exp_plan=exp_plan,
        )
        resp = self._chat(sp.system, sp.user, max_tokens=max_tokens)

        files = self._extract_files(resp.content)
        truncated = bool(getattr(resp, "truncated", False))
        if not files and (resp.content.strip() or truncated):
            # Retry with higher token budget (P-178: also on truncation)
            self._log_event(
                "  Empty extraction%s, retrying with 32768 tokens"
                % (" after truncation" if truncated else "")
            )
            resp = self._chat(sp.system, sp.user, max_tokens=32768)
            files = self._extract_files(resp.content)

        return files

    def _fix_runtime_error(
        self, files: dict[str, str], result: Any,
    ) -> dict[str, str]:
        """Fix a runtime error using targeted or full-file repair.

        E-05: Parse the error traceback to identify the failing file and
        line, then send only the affected file with a focused context
        window.  Falls back to full-file repair if parsing fails.
        """
        stderr_tail = (result.stderr or "")[-3000:]
        stdout_tail = "\n".join(
            (result.stdout or "").split("\n")[-50:]
        )

        # Try targeted repair first (E-05)
        error_loc = self._parse_error_location(stderr_tail, files)
        if error_loc:
            fname, lineno, error_msg = error_loc
            self._log_event(
                f"  Targeted repair: {fname}:{lineno} — {error_msg[:80]}"
            )
            fixed = self._targeted_file_repair(
                files, fname, lineno, error_msg, stderr_tail,
            )
            if fixed:
                return fixed

        # Fallback: full-file repair
        files_ctx = self._format_files(files)
        sp = self._pm.sub_prompt(
            "code_exec_fix",
            stderr=stderr_tail or "(empty)",
            stdout_tail=stdout_tail or "(empty)",
            returncode=str(result.returncode),
            files_context=files_ctx,
        )
        resp = self._chat(sp.system, sp.user, max_tokens=16384)

        fixed = self._extract_files(resp.content)
        if fixed:
            merged = dict(files)
            merged.update(fixed)
            return merged
        return files

    @staticmethod
    def _parse_error_location(
        stderr: str, files: dict[str, str],
    ) -> tuple[str, int, str] | None:
        """Parse Python traceback to find failing file and line.

        Returns (filename, line_number, error_message) or None.
        """
        known_files = set(files.keys())
        # Parse traceback lines: File "xxx.py", line NNN
        tb_pattern = re.compile(
            r'File "(?:[^"]*[/\\])?([^"]+\.py)", line (\d+)'
        )
        matches = list(tb_pattern.finditer(stderr))
        if not matches:
            return None

        # Find the last match that references one of our files
        for m in reversed(matches):
            fname = m.group(1)
            lineno = int(m.group(2))
            if fname in known_files:
                # Extract error message (last line of stderr)
                lines = stderr.strip().split("\n")
                error_msg = lines[-1] if lines else "Unknown error"
                return fname, lineno, error_msg

        return None

    def _targeted_file_repair(
        self,
        files: dict[str, str],
        target_file: str,
        error_line: int,
        error_msg: str,
        full_stderr: str,
    ) -> dict[str, str] | None:
        """Repair a single file with focused context around the error."""
        if target_file not in files:
            return None

        code = files[target_file]
        code_lines = code.split("\n")
        total_lines = len(code_lines)

        # Extract context window: ±30 lines around error
        window = 30
        start = max(0, error_line - window - 1)
        end = min(total_lines, error_line + window)
        context_lines = code_lines[start:end]

        # Number the lines for the LLM
        numbered = "\n".join(
            f"{start + i + 1:4d} | {line}"
            for i, line in enumerate(context_lines)
        )

        # Build compact dependency context (summaries only)
        dep_summaries = ""
        for fname, fcode in files.items():
            if fname != target_file and fname.endswith(".py"):
                summary = self._build_code_summary(fname, fcode)
                dep_summaries += (
                    f"\n### {fname}: "
                    f"{len(summary.get('classes', []))} classes, "
                    f"{len(summary.get('functions', []))} functions\n"
                )
                for cls in summary.get("classes", []):
                    methods = ", ".join(
                        m["name"] for m in cls.get("methods", [])
                    )
                    dep_summaries += (
                        f"  class {cls['name']}"
                        f"({', '.join(cls.get('bases', []))})"
                        f": [{methods}]\n"
                    )

        prompt = (
            f"Fix the runtime error in `{target_file}` at line {error_line}.\n\n"
            f"## Error\n```\n{error_msg}\n```\n\n"
            f"## Full Traceback (last 1500 chars)\n"
            f"```\n{full_stderr[-1500:]}\n```\n\n"
            f"## {target_file} (lines {start + 1}-{end})\n"
            f"```python\n{numbered}\n```\n\n"
            f"## Other Files in Project\n{dep_summaries}\n\n"
            f"## Full File ({target_file}, {total_lines} lines)\n"
            f"```python\n{code}\n```\n\n"
            f"Output the COMPLETE fixed `{target_file}` in "
            f"```filename:{target_file}``` format. Fix the root cause, "
            f"not just the symptom."
        )

        sys_prompt = (
            "You are a debugging expert. Fix the specific runtime error "
            "shown. Preserve experiment design and scientific methodology. "
            "Output the COMPLETE fixed file."
        )
        resp = self._chat(sys_prompt, prompt, max_tokens=16384)

        fixed = self._extract_files(resp.content)
        if not fixed:
            # Try extracting as single file
            code_match = re.search(
                r"```(?:python|filename:\S+)\s*\n(.*?)```",
                resp.content, re.DOTALL,
            )
            if code_match:
                fixed = {target_file: code_match.group(1).strip()}

        if fixed and target_file in fixed:
            merged = dict(files)
            merged.update(fixed)
            self._log_event(
                f"  Targeted repair applied to {target_file} "
                f"({len(fixed[target_file].split(chr(10)))} lines)"
            )
            return merged

        return None

    # ── Phase 3: Solution Tree Search ─────────────────────────────────────

    def _phase3_tree_search(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> tuple[SolutionNode, int]:
        """Explore multiple candidate solutions via tree search."""
        self._log_event("Phase 3: Solution tree search")
        all_nodes: list[SolutionNode] = []

        # Generate initial candidates
        n_cand = max(self._cfg.tree_search_candidates, 1)
        for k in range(n_cand):
            self._log_event(f"  Generating candidate {k + 1}/{n_cand}")
            files = self._generate_code(
                topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
            )
            node = SolutionNode(
                node_id=f"gen-{k}",
                files=files,
                depth=0,
                generation_method="initial",
            )
            all_nodes.append(node)

        # Iterative evaluate-fix-branch loop
        for depth in range(self._cfg.tree_search_max_depth):
            # Evaluate unevaluated nodes
            for node in all_nodes:
                if not node.evaluated:
                    self._evaluate_node(node, metric)

            # Sort by score
            all_nodes.sort(key=lambda n: n.score, reverse=True)

            self._log_event(
                f"  Depth {depth}: {len(all_nodes)} nodes, "
                f"best={all_nodes[0].node_id} score={all_nodes[0].score:.2f}"
            )

            # If best runs OK, we're done
            if all_nodes[0].runs_ok:
                break

            # Generate fix variants for top-2 crashing candidates
            new_nodes: list[SolutionNode] = []
            for node in all_nodes[:2]:
                if not node.runs_ok:
                    fixed_files = self._fix_runtime_error(
                        node.files,
                        _SimpleResult(
                            returncode=node.returncode,
                            stdout=node.stdout,
                            stderr=node.stderr,
                        ),
                    )
                    new_node = SolutionNode(
                        node_id=f"{node.node_id}-fix{depth}",
                        files=fixed_files,
                        parent_id=node.node_id,
                        depth=depth + 1,
                        generation_method="fix",
                    )
                    new_nodes.append(new_node)

            all_nodes.extend(new_nodes)

        # Final evaluation of any remaining unevaluated nodes
        for node in all_nodes:
            if node.returncode == -1:
                self._evaluate_node(node, metric)

        all_nodes.sort(key=lambda n: n.score, reverse=True)
        best = all_nodes[0]
        self._log_event(
            f"  Tree search complete: best={best.node_id} "
            f"score={best.score:.2f}, explored {len(all_nodes)} nodes"
        )

        return best, len(all_nodes)

    def _evaluate_node(self, node: SolutionNode, metric_key: str) -> None:
        """Run a node's code in sandbox and update its score."""
        if not node.files:
            node.score = 0.0
            return

        result = self._run_in_sandbox(
            node.files,
            timeout_sec=self._cfg.tree_search_eval_timeout_sec,
        )
        node.evaluated = True
        node.returncode = result.returncode
        node.stdout = result.stdout
        node.stderr = result.stderr
        node.runs_ok = result.returncode == 0
        node.metrics = dict(result.metrics) if result.metrics else {}
        node.score = self._score_node(node, metric_key)

    @staticmethod
    def _score_node(node: SolutionNode, metric_key: str) -> float:
        """Score a solution node based on execution results."""
        score = 0.0
        if node.runs_ok:
            score += 1.0
        if node.stdout and len(node.stdout) > 100:
            score += 0.3  # produces meaningful output
        if node.metrics:
            score += 0.5
            if metric_key in node.metrics:
                score += 0.5
        if node.stderr and "Error" in node.stderr:
            score -= 0.2
        return max(score, 0.0)

    # ── Phase 5: Multi-Agent Review Dialog ────────────────────────────────

    def _phase4_review(
        self,
        files: dict[str, str],
        topic: str,
        exp_plan: str,
        metric: str,
    ) -> tuple[dict[str, str], int]:
        """Reviewer agent examines code; coder fixes critical issues."""
        self._log_event("Phase 4: Review dialog")

        rounds = 0
        for r in range(self._cfg.review_max_rounds):
            rounds += 1
            files_ctx = self._format_files(files)

            sp = self._pm.sub_prompt(
                "code_reviewer",
                topic=topic,
                exp_plan=exp_plan,
                metric=metric,
                files_context=files_ctx,
            )
            resp = self._chat(sp.system, sp.user, max_tokens=4096)

            review = self._parse_json(resp.content)
            if not isinstance(review, dict) or not review:
                self._log_event(
                    f"  Review round {r + 1}: could not parse JSON, skipping"
                )
                break

            verdict = review.get("verdict", "APPROVE")
            score = review.get("score", 10)
            critical = review.get("critical_issues", [])

            self._log_event(
                f"  Review round {r + 1}: verdict={verdict}, score={score}, "
                f"critical_issues={len(critical)}"
            )

            if verdict == "APPROVE" or not critical:
                break

            # Fix critical issues using the code_generation system prompt
            fix_prompt = (
                "A code reviewer found these critical issues in your experiment code.\n"
                "Fix ALL of them while preserving the experiment design.\n\n"
                "## Critical Issues\n"
                + "\n".join(f"- {issue}" for issue in critical)
                + f"\n\n## Current Code\n{files_ctx}\n\n"
                "Output ALL files in ```filename:xxx.py``` format, "
                "including unchanged files."
            )
            sys_prompt = self._pm.system("code_generation")
            fix_resp = self._chat(sys_prompt, fix_prompt, max_tokens=16384)

            fixed = self._extract_files(fix_resp.content)
            if fixed:
                files = dict(files)
                files.update(fixed)

        return files, rounds

    # ── Helpers ────────────────────────────────────────────────────────────

    def _chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 8192,
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        """Make an LLM call and track count."""
        self._calls += 1
        messages = [{"role": "user", "content": user}]
        kwargs: dict[str, Any] = {
            "messages": messages,
            "system": system,
            "max_tokens": max_tokens,
        }
        if extra_body:
            kwargs["extra_body"] = extra_body
        return self._llm.chat(**kwargs)

    def _get_or_create_sandbox(self) -> _SandboxLike:
        """Lazily create a single sandbox instance for all validation runs."""
        if self._sandbox is None:
            sandbox_dir = self._stage_dir / "agent_sandbox"
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            self._sandbox = self._sandbox_factory(
                self._exp_config, sandbox_dir,
            )
        return self._sandbox

    def _run_in_sandbox(
        self,
        files: dict[str, str],
        timeout_sec: int | None = None,
    ) -> Any:
        """Write files to a temp directory and run in sandbox."""
        if not self._sandbox_factory:
            raise RuntimeError("No sandbox factory configured")

        self._runs += 1
        timeout = timeout_sec or self._cfg.exec_fix_timeout_sec

        # Write files to a numbered attempt directory
        run_dir = self._stage_dir / "agent_runs" / f"attempt_{self._runs:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for fname, code in files.items():
            fpath = (run_dir / fname).resolve()
            # BUG-CA-10: Prevent path traversal from LLM-generated filenames
            if not fpath.is_relative_to(run_dir.resolve()):
                self._log_event(f"  WARNING: Skipping path-traversal filename: {fname}")
                continue
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(code, encoding="utf-8")

        # Run using the sandbox
        sandbox = self._get_or_create_sandbox()
        try:
            result = sandbox.run_project(run_dir, timeout_sec=timeout)
        except Exception as exc:
            self._log_event(f"  Sandbox run failed: {exc}")
            result = _SimpleResult(
                returncode=1,
                stdout="",
                stderr=f"Sandbox exception: {exc}",
            )

        return result

    def _extract_files(self, content: str) -> dict[str, str]:
        """Extract multi-file code blocks from LLM output."""
        # Local import to avoid circular dependency with executor.py
        from researchclaw.pipeline.executor import _extract_multi_file_blocks

        return _extract_multi_file_blocks(content)

    @staticmethod
    def _format_files(files: dict[str, str]) -> str:
        """Format files for inclusion in a prompt."""
        parts = []
        for fname in sorted(files):
            parts.append(f"```filename:{fname}\n{files[fname]}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """Best-effort JSON extraction from LLM response.

        BUG-17: Always returns ``dict | None`` — never a bare string or list,
        which would cause ``.get()`` crashes in callers.
        """
        def _as_dict(val: Any) -> dict[str, Any] | None:
            return val if isinstance(val, dict) else None

        # Direct parse
        try:
            return _as_dict(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass
        # ```json``` fenced block
        m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
        if m:
            try:
                return _as_dict(json.loads(m.group(1)))
            except (json.JSONDecodeError, ValueError):
                pass
        # First {...} object (supports up to 2 levels of nesting)
        m = re.search(
            r"\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}",
            text, re.DOTALL,
        )
        if m:
            try:
                return _as_dict(json.loads(m.group(0)))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _log_event(self, msg: str) -> None:
        """Log to both Python logger and the internal validation log."""
        logger.info("[CodeAgent] %s", msg)
        self._log.append(msg)


# ---------------------------------------------------------------------------
# Lightweight result stand-in for error plumbing
# ---------------------------------------------------------------------------


@dataclass
class _SimpleResult:
    """Minimal sandbox result for internal error plumbing."""

    returncode: int = 1
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0
    metrics: dict[str, object] = field(default_factory=dict)
    timed_out: bool = False
