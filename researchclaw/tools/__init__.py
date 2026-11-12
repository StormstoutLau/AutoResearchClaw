"""Tool registry subsystem (G4-M1): single source of truth for tool metadata."""
from researchclaw.tools.registry import (
    E_REGISTRY_APPROVAL,
    E_REGISTRY_ENUM,
    E_REGISTRY_HANDLER,
    E_REGISTRY_HANDLER_UNRESOLVED,
    E_REGISTRY_NAME,
    E_REGISTRY_PROFILE,
    E_REGISTRY_PROFILE_INVALID,
    E_REGISTRY_SCHEMA_INVALID,
    E_REGISTRY_SCHEMA_MISSING,
    E_REGISTRY_VERSION,
    Registry,
    RegistryError,
    ToolSpec,
    load_registry,
)

__all__ = [
    "E_REGISTRY_APPROVAL",
    "E_REGISTRY_ENUM",
    "E_REGISTRY_HANDLER",
    "E_REGISTRY_HANDLER_UNRESOLVED",
    "E_REGISTRY_NAME",
    "E_REGISTRY_PROFILE",
    "E_REGISTRY_PROFILE_INVALID",
    "E_REGISTRY_SCHEMA_INVALID",
    "E_REGISTRY_SCHEMA_MISSING",
    "E_REGISTRY_VERSION",
    "Registry",
    "RegistryError",
    "ToolSpec",
    "load_registry",
]
