"""Packaging contract tests for the PR-1 remediation.

These tests are intentionally lightweight: they validate the declared
build/packaging contract rather than building a wheel (wheel construction
is covered by CI and by the acceptance checklist).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_wheel_packages_only_existing_package() -> None:
    data = _load_pyproject()
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["researchclaw"]


def test_wheel_does_not_force_include_package_data() -> None:
    data = _load_pyproject()
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "force-include" not in wheel


def test_build_backend_pins_hatchling_range() -> None:
    data = _load_pyproject()
    requires = data["build-system"]["requires"]
    assert any(req.startswith("hatchling>=") for req in requires), requires


def test_server_mcp_voice_extras_are_declared() -> None:
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]

    assert "server" in extras
    assert any(dep.startswith("fastapi") for dep in extras["server"])
    assert any(dep.startswith("uvicorn") for dep in extras["server"])

    assert "mcp" in extras
    assert any(dep.startswith("mcp>=") for dep in extras["mcp"])

    assert "voice" in extras
    assert any(dep.startswith("httpx") for dep in extras["voice"])


def test_all_extra_includes_server_and_mcp() -> None:
    data = _load_pyproject()
    all_extra = data["project"]["optional-dependencies"]["all"]
    joined = "\n".join(all_extra)
    assert "fastapi" in joined
    assert "uvicorn" in joined
    assert "mcp>=" in joined


def test_serve_hints_use_server_extra() -> None:
    cli_source = (ROOT / "researchclaw" / "cli.py").read_text(encoding="utf-8")
    assert "researchclaw[server]" in cli_source
