"""Pluggable code-generation backends for experiment Stages 10 & 13.

Supports three providers:
  - ``llm``         — existing LLM chat API (backward-compatible default)
  - ``claude_code`` — Claude Code CLI (``claude -p``)
  - ``codex``       — OpenAI Codex CLI (``codex exec``)

Usage::

    from researchclaw.experiment.code_agent import create_code_agent

    agent = create_code_agent(config, llm=llm_client, prompts=pm)
    result = agent.generate(exp_plan=plan, topic=topic, ...)
    if result.ok:
        files = result.files  # dict[str, str]
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from researchclaw.config import RCConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CodeAgentResult:
    """Output from a code agent invocation."""

    files: dict[str, str]  # filename -> code content
    provider_name: str  # "llm", "claude_code", "codex"
    elapsed_sec: float
    raw_output: str = ""
    error: str | None = None
    #: A1-9：本次调用实际使用的 provider 会话（``id`` / ``resumed``），
    #: 无会话能力时为 None。
    session_info: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.files)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class CodeAgentProvider(Protocol):
    """Protocol for code generation backends."""

    @property
    def name(self) -> str: ...

    def generate(
        self,
        *,
        exp_plan: str,
        topic: str,
        metric_key: str,
        pkg_hint: str,
        compute_budget: str,
        extra_guidance: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        """Generate experiment code from scratch (Stage 10)."""
        ...

    def refine(
        self,
        *,
        current_files: dict[str, str],
        run_summaries: list[str],
        metric_key: str,
        metric_direction: str,
        topic: str,
        extra_hints: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        """Refine existing experiment code based on run results (Stage 13)."""
        ...

    def repair(
        self,
        *,
        files: dict[str, str],
        issues: str,
        workdir: Path,
        timeout_sec: int = 300,
    ) -> CodeAgentResult:
        """Fix validation or runtime issues in code."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _collect_py_files(workdir: Path) -> dict[str, str]:
    """Read all .py files from a directory (flat, no subdirs)."""
    files: dict[str, str] = {}
    for pyfile in sorted(workdir.glob("*.py")):
        if pyfile.name.startswith("_codex_") or pyfile.name.startswith("_agent_"):
            continue
        files[pyfile.name] = pyfile.read_text(encoding="utf-8")
    return files


def _seed_workdir(workdir: Path, files: dict[str, str]) -> None:
    """Pre-populate workdir with files for refinement/repair."""
    workdir.mkdir(parents=True, exist_ok=True)
    for fname, content in files.items():
        (workdir / fname).write_text(content, encoding="utf-8")


def format_feedback_for_agent(
    sandbox_result: Any,
    metric_key: str,
    metric_direction: str,
    best_metric: float | None,
) -> str:
    """Format sandbox run results as structured feedback for CLI agents."""
    parts = ["## Previous Run Results"]
    parts.append(f"Return code: {sandbox_result.returncode}")
    parts.append(f"Elapsed: {sandbox_result.elapsed_sec:.1f}s")
    parts.append(f"Timed out: {sandbox_result.timed_out}")
    if sandbox_result.metrics:
        parts.append("Metrics:")
        for k, v in sandbox_result.metrics.items():
            parts.append(f"  {k}: {v}")
    if sandbox_result.stderr:
        parts.append(f"Stderr (last 1000 chars):\n{sandbox_result.stderr[-1000:]}")
    parts.append(f"\nTarget: {metric_direction} '{metric_key}'")
    if best_metric is not None:
        parts.append(f"Best so far: {best_metric}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LlmCodeAgent — wraps existing LLM chat API (backward-compatible)
# ---------------------------------------------------------------------------

class LlmCodeAgent:
    """Code agent backed by the existing OpenAI-compatible LLM chat API.

    This implementation extracts the LLM call + response parsing logic that was
    previously inline in ``_execute_code_generation`` and
    ``_execute_iterative_refine``, preserving exact behavior.
    """

    def __init__(
        self,
        llm: Any,
        prompts: Any,
        config: RCConfig,
    ) -> None:
        self._llm = llm
        self._pm = prompts
        self._config = config

    @property
    def name(self) -> str:
        return "llm"

    def generate(
        self,
        *,
        exp_plan: str,
        topic: str,
        metric_key: str,
        pkg_hint: str,
        compute_budget: str,
        extra_guidance: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        from researchclaw.pipeline.executor import (
            _chat_with_prompt,
            _extract_multi_file_blocks,
        )

        start = time.monotonic()
        sp = self._pm.for_stage(
            "code_generation",
            topic=topic,
            metric=metric_key,
            pkg_hint=pkg_hint + "\n" + compute_budget + "\n" + extra_guidance,
            exp_plan=exp_plan,
        )
        # Higher max_tokens for reasoning models
        _code_max_tokens = sp.max_tokens or 8192
        if any(
            self._config.llm.primary_model.startswith(p)
            for p in ("gpt-5", "o3", "o4")
        ):
            _code_max_tokens = max(_code_max_tokens, 16384)

        try:
            resp = _chat_with_prompt(
                self._llm,
                sp.system,
                sp.user,
                json_mode=sp.json_mode,
                max_tokens=_code_max_tokens,
            )
            files = _extract_multi_file_blocks(resp.content)
            # Retry on empty response with higher token limit
            if not files and not resp.content.strip():
                logger.warning(
                    "LlmCodeAgent: empty response (len=%d, finish=%s). "
                    "Retrying with 32768 tokens.",
                    len(resp.content),
                    resp.finish_reason,
                )
                resp = _chat_with_prompt(
                    self._llm,
                    sp.system,
                    sp.user,
                    json_mode=sp.json_mode,
                    max_tokens=32768,
                )
                files = _extract_multi_file_blocks(resp.content)

            elapsed = time.monotonic() - start
            if not files:
                logger.warning(
                    "LlmCodeAgent: no files extracted (resp len=%d)",
                    len(resp.content),
                )
            return CodeAgentResult(
                files=files,
                provider_name="llm",
                elapsed_sec=elapsed,
                raw_output=resp.content[:2000],
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("LlmCodeAgent.generate failed: %s", exc)
            return CodeAgentResult(
                files={},
                provider_name="llm",
                elapsed_sec=elapsed,
                error=str(exc),
            )

    def refine(
        self,
        *,
        current_files: dict[str, str],
        run_summaries: list[str],
        metric_key: str,
        metric_direction: str,
        topic: str,
        extra_hints: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        from researchclaw.pipeline.executor import (
            _chat_with_prompt,
            _extract_code_block,
            _extract_multi_file_blocks,
        )

        start = time.monotonic()

        def _files_to_context(project_files: dict[str, str]) -> str:
            parts = []
            for fname, code in sorted(project_files.items()):
                parts.append(f"```filename:{fname}\n{code}\n```")
            return "\n\n".join(parts)

        try:
            ip = self._pm.sub_prompt(
                "iterative_improve",
                metric_key=metric_key,
                metric_direction=metric_direction,
                files_context=_files_to_context(current_files),
                run_summaries=chr(10).join(run_summaries[:20]),
                condition_coverage_hint="",
                topic=topic,
            )
            user_prompt = ip.user + extra_hints

            response = _chat_with_prompt(
                self._llm,
                ip.system,
                user_prompt,
                max_tokens=ip.max_tokens or 8192,
            )
            extracted_files = _extract_multi_file_blocks(response.content)
            if not extracted_files:
                single_code = _extract_code_block(response.content)
                if single_code.strip():
                    extracted_files = {"main.py": single_code}

            elapsed = time.monotonic() - start
            return CodeAgentResult(
                files=extracted_files,
                provider_name="llm",
                elapsed_sec=elapsed,
                raw_output=response.content[:2000],
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("LlmCodeAgent.refine failed: %s", exc)
            return CodeAgentResult(
                files={},
                provider_name="llm",
                elapsed_sec=elapsed,
                error=str(exc),
            )

    def repair(
        self,
        *,
        files: dict[str, str],
        issues: str,
        workdir: Path,
        timeout_sec: int = 300,
    ) -> CodeAgentResult:
        from researchclaw.pipeline.executor import (
            _chat_with_prompt,
            _extract_code_block,
            _extract_multi_file_blocks,
        )

        start = time.monotonic()
        all_files_ctx = "\n\n".join(
            f"```filename:{f}\n{c}\n```" for f, c in files.items()
        )
        try:
            rp = self._pm.sub_prompt(
                "code_repair",
                fname="main.py",
                issues_text=issues,
                all_files_ctx=all_files_ctx,
            )
            resp = _chat_with_prompt(self._llm, rp.system, rp.user)
            # Try multi-file extraction first, then single-block
            repaired = _extract_multi_file_blocks(resp.content)
            if not repaired:
                code = _extract_code_block(resp.content)
                if code.strip():
                    repaired = {"main.py": code}

            elapsed = time.monotonic() - start
            return CodeAgentResult(
                files=repaired,
                provider_name="llm",
                elapsed_sec=elapsed,
                raw_output=resp.content[:2000],
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return CodeAgentResult(
                files={},
                provider_name="llm",
                elapsed_sec=elapsed,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# CLI agent base — shared subprocess logic for Claude Code / Codex
# ---------------------------------------------------------------------------

class _CliAgentBase:
    """Shared infrastructure for CLI-based coding agents."""

    _provider_name: str = ""

    def __init__(
        self,
        binary_path: str,
        model: str = "",
        max_budget_usd: float = 5.0,
        timeout_sec: int = 600,
        extra_args: list[str] | None = None,
        env_extra: list[tuple[str, str]] | None = None,
        session_id: str | None = None,
        resume_session: bool = False,
    ) -> None:
        self._binary = binary_path
        self._model = model
        self._max_budget_usd = max_budget_usd
        self._default_timeout = timeout_sec
        self._extra_args = extra_args or []
        self._env_extra = dict(env_extra or [])
        # A1-9：同一 (run, stage) 首跑固定 session id，重试 --resume 续接。
        self._session_id = session_id
        self._resume_session = bool(resume_session)
        self.last_session: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return self._provider_name

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        """Kill a subprocess and its children (npm .CMD wrappers spawn a child)."""
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=15,
                )
                return
            except (OSError, subprocess.SubprocessError):
                pass
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, AttributeError):
            proc.terminate()

    def _run_subprocess(
        self,
        cmd: list[str],
        workdir: Path,
        timeout_sec: int,
        stdin_text: str | None = None,
    ) -> tuple[int, str, str, float, bool]:
        """Run command as subprocess with process-group cleanup on timeout.

        ``stdin_text`` is required on Windows when the prompt contains newlines:
        npm ``.CMD`` shims route argv through cmd.exe, which truncates a quoted
        argument at the first newline.

        Returns (returncode, stdout, stderr, elapsed_sec, timed_out).
        """
        workdir.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        timed_out = False
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir,
            env={**os.environ, **self._env_extra},
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                stdin_text.encode("utf-8") if stdin_text is not None else None,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            # Kill the whole tree: os.killpg/os.getpgid do not exist on Windows
            # (AttributeError, not OSError), and terminate() only reaps the
            # cmd.exe shim while the node child keeps the pipes open.
            self._kill_process_tree(proc)
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    stdout_bytes, stderr_bytes = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    stdout_bytes, stderr_bytes = b"", b""

        elapsed = time.monotonic() - start
        return (
            proc.returncode if proc.returncode is not None else -1,
            _to_text(stdout_bytes),
            _to_text(stderr_bytes),
            elapsed,
            timed_out,
        )

    def _build_result(
        self,
        workdir: Path,
        returncode: int,
        stdout: str,
        stderr: str,
        elapsed: float,
        timed_out: bool,
    ) -> CodeAgentResult:
        """Collect .py files from workdir and build result."""
        files = _collect_py_files(workdir)
        error = None
        if timed_out:
            error = f"Timed out after {elapsed:.0f}s"
        elif returncode != 0 and not files:
            error = f"Exited {returncode}: {stderr[:500]}"
        return CodeAgentResult(
            files=files,
            provider_name=self._provider_name,
            elapsed_sec=elapsed,
            raw_output=stdout[:3000],
            error=error,
            session_info=self.last_session,
        )

    @staticmethod
    def _generate_prompt(
        topic: str,
        exp_plan: str,
        metric_key: str,
        pkg_hint: str,
        compute_budget: str,
        extra_guidance: str,
    ) -> str:
        return (
            "You are a non-interactive code-generation agent for a research "
            "paper. Do NOT ask questions or wait for clarification; if any "
            "detail is missing, choose a reasonable default and write the "
            "files now.\n\n"
            f"TOPIC: {topic}\n\n"
            f"EXPERIMENT PLAN:\n{exp_plan}\n\n"
            f"PRIMARY METRIC: {metric_key}\n"
            f"{pkg_hint}\n{compute_budget}\n{extra_guidance}\n\n"
            "INSTRUCTIONS:\n"
            "1. Create a multi-file Python project in the current directory.\n"
            "2. The entry point MUST be main.py.\n"
            "3. main.py must print metrics as 'name: value' lines to stdout.\n"
            f"4. Use condition labels: 'condition=<name> {metric_key}: <value>'\n"
            "5. FORBIDDEN: subprocess, os.system, eval, exec, shutil, socket, "
            "network calls, external data files.\n"
            "6. Use deterministic seeds (numpy.random.seed or random.seed).\n"
            "7. Write ALL files to the current working directory.\n"
            "8. Do NOT create subdirectories.\n"
            "9. Write the files and stop. Do NOT run the code or any "
            "experiments; the harness executes main.py separately.\n"
        )

    @staticmethod
    def _refine_prompt(
        current_files: dict[str, str],
        run_summaries: list[str],
        metric_key: str,
        metric_direction: str,
        topic: str,
        extra_hints: str,
    ) -> str:
        files_listing = "\n".join(
            f"  - {fname} ({len(code)} chars)" for fname, code in current_files.items()
        )
        summaries_text = "\n".join(run_summaries[:10]) if run_summaries else "(no prior runs)"
        return (
            "You are improving experiment code for a research paper. Do NOT ask "
            "questions; edit the files directly.\n\n"
            f"TOPIC: {topic}\n"
            f"TARGET: {metric_direction} '{metric_key}'\n\n"
            f"EXISTING FILES in current directory:\n{files_listing}\n\n"
            "Read the existing files, then improve them based on these run results:\n\n"
            f"PRIOR RUN SUMMARIES:\n{summaries_text}\n\n"
            f"{extra_hints}\n\n"
            "INSTRUCTIONS:\n"
            "1. Read existing code, understand the experiment structure.\n"
            "2. Modify files to improve the metric.\n"
            "3. Keep the entry point as main.py.\n"
            "4. Write modified files to the current directory.\n"
            "5. FORBIDDEN: subprocess, os.system, eval, exec, shutil, socket.\n"
        )

    @staticmethod
    def _repair_prompt(
        files: dict[str, str],
        issues: str,
    ) -> str:
        files_listing = "\n".join(
            f"  - {fname} ({len(code)} chars)" for fname, code in files.items()
        )
        return (
            "The experiment code has validation or runtime issues. Do NOT ask "
            "questions; fix the files directly.\n\n"
            f"ISSUES:\n{issues}\n\n"
            f"FILES in current directory:\n{files_listing}\n\n"
            "INSTRUCTIONS:\n"
            "1. Read the existing files in the current directory.\n"
            "2. Fix ALL reported issues.\n"
            "3. Write the corrected files back.\n"
            "4. FORBIDDEN: subprocess, os.system, eval, exec, shutil, socket.\n"
        )


# ---------------------------------------------------------------------------
# ClaudeCodeAgent
# ---------------------------------------------------------------------------

class ClaudeCodeAgent(_CliAgentBase):
    """Code agent backed by Claude Code CLI (``claude -p``)."""

    _provider_name = "claude_code"

    def _build_cmd(self, workdir: Path) -> list[str]:
        # The prompt is piped via stdin, not argv: on Windows the npm .CMD shim
        # passes argv through cmd.exe, which truncates a multi-line argument at
        # the first newline (the model then only sees the first sentence).
        cmd = [
            self._binary,
            "-p",
            "--dangerously-skip-permissions",
            "--output-format", "text",
            "--allowed-tools", "Bash Edit Write Read",
            "--add-dir", str(workdir),
        ]
        if self._model:
            cmd += ["--model", self._model]
        if self._max_budget_usd:
            cmd += ["--max-budget-usd", str(self._max_budget_usd)]
        # A1-9：首跑固定会话 id，重试续接同一会话（不重放全部上下文）。
        if self._session_id:
            if self._resume_session:
                cmd += ["--resume", self._session_id]
            else:
                cmd += ["--session-id", self._session_id]
        cmd.extend(self._extra_args)
        return cmd

    #: 会话不存在时 CLI 的报错（本地实测：exit 1 + 该行 stderr）。
    _SESSION_MISSING_MARKERS = ("no conversation found with session id",)

    def _invoke(
        self, prompt: str, workdir: Path, timeout_sec: int,
    ) -> tuple[int, str, str, float, bool]:
        """Run one invocation, degrading loudly when --resume has no session.

        P-035 §6.3 的陷阱是「会话过期后静默从零开始」。实测该 CLI 在会话
        不存在时 **hard fail**（exit 1），因此这里先续接、失败则显式新建会话
        并在 ``last_session.resumed`` 记 False——attempt 记录不会假装续接。
        """
        resume_requested = bool(self._session_id and self._resume_session)
        rc, out, err, elapsed, timed_out = self._run_subprocess(
            self._build_cmd(workdir), workdir, timeout_sec, stdin_text=prompt,
        )
        resumed = resume_requested
        if (
            resume_requested
            and not timed_out
            and rc != 0
            and any(m in err.lower() for m in self._SESSION_MISSING_MARKERS)
        ):
            logger.warning(
                "Claude session %s not found; starting a new session "
                "(context will be replayed)", self._session_id,
            )
            self._resume_session = False
            try:
                rc, out, err, extra_elapsed, timed_out = self._run_subprocess(
                    self._build_cmd(workdir), workdir, timeout_sec,
                    stdin_text=prompt,
                )
            finally:
                self._resume_session = True
            elapsed += extra_elapsed
            resumed = False
        if self._session_id:
            self.last_session = {
                "id": self._session_id,
                "resumed": resumed,
                "resume_requested": resume_requested,
            }
        return rc, out, err, elapsed, timed_out

    def generate(
        self,
        *,
        exp_plan: str,
        topic: str,
        metric_key: str,
        pkg_hint: str,
        compute_budget: str,
        extra_guidance: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        prompt = self._generate_prompt(
            topic, exp_plan, metric_key, pkg_hint, compute_budget, extra_guidance,
        )
        rc, stdout, stderr, elapsed, to = self._invoke(
            prompt, workdir, timeout_sec or self._default_timeout,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)

    def refine(
        self,
        *,
        current_files: dict[str, str],
        run_summaries: list[str],
        metric_key: str,
        metric_direction: str,
        topic: str,
        extra_hints: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        _seed_workdir(workdir, current_files)
        prompt = self._refine_prompt(
            current_files, run_summaries, metric_key, metric_direction,
            topic, extra_hints,
        )
        rc, stdout, stderr, elapsed, to = self._invoke(
            prompt, workdir, timeout_sec or self._default_timeout,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)

    def repair(
        self,
        *,
        files: dict[str, str],
        issues: str,
        workdir: Path,
        timeout_sec: int = 300,
    ) -> CodeAgentResult:
        _seed_workdir(workdir, files)
        prompt = self._repair_prompt(files, issues)
        rc, stdout, stderr, elapsed, to = self._invoke(
            prompt, workdir, timeout_sec or self._default_timeout,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)


# ---------------------------------------------------------------------------
# CodexAgent
# ---------------------------------------------------------------------------

class CodexAgent(_CliAgentBase):
    """Code agent backed by OpenAI Codex CLI (``codex exec``)."""

    _provider_name = "codex"

    def _build_cmd(self, workdir: Path) -> list[str]:
        # `codex exec -` reads the full prompt from stdin; argv stays free of
        # newlines (same Windows .cmd shim constraint as ClaudeCodeAgent).
        cmd = [
            self._binary,
            "exec", "-",
            "--sandbox", "workspace-write",
            "--json",
            "-C", str(workdir),
        ]
        if self._model:
            cmd += ["-m", self._model]
        cmd.extend(self._extra_args)
        return cmd

    def generate(
        self,
        *,
        exp_plan: str,
        topic: str,
        metric_key: str,
        pkg_hint: str,
        compute_budget: str,
        extra_guidance: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        prompt = self._generate_prompt(
            topic, exp_plan, metric_key, pkg_hint, compute_budget, extra_guidance,
        )
        cmd = self._build_cmd(workdir)
        rc, stdout, stderr, elapsed, to = self._run_subprocess(
            cmd, workdir, timeout_sec or self._default_timeout,
            stdin_text=prompt,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)

    def refine(
        self,
        *,
        current_files: dict[str, str],
        run_summaries: list[str],
        metric_key: str,
        metric_direction: str,
        topic: str,
        extra_hints: str,
        workdir: Path,
        timeout_sec: int = 600,
    ) -> CodeAgentResult:
        _seed_workdir(workdir, current_files)
        prompt = self._refine_prompt(
            current_files, run_summaries, metric_key, metric_direction,
            topic, extra_hints,
        )
        cmd = self._build_cmd(workdir)
        rc, stdout, stderr, elapsed, to = self._run_subprocess(
            cmd, workdir, timeout_sec or self._default_timeout,
            stdin_text=prompt,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)

    def repair(
        self,
        *,
        files: dict[str, str],
        issues: str,
        workdir: Path,
        timeout_sec: int = 300,
    ) -> CodeAgentResult:
        _seed_workdir(workdir, files)
        prompt = self._repair_prompt(files, issues)
        cmd = self._build_cmd(workdir)
        rc, stdout, stderr, elapsed, to = self._run_subprocess(
            cmd, workdir, timeout_sec or self._default_timeout,
            stdin_text=prompt,
        )
        return self._build_result(workdir, rc, stdout, stderr, elapsed, to)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_code_agent(
    config: RCConfig,
    llm: Any | None = None,
    prompts: Any | None = None,
    *,
    session_ctx: tuple[Path, int] | None = None,
) -> CodeAgentProvider:
    """Create the appropriate code agent based on config.experiment.cli_agent.

    ``session_ctx=(run_dir, stage)`` enables A1-9 session continuation for
    backends in ``SESSION_RESUME_BACKENDS``: the first attempt pins a
    deterministic ``--session-id``, later attempts ``--resume`` it.
    """
    agent_cfg = config.experiment.cli_agent
    provider = agent_cfg.provider

    if provider == "llm":
        if llm is None:
            raise RuntimeError("LLM code agent requires an LLM client")
        from researchclaw.prompts import PromptManager

        return LlmCodeAgent(llm, prompts or PromptManager(), config)  # type: ignore[return-value]

    session_id: str | None = None
    resume_session = False
    if session_ctx is not None:
        from researchclaw.runtime.attempt import (
            next_attempt_number, session_resume_supported, stage_session_id,
        )

        run_dir, stage = session_ctx
        if session_resume_supported(provider):
            session_id = stage_session_id(run_dir, stage)
            resume_session = next_attempt_number(run_dir, stage) > 1

    if provider == "claude_code":
        binary = agent_cfg.binary_path or shutil.which("claude")
        if not binary:
            raise RuntimeError(
                "Claude Code binary not found. "
                "Install it or set experiment.cli_agent.binary_path."
            )
        return ClaudeCodeAgent(  # type: ignore[return-value]
            binary_path=binary,
            model=agent_cfg.model or "sonnet",
            max_budget_usd=agent_cfg.max_budget_usd,
            timeout_sec=agent_cfg.timeout_sec,
            extra_args=list(agent_cfg.extra_args),
            env_extra=list(agent_cfg.env_extra),
            session_id=session_id,
            resume_session=resume_session,
        )

    if provider == "codex":
        binary = agent_cfg.binary_path or shutil.which("codex")
        if not binary:
            raise RuntimeError(
                "Codex binary not found. "
                "Install it or set experiment.cli_agent.binary_path."
            )
        return CodexAgent(  # type: ignore[return-value]
            binary_path=binary,
            model=agent_cfg.model or "",
            max_budget_usd=agent_cfg.max_budget_usd,
            timeout_sec=agent_cfg.timeout_sec,
            extra_args=list(agent_cfg.extra_args),
            env_extra=list(agent_cfg.env_extra),
        )

    raise ValueError(f"Unknown code agent provider: {provider}")