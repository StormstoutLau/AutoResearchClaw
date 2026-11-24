"""Run equivalence comparison (P-149, extended in P-150).

Compares two run directories on deterministic, recorded projections instead of
raw logs: completed/failed stage sequences, tool and parameter sequences, action
statuses, artifact content hashes, the pipeline summary digest, and both hash
chains. Volatile fields (``run_id``, timestamps, durations, action UUIDs,
absolute path prefixes) are excluded by construction, so two reruns of the same
deterministic pipeline are expected to compare equal.

Artifact hashes come from the action ledger when it records output artifacts.
Stages that record no outputs (for example the first three LLM-only stages,
whose actions are empty or absent) fall back to the content-addressed node index
at ``artifacts/nodes.jsonl`` (P-150, widened in P-151), which is the only
recorded artifact evidence for such runs.

This is a *comparator*, not a re-executor: it makes no claim that a concrete
rerun will be equivalent, only that two recorded runs can be mechanically
checked for it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from researchclaw.evidence.artifact_node import NODES_FILE, load_nodes
from researchclaw.evidence.summary_check import summary_digest
from researchclaw.runtime.action_ledger import ActionLedger
from researchclaw.runtime.event_log import EventLog

#: Categories evaluated on every comparison (``checks`` is always this length).
CHECKS = 9

DIFFERENCE_KINDS = (
    "activity",
    "stage_sequence",
    "stage_failures",
    "tool_sequence",
    "params_sequence",
    "status_sequence",
    "artifacts",
    "run_summary",
    "event_chain",
    "action_chain",
)


def _stage_numbers(events: list[dict], event_type: str) -> list[int]:
    out: list[int] = []
    for event in events:
        if event.get("type") != event_type:
            continue
        payload = event.get("payload") or {}
        value = payload.get("stage", event.get("stage"))
        try:
            out.append(int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return out


def _output_key(raw: str, run_dir: Path) -> str:
    """Run-relative POSIX path when inside the run, else the basename.

    Ledger output keys are raw strings and may be absolute; the absolute prefix
    differs between runs and is not part of behaviour.
    """
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = run_dir / candidate
        return candidate.resolve().relative_to(run_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return Path(raw).name


def _node_artifacts(run_dir: Path) -> dict[str, str]:
    """Project ``artifacts/nodes.jsonl`` to ``locator -> content_hash``.

    A malformed index is unverifiable evidence, so it fails closed instead of
    being treated as an empty artifact set.
    """
    try:
        nodes = load_nodes(run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"artifact node index unreadable: {run_dir}: {exc}") from exc
    artifacts: dict[str, str] = {}
    for node in nodes:
        artifacts[str(node.locator)] = str(node.content_hash)
    return dict(sorted(artifacts.items()))


def _summary_digest(run_dir: Path) -> str | None:
    """Canonical digest of ``pipeline_summary.json``; ``None`` when absent."""
    path = run_dir / "pipeline_summary.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"pipeline summary unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"pipeline summary is not an object: {path}")
    return summary_digest(data)


def _facts(run_dir: Path) -> dict:
    log = EventLog(run_dir, run_dir.name)
    events = log.read_all()
    chain_ok, chain_message = log.verify_chain()

    ledger = ActionLedger(run_dir, run_dir.name, fsync=False)
    actions = ledger.read_all()
    ledger_ok, ledger_message = ledger.verify_chain()

    ledger_artifacts: dict[str, str] = {}
    for action in actions:
        for raw, digest in (action.get("outputs") or {}).items():
            ledger_artifacts[_output_key(str(raw), run_dir)] = str(digest)

    if ledger_artifacts:
        artifacts = ledger_artifacts
        artifacts_source = "ledger"
    elif (run_dir / NODES_FILE).is_file():
        artifacts = _node_artifacts(run_dir)
        artifacts_source = "node_index"
    else:
        artifacts = {}
        artifacts_source = "none"

    return {
        "run_id": run_dir.name,
        "stages": _stage_numbers(events, "stage.completed"),
        "stage_failures": _stage_numbers(events, "stage.failed"),
        "tools": [str(action.get("tool", "")) for action in actions],
        "params": [str(action.get("params_sha256", "")) for action in actions],
        "statuses": [str(action.get("status", "")) for action in actions],
        "artifacts": dict(sorted(artifacts.items())),
        "artifacts_source": artifacts_source,
        "summary_digest": _summary_digest(run_dir),
        "event_chain_ok": bool(chain_ok),
        "event_chain_message": chain_message,
        "action_chain_ok": bool(ledger_ok),
        "action_chain_message": ledger_message,
        "action_count": len(actions),
    }


def _sequence_difference(kind: str, left: list[Any], right: list[Any]) -> dict | None:
    if left == right:
        return None
    return {"kind": kind, "left": left, "right": right}


def _artifact_difference(left: Mapping[str, str], right: Mapping[str, str]) -> dict | None:
    missing_in_left = sorted(set(right) - set(left))
    missing_in_right = sorted(set(left) - set(right))
    changed = sorted(path for path in set(left) & set(right) if left[path] != right[path])
    if not (missing_in_left or missing_in_right or changed):
        return None
    return {
        "kind": "artifacts",
        "missing_in_left": missing_in_left,
        "missing_in_right": missing_in_right,
        "changed": changed,
    }


def _summary(facts: Mapping[str, Any]) -> dict:
    return {
        "run_id": facts["run_id"],
        "stages": facts["stages"],
        "actions": facts["action_count"],
        "artifacts": len(facts["artifacts"]),
        "artifacts_source": facts["artifacts_source"],
        "summary_digest": facts["summary_digest"],
        "event_chain_ok": facts["event_chain_ok"],
        "action_chain_ok": facts["action_chain_ok"],
    }


def compare_runs(left_dir: str | Path, right_dir: str | Path) -> dict:
    """Compare two runs. Read-only; differences are reported, not raised.

    Missing run directories raise ``FileNotFoundError``: nothing was recorded,
    nothing can be compared. An empty run on either side fails closed with an
    ``activity`` difference instead of comparing two empty sequences as equal.
    """
    left_path = Path(left_dir)
    right_path = Path(right_dir)
    for path in (left_path, right_path):
        if not path.is_dir():
            raise FileNotFoundError(f"run directory does not exist: {path}")

    left = _facts(left_path)
    right = _facts(right_path)
    differences: list[dict] = []

    if not (left["stages"] or left["action_count"]) or not (
        right["stages"] or right["action_count"]
    ):
        differences.append({
            "kind": "activity",
            "detail": "no recorded activity on one or both sides",
            "left": left["action_count"],
            "right": right["action_count"],
        })

    for kind in ("stage_sequence", "stage_failures", "tool_sequence",
                 "params_sequence", "status_sequence"):
        key = {
            "stage_sequence": "stages",
            "stage_failures": "stage_failures",
            "tool_sequence": "tools",
            "params_sequence": "params",
            "status_sequence": "statuses",
        }[kind]
        difference = _sequence_difference(kind, left[key], right[key])
        if difference is not None:
            differences.append(difference)

    artifact_difference = _artifact_difference(left["artifacts"], right["artifacts"])
    if artifact_difference is not None:
        differences.append(artifact_difference)

    if left["summary_digest"] != right["summary_digest"]:
        differences.append({
            "kind": "run_summary",
            "left": left["summary_digest"],
            "right": right["summary_digest"],
        })

    if not (left["event_chain_ok"] and right["event_chain_ok"]):
        differences.append({
            "kind": "event_chain",
            "left": left["event_chain_ok"],
            "right": right["event_chain_ok"],
            "left_message": left["event_chain_message"],
            "right_message": right["event_chain_message"],
        })

    if not (left["action_chain_ok"] and right["action_chain_ok"]):
        differences.append({
            "kind": "action_chain",
            "left": left["action_chain_ok"],
            "right": right["action_chain_ok"],
            "left_message": left["action_chain_message"],
            "right_message": right["action_chain_message"],
        })

    return {
        "equivalent": not differences,
        "checks": CHECKS,
        "differences": differences,
        "left": _summary(left),
        "right": _summary(right),
    }
