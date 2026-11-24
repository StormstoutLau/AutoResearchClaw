"""SkillPack manifest validation with digest and HMAC signature (P-155 / K3)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from researchclaw.knowledge.models import SkillPackInfo

KNOWN_PACK_IDS: tuple[str, ...] = (
    "literature-search",
    "hypothesis-formulation",
    "experimental-design",
    "statistical-reporting",
    "scientific-writing",
)
MAX_PACKS = 5


class SkillPackError(ValueError):
    """A pack is missing, tampered with or has an invalid signature."""


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_pack_path(path: str) -> Path:
    """Anchor manifest-relative pack paths to the repo root, not the CWD."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return _REPO_ROOT / candidate


def compute_pack_digest(path: str | Path) -> str:
    root = Path(path)
    if not root.is_dir():
        raise SkillPackError(f"skill pack directory does not exist: {root}")
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if not files:
        raise SkillPackError(f"skill pack is empty: {root}")
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode("utf-8"))
        digest.update(file.read_bytes())
    return "sha256:" + digest.hexdigest()


def sign_pack(pack_id: str, version: str, digest: str, key: str) -> str:
    message = f"{pack_id}{version}{digest}".encode("utf-8")
    return "hmac-sha256:" + hmac.new(
        key.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def load_skillpacks(
    manifest: str | Path | dict,
    key_env: str = "RC_SKILLPACK_KEY",
    *,
    require_signature: bool = True,
) -> list[SkillPackInfo]:
    """Load at most five known packs; any integrity failure rejects the pack."""
    if isinstance(manifest, dict):
        data = manifest
    else:
        path = Path(manifest)
        if not path.is_file():
            raise SkillPackError(f"skill pack manifest does not exist: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SkillPackError(f"invalid skill pack manifest: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("packs"), list):
        raise SkillPackError("skill pack manifest needs a packs list")

    key = os.environ.get(key_env, "")
    if require_signature and not key:
        raise SkillPackError(f"missing signature key: {key_env}")

    loaded: list[SkillPackInfo] = []
    for raw in data["packs"]:
        if not isinstance(raw, dict):
            raise SkillPackError("skill pack entry must be an object")
        pack_id = str(raw.get("id") or "")
        if pack_id not in KNOWN_PACK_IDS:
            continue
        version = str(raw.get("version") or "")
        digest = str(raw.get("digest") or "")
        signature = str(raw.get("signature") or "")
        path = str(raw.get("path") or "")
        if not pack_id or not version or not digest or not path:
            raise SkillPackError(f"skill pack {pack_id or '<unknown>'} is missing fields")
        actual = compute_pack_digest(_resolve_pack_path(path))
        if actual != digest:
            raise SkillPackError(f"skill pack digest mismatch: {pack_id}")
        if require_signature:
            expected = sign_pack(pack_id, version, digest, key)
            if not hmac.compare_digest(expected, signature):
                raise SkillPackError(f"skill pack signature mismatch: {pack_id}")
        loaded.append(SkillPackInfo(
            id=pack_id,
            path=path,
            version=version,
            digest=digest,
            signature=signature,
        ))
        if len(loaded) >= MAX_PACKS:
            break
    return loaded
