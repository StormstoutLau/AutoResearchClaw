"""G7 A7-2/A7-3: concurrent runs stay isolated; both claim planes agree."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from researchclaw.evidence.offline_audit import run_offline_audit
from researchclaw.evidence.stage_hooks import (
    run_stage20_gate,
    run_stage23_consistency,
)
from researchclaw.runtime.event_log import EventLog
from researchclaw.runtime.lease import LeaseBusy, acquire, read_lease


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _claim(**overrides) -> dict:
    claim = {
        "claim_id": "c-11111111",
        "claim_class": "C",
        "claim_type": "exploratory",
        "statement": "The ablation lowers error by 1.3 points on the held-out set.",
        "formal_statement": None,
        "formality": {"status": "formal", "reason": None},
        "assumptions": [],
        "evidence": [],
        "reasoning_chain": [],
        "stats_protocol": None,
        "falsifier": {"condition": "error delta <= 0", "test_ref": ""},
        "verification_depth": "stage1",
        "status": "speculation",
        "policy_version": 2,
    }
    claim.update(overrides)
    return claim


def _write_claim(run_dir: Path, claim: dict) -> None:
    _write_jsonl(run_dir / "stage-09" / "claims.jsonl", [claim])


def _run_worker(run_dir: Path, errors: list[BaseException]) -> None:
    try:
        lease = acquire(run_dir, owner=f"worker:{run_dir.name}")
        log = EventLog(run_dir, run_dir.name, fsync=False, fencing=lease.fencing)
        log.append("run.started", {"worker": run_dir.name})
        log.append("stage.started", {}, stage=1)
        sandbox = run_dir / "stage-12" / "runs" / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "marker.txt").write_text(run_dir.name, encoding="utf-8")
        log.write_summary()
    except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
        errors.append(exc)


def test_two_runs_have_independent_leases_events_and_sandboxes(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_a.mkdir()
    run_b.mkdir()
    errors: list[BaseException] = []

    threads = [
        threading.Thread(target=_run_worker, args=(run_a, errors)),
        threading.Thread(target=_run_worker, args=(run_b, errors)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert read_lease(run_a).fencing == read_lease(run_b).fencing == 1
    assert (run_a / "stage-12" / "runs" / "sandbox" / "marker.txt").read_text() == "run-a"
    assert (run_b / "stage-12" / "runs" / "sandbox" / "marker.txt").read_text() == "run-b"
    for run_dir in (run_a, run_b):
        events = EventLog(run_dir, run_dir.name, fsync=False).read_all()
        assert [row["run_id"] for row in events] == [run_dir.name, run_dir.name]
        assert all(row["run_id"] == run_dir.name for row in events)


def test_same_run_directory_rejects_a_second_writer(tmp_path: Path) -> None:
    acquire(tmp_path, owner="worker:1")

    try:
        acquire(tmp_path, owner="worker:2")
    except LeaseBusy:
        pass
    else:  # pragma: no cover - a broken lease must not silently pass
        raise AssertionError("a second writer must not acquire the same run lease")


def test_both_claim_planes_agree_under_concurrent_runs(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    for run_dir in (run_a, run_b):
        run_dir.mkdir()
        _write_claim(run_dir, _claim())
        gate_dir = run_dir / "stage-20"
        gate_dir.mkdir()
        run_stage20_gate(gate_dir, run_dir)

    results: dict[str, dict] = {}
    errors: list[BaseException] = []

    def verify(name: str, run_dir: Path) -> None:
        try:
            stage23 = run_stage23_consistency(run_dir / "stage-23", run_dir)
            audit = run_offline_audit(run_dir)
            results[name] = {"stage23": stage23, "audit": audit}
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=verify, args=("a", run_a)),
        threading.Thread(target=verify, args=("b", run_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results["a"]["stage23"]["consistent"] is True
    assert results["b"]["stage23"]["consistent"] is True
    assert results["a"]["audit"]["consistent"] is True
    assert results["b"]["audit"]["consistent"] is True
    statuses_a = {row["status"] for row in results["a"]["audit"]["audit"].values()}
    statuses_b = {row["status"] for row in results["b"]["audit"]["audit"].values()}
    assert statuses_a == statuses_b == {"speculation"}


def test_tampered_claim_is_detected_without_touching_the_other_run(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    for run_dir in (run_a, run_b):
        run_dir.mkdir()
        _write_claim(run_dir, _claim())
        gate_dir = run_dir / "stage-20"
        gate_dir.mkdir()
        run_stage20_gate(gate_dir, run_dir)
    before_b = _tree_digest(run_b)

    _write_jsonl(run_a / "stage-20" / "claims.jsonl", [_claim(status="failed")])
    audit_a = run_offline_audit(run_a)
    audit_b = run_offline_audit(run_b)

    assert audit_a["consistent"] is False
    assert any(diff["reason"] == "status_mismatch" for diff in audit_a["diffs"])
    assert audit_b["consistent"] is True
    assert _tree_digest(run_b) == before_b
