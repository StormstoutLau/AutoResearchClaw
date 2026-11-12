"""Tool registry API routes (G4-M2, A4-10).

The registry loads lazily but fail-closed (P-099 Q-3): the first request that
needs it — and the application startup call in ``app.py`` — raises
``RegistryError`` when the file is invalid, so a bad registry never serves.
The response exposes a whitelist of fields; ``handler`` and
``sandbox_profile`` are internal and never leave the process.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from researchclaw.tools.registry import Registry, load_registry, unfreeze

router = APIRouter(prefix="/api", tags=["tools"])

REGISTRY: Registry | None = None


def get_registry() -> Registry:
    """Lazily load the registry; app startup calls this to fail closed."""
    global REGISTRY
    if REGISTRY is None:
        REGISTRY = load_registry(strict_handlers=True)
    return REGISTRY


def load_tools_registry() -> Registry:
    """Force a reload (tests and callers that need fresh state)."""
    global REGISTRY
    REGISTRY = load_registry(strict_handlers=True)
    return REGISTRY


def _public_entry(spec: Any) -> dict[str, Any]:
    return {
        "name": spec.name,
        "version": spec.version,
        "description": spec.description,
        "inputSchema": unfreeze(spec.input_schema),
        "outputSchema": unfreeze(spec.output_schema) if spec.output_schema is not None else None,
        "scope": spec.scope,
        "risk": spec.risk,
        "approval": spec.approval,
    }


@router.get("/tools")
def get_tools() -> dict[str, Any]:
    registry = get_registry()
    return {
        "version": registry.version,
        "tools": [_public_entry(spec) for spec in registry.tools],
    }
