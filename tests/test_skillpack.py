"""P-155 T16-T19: SkillPack manifest, digest and HMAC verification."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from researchclaw.knowledge.skillpack import (
    KNOWN_PACK_IDS,
    SkillPackError,
    load_skillpacks,
)

KEY = "test-skillpack-key"


def _pack_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(file.relative_to(path).as_posix().encode("utf-8"))
        digest.update(file.read_bytes())
    return "sha256:" + digest.hexdigest()


def _sign(pack_id: str, version: str, digest: str) -> str:
    message = f"{pack_id}{version}{digest}".encode("utf-8")
    return "hmac-sha256:" + hmac.new(KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _make_manifest(tmp_path: Path, count: int = 5) -> Path:
    packs = []
    for index in range(count):
        pack_id = KNOWN_PACK_IDS[index]
        path = tmp_path / pack_id
        path.mkdir()
        (path / "SKILL.md").write_text(f"# {pack_id}\n", encoding="utf-8")
        version = "1.0.0"
        digest = _pack_digest(path)
        packs.append({
            "id": pack_id,
            "path": str(path),
            "version": version,
            "digest": digest,
            "signature": _sign(pack_id, version, digest),
        })
    manifest = tmp_path / "skillpacks.json"
    manifest.write_text(json.dumps({"packs": packs}), encoding="utf-8")
    return manifest


class TestSkillPack:
    def test_load_five_packs(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RC_SKILLPACK_KEY", KEY)
        manifest = _make_manifest(tmp_path)
        packs = load_skillpacks(manifest)
        assert len(packs) == 5
        assert {pack.id for pack in packs} == set(KNOWN_PACK_IDS)

        shipped = (
            Path(__file__).resolve().parents[1]
            / "researchclaw"
            / "knowledge"
            / "skillpacks.json"
        )
        real = load_skillpacks(shipped, require_signature=False)
        assert len(real) == 5
        assert {pack.id for pack in real} == set(KNOWN_PACK_IDS)

    def test_tampered_pack_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RC_SKILLPACK_KEY", KEY)
        manifest = _make_manifest(tmp_path)
        target = tmp_path / KNOWN_PACK_IDS[0] / "SKILL.md"
        target.write_text("# tampered\n", encoding="utf-8")
        with pytest.raises(SkillPackError):
            load_skillpacks(manifest)

    def test_bad_signature_rejected(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("RC_SKILLPACK_KEY", KEY)
        manifest = _make_manifest(tmp_path)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["packs"][0]["signature"] = "hmac-sha256:" + "0" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(SkillPackError):
            load_skillpacks(manifest)

    def test_missing_key_fails_closed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("RC_SKILLPACK_KEY", raising=False)
        manifest = _make_manifest(tmp_path)
        with pytest.raises(SkillPackError):
            load_skillpacks(manifest)
