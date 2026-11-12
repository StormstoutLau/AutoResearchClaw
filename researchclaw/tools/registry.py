"""Tool registry loader: single source of truth for tool metadata (G4-M1, A4-1).

``tools/registry.yaml`` is the only source for tool metadata. Loading is
fail-closed: any invalid entry raises :class:`RegistryError` and the caller
(server / MCP / invoker entry points) decides to abort startup. A pure
pipeline CLI does not load the registry at all (P-099 Q-3).

P-103 (D-1/D-2/D-3): the registry ships as an in-package resource so wheel
installs work; nested containers are read-only; unreadable vs. malformed
files have dedicated error codes.
"""
from __future__ import annotations

import importlib
import importlib.resources
import inspect
import os
import re
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

E_REGISTRY_VERSION = "E_REGISTRY_VERSION"
E_REGISTRY_NAME = "E_REGISTRY_NAME"
E_REGISTRY_SCHEMA_MISSING = "E_REGISTRY_SCHEMA_MISSING"
E_REGISTRY_SCHEMA_INVALID = "E_REGISTRY_SCHEMA_INVALID"
E_REGISTRY_ENUM = "E_REGISTRY_ENUM"
E_REGISTRY_HANDLER = "E_REGISTRY_HANDLER"
E_REGISTRY_HANDLER_UNRESOLVED = "E_REGISTRY_HANDLER_UNRESOLVED"
E_REGISTRY_PROFILE = "E_REGISTRY_PROFILE"
E_REGISTRY_PROFILE_INVALID = "E_REGISTRY_PROFILE_INVALID"
E_REGISTRY_APPROVAL = "E_REGISTRY_APPROVAL"
E_REGISTRY_UNREADABLE = "E_REGISTRY_UNREADABLE"
E_REGISTRY_PARSE = "E_REGISTRY_PARSE"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_HANDLER_FORMAT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
_SIZE_RE = re.compile(r"^\d+[gm]$")
_RISKS = {"low", "medium", "high"}
_APPROVALS = {"never", "always", "high_only"}
_SCOPES = {"run", "global"}
_NETWORKS = {"none", "setup_only", "full"}

_DEFAULT_REGISTRY_NAME = "registry.yaml"


class RegistryError(ValueError):
    """Raised when a registry file violates the M0 schema (fail-closed)."""

    def __init__(self, code: str, message: str, *, tool: str | None = None,
                 path: str | None = None) -> None:
        super().__init__(f"{code}: {message}" + (f" [tool={tool}]" if tool else ""))
        self.code = code
        self.message = message
        self.tool = tool
        self.path = path


def _freeze(obj: Any) -> Any:
    """Recursively wrap containers read-only (P-103 / D-2)."""
    if isinstance(obj, dict):
        return types.MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


def unfreeze(obj: Any) -> Any:
    """Recursively restore plain containers (for JSON serialization seams).

    ``MappingProxyType`` breaks pydantic serialization when a schema crosses the
    in-memory JSON-RPC boundary, so SDK injection and REST output must unwrap.
    """
    if isinstance(obj, types.MappingProxyType):
        return {k: unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, dict):
        return {k: unfreeze(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [unfreeze(v) for v in obj]
    return obj


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    scope: str
    risk: str
    approval: str
    sandbox_profile: str
    handler: str

    def resolve(self) -> object:
        """Import and return the handler (V-5b; call from server/invoker entries)."""
        module_name, _, attr = self.handler.partition(":")
        try:
            module = importlib.import_module(module_name)
            obj = getattr(module, attr)
        except (ImportError, AttributeError) as exc:
            raise RegistryError(
                E_REGISTRY_HANDLER_UNRESOLVED,
                f"handler '{self.handler}' is not importable: {exc}",
                tool=self.name,
            ) from exc
        # P-103 review D-3: resolvable is not callable-safe. A class would be
        # *constructed* (not invoked) by an invoker call; reject non-functions.
        if inspect.isclass(obj) or not callable(obj):
            raise RegistryError(
                E_REGISTRY_HANDLER,
                f"handler '{self.handler}' must resolve to a callable function, "
                f"got {type(obj).__name__}",
                tool=self.name,
            )
        return obj


@dataclass(frozen=True)
class Registry:
    version: int
    tools: tuple[ToolSpec, ...]
    sandbox_profiles: dict[str, dict[str, Any]]
    source_path: Any

    def get(self, name: str) -> ToolSpec | None:
        for spec in self.tools:
            if spec.name == name:
                return spec
        return None

    def resolve_handlers(self, *, strict: bool = False) -> None:
        """V-5b: import every handler when strict; format already checked at load."""
        if not strict:
            return
        for spec in self.tools:
            spec.resolve()

    def reload(self) -> "Registry":
        """Re-read and re-validate the source file; the old instance is untouched."""
        return load_registry(self.source_path)


def _default_registry_path() -> Any:
    """Resolve the bundled registry resource; wheel installs read from the package."""
    env = os.environ.get("RC_TOOL_REGISTRY")
    if env:
        return Path(env)
    # P-103 / D-1: prefer the in-package resource so wheel installs work.
    try:
        return importlib.resources.files("researchclaw.tools").joinpath("registry.yaml")
    except (ModuleNotFoundError, TypeError):
        return Path(__file__).resolve().parents[2] / "tools" / _DEFAULT_REGISTRY_NAME


def _fail(code: str, message: str, *, tool: str | None = None,
          path: Any) -> RegistryError:
    return RegistryError(code, message, tool=tool, path=str(path))


def _read_text(source: Any) -> str:
    read = getattr(source, "read_text", None)
    if callable(read):
        return read(encoding="utf-8")
    return Path(source).read_text(encoding="utf-8")


def _check_json_schema(schema: Any, *, tool: str, path: Path) -> None:
    if schema is None:
        raise _fail(E_REGISTRY_SCHEMA_MISSING, "inputSchema is required", tool=tool, path=path)
    if not isinstance(schema, dict):
        raise _fail(E_REGISTRY_SCHEMA_INVALID, "inputSchema must be an object",
                    tool=tool, path=path)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise _fail(E_REGISTRY_SCHEMA_INVALID,
                    f"inputSchema violates JSON Schema 2020-12: {exc.message}",
                    tool=tool, path=path) from exc
    if schema.get("type") != "object":
        raise _fail(E_REGISTRY_SCHEMA_INVALID, "inputSchema.type must be 'object'",
                    tool=tool, path=path)


def _load_payload(source: Any) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(_read_text(source))
    except OSError as exc:
        raise _fail(E_REGISTRY_UNREADABLE, f"registry file unreadable: {exc}", path=source) from exc
    except yaml.YAMLError as exc:
        raise _fail(E_REGISTRY_PARSE, f"registry YAML invalid: {exc}", path=source) from exc
    if not isinstance(raw, dict):
        raise _fail(E_REGISTRY_PARSE, "registry file must be a mapping", path=source)
    return raw


def _validate_tool(tool: Any, path: Path) -> ToolSpec:
    if not isinstance(tool, dict):
        raise _fail(E_REGISTRY_NAME, "each tool must be a mapping", path=path)
    name = tool.get("name")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise _fail(E_REGISTRY_NAME, f"tool name '{name}' must match {_NAME_RE.pattern}",
                    path=path)

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        raise _fail(E_REGISTRY_NAME, "description must be a non-empty string",
                    tool=name, path=path)
    version = tool.get("version")
    if not isinstance(version, str) or not version.strip():
        raise _fail(E_REGISTRY_NAME, "version must be a non-empty string",
                    tool=name, path=path)

    _check_json_schema(tool.get("inputSchema"), tool=name, path=path)
    output_schema = tool.get("outputSchema")
    if output_schema is not None:
        if not isinstance(output_schema, dict):
            raise _fail(E_REGISTRY_SCHEMA_INVALID, "outputSchema must be an object",
                        tool=name, path=path)
        try:
            Draft202012Validator.check_schema(output_schema)
        except SchemaError as exc:
            raise _fail(E_REGISTRY_SCHEMA_INVALID,
                        f"outputSchema violates JSON Schema 2020-12: {exc.message}",
                        tool=name, path=path) from exc

    risk, approval, scope = tool.get("risk"), tool.get("approval"), tool.get("scope")
    if risk not in _RISKS:
        raise _fail(E_REGISTRY_ENUM, f"risk '{risk}' must be one of {sorted(_RISKS)}",
                    tool=name, path=path)
    if approval not in _APPROVALS:
        raise _fail(E_REGISTRY_ENUM, f"approval '{approval}' must be one of {sorted(_APPROVALS)}",
                    tool=name, path=path)
    if scope not in _SCOPES:
        raise _fail(E_REGISTRY_ENUM, f"scope '{scope}' must be one of {sorted(_SCOPES)}",
                    tool=name, path=path)

    # P-099 D-1 / P-100 D-1: a high-risk tool can never bypass approval.
    if risk == "high" and approval == "never":
        raise _fail(E_REGISTRY_APPROVAL,
                    "risk=high requires approval in {always, high_only}",
                    tool=name, path=path)

    handler = tool.get("handler")
    if not isinstance(handler, str) or not _HANDLER_FORMAT_RE.fullmatch(handler):
        raise _fail(E_REGISTRY_HANDLER,
                    f"handler '{handler}' must be 'module:attr'", tool=name, path=path)

    profile = tool.get("sandbox_profile")
    if not isinstance(profile, str) or not profile:
        raise _fail(E_REGISTRY_PROFILE, "sandbox_profile must be a non-empty string",
                    tool=name, path=path)

    return ToolSpec(
        name=name,
        version=version,
        description=description,
        input_schema=_freeze(tool["inputSchema"]),
        output_schema=_freeze(output_schema) if output_schema is not None else None,
        scope=scope,
        risk=risk,
        approval=approval,
        sandbox_profile=profile,
        handler=handler,
    )


def _validate_profiles(profiles: Any, path: Path) -> dict[str, dict[str, Any]]:
    if not isinstance(profiles, dict) or not profiles:
        raise _fail(E_REGISTRY_PROFILE_INVALID, "sandbox_profiles must be a non-empty mapping",
                    path=path)
    checked: dict[str, dict[str, Any]] = {}
    for pname, pdata in profiles.items():
        if not isinstance(pdata, dict):
            raise _fail(E_REGISTRY_PROFILE_INVALID, f"profile '{pname}' must be a mapping",
                        path=path)
        missing = [k for k in ("network", "cpu", "memory", "pids", "disk", "ttl_sec")
                   if k not in pdata]
        if missing:
            raise _fail(E_REGISTRY_PROFILE_INVALID,
                        f"profile '{pname}' missing fields: {missing}", path=path)
        if pdata["network"] not in _NETWORKS:
            raise _fail(E_REGISTRY_PROFILE_INVALID,
                        f"profile '{pname}'.network must be one of {sorted(_NETWORKS)}",
                        path=path)
        for int_key in ("cpu", "pids", "ttl_sec"):
            value = pdata[int_key]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise _fail(E_REGISTRY_PROFILE_INVALID,
                            f"profile '{pname}'.{int_key} must be a positive int", path=path)
        for size_key in ("memory", "disk"):
            value = pdata[size_key]
            if not isinstance(value, str) or not _SIZE_RE.fullmatch(value):
                raise _fail(E_REGISTRY_PROFILE_INVALID,
                            f"profile '{pname}'.{size_key} must match {value!r} pattern "
                            f"{_SIZE_RE.pattern}", path=path)
        checked[str(pname)] = dict(pdata)
    return _freeze(checked)


def load_registry(path: str | Path | None = None, *,
                  strict_handlers: bool = False) -> Registry:
    """Load and validate ``tools/registry.yaml`` (fail-closed, A4-1).

    Any invalid entry raises :class:`RegistryError`; there is no fallback and
    no "skip bad entries" path. ``strict_handlers=True`` additionally imports
    every handler module (used by server/invoker entry points).
    """
    resolved = Path(path) if path is not None else _default_registry_path()
    payload = _load_payload(resolved)

    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise _fail(E_REGISTRY_VERSION,
                    f"registry version must be the integer 1, got {version!r}", path=resolved)

    tools_raw = payload.get("tools")
    if not isinstance(tools_raw, list) or not tools_raw:
        raise _fail(E_REGISTRY_NAME, "tools must be a non-empty list", path=resolved)

    specs: list[ToolSpec] = []
    seen: set[str] = set()
    for tool in tools_raw:
        spec = _validate_tool(tool, resolved)
        if spec.name in seen:
            raise _fail(E_REGISTRY_NAME, f"duplicate tool name '{spec.name}'", path=resolved)
        seen.add(spec.name)
        specs.append(spec)

    profiles = _validate_profiles(payload.get("sandbox_profiles"), resolved)
    for spec in specs:
        if spec.sandbox_profile not in profiles:
            raise _fail(E_REGISTRY_PROFILE,
                        f"sandbox_profile '{spec.sandbox_profile}' is not defined",
                        tool=spec.name, path=resolved)

    registry = Registry(version=version, tools=tuple(specs),
                        sandbox_profiles=profiles, source_path=resolved)
    if strict_handlers:
        registry.resolve_handlers(strict=True)
    return registry
