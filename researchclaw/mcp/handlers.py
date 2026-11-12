"""Per-tool handler entry points referenced by ``tools/registry.yaml`` (G4-M3).

``handler`` format is ``module:attr`` and cannot express ``Class.method``, so
each tool gets a module-level coroutine. The server binds its own instance via
``functools.partial`` at construction time — no global singleton dispatch
(P-103 review O-11).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

HANDLERS: dict[str, Callable[[Any, dict], Awaitable[dict]]] = {}


async def handle_run_pipeline(server: Any, args: dict) -> dict:
    return await server._handle_run_pipeline(args)


async def handle_get_pipeline_status(server: Any, args: dict) -> dict:
    return await server._handle_get_status(args)


async def handle_get_experiment_results(server: Any, args: dict) -> dict:
    return await server._handle_get_results(args)


async def handle_search_literature(server: Any, args: dict) -> dict:
    return await server._handle_search_literature(args)


async def handle_review_paper(server: Any, args: dict) -> dict:
    return await server._handle_review_paper(args)


async def handle_get_paper(server: Any, args: dict) -> dict:
    return await server._handle_get_paper(args)


HANDLERS.update({
    "run_pipeline": handle_run_pipeline,
    "get_pipeline_status": handle_get_pipeline_status,
    "get_experiment_results": handle_get_experiment_results,
    "search_literature": handle_search_literature,
    "review_paper": handle_review_paper,
    "get_paper": handle_get_paper,
})
