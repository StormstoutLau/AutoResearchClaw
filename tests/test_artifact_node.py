"""G3 M1 (P-075): ArtifactNode v1, lineage and projection."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from researchclaw.evidence.artifact_node import (
    ArtifactNode,
    build_node,
    load_nodes,
    project_to_evidence,
    register_stage_artifacts,
    verify_tree,
)


def _write(run_dir: Path, rel: str, data: bytes) -> Path:
    path = run_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_build_node_materializes_small_text(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"hello world\n")
    node = build_node(tmp_path, "stage-01/a.txt", producer={"stage": 1})
    assert node.node_id.startswith("an-")
    assert node.content_hash.startswith("sha256:")
    assert node.materialized is True
    assert node.sensitive is False
    assert node.size_bytes == 12
    blob = tmp_path / "artifacts" / "blobs" / node.content_hash.split(":", 1)[1]
    assert blob.read_bytes() == b"hello world\n"


def test_build_node_pointer_for_sensitive(tmp_path: Path) -> None:
    _write(tmp_path, "stage-12/sensitive.txt", b"secret\n")
    node = build_node(tmp_path, "stage-12/sensitive.txt", sensitive=True)
    assert node.materialized is False
    assert node.sensitive is True
    assert not list(tmp_path.glob("artifacts/blobs/*"))


def test_build_node_pointer_for_large_or_binary(tmp_path: Path) -> None:
    _write(tmp_path, "stage-12/large.txt", b"x" * 10)
    large = build_node(tmp_path, "stage-12/large.txt", materialize_limit=5)
    assert large.materialized is False
    _write(tmp_path, "stage-12/blob.bin", b"\x00\x01\x02")
    binary = build_node(tmp_path, "stage-12/blob.bin")
    assert binary.materialized is False


def test_project_to_evidence_uses_content_hash(tmp_path: Path) -> None:
    _write(tmp_path, "stage-04/paper.txt", b"evidence\n")
    evidence = {
        "evidence_id": "e-001",
        "source_layer": "T1",
        "tier": "E1",
        "kind": "snapshot",
        "source_id": "paper:demo",
        "locator": "§3",
        "quote": "evidence",
        "digest": "sha256:old",
        "independent": True,
        "replay_cmd": None,
    }
    node = build_node(tmp_path, "stage-04/paper.txt", evidence=evidence)
    projected = project_to_evidence(node)
    assert projected is not None
    assert projected["digest"] == node.content_hash
    assert projected["source_id"] == "paper:demo"
    assert project_to_evidence(build_node(tmp_path, "stage-04/paper.txt")) is None


def test_verify_tree_clean_chain(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    first = build_node(tmp_path, "stage-01/a.txt", producer={"stage": 1})
    _write(tmp_path, "stage-02/b.txt", b"b\n")
    second = build_node(
        tmp_path,
        "stage-02/b.txt",
        parent_nodes=[first],
        producer={"stage": 2},
    )
    assert verify_tree(tmp_path, [first, second]) == []


def test_verify_tree_detects_blob_tamper(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    node = build_node(tmp_path, "stage-01/a.txt")
    blob = tmp_path / "artifacts" / "blobs" / node.content_hash.split(":", 1)[1]
    blob.write_bytes(b"tampered\n")
    errors = verify_tree(tmp_path, [node])
    assert any(e["code"] == "E_ARTIFACT_HASH" for e in errors)


def test_verify_tree_detects_missing_parent(tmp_path: Path) -> None:
    _write(tmp_path, "stage-02/b.txt", b"b\n")
    node = build_node(tmp_path, "stage-02/b.txt")
    broken = dataclasses.replace(node, parent_ids=("an-missing",))
    errors = verify_tree(tmp_path, [broken])
    assert any(e["code"] == "E_ARTIFACT_PARENT" for e in errors)


def test_verify_tree_detects_cycle(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    _write(tmp_path, "stage-01/b.txt", b"b\n")
    a = build_node(tmp_path, "stage-01/a.txt")
    b = build_node(tmp_path, "stage-01/b.txt")
    a = dataclasses.replace(a, parent_ids=(b.node_id,))
    b = dataclasses.replace(b, parent_ids=(a.node_id,))
    errors = verify_tree(tmp_path, [a, b])
    assert any(e["code"] == "E_ARTIFACT_CYCLE" for e in errors)


def test_verify_tree_detects_inputs_digest_tamper(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    node = build_node(tmp_path, "stage-01/a.txt")
    broken = dataclasses.replace(node, inputs_digest="sha256:" + "0" * 64)
    errors = verify_tree(tmp_path, [broken])
    assert any(e["code"] == "E_ARTIFACT_INPUTS" for e in errors)


def test_register_stage_artifacts_builds_linear_chain(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    _write(tmp_path, "stage-02/b.txt", b"b\n")
    first = register_stage_artifacts(tmp_path, 1, "TOPIC_INIT", ("a.txt",))
    second = register_stage_artifacts(tmp_path, 2, "PROBLEM_DECOMPOSE", ("b.txt",))
    assert len(first) == 1 and len(second) == 1
    assert second[0].parent_ids == (first[0].node_id,)
    assert verify_tree(tmp_path) == []
    assert len(load_nodes(tmp_path)) == 2


def test_register_stage_artifacts_is_idempotent(tmp_path: Path) -> None:
    _write(tmp_path, "stage-01/a.txt", b"a\n")
    register_stage_artifacts(tmp_path, 1, "TOPIC_INIT", ("a.txt",))
    register_stage_artifacts(tmp_path, 1, "TOPIC_INIT", ("a.txt",))
    assert len(load_nodes(tmp_path)) == 1


def test_register_skips_missing_artifact(tmp_path: Path) -> None:
    assert register_stage_artifacts(tmp_path, 1, "TOPIC_INIT", ("missing.txt",)) == []
    assert load_nodes(tmp_path) == []
