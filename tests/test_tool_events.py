"""G4-M3 (P-104): tool events, orphan_call and approval gate (A4-4/A4-5)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from researchclaw.mcp.server import ResearchClawMCPServer
from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.tools.approvals import grant, read_approvals
from researchclaw.tools.invoker import ToolInvoker, emit_orphan_markers
from researchclaw.tools.registry import load_registry

HANDLER = "tests.test_tool_events:noop_handler"


async def noop_handler(server, args):  # noqa: ANN001, ANN002
    return {"success": True, "keys": sorted(args)}


def _tool(name: str, *, risk: str = "low", approval: str = "never",
          required: bool = True) -> dict:
    return {
        "name": name,
        "version": "1.0",
        "description": name,
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"] if required else [],
        },
        "scope": "global",
        "risk": risk,
        "approval": approval,
        "sandbox_profile": "default",
        "handler": HANDLER,
    }


def _registry(tmp_path: Path, tools: list[dict]) -> Path:
    payload = {
        "version": 1,
        "tools": tools,
        "sandbox_profiles": {
            "default": {"network": "none", "cpu": 2, "memory": "4g",
                        "pids": 512, "disk": "10g", "ttl_sec": 1800},
        },
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def _invoker(tmp_path: Path, tools: list[dict], *, event_log=None,
             approvals_path=None, calls: list | None = None):
    registry = load_registry(_registry(tmp_path, tools), strict_handlers=True)
    calls = calls if calls is not None else []

    async def _handler(args):
        calls.append(dict(args))
        return {"success": True, "keys": sorted(args)}

    handlers = {t["name"]: _handler for t in tools}
    return ToolInvoker(registry, handlers, event_log=event_log,
                       approvals_path=approvals_path), calls


def _events(run_dir: Path) -> list[dict]:
    return EventLog(run_dir, run_dir.name).read_all()


def _by_type(events: list[dict], kind: str) -> list[dict]:
    return [e for e in events if e.get("type") == kind]


# ── T-1..T-4: pairing, fields, digests, no raw args ───────────────


def test_t1_call_and_result_pair(tmp_path: Path) -> None:
    run_dir = tmp_path / "run1"
    ev = EventLog(run_dir, "run1", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    out = asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    assert out["success"] is True
    events = _events(run_dir)
    calls = _by_type(events, "tool.call")
    results = _by_type(events, "tool.result")
    assert len(calls) == 1 and len(results) == 1
    assert calls[0]["payload"]["call_id"] == results[0]["payload"]["call_id"]


def test_t2_required_event_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "run2"
    ev = EventLog(run_dir, "run2", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    events = _events(run_dir)
    call = _by_type(events, "tool.call")[0]["payload"]
    result = _by_type(events, "tool.result")[0]["payload"]
    for key in ("tool", "call_id", "risk", "args_digest", "args_summary"):
        assert key in call
    for key in ("tool", "call_id", "risk", "exit_code", "result_digest",
                "result_summary", "duration_ms"):
        assert key in result


def test_t3_digests_recompute(tmp_path: Path) -> None:
    run_dir = tmp_path / "run3"
    ev = EventLog(run_dir, "run3", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    args = {"topic": "x"}
    asyncio.run(invoker.invoke("probe_a", args))
    events = _events(run_dir)
    call = _by_type(events, "tool.call")[0]["payload"]
    result = _by_type(events, "tool.result")[0]["payload"]
    assert call["args_digest"] == hashlib.sha256(
        canonical_json(args).encode("utf-8")).hexdigest()
    expected = hashlib.sha256(
        canonical_json({"success": True, "keys": ["topic"]}).encode("utf-8")
    ).hexdigest()
    assert result["result_digest"] == expected


def test_t4_no_raw_arguments_in_events(tmp_path: Path) -> None:
    run_dir = tmp_path / "run4"
    ev = EventLog(run_dir, "run4", fsync=False)
    sentinel = "SENTINEL-RAW-42"
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    asyncio.run(invoker.invoke("probe_a", {"topic": sentinel}))
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert sentinel not in lines


# ── T-5..T-9: approval gate ───────────────────────────────────────


def test_t5_high_risk_without_approval_is_denied(tmp_path: Path) -> None:
    run_dir = tmp_path / "run5"
    ev = EventLog(run_dir, "run5", fsync=False)
    invoker, calls = _invoker(
        tmp_path, [_tool("probe_high", risk="high", approval="high_only")],
        event_log=ev, approvals_path=run_dir / "approvals.json")
    out = asyncio.run(invoker.invoke("probe_high", {"topic": "x"}))
    assert out["error_code"] == "E_APPROVAL_REQUIRED"
    assert calls == []
    events = _events(run_dir)
    assert _by_type(events, "approval.required")
    assert not _by_type(events, "tool.call")
    assert not _by_type(events, "tool.result")


def test_t6_approved_tool_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run6"
    ev = EventLog(run_dir, "run6", fsync=False)
    grant(run_dir, "probe_high", by="tester")
    invoker, calls = _invoker(
        tmp_path, [_tool("probe_high", risk="high", approval="high_only")],
        event_log=ev, approvals_path=run_dir / "approvals.json")
    out = asyncio.run(invoker.invoke("probe_high", {"topic": "x"}))
    assert out["success"] is True
    assert len(calls) == 1


def test_t7_malformed_approvals_fail_closed(tmp_path: Path) -> None:
    run_dir = tmp_path / "run7"
    run_dir.mkdir(parents=True)
    (run_dir / "approvals.json").write_text("{not json", encoding="utf-8")
    ev = EventLog(run_dir, "run7", fsync=False)
    invoker, calls = _invoker(
        tmp_path, [_tool("probe_high", risk="high", approval="high_only")],
        event_log=ev, approvals_path=run_dir / "approvals.json")
    out = asyncio.run(invoker.invoke("probe_high", {"topic": "x"}))
    assert out["error_code"] == "E_APPROVAL_REQUIRED"
    assert calls == []
    assert read_approvals(run_dir) == {}


def test_t8_never_approval_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "run8"
    ev = EventLog(run_dir, "run8", fsync=False)
    invoker, calls = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    out = asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    assert out["success"] is True and len(calls) == 1


def test_t9_always_approval_denied_without_grant(tmp_path: Path) -> None:
    run_dir = tmp_path / "run9"
    ev = EventLog(run_dir, "run9", fsync=False)
    invoker, calls = _invoker(
        tmp_path, [_tool("probe_always", approval="always")],
        event_log=ev, approvals_path=run_dir / "approvals.json")
    out = asyncio.run(invoker.invoke("probe_always", {"topic": "x"}))
    assert out["error_code"] == "E_APPROVAL_REQUIRED"
    assert calls == []


# ── T-10..T-12: orphan detection ──────────────────────────────────


def _drop_results(run_dir: Path) -> None:
    path = run_dir / "events.jsonl"
    kept = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if '"type":"tool.result"' not in ln]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def test_t10_missing_result_emits_orphan(tmp_path: Path) -> None:
    run_dir = tmp_path / "run10"
    ev = EventLog(run_dir, "run10", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    _drop_results(run_dir)
    marked = emit_orphan_markers(EventLog(run_dir, "run10", fsync=False))
    assert len(marked) == 1
    events = _events(run_dir)
    orphan = _by_type(events, "tool.orphan_call")[0]["payload"]
    call_id = _by_type(events, "tool.call")[0]["payload"]["call_id"]
    assert orphan["call_id"] == call_id


def test_t11_complete_log_has_no_orphan(tmp_path: Path) -> None:
    run_dir = tmp_path / "run11"
    ev = EventLog(run_dir, "run11", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    assert emit_orphan_markers(EventLog(run_dir, "run11", fsync=False)) == []
    assert not _by_type(_events(run_dir), "tool.orphan_call")


def test_t12_orphan_precedes_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run12"
    ev = EventLog(run_dir, "run12", fsync=False)
    invoker, _ = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    _drop_results(run_dir)
    log = EventLog(run_dir, "run12", fsync=False)
    emit_orphan_markers(log)
    summary = log.append("pipeline.summary", {"digest": "d"})
    events = _events(run_dir)
    orphan_seq = _by_type(events, "tool.orphan_call")[0]["seq"]
    assert orphan_seq < summary.seq


# ── T-13..T-16: O-10 / O-11 / no-sink boundary ───────────────────


def test_t13_schema_validation_rejects_bad_args(tmp_path: Path) -> None:
    run_dir = tmp_path / "run13"
    ev = EventLog(run_dir, "run13", fsync=False)
    invoker, calls = _invoker(tmp_path, [_tool("probe_a")], event_log=ev)
    out = asyncio.run(invoker.invoke("probe_a", {"topic": None}))
    assert out["error_code"] == "E_INVALID_ARGUMENTS"
    assert calls == []
    assert not _by_type(_events(run_dir), "tool.call")


def test_t14_no_singleton_dispatch_left(tmp_path: Path) -> None:
    import researchclaw.mcp.server as server_module

    assert not hasattr(server_module, "dispatch_tool")
    assert not hasattr(server_module, "_default_server")
    invoker, calls = _invoker(tmp_path, [_tool("probe_a")])
    assert asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))["success"] is True
    assert len(calls) == 1


def test_t15_mcp_smoke_unchanged(tmp_path: Path) -> None:
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    out = asyncio.run(server.handle_tool_call("nonexistent", {}))
    assert out["error_code"] == "INVALID_TOOL"


def test_t16_no_event_log_means_no_run_events(tmp_path: Path) -> None:
    run_dir = tmp_path / "run16"
    invoker, calls = _invoker(tmp_path, [_tool("probe_a")])
    out = asyncio.run(invoker.invoke("probe_a", {"topic": "x"}))
    assert out["success"] is True and len(calls) == 1
    assert not (run_dir / "events.jsonl").exists()


# ── T-17..T-19: grant concurrency, CLI, lifecycle ────────────────


def test_t17_concurrent_grants_keep_file_valid(tmp_path: Path) -> None:
    run_dir = tmp_path / "run17"
    run_dir.mkdir(parents=True)
    errors: list[BaseException] = []

    def _worker(i: int) -> None:
        try:
            grant(run_dir, f"probe_{i}", by="tester")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    data = json.loads((run_dir / "approvals.json").read_text(encoding="utf-8"))
    assert len(data) == 8 and all(v["approved"] for v in data.values())


def test_t18_cli_grant_unblocks_gate(tmp_path: Path) -> None:
    from researchclaw.cli import main

    art = tmp_path / "artifacts"
    run_dir = art / "rc-20260101-000000-abcdef"
    run_dir.mkdir(parents=True)
    rc = main(["approvals", "grant", "--run-id", run_dir.name,
               "--tool", "probe_high", "--by", "tester",
               "--artifacts-dir", str(art)])
    assert rc == 0
    assert read_approvals(run_dir)["probe_high"]["approved"] is True
    invoker, calls = _invoker(
        tmp_path, [_tool("probe_high", risk="high", approval="high_only")],
        approvals_path=run_dir / "approvals.json")
    out = asyncio.run(invoker.invoke("probe_high", {"topic": "x"}))
    assert out["success"] is True and len(calls) == 1


def test_t19_stop_cancels_actual_task(tmp_path: Path) -> None:
    release = threading.Event()

    def fake_pipeline(**kwargs):  # noqa: ANN003
        release.wait(timeout=5)

    config = SimpleNamespace(knowledge_base=None)
    server = ResearchClawMCPServer(config=config, artifacts_dir=tmp_path,
                                   execute_pipeline_fn=fake_pipeline)

    async def _scenario() -> tuple[str, object]:
        out = await server.handle_tool_call("run_pipeline", {"topic": "x"})
        assert out["success"] is True
        run_id = out["run_id"]
        task = server._active_tasks[run_id]
        await server.stop()
        # to_thread keeps the OS thread alive until it returns, so the task is
        # "cancelling" rather than "done" immediately after stop().
        assert task.cancelling() >= 1
        assert run_id not in server._active_tasks
        release.set()
        await asyncio.sleep(0.1)
        assert task.done()
        return run_id, task

    run_id, task = asyncio.run(_scenario())
    assert run_id


# ── P-104 review convergence: single execution path + digest robustness ──


def test_t20_handle_tool_call_enforces_approval(tmp_path: Path) -> None:
    """Review D-1: the public API must not bypass the approval gate."""
    reg_path = _registry(tmp_path, [_tool("probe_high", risk="high",
                                          approval="high_only")])
    server = ResearchClawMCPServer(artifacts_dir=tmp_path)
    server._registry = load_registry(reg_path, strict_handlers=True)

    calls: list = []

    async def gated(args):
        calls.append(dict(args))
        return {"success": True}

    server._handlers = {"probe_high": gated}
    server._invoker = ToolInvoker(server._registry, server._handlers)
    out = asyncio.run(server.handle_tool_call("probe_high", {"topic": "x"}))
    assert out["error_code"] == "E_APPROVAL_REQUIRED"
    assert calls == []


def test_t21_non_json_result_does_not_escape(tmp_path: Path) -> None:
    """Review D-2: digest must survive non-JSON values; pairing preserved."""
    from pathlib import Path as _P

    run_dir = tmp_path / "run21"
    ev = EventLog(run_dir, "run21", fsync=False)
    reg = load_registry(_registry(tmp_path, [_tool("probe_bad")]),
                        strict_handlers=True)

    async def bad_h(args):
        return {"success": True, "path": _P("x")}

    inv = ToolInvoker(reg, {"probe_bad": bad_h}, event_log=ev)
    out = asyncio.run(inv.invoke("probe_bad", {"topic": "x"}))
    assert out["success"] is True
    events = _events(run_dir)
    assert len(_by_type(events, "tool.call")) == 1
    assert len(_by_type(events, "tool.result")) == 1
    result = _by_type(events, "tool.result")[0]["payload"]
    assert result["result_digest"] and result["result_summary"]
