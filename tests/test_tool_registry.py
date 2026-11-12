"""G4-M1 (P-101): tool registry loading and startup validation (A4-1)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

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
    RegistryError,
    load_registry,
)


def _write_registry(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def _valid_tool(**overrides) -> dict:
    tool = {
        "name": "run_pipeline",
        "version": "1.0",
        "description": "Start a research pipeline run.",
        "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}},
                        "required": ["topic"]},
        "scope": "global",
        "risk": "medium",
        "approval": "never",
        "sandbox_profile": "default",
        "handler": "researchclaw.tools.registry:load_registry",
    }
    tool.update(overrides)
    return tool


def _payload(**overrides) -> dict:
    tools = overrides.pop("tools", None)
    return {
        "version": 1,
        "tools": tools if tools is not None else [_valid_tool(**overrides)],
        "sandbox_profiles": {
            "default": {
                "network": "none", "cpu": 2, "memory": "4g",
                "pids": 512, "disk": "10g", "ttl_sec": 1800,
            }
        },
    }


# ── T-1/T-2: real registry ───────────────────────────────────────


def test_load_real_registry_six_tools() -> None:
    registry = load_registry()
    names = {t.name for t in registry.tools}
    assert names == {
        "run_pipeline", "get_pipeline_status", "get_experiment_results",
        "search_literature", "review_paper", "get_paper",
    }
    assert registry.version == 1


def test_registry_schemas_match_hardcoded_definitions() -> None:
    # INV-4 / T-2: byte-level equivalence with the pre-migration source.
    # `researchclaw.mcp` package imports the mcp SDK (fail-closed by design),
    # so environments without the extra skip this check; CI tests job and the
    # primary env install [mcp] and run it for real.
    pytest.importorskip("mcp")
    from researchclaw.mcp.tools import get_tool_schema
    from researchclaw.tools.registry import unfreeze

    registry = load_registry()
    for spec in registry.tools:
        legacy = get_tool_schema(spec.name)
        assert legacy is not None, spec.name
        assert unfreeze(spec.input_schema) == legacy["inputSchema"], spec.name
        assert spec.description == legacy["description"], spec.name


# ── T-3/T-4: schema rules ────────────────────────────────────────


def test_missing_input_schema_fails(tmp_path: Path) -> None:
    tool = _valid_tool()
    del tool["inputSchema"]
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(tools=[tool])))
    assert exc.value.code == E_REGISTRY_SCHEMA_MISSING


def test_non_object_input_schema_fails(tmp_path: Path) -> None:
    tool = _valid_tool(inputSchema={"type": "array", "items": {"type": "string"}})
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(tools=[tool])))
    assert exc.value.code == E_REGISTRY_SCHEMA_INVALID


def test_schema_draft_violation_fails(tmp_path: Path) -> None:
    # `required` as a string (not array of strings) violates 2020-12.
    tool = _valid_tool(inputSchema={"type": "object", "required": "topic"})
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(tools=[tool])))
    assert exc.value.code == E_REGISTRY_SCHEMA_INVALID


# ── T-5/T-6: enum + approval matrix ──────────────────────────────


@pytest.mark.parametrize("field,value", [
    ("risk", "critical"),
    ("approval", "sometimes"),
    ("scope", "session"),
])
def test_invalid_enum_fails(tmp_path: Path, field: str, value: str) -> None:
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(**{field: value})))
    assert exc.value.code == E_REGISTRY_ENUM


def test_high_risk_with_never_approval_fails(tmp_path: Path) -> None:
    # P-100 D-1 closure evidence: the combination must be rejected at load time.
    tool = _valid_tool(risk="high", approval="never")
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(tools=[tool])))
    assert exc.value.code == E_REGISTRY_APPROVAL


def test_high_risk_with_always_approval_passes(tmp_path: Path) -> None:
    tool = _valid_tool(risk="high", approval="always")
    registry = load_registry(_write_registry(tmp_path, _payload(tools=[tool])))
    assert registry.tools[0].risk == "high"


# ── T-7/T-8: name + version rules ────────────────────────────────


def test_duplicate_names_fail(tmp_path: Path) -> None:
    payload = _payload()
    payload["tools"] = [_valid_tool(), _valid_tool()]
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, payload))
    assert exc.value.code == E_REGISTRY_NAME


def test_bad_name_pattern_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(name="Run-Pipeline")))
    assert exc.value.code == E_REGISTRY_NAME


def test_string_top_level_version_fails(tmp_path: Path) -> None:
    payload = _payload()
    payload["version"] = "1"
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, payload))
    assert exc.value.code == E_REGISTRY_VERSION


# ── T-9/T-10/T-11: handler + profile rules ───────────────────────


def test_bad_handler_format_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(handler="researchclaw.mcp.server")))
    assert exc.value.code == E_REGISTRY_HANDLER


def test_undefined_sandbox_profile_fails(tmp_path: Path) -> None:
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, _payload(sandbox_profile="gpu")))
    assert exc.value.code == E_REGISTRY_PROFILE


def test_profile_missing_pids_fails(tmp_path: Path) -> None:
    payload = _payload()
    del payload["sandbox_profiles"]["default"]["pids"]
    with pytest.raises(RegistryError) as exc:
        load_registry(_write_registry(tmp_path, payload))
    assert exc.value.code == E_REGISTRY_PROFILE_INVALID


# ── T-12: deferred handler resolution ────────────────────────────


def test_strict_resolution(tmp_path: Path) -> None:
    ok = _write_registry(tmp_path / "ok", _payload(
        handler="researchclaw.tools.registry:load_registry"))
    registry = load_registry(ok, strict_handlers=True)
    registry.resolve_handlers(strict=True)

    bad = _write_registry(tmp_path / "bad", _payload(
        handler="researchclaw.tools.registry:no_such_symbol"))
    registry_bad = load_registry(bad)            # format-level: loads fine
    with pytest.raises(RegistryError) as exc:
        registry_bad.resolve_handlers(strict=True)
    assert exc.value.code == E_REGISTRY_HANDLER_UNRESOLVED


# ── T-13: reload semantics ───────────────────────────────────────


def test_reload_failure_keeps_old_instance(tmp_path: Path) -> None:
    path = _write_registry(tmp_path, _payload())
    registry = load_registry(path)
    assert len(registry.tools) == 1

    path.write_text("version: 9\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        registry.reload()
    assert len(registry.tools) == 1              # old instance intact

    good = json.dumps({
        "version": 1,
        "tools": [_valid_tool(name="second_tool")],
        "sandbox_profiles": _payload()["sandbox_profiles"],
    })
    path.write_text(textwrap.dedent(good), encoding="utf-8")
    reloaded = registry.reload()
    assert {t.name for t in reloaded.tools} == {"second_tool"}
    assert len(registry.tools) == 1              # original untouched


# ── T-14: V-8 self-consistency of the shipped registry ───────────


def test_shipped_registry_is_v8_self_consistent() -> None:
    registry = load_registry()
    for spec in registry.tools:
        if spec.risk == "high":
            assert spec.approval in {"always", "high_only"}


# ── P-103: P-102 D-1/D-2/D-3 fixes ───────────────────────────────


def test_package_resource_matches_repo_root() -> None:
    # T-R1 (P-102 D-1): package copy must not drift from the repo-root source.
    import importlib.resources

    import yaml

    res = importlib.resources.files("researchclaw.tools").joinpath("registry.yaml")
    packaged = yaml.safe_load(res.read_text(encoding="utf-8"))
    repo = Path(__file__).resolve().parents[1] / "tools" / "registry.yaml"
    source = yaml.safe_load(repo.read_text(encoding="utf-8"))
    assert packaged == source


def test_frozen_nested_containers() -> None:
    # T-R3 (P-102 D-2): nested containers must be read-only.
    registry = load_registry()
    with pytest.raises(TypeError):
        registry.sandbox_profiles["default"]["cpu"] = 99  # type: ignore[index]
    spec = registry.tools[0]
    with pytest.raises(TypeError):
        spec.input_schema["type"] = "array"  # type: ignore[index]


def test_missing_file_has_dedicated_code(tmp_path: Path) -> None:
    from researchclaw.tools.registry import E_REGISTRY_UNREADABLE

    with pytest.raises(RegistryError) as exc:
        load_registry(tmp_path / "nope.yaml")
    assert exc.value.code == E_REGISTRY_UNREADABLE


def test_bad_yaml_has_dedicated_code(tmp_path: Path) -> None:
    from researchclaw.tools.registry import E_REGISTRY_PARSE

    path = tmp_path / "broken.yaml"
    path.write_text("version: 1\n  bad indent: [", encoding="utf-8")
    with pytest.raises(RegistryError) as exc:
        load_registry(path)
    assert exc.value.code == E_REGISTRY_PARSE


def test_non_mapping_payload_has_dedicated_code(tmp_path: Path) -> None:
    from researchclaw.tools.registry import E_REGISTRY_PARSE

    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RegistryError) as exc:
        load_registry(path)
    assert exc.value.code == E_REGISTRY_PARSE
