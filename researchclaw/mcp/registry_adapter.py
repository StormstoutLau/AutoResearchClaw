"""Dynamic tool registration from the registry (G4-M2, A4-10).

The registry (``tools/registry.yaml``) is the single source of truth: this
adapter registers every tool it declares, injects its ``inputSchema`` verbatim
into the SDK (P-100 D-5 resolution: write ``Tool.parameters`` after
``add_tool``), and wires calls through a caller-provided dispatcher. No tool
names are hard-coded here.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable

from researchclaw.tools.registry import Registry, ToolSpec, unfreeze

Dispatcher = Callable[[str, dict], Any]
Notifier = Callable[[], None]


def _make_call(dispatcher: Dispatcher, name: str,
               schema: dict[str, Any]) -> Callable[..., Any]:
    """Build the SDK-facing coroutine for one tool.

    The synthetic signature lists every ``inputSchema.properties`` key as a
    keyword-only parameter (required keys without a default) so the SDK passes
    arguments through normally; the authoritative schema is injected verbatim
    afterwards (path B), which allows richer shapes such as ``anyOf``.
    """
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    params = [
        inspect.Parameter(
            key, inspect.Parameter.KEYWORD_ONLY,
            default=inspect.Parameter.empty if key in required else None,
            annotation=Any,
        )
        for key in properties
    ]

    async def _call(**kwargs: Any) -> Any:
        return await dispatcher(name, kwargs)

    _call.__name__ = name
    _call.__signature__ = inspect.Signature(parameters=params)
    return _call


def _inject_schema(server: Any, name: str, schema: dict[str, Any]) -> None:
    """Path B (P-100 D-5): the registry schema is the single source of truth.

    ``unfreeze`` restores plain containers — ``MappingProxyType`` cannot cross
    the pydantic serialization boundary of a JSON-RPC response (P-103 finding).
    """
    tool = server._tool_manager.get_tool(name)  # noqa: SLF001 - SDK seam
    if tool is None:
        raise RuntimeError(f"tool '{name}' missing after registration")
    tool.parameters = unfreeze(schema)


def register_from_registry(server: Any, registry: Registry,
                           dispatcher: Dispatcher) -> list[str]:
    """Register every registry tool on ``server``; return the registered names."""
    registered: list[str] = []
    for spec in registry.tools:
        _register_one(server, spec, dispatcher)
        registered.append(spec.name)
    return registered


def _register_one(server: Any, spec: ToolSpec, dispatcher: Dispatcher) -> None:
    handler = spec.resolve()
    call = _make_call(dispatcher, spec.name, spec.input_schema)

    async def _entry(**kwargs: Any) -> Any:
        # ``handler`` exists so strict resolution covers the import; the actual
        # dispatch goes through the invoker seam (M3 replaces the dispatcher).
        return await call(**kwargs)

    _entry.__signature__ = call.__signature__
    _entry.__name__ = spec.name
    # structured_output=False keeps the legacy contract: the dispatcher already
    # returns a fully-formed CallToolResult (self._as_result), which the SDK
    # must not wrap again.
    server.add_tool(_entry, name=spec.name, description=spec.description,
                    structured_output=False)
    _inject_schema(server, spec.name, spec.input_schema)
    # bind the resolved handler so strict resolution is meaningful at runtime
    setattr(_entry, "__registry_handler__", handler)


def refresh_from_registry(server: Any, old_registry: Registry,
                          dispatcher: Dispatcher, *, notifier: Notifier | None = None,
                          path: Any = None) -> Registry:
    """Reload the registry, swap the registered tools, fire the notifier seam.

    The SDK-side registration is only mutated after the new registry validates
    successfully; on failure the old registration is intact and the error
    propagates (I-6).
    """
    new_registry = load_registry_for_refresh(old_registry, path)
    for spec in old_registry.tools:
        try:
            server.remove_tool(spec.name)
        except Exception:  # noqa: BLE001 - SDK raises on unknown tools; ignore
            pass
    register_from_registry(server, new_registry, dispatcher)
    if notifier is not None:
        notifier()
    return new_registry


def load_registry_for_refresh(old_registry: Registry, path: Any) -> Registry:
    from researchclaw.tools.registry import load_registry

    source = path if path is not None else old_registry.source_path
    return load_registry(source)
