"""P-143: action-level ledger and its tool-invoker producer."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from researchclaw.runtime.action_ledger import ActionLedger, hash_path
from researchclaw.runtime.event_log import EventLog
from researchclaw.tools.approvals import grant
from researchclaw.tools.invoker import ToolInvoker
from researchclaw.tools.registry import load_registry

HANDLER = "tests.test_action_ledger:noop_handler"


async def noop_handler(server, args):  # noqa: ANN001, ANN002
    return {"success": True, "keys": sorted(args)}


def _tool(name: str, *, risk: str = "low", approval: str = "never") -> dict:
    return {
        "name": name,
        "version": "1.0",
        "description": name,
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
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


def _invoker(tmp_path: Path, *, tools: list[dict], ledger=None, event_log=None,
             approvals_path=None, success: bool = True):
    registry = load_registry(_registry(tmp_path, tools), strict_handlers=True)

    async def _handler(args):
        if not success:
            return {"success": False, "error": "boom"}
        return {"success": True, "keys": sorted(args)}

    handlers = {t["name"]: _handler for t in tools}
    return ToolInvoker(registry, handlers, event_log=event_log,
                       approvals_path=approvals_path, action_ledger=ledger)


class TestActionLedger:
    def test_record_appends_and_verifies(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        first = ledger.record("search", {"q": "x"})
        second = ledger.record("search", {"q": "y"})
        assert (first.seq, second.seq) == (1, 2)
        assert ledger.count == 2
        assert second.prev_sha256 == hashlib.sha256(first.to_line().encode()).hexdigest()
        ok, msg = ledger.verify_chain()
        assert ok, msg

    def test_input_and_output_hashes(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        src = tmp_path / "in.txt"
        src.write_text("abc", encoding="utf-8")
        out = tmp_path / "out.txt"
        out.write_text("def", encoding="utf-8")
        rec = ledger.record("run", {}, inputs=[src], outputs=[out, tmp_path / "missing.txt"])
        assert rec.inputs[str(src)] == hash_path(src)
        assert rec.outputs[str(out)] == hash_path(out)
        assert str(tmp_path / "missing.txt") not in rec.outputs

    def test_missing_input_raises(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        with pytest.raises(FileNotFoundError):
            ledger.record("run", {}, inputs=[tmp_path / "nope.txt"])
        assert ledger.count == 0

    def test_env_seed_and_approver(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        rec = ledger.record("sim", {"n": 1}, env={"CUDA_VISIBLE_DEVICES": "0"},
                            seed=42, approver="peng")
        assert rec.env == {"CUDA_VISIBLE_DEVICES": "0"}
        assert rec.seed == 42
        assert rec.approver == "peng"

    def test_tamper_is_detected(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        ledger.record("search", {"q": "x"})
        path = tmp_path / "actions.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace('"tool":"search"', '"tool":"other"')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, msg = ledger.verify_chain()
        assert not ok and "record_sha256" in msg

    def test_malformed_tail_fails_closed(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        ledger.record("search", {"q": "x"})
        with (tmp_path / "actions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        ok, msg = ledger.verify_chain()
        assert not ok and "malformed" in msg


class TestInvokerIntegration:
    def test_invoker_writes_action_with_event_seq(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        log = EventLog(tmp_path, "run-1")
        invoker = _invoker(tmp_path, tools=[_tool("echo")], ledger=ledger, event_log=log)
        result = asyncio.run(invoker.invoke("echo", {"topic": "x"}))
        assert result["success"] is True
        records = ledger.read_all()
        assert len(records) == 1
        rec = records[0]
        assert rec["tool"] == "echo"
        assert rec["status"] == "ok"
        assert rec["event_seq_call"] == 1
        assert rec["event_seq_result"] == 2
        assert rec["params_sha256"].startswith("sha256:")
        assert ledger.verify_chain()[0]

    def test_invoker_records_error_status(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        invoker = _invoker(tmp_path, tools=[_tool("echo")], ledger=ledger, success=False)
        result = asyncio.run(invoker.invoke("echo", {"topic": "x"}))
        assert result["success"] is False
        assert ledger.read_all()[0]["status"] == "error"

    def test_invoker_records_approver_identity(self, tmp_path: Path) -> None:
        ledger = ActionLedger(tmp_path, "run-1")
        approvals_path = tmp_path / "approvals.json"
        grant(tmp_path, "echo", by="peng")
        invoker = _invoker(tmp_path, tools=[_tool("echo", risk="high", approval="always")],
                           ledger=ledger, approvals_path=approvals_path)
        result = asyncio.run(invoker.invoke("echo", {"topic": "x"}))
        assert result["success"] is True
        assert ledger.read_all()[0]["approver"] == "peng"

    def test_invoker_without_ledger_unchanged(self, tmp_path: Path) -> None:
        invoker = _invoker(tmp_path, tools=[_tool("echo")])
        result = asyncio.run(invoker.invoke("echo", {"topic": "x"}))
        assert result["success"] is True
        assert not (tmp_path / "actions.jsonl").exists()
