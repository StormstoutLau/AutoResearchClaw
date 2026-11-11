"""Vendor provenance and license-boundary checks for the Auto_Prover kernel (G2 M2)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "researchclaw" / "vendor" / "auto_prover"
SOURCE = json.loads((VENDOR / "SOURCE.json").read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_upstream_pin_is_frozen():
    upstream = SOURCE["upstream"]
    assert upstream["name"] == "Auto_Prover"
    assert upstream["version"] == "3.7.0"
    assert upstream["commit"] == "bd95f02"
    assert upstream["license"] == "Apache-2.0"
    assert SOURCE["file_count"] == len(SOURCE["files"]) == 27


@pytest.mark.parametrize("entry", SOURCE["files"], ids=lambda item: item["path"])
def test_vendored_file_matches_sha256(entry):
    path = VENDOR / entry["path"]
    assert path.is_file(), f"missing vendored file: {entry['path']}"
    assert path.stat().st_size == entry["bytes"]
    assert _sha256(path) == entry["sha256"]


@pytest.mark.parametrize("entry", SOURCE["license_files"], ids=lambda item: item["path"])
def test_license_files_are_intact(entry):
    path = VENDOR / entry["path"]
    assert path.is_file()
    assert _sha256(path) == entry["sha256"]


def test_apache_license_and_notice_present():
    license_text = (VENDOR / "LICENSE").read_text(encoding="utf-8")
    notice_text = (VENDOR / "NOTICE").read_text(encoding="utf-8")
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text
    assert "Aiming Lab" in notice_text
    assert "Apache License, Version 2.0" in notice_text


def test_declared_additions_and_modifications_exist():
    for entry in SOURCE["added"]:
        assert (VENDOR / entry["path"]).is_file(), entry["path"]
    for entry in SOURCE["modifications"]:
        path = VENDOR / entry["path"]
        assert path.is_file(), entry["path"]
        assert "Modified by AutoResearchClaw" in path.read_text(encoding="utf-8")


def test_excluded_modules_are_not_vendored():
    for relative in (
        "kg/kg_importer.py",
        "kg/kg_writeback.py",
        "kg/verdict_store.py",
        "stages/stage3_proving.py",
        "stages/stage0_retrieval.py",
        "mcp_servers",
        "atlas_bridge",
    ):
        assert not (VENDOR / relative).exists(), relative


def test_vendored_python_files_are_covered_by_source_json():
    covered = {entry["path"] for entry in SOURCE["files"]}
    covered |= {entry["path"] for entry in SOURCE["added"]}
    actual = {
        path.relative_to(VENDOR).as_posix()
        for path in VENDOR.rglob("*.py")
    }
    assert actual == covered
