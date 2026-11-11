"""ArtifactNode v1: content-addressed artifact lineage (G3 M1, P-075).

Pure-ish helpers plus a small append-only store under ``run_dir/artifacts``.
No network, no pipeline imports. Failures are reported as error dicts so the
caller (runner or a check command) can decide whether to block.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

NODES_FILE = "artifacts/nodes.jsonl"
BLOBS_DIR = "artifacts/blobs"
DEFAULT_MATERIALIZE_LIMIT = 1024 * 1024  # 1 MiB

E_ARTIFACT_HASH = "E_ARTIFACT_HASH"
E_ARTIFACT_PARENT = "E_ARTIFACT_PARENT"
E_ARTIFACT_CYCLE = "E_ARTIFACT_CYCLE"
E_ARTIFACT_INPUTS = "E_ARTIFACT_INPUTS"
E_ARTIFACT_ID = "E_ARTIFACT_ID"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


@dataclass(frozen=True)
class ArtifactNode:
    node_id: str
    type: str
    locator: str
    content_hash: str
    parent_ids: tuple[str, ...]
    inputs_digest: str
    producer: dict
    materialized: bool
    sensitive: bool
    size_bytes: int
    created_at: str
    evidence: dict | None = None

    def as_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "type": self.type,
            "locator": self.locator,
            "content_hash": self.content_hash,
            "parent_ids": list(self.parent_ids),
            "inputs_digest": self.inputs_digest,
            "producer": dict(self.producer),
            "materialized": self.materialized,
            "sensitive": self.sensitive,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "evidence": self.evidence,
        }


def _inputs_digest(parent_hashes: Iterable[str], producer: Mapping[str, Any]) -> str:
    payload = {"parents": sorted(parent_hashes), "params": dict(producer)}
    return _sha256_text(_canonical_json(payload))


def build_node(
    run_dir: Path,
    locator: str,
    *,
    node_type: str = "stage_artifact",
    parent_nodes: Iterable[ArtifactNode] = (),
    producer: Mapping[str, Any] | None = None,
    sensitive: bool = False,
    evidence: Mapping[str, Any] | None = None,
    materialize_limit: int = DEFAULT_MATERIALIZE_LIMIT,
    created_at: str | None = None,
) -> ArtifactNode:
    run_dir = Path(run_dir)
    path = run_dir / locator
    if not path.is_file():
        raise FileNotFoundError(f"artifact not found: {locator}")
    data = path.read_bytes()
    content_hash = _sha256_bytes(data)
    parents = tuple(sorted({node.node_id for node in parent_nodes}))
    parent_hashes = [node.content_hash for node in parent_nodes]
    producer_dict = dict(producer or {})
    materialized = (
        not sensitive
        and len(data) <= materialize_limit
        and _is_text(data)
    )
    if materialized:
        blob = run_dir / BLOBS_DIR / content_hash.split(":", 1)[1]
        if not blob.exists() or blob.read_bytes() != data:
            _atomic_write(blob, data)
    node_id = "an-" + _sha256_text(
        _canonical_json({"type": node_type, "locator": locator, "hash": content_hash})
    )[7:23]
    return ArtifactNode(
        node_id=node_id,
        type=node_type,
        locator=locator,
        content_hash=content_hash,
        parent_ids=parents,
        inputs_digest=_inputs_digest(parent_hashes, producer_dict),
        producer=producer_dict,
        materialized=materialized,
        sensitive=sensitive,
        size_bytes=len(data),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        evidence=dict(evidence) if evidence is not None else None,
    )


def project_to_evidence(node: ArtifactNode | Mapping[str, Any]) -> dict | None:
    """AN-4: project a node to the legacy EvidenceRef shape (or None)."""
    raw = node.as_dict() if isinstance(node, ArtifactNode) else dict(node)
    evidence = raw.get("evidence")
    if not isinstance(evidence, dict):
        return None
    projected = dict(evidence)
    projected["digest"] = raw.get("content_hash")
    return projected


def load_nodes(run_dir: Path) -> list[ArtifactNode]:
    path = Path(run_dir) / NODES_FILE
    if not path.is_file():
        return []
    nodes: list[ArtifactNode] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        nodes.append(
            ArtifactNode(
                node_id=raw["node_id"],
                type=raw["type"],
                locator=raw["locator"],
                content_hash=raw["content_hash"],
                parent_ids=tuple(raw.get("parent_ids") or ()),
                inputs_digest=raw["inputs_digest"],
                producer=dict(raw.get("producer") or {}),
                materialized=bool(raw.get("materialized")),
                sensitive=bool(raw.get("sensitive")),
                size_bytes=int(raw.get("size_bytes") or 0),
                created_at=raw.get("created_at", ""),
                evidence=raw.get("evidence"),
            )
        )
    return nodes


def register_stage_artifacts(
    run_dir: Path,
    stage: int,
    stage_name: str,
    artifacts: Iterable[str],
    *,
    attempt: int = 1,
) -> list[ArtifactNode]:
    """Register a DONE stage's artifacts; linear parent = latest earlier stage."""
    run_dir = Path(run_dir)
    existing = load_nodes(run_dir)
    by_id = {node.node_id: node for node in existing}
    earlier = [n for n in existing if int(n.producer.get("stage", -1)) < int(stage)]
    if earlier:
        latest_stage = max(int(n.producer.get("stage", -1)) for n in earlier)
        parents = [n for n in earlier if int(n.producer.get("stage", -1)) == latest_stage]
    else:
        parents = []
    producer = {"stage": int(stage), "stage_name": stage_name, "attempt": int(attempt)}
    added: list[ArtifactNode] = []
    for name in artifacts:
        locator = f"stage-{int(stage):02d}/{name}"
        if (run_dir / locator).is_file() is False:
            continue
        node = build_node(
            run_dir,
            locator,
            parent_nodes=parents,
            producer=producer,
        )
        if node.node_id in by_id:
            continue
        by_id[node.node_id] = node
        added.append(node)
    if added:
        path = run_dir / NODES_FILE
        lines = "".join(
            _canonical_json(node.as_dict()) + "\n" for node in by_id.values()
        )
        _atomic_write(path, lines.encode("utf-8"))
    return added


def _cycle_detected(
    node_id: str, parents: Mapping[str, tuple[str, ...]], visiting: set[str], done: set[str]
) -> bool:
    if node_id in visiting:
        return True
    if node_id in done:
        return False
    visiting.add(node_id)
    for parent in parents.get(node_id, ()):
        if _cycle_detected(parent, parents, visiting, done):
            return True
    visiting.remove(node_id)
    done.add(node_id)
    return False


def verify_tree(
    run_dir: Path, nodes: Iterable[ArtifactNode] | None = None
) -> list[dict]:
    """Verify hashes, parents, cycles and inputs_digest. Returns error dicts."""
    run_dir = Path(run_dir)
    items = list(nodes) if nodes is not None else load_nodes(run_dir)
    by_id: dict[str, ArtifactNode] = {}
    errors: list[dict] = []
    for node in items:
        if node.node_id in by_id:
            errors.append({"code": E_ARTIFACT_ID, "node_id": node.node_id, "field": "node_id"})
            continue
        by_id[node.node_id] = node
    parents_map = {node.node_id: node.parent_ids for node in by_id.values()}
    done: set[str] = set()
    for node in by_id.values():
        if _cycle_detected(node.node_id, parents_map, set(), done):
            errors.append({"code": E_ARTIFACT_CYCLE, "node_id": node.node_id, "field": "parent_ids"})
    for node in by_id.values():
        for parent_id in node.parent_ids:
            if parent_id not in by_id:
                errors.append({
                    "code": E_ARTIFACT_PARENT,
                    "node_id": node.node_id,
                    "field": "parent_ids",
                })
        expected_id = "an-" + _sha256_text(
            _canonical_json({
                "type": node.type,
                "locator": node.locator,
                "hash": node.content_hash,
            })
        )[7:23]
        if expected_id != node.node_id:
            errors.append({"code": E_ARTIFACT_ID, "node_id": node.node_id, "field": "node_id"})
        if node.sensitive and node.materialized:
            errors.append({
                "code": E_ARTIFACT_HASH,
                "node_id": node.node_id,
                "field": "materialized",
            })
        if node.materialized:
            blob = run_dir / BLOBS_DIR / node.content_hash.split(":", 1)[1]
            if not blob.is_file() or _sha256_bytes(blob.read_bytes()) != node.content_hash:
                errors.append({
                    "code": E_ARTIFACT_HASH,
                    "node_id": node.node_id,
                    "field": "content_hash",
                })
        else:
            path = run_dir / node.locator
            if not path.is_file() or _sha256_bytes(path.read_bytes()) != node.content_hash:
                errors.append({
                    "code": E_ARTIFACT_HASH,
                    "node_id": node.node_id,
                    "field": "content_hash",
                })
        parent_hashes = [
            by_id[pid].content_hash for pid in node.parent_ids if pid in by_id
        ]
        if _inputs_digest(parent_hashes, node.producer) != node.inputs_digest:
            errors.append({
                "code": E_ARTIFACT_INPUTS,
                "node_id": node.node_id,
                "field": "inputs_digest",
            })
    return errors
