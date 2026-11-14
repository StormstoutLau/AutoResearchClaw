"""Vendor provenance and license-boundary checks for the Auto_Prover kernel (G2 M2)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "researchclaw" / "vendor" / "auto_prover"
SOURCE = json.loads((VENDOR / "SOURCE.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location(
    "vendor_source_sync_under_test", ROOT / "scripts" / "spec" / "vendor_source_sync.py")
SYNC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SYNC)

_BLOBS: dict[str, bytes] | None = None


def _blob_bytes(rel: str) -> bytes:
    """返回 `researchclaw/vendor/auto_prover/<rel>` 在 git index 中的原始字节。

    无 .git / 未入库 ⇒ pytest.skip（sdist 场景优雅降级，DESIGN §4.1 O-3）。
    一次 `git cat-file --batch` 载入全部条目，测试只查内存表（单一实现 = vendor_source_sync）。
    """
    global _BLOBS
    if _BLOBS is None:
        if not (ROOT / ".git").exists():
            pytest.skip("无 .git：非 git 工作树，跳过 blob 溯源校验（CI 不受影响）")
        _BLOBS = SYNC.blob_bytes(SYNC.all_paths(SOURCE), ROOT)
    rel = f"{SYNC.VENDOR_DIR}/{rel}"
    if rel not in _BLOBS:
        pytest.skip(f"未入库：{rel} 不在 git index 内")
    return _BLOBS[rel]


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
    raw = _blob_bytes(entry["path"])
    assert len(raw) == entry["bytes"]
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("entry", SOURCE["license_files"], ids=lambda item: item["path"])
def test_license_files_are_intact(entry):
    path = VENDOR / entry["path"]
    assert path.is_file()
    assert hashlib.sha256(_blob_bytes(entry["path"])).hexdigest() == entry["sha256"]


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
