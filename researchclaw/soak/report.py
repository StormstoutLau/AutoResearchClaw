"""Soak report rendering (P-160).

JSON is the machine-readable source; Markdown is a derived view.
"""
from __future__ import annotations

import json
import os
import statistics
from dataclasses import asdict
from pathlib import Path

from researchclaw.soak.driver import (
    FIELD_WALL_SECONDS,
    MIN_FIELD_RESTARTS,
    SoakConfig,
    SoakResult,
)

SCHEMA = "arc-soak-report/1"


def _recovery_stats(restarts: list[dict]) -> dict:
    values = [float(r["recovery_seconds"]) for r in restarts
              if r.get("recovery_seconds") is not None]
    return {
        "count": len(values),
        "missing": len(restarts) - len(values),
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
        "values": values,
    }


def build_report(result: SoakResult, session: list[dict],
                 config: SoakConfig) -> dict:
    restarts = [asdict(record) for record in result.restarts]
    injected = sum(1 for row in restarts if row["reason"] == "injected")
    unexpected = len(restarts) - injected
    verification = asdict(result.verification)
    failure_stages = {
        str(stage): count for stage, count in result.verification.failure_stages
    }
    timestamps = [str(row.get("ts")) for row in session if row.get("ts")]
    reference = {
        "run_dir": str(config.reference_run_dir) if config.reference_run_dir else None,
        "signature": result.verification.reference_signature,
        "match": (result.verification.converged
                  if config.reference_run_dir is not None else None),
    }
    return {
        "schema": SCHEMA,
        "run_id": result.verification.run_id,
        "started_at": timestamps[0] if timestamps else None,
        "ended_at": timestamps[-1] if timestamps else None,
        "wall_seconds": round(result.wall_seconds, 3),
        "status": result.status,
        "config": {
            "duration_seconds": config.duration_seconds,
            "max_restarts": config.max_restarts,
            "inject_at_stages": list(config.inject_at_stages),
            "poll_seconds": config.poll_seconds,
            "min_restart_interval_seconds": config.min_restart_interval_seconds,
            "reference_run_dir": str(config.reference_run_dir)
            if config.reference_run_dir else None,
        },
        "restart_count": len(restarts),
        "injected_restarts": injected,
        "unexpected_restarts": unexpected,
        "restarts": restarts,
        "recovery_seconds": _recovery_stats(restarts),
        "failure_stages": failure_stages,
        "verification": verification,
        "reference": reference,
        "converged": result.verification.converged,
        "requirements": {
            "min_restarts": MIN_FIELD_RESTARTS,
            "observed_restarts": len(restarts),
            "restarts_satisfied": len(restarts) >= MIN_FIELD_RESTARTS,
            "field_duration_satisfied": result.wall_seconds >= FIELD_WALL_SECONDS,
            "field_run_satisfied": result.field_run_satisfied,
        },
        "field_run": {
            "required_wall_seconds": FIELD_WALL_SECONDS,
            "required_restarts": MIN_FIELD_RESTARTS,
            "satisfied": result.field_run_satisfied,
        },
    }


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "%.2f" % value
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else "-"
    return str(value)


def render_markdown(report: dict) -> str:
    verification = report.get("verification") or {}
    lines = [
        "# ARC soak report: %s" % _fmt(report.get("run_id")),
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Status | %s |" % _fmt(report.get("status")),
        "| Converged | %s |" % _fmt(report.get("converged")),
        "| Wall seconds | %s |" % _fmt(report.get("wall_seconds")),
        "| Restarts | %s |" % _fmt(report.get("restart_count")),
        "| Injected / unexpected | %s / %s |" % (
            _fmt(report.get("injected_restarts")),
            _fmt(report.get("unexpected_restarts"))),
        "",
        "## Run",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Started | %s |" % _fmt(report.get("started_at")),
        "| Ended | %s |" % _fmt(report.get("ended_at")),
        "| Duration limit (s) | %s |" % _fmt(
            (report.get("config") or {}).get("duration_seconds")),
        "| Inject at stages | %s |" % _fmt(
            (report.get("config") or {}).get("inject_at_stages")),
        "",
        "## Restarts",
        "",
        "| # | Reason | At | Exit | Stage before | Stage after | Recovery (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(report.get("restarts") or [], 1):
        lines.append("| %d | %s | %s | %s | %s | %s | %s |" % (
            index, _fmt(row.get("reason")), _fmt(row.get("at")),
            _fmt(row.get("exit_code")), _fmt(row.get("stage_before")),
            _fmt(row.get("stage_after")), _fmt(row.get("recovery_seconds")),
        ))
    recovery = report.get("recovery_seconds") or {}
    lines += [
        "",
        "## Recovery",
        "",
        "| Count | Missing | Min | Median | Max |",
        "|---|---|---|---|---|",
        "| %s | %s | %s | %s | %s |" % (
            _fmt(recovery.get("count")), _fmt(recovery.get("missing")),
            _fmt(recovery.get("min")), _fmt(recovery.get("median")),
            _fmt(recovery.get("max")),
        ),
        "",
        "## Failure stages",
        "",
        "| Stage | Failures |",
        "|---|---|",
    ]
    failures = report.get("failure_stages") or {}
    if failures:
        for stage in sorted(failures, key=lambda value: int(value)):
            lines.append("| %s | %s |" % (stage, failures[stage]))
    else:
        lines.append("| n/a | 0 |")
    lines += [
        "",
        "## Event replay",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Chain ok | %s |" % _fmt(verification.get("chain_ok")),
        "| Chain message | %s |" % _fmt(verification.get("chain_message")),
        "| First / last seq | %s / %s |" % (
            _fmt(verification.get("first_seq")),
            _fmt(verification.get("last_seq"))),
        "| Events | %s |" % _fmt(verification.get("event_count")),
        "| Seq gaps | %s |" % _fmt(verification.get("seq_gaps")),
        "| Duplicate seqs | %s |" % _fmt(verification.get("duplicate_seqs")),
        "| Checkpoint / event skew | %s |" % _fmt(
            verification.get("event_checkpoint_skew")),
        "| Segments | %s |" % _fmt([
            segment.get("file") for segment in verification.get("segments") or []
        ]),
        "",
        "## Convergence",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Final status | %s |" % _fmt(
            (verification.get("convergence_signature") or {}).get("final_status")),
        "| Final stage | %s |" % _fmt(
            (verification.get("convergence_signature") or {}).get(
                "last_completed_stage")),
        "| Final name | %s |" % _fmt(
            (verification.get("convergence_signature") or {}).get(
                "last_completed_name")),
        "| Reference match | %s |" % _fmt(
            (report.get("reference") or {}).get("match")),
        "| Problems | %s |" % _fmt(verification.get("problems")),
        "",
        "**Verdict: %s**" % (
            "PASSED" if report.get("status") == "passed" else "FAILED"),
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_report(run_dir: str | Path, report: dict) -> tuple[Path, Path]:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "soak_report.json"
    md_path = run_dir / "soak_report.md"
    _atomic_write(json_path, json.dumps(report, indent=2, ensure_ascii=False))
    _atomic_write(md_path, render_markdown(report))
    return json_path, md_path
