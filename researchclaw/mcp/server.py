"""ResearchClaw MCP server built on the official MCP Python SDK (v2).

Six tools are exposed over stdio:

- ``run_pipeline`` (background run, returns a real ``run_id``)
- ``get_pipeline_status`` (reads the shared :mod:`researchclaw.run_state`)
- ``get_experiment_results`` (stage-14 / stage-12 / root ``results.json``)
- ``search_literature`` (real multi-source literature search)
- ``review_paper`` (Stage 18 review core, reuses ``pipeline.review_service``)
- ``get_paper`` (stage-23 / stage-22 / stage-17 / deliverables)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:  # The MCP SDK is an optional extra: pip install researchclaw[mcp]
    from mcp.server import MCPServer as _SDKMCPServer
    from mcp.types import CallToolResult, TextContent
except ImportError as _exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "MCP support requires the 'mcp' extra: pip install researchclaw[mcp]"
    ) from _exc

from researchclaw import __version__
from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig, resolve_config_path
from researchclaw.literature.search import search_papers
from researchclaw.mcp.tools import TOOL_DEFINITIONS
from researchclaw.pipeline.review_service import (
    ReviewConfigError,
    has_llm_config,
    review_paper_text,
)
from researchclaw.pipeline.runner import execute_pipeline
from researchclaw.run_state import read_run_state

logger = logging.getLogger(__name__)

_VALID_RUN_ID = re.compile(r"^rc-\d{8}-\d{6}-[a-f0-9]{6,64}$")
_MAX_TOPIC_LEN = 2000
_MAX_QUERY_LEN = 500
_MAX_PAPER_PATH_LEN = 1024


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _generate_run_id(topic: str) -> str:
    """Match the CLI run-id format: ``rc-YYYYMMDD-HHMMSS-<topic hash>``."""
    import hashlib

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    topic_hash = hashlib.sha256(topic.encode()).hexdigest()[:6]
    return f"rc-{stamp}-{topic_hash}"


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "error": message}


def _paper_to_dict(paper: Any) -> dict[str, Any]:
    authors = [getattr(author, "name", str(author)) for author in getattr(paper, "authors", ())]
    return {
        "paper_id": getattr(paper, "paper_id", ""),
        "title": getattr(paper, "title", ""),
        "authors": authors,
        "year": getattr(paper, "year", 0),
        "abstract": getattr(paper, "abstract", ""),
        "venue": getattr(paper, "venue", ""),
        "citation_count": getattr(paper, "citation_count", 0),
        "doi": getattr(paper, "doi", ""),
        "arxiv_id": getattr(paper, "arxiv_id", ""),
        "url": getattr(paper, "url", ""),
        "source": getattr(paper, "source", ""),
    }


class ResearchClawMCPServer:
    """Expose AutoResearchClaw capabilities as MCP tools.

    The class owns an official SDK ``MCPServer`` instance built with
    ``@mcp.tool()``; it does not implement its own JSON-RPC loop.
    """

    def __init__(
        self,
        config: Any = None,
        *,
        artifacts_dir: str | Path | None = None,
        execute_pipeline_fn: Any = None,
    ) -> None:
        self.config = config
        self.artifacts_root = Path(artifacts_dir or "artifacts")
        self._execute_pipeline = execute_pipeline_fn or execute_pipeline
        self._running = False
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._active_cancels: dict[str, threading.Event] = {}
        self._handlers = {
            "run_pipeline": self._handle_run_pipeline,
            "get_pipeline_status": self._handle_get_status,
            "get_experiment_results": self._handle_get_results,
            "search_literature": self._handle_search_literature,
            "review_paper": self._handle_review_paper,
            "get_paper": self._handle_get_paper,
        }
        self._mcp = _SDKMCPServer(
            name="researchclaw",
            version=__version__,
            instructions=(
                "AutoResearchClaw: run a 23-stage autonomous research pipeline. "
                "Long runs return a run_id; poll get_pipeline_status, then read "
                "get_experiment_results / get_paper."
            ),
        )
        self._register_tools()

    # ── public API ────────────────────────────────────────────────

    def get_tools(self) -> list[dict[str, Any]]:
        """Return the declarative tool definitions (kept for compatibility)."""
        return TOOL_DEFINITIONS

    @property
    def mcp(self) -> Any:
        """Return the underlying official SDK server."""
        return self._mcp

    @property
    def is_running(self) -> bool:
        return self._running

    async def run_stdio_async(self) -> None:
        """Serve the MCP protocol over stdio until the client disconnects."""
        self._running = True
        try:
            await self._mcp.run_stdio_async()
        finally:
            self._running = False

    async def start(self, transport: str = "stdio") -> None:
        """Start the server; blocks for stdio transport."""
        if transport != "stdio":
            raise NotImplementedError(
                f"Transport {transport!r} is not implemented; use 'stdio'"
            )
        await self.run_stdio_async()

    def run(self, transport: str = "stdio") -> None:
        """Synchronous entry point used by the CLI."""
        if transport != "stdio":
            raise NotImplementedError(
                f"Transport {transport!r} is not implemented; use 'stdio'"
            )
        self._mcp.run(transport="stdio")

    async def stop(self) -> None:
        """Cancel active runs and mark the server stopped."""
        self._running = False
        for cancel in list(self._active_cancels.values()):
            cancel.set()
        for task in list(self._active_tasks.values()):
            if not task.done():
                task.cancel()
        self._active_tasks.clear()
        self._active_cancels.clear()
        logger.info("MCP server stopped")

    async def handle_tool_call(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch a tool call directly (unit-test friendly)."""
        handler = self._handlers.get(name)
        if handler is None:
            return _error("INVALID_TOOL", f"Unknown tool: {name}")
        logger.info("MCP tool call: %s(%s)", name, json.dumps(arguments, default=str)[:200])
        try:
            return await handler(arguments or {})
        except ValueError as exc:
            return _error("INVALID_ARGUMENT", str(exc))
        except Exception as exc:  # noqa: BLE001 - report as protocol-level error
            logger.exception("MCP tool %s failed", name)
            return _error("INTERNAL_ERROR", self._safe_error(exc))

    # ── tool registration ────────────────────────────────────────

    def _register_tools(self) -> None:
        mcp = self._mcp

        @mcp.tool(name="run_pipeline", description=self._tool_description("run_pipeline"))
        async def _run_pipeline(
            topic: str,
            config_path: str | None = None,
            auto_approve: bool = True,
        ) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call(
                    "run_pipeline",
                    {
                        "topic": topic,
                        "config_path": config_path,
                        "auto_approve": auto_approve,
                    },
                )
            )

        @mcp.tool(
            name="get_pipeline_status",
            description=self._tool_description("get_pipeline_status"),
        )
        async def _get_pipeline_status(run_id: str) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call("get_pipeline_status", {"run_id": run_id})
            )

        @mcp.tool(
            name="get_experiment_results",
            description=self._tool_description("get_experiment_results"),
        )
        async def _get_experiment_results(
            run_id: str, stage: str | None = None
        ) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call(
                    "get_experiment_results", {"run_id": run_id, "stage": stage}
                )
            )

        @mcp.tool(
            name="search_literature",
            description=self._tool_description("search_literature"),
        )
        async def _search_literature(
            query: str, max_results: int = 10
        ) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call(
                    "search_literature", {"query": query, "max_results": max_results}
                )
            )

        @mcp.tool(
            name="review_paper",
            description=self._tool_description("review_paper"),
        )
        async def _review_paper(
            paper_path: str | None = None, run_id: str | None = None
        ) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call(
                    "review_paper", {"paper_path": paper_path, "run_id": run_id}
                )
            )

        @mcp.tool(name="get_paper", description=self._tool_description("get_paper"))
        async def _get_paper(
            run_id: str, format: Literal["markdown", "latex"] = "markdown"
        ) -> CallToolResult:
            return self._as_result(
                await self.handle_tool_call(
                    "get_paper", {"run_id": run_id, "format": format}
                )
            )

    @staticmethod
    def _tool_description(name: str) -> str:
        for tool in TOOL_DEFINITIONS:
            if tool["name"] == name:
                return str(tool["description"])
        return name

    @staticmethod
    def _as_result(payload: dict[str, Any]) -> CallToolResult:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=False, default=str),
                )
            ],
            structured_content=payload,
            is_error=payload.get("success") is False,
        )

    # ── handlers ─────────────────────────────────────────────────

    async def _handle_run_pipeline(self, args: dict[str, Any]) -> dict[str, Any]:
        topic = str(args.get("topic", "")).strip()
        if not topic or len(topic) > _MAX_TOPIC_LEN:
            return _error(
                "INVALID_ARGUMENT",
                f"topic must be a non-empty string <= {_MAX_TOPIC_LEN} characters",
            )
        if any(not task.done() for task in self._active_tasks.values()):
            return _error("RUN_IN_PROGRESS", "Another pipeline run is already active")

        try:
            config = self._load_config(args.get("config_path"))
        except (OSError, ValueError) as exc:
            return _error("INVALID_ARGUMENT", str(exc))
        if config is None:
            return _error(
                "CONFIG_REQUIRED",
                "No researchclaw config found; pass config_path or run `researchclaw init`",
            )

        run_id = _generate_run_id(topic)
        run_dir = self.artifacts_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        config_path = args.get("config_path")
        if config_path:
            try:
                shutil.copy2(Path(str(config_path)), run_dir / "config.yaml")
            except OSError as exc:
                logger.warning("MCP config snapshot failed: %s", exc)

        cancel = threading.Event()
        auto_approve = bool(args.get("auto_approve", True))
        task = asyncio.create_task(
            asyncio.to_thread(
                self._run_pipeline_thread,
                run_dir,
                run_id,
                config,
                auto_approve,
                cancel,
            )
        )
        self._active_tasks[run_id] = task
        self._active_cancels[run_id] = cancel
        task.add_done_callback(lambda _task, rid=run_id: self._finish_run(rid))

        return {
            "success": True,
            "run_id": run_id,
            "status": "started",
            "output_dir": f"artifacts/{run_id}",
            "started_at": _utcnow_iso(),
        }

    def _run_pipeline_thread(
        self,
        run_dir: Path,
        run_id: str,
        config: RCConfig,
        auto_approve: bool,
        cancel: threading.Event,
    ) -> None:
        try:
            kb_root = None
            root = getattr(getattr(config, "knowledge_base", None), "root", "")
            if root:
                kb_root = Path(root)
                kb_root.mkdir(parents=True, exist_ok=True)
            self._execute_pipeline(
                run_dir=run_dir,
                run_id=run_id,
                config=config,
                adapters=AdapterBundle(),
                auto_approve_gates=auto_approve,
                kb_root=kb_root,
                cancel_event=cancel,
            )
        except Exception:  # noqa: BLE001 - failures are visible via run_state
            logger.exception("MCP pipeline run %s failed", run_id)

    def _finish_run(self, run_id: str) -> None:
        task = self._active_tasks.pop(run_id, None)
        self._active_cancels.pop(run_id, None)
        if task is not None and task.cancelled():
            logger.info("MCP pipeline run %s cancelled", run_id)

    async def _handle_get_status(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._require_run_id(args)
        run_dir = self._run_dir(run_id)
        if not run_dir.is_dir():
            return _error("RUN_NOT_FOUND", f"Run not found: {run_id}")
        state = read_run_state(run_dir)
        return {
            "success": True,
            "run_id": run_id,
            "stage": state.current_stage,
            "stage_name": state.current_stage_name,
            "status": state.status.value,
            "is_active": state.is_active,
            "updated_at": state.last_update,
            "error": state.error,
        }

    async def _handle_get_results(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._require_run_id(args)
        run_dir = self._run_dir(run_id)
        if not run_dir.is_dir():
            return _error("RUN_NOT_FOUND", f"Run not found: {run_id}")

        stage_hint = args.get("stage")
        candidates = self._result_candidates(run_dir, stage_hint)
        for stage, path, metrics_key, conditions_key in candidates:
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            return {
                "success": True,
                "run_id": run_id,
                "stage": int(stage) if stage else 0,
                "metrics": data.get(metrics_key) or {},
                "conditions": data.get(conditions_key) or {},
                "source_path": self._relative(run_dir, path),
            }
        return _error("NO_RESULTS", f"No experiment results found for {run_id}")

    def _result_candidates(
        self, run_dir: Path, stage_hint: Any
    ) -> list[tuple[int | None, Path, str, str]]:
        stage_num: int | None = None
        if stage_hint not in (None, ""):
            match = re.search(r"(\d{1,2})", str(stage_hint))
            stage_num = int(match.group(1)) if match else None

        if stage_num == 14:
            path = self._stage_json(run_dir, 14, "experiment_summary.json")
            return [(14, path, "metrics_summary", "condition_summaries")] if path else []
        if stage_num == 12:
            return [
                (12, self._stage_json(run_dir, 12, "runs/results.json"), "metrics", "conditions"),
                (12, self._stage_json(run_dir, 12, "results.json"), "metrics", "conditions"),
            ]
        if stage_num is not None and stage_num not in (12, 14):
            path = self._stage_json(run_dir, stage_num, "results.json")
            return [(stage_num, path, "metrics", "conditions")] if path else []

        candidates: list[tuple[int | None, Path, str, str]] = []
        summary = self._stage_json(run_dir, 14, "experiment_summary.json")
        if summary:
            candidates.append((14, summary, "metrics_summary", "condition_summaries"))
        stage12 = self._stage_json(run_dir, 12, "runs/results.json")
        if stage12:
            candidates.append((12, stage12, "metrics", "conditions"))
        stage12_flat = self._stage_json(run_dir, 12, "results.json")
        if stage12_flat:
            candidates.append((12, stage12_flat, "metrics", "conditions"))
        candidates.append((None, run_dir / "results.json", "metrics", "conditions"))
        return candidates

    async def _handle_search_literature(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query or len(query) > _MAX_QUERY_LEN:
            return _error(
                "INVALID_ARGUMENT",
                f"query must be a non-empty string <= {_MAX_QUERY_LEN} characters",
            )
        try:
            max_results = int(args.get("max_results", 10) or 10)
        except (TypeError, ValueError):
            return _error("INVALID_ARGUMENT", "max_results must be an integer")
        max_results = max(1, min(max_results, 50))

        config = self._config_or_default()
        search_cfg = getattr(config, "literature_search", None) if config else None
        kwargs: dict[str, Any] = {}
        if search_cfg is not None:
            kwargs["s2_api_key"] = getattr(search_cfg, "s2_api_key", "") or ""
            kwargs["openalex_email"] = getattr(search_cfg, "openalex_email", "") or ""
            kwargs["openalex_api_key"] = getattr(search_cfg, "openalex_api_key", "") or ""

        try:
            papers = await asyncio.to_thread(
                search_papers, query, limit=max_results, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - upstream/network failure
            logger.warning("MCP literature search failed: %s", exc)
            return _error("UPSTREAM_ERROR", self._safe_error(exc))

        results = [_paper_to_dict(paper) for paper in papers]
        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }

    async def _handle_review_paper(self, args: dict[str, Any]) -> dict[str, Any]:
        paper_path = args.get("paper_path")
        run_id = args.get("run_id")
        if not paper_path and not run_id:
            return _error(
                "INVALID_ARGUMENT", "Provide either paper_path or run_id"
            )

        run_dir: Path | None = None
        if paper_path:
            try:
                path = self._resolve_paper_path(str(paper_path))
            except ValueError as exc:
                return _error("INVALID_PATH", str(exc))
        else:
            run_id = self._require_run_id({"run_id": run_id})
            run_dir = self._run_dir(run_id)
            if not run_dir.is_dir():
                return _error("RUN_NOT_FOUND", f"Run not found: {run_id}")
            path = self._find_paper(run_dir, "markdown") or self._find_paper(
                run_dir, "latex"
            )
            if path is None:
                return _error("PAPER_NOT_FOUND", f"No paper found for {run_id}")

        config = self._config_or_default()
        if not has_llm_config(config):
            return _error(
                "CONFIG_REQUIRED",
                "LLM configuration is required for paper review "
                "(set llm.base_url and the API key environment variable)",
            )

        try:
            from researchclaw.llm import create_llm_client

            llm = await asyncio.to_thread(create_llm_client, config)
        except Exception as exc:  # noqa: BLE001 - most likely missing config
            logger.warning("MCP review LLM init failed: %s", exc)
            return _error("CONFIG_REQUIRED", self._safe_error(exc))

        try:
            paper_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return _error("INTERNAL_ERROR", self._safe_error(exc))

        try:
            result = await asyncio.to_thread(
                review_paper_text,
                paper_text,
                config=config,
                llm=llm,
                run_dir=run_dir,
                topic=config.research.topic,
            )
        except ReviewConfigError as exc:
            return _error("CONFIG_REQUIRED", str(exc))
        except Exception as exc:  # noqa: BLE001 - provider / parsing failure
            logger.exception("MCP paper review failed")
            return _error("INTERNAL_ERROR", self._safe_error(exc))

        return {
            "success": True,
            "review_markdown": result.review_markdown,
            "model": result.model,
            "independent": result.independent,
            "tokens": result.tokens,
        }

    async def _handle_get_paper(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._require_run_id(args)
        run_dir = self._run_dir(run_id)
        if not run_dir.is_dir():
            return _error("RUN_NOT_FOUND", f"Run not found: {run_id}")

        fmt = str(args.get("format", "markdown") or "markdown").lower()
        if fmt not in ("markdown", "latex"):
            return _error("INVALID_ARGUMENT", "format must be 'markdown' or 'latex'")

        path = self._find_paper(run_dir, fmt)
        if path is None:
            return _error("PAPER_NOT_FOUND", f"No {fmt} paper found for {run_id}")
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return _error("INTERNAL_ERROR", self._safe_error(exc))
        return {
            "success": True,
            "run_id": run_id,
            "format": fmt,
            "path": self._relative(run_dir, path),
            "content": content,
        }

    # ── path / config helpers ────────────────────────────────────

    def _require_run_id(self, args: dict[str, Any]) -> str:
        run_id = str(args.get("run_id", "") or "")
        if not _VALID_RUN_ID.fullmatch(run_id):
            raise ValueError(f"Invalid run_id: {run_id!r}")
        return run_id

    def _run_dir(self, run_id: str) -> Path:
        root = self.artifacts_root.resolve()
        candidate = (root / run_id).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Invalid run_id: {run_id!r}")
        return candidate

    def _resolve_paper_path(self, paper_path: str) -> Path:
        if len(paper_path) > _MAX_PAPER_PATH_LEN:
            raise ValueError("paper_path is too long")
        candidate = Path(paper_path).expanduser()
        if candidate.suffix.lower() not in (".md", ".tex"):
            raise ValueError("paper_path must be a .md or .tex file")
        root = self.artifacts_root.resolve()
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("paper_path must be inside the artifacts directory")
        if not resolved.is_file():
            raise ValueError("paper_path does not exist")
        return resolved

    def _find_paper(self, run_dir: Path, fmt: str) -> Path | None:
        if fmt == "markdown":
            for stage, filename in (
                (23, "paper_final_verified.md"),
                (22, "paper_final.md"),
                (17, "paper_draft.md"),
            ):
                path = self._stage_file(run_dir, stage, filename)
                if path is not None:
                    return path
            return None

        for stage, filename in ((22, "paper.tex"),):
            path = self._stage_file(run_dir, stage, filename)
            if path is not None:
                return path
        delivered = run_dir / "deliverables" / "paper.tex"
        return delivered if delivered.is_file() else None

    @staticmethod
    def _stage_file(run_dir: Path, stage: int, filename: str) -> Path | None:
        base = f"stage-{stage:02d}"
        exact = run_dir / base / filename
        if exact.is_file():
            return exact
        for directory in sorted(run_dir.glob(f"{base}*"), reverse=True):
            candidate = directory / filename
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _stage_json(run_dir: Path, stage: int, filename: str) -> Path | None:
        return ResearchClawMCPServer._stage_file(run_dir, stage, filename)

    @staticmethod
    def _relative(run_dir: Path, path: Path) -> str:
        try:
            return path.relative_to(run_dir).as_posix()
        except ValueError:
            return path.name

    def _load_config(self, config_path: Any) -> RCConfig | None:
        if config_path:
            candidate = Path(str(config_path)).expanduser()
            if not candidate.is_file():
                raise ValueError(f"Config file not found: {Path(str(config_path)).name}")
            return RCConfig.load(candidate, check_paths=False)
        if self.config is not None:
            return self.config
        found = resolve_config_path(None)
        if found is not None and found.is_file():
            return RCConfig.load(found, check_paths=False)
        return None

    def _config_or_default(self) -> RCConfig | None:
        if self.config is not None:
            return self.config
        try:
            return self._load_config(None)
        except (OSError, ValueError):
            return None

    def _safe_error(self, exc: BaseException) -> str:
        """Never echo absolute local paths to the MCP client."""
        text = str(exc) or exc.__class__.__name__
        try:
            text = text.replace(str(self.artifacts_root.resolve()), "artifacts")
            text = text.replace(str(Path.cwd()), ".")
        except OSError:
            pass
        return text[:400]
