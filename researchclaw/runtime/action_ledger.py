"""Action-level ledger (P-143 / P-140 P0-1).

``events.jsonl`` records what the pipeline *observed*; this ledger records what
it *did*. One line per executed action, hash-chained like the event log, with:

- the parameters digest (never raw values),
- environment and random seed,
- input/output artifact hashes (``sha256:<hex>``),
- the approving actor when one was required,
- status / exit code,
- the ``events.jsonl`` seq range that brackets the action.

The ledger is append-only and fsync'd. Verification checks seq continuity,
the ``prev_sha256`` pointer and the per-record digest, so a truncated or
edited tail is detectable offline without the event log.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from researchclaw.runtime.event_log import canonical_json

ACTIONS_NAME = "actions.jsonl"
ZERO_HASH = "0" * 64
SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_path(path: str | Path) -> str:
    """Content hash of a file as ``sha256:<hex>``. Raises if it is missing."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _hash_if_exists(path: str | Path) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    return hash_path(p)


@dataclass(frozen=True)
class ActionRecord:
    """One line of ``actions.jsonl``."""

    seq: int
    ts: str
    run_id: str
    action_id: str
    tool: str
    params_sha256: str
    prev_sha256: str
    record_sha256: str
    env: dict[str, str] = field(default_factory=dict)
    seed: int | str | None = None
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    approver: str | None = None
    status: str = "ok"
    exit_code: int | None = None
    event_seq_call: int | None = None
    event_seq_result: int | None = None
    schema: int = SCHEMA_VERSION

    def body(self) -> dict:
        """Record without its own digest (the hashed surface)."""
        return {
            "schema": self.schema,
            "seq": self.seq,
            "ts": self.ts,
            "run_id": self.run_id,
            "action_id": self.action_id,
            "tool": self.tool,
            "params_sha256": self.params_sha256,
            "env": self.env,
            "seed": self.seed,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "approver": self.approver,
            "status": self.status,
            "exit_code": self.exit_code,
            "event_seq_call": self.event_seq_call,
            "event_seq_result": self.event_seq_result,
            "prev_sha256": self.prev_sha256,
        }

    def to_dict(self) -> dict:
        data = self.body()
        data["record_sha256"] = self.record_sha256
        return data

    def to_line(self) -> str:
        return canonical_json(self.to_dict())


class ActionLedger:
    """Single-writer append-only action ledger."""

    def __init__(self, run_dir: str | Path, run_id: str, *, fsync: bool = True) -> None:
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.fsync = fsync
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._last_seq = 0
        self._last_hash = ZERO_HASH
        self._count = 0
        self._refresh()

    @property
    def path(self) -> Path:
        return self.run_dir / ACTIONS_NAME

    @property
    def last_seq(self) -> int:
        return self._last_seq

    @property
    def count(self) -> int:
        return self._count

    def _refresh(self) -> None:
        """Rebuild counters from disk; a torn tail is ignored."""
        if not self.path.is_file():
            return
        good: list[str] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                canonical_load(line)
            except ValueError:
                break
            good.append(line)
        if good:
            self._count = len(good)
            self._last_hash = _sha256_text(good[-1])
            self._last_seq = int(canonical_load(good[-1]).get("seq", len(good)))

    def record(
        self,
        tool: str,
        params: Mapping[str, Any] | None = None,
        *,
        action_id: str | None = None,
        inputs: Iterable[str | Path] = (),
        outputs: Iterable[str | Path] = (),
        env: Mapping[str, str] | None = None,
        seed: int | str | None = None,
        approver: str | None = None,
        status: str = "ok",
        exit_code: int | None = None,
        event_seq_call: int | None = None,
        event_seq_result: int | None = None,
        ts: str | None = None,
    ) -> ActionRecord:
        """Append one action. Missing input files raise; missing outputs are skipped."""
        in_hashes = {str(p): hash_path(p) for p in inputs}
        out_hashes: dict[str, str] = {}
        for p in outputs:
            digest = _hash_if_exists(p)
            if digest is not None:
                out_hashes[str(p)] = digest

        body = {
            "schema": SCHEMA_VERSION,
            "seq": self._last_seq + 1,
            "ts": ts or _now_iso(),
            "run_id": self.run_id,
            "action_id": action_id or uuid.uuid4().hex,
            "tool": str(tool),
            "params_sha256": "sha256:" + _sha256_text(canonical_json(dict(params or {}))),
            "env": {str(k): str(v) for k, v in (env or {}).items()},
            "seed": seed,
            "inputs": in_hashes,
            "outputs": out_hashes,
            "approver": approver,
            "status": str(status),
            "exit_code": exit_code,
            "event_seq_call": event_seq_call,
            "event_seq_result": event_seq_result,
            "prev_sha256": self._last_hash,
        }
        record_sha256 = "sha256:" + _sha256_text(canonical_json(body))
        record = ActionRecord(record_sha256=record_sha256, **body)
        data = (record.to_line() + "\n").encode("utf-8")

        with self.path.open("ab") as fh:
            fh.write(data)
            fh.flush()
            if self.fsync:
                os.fsync(fh.fileno())

        self._last_seq = record.seq
        self._last_hash = _sha256_text(record.to_line())
        self._count += 1
        return record

    def read_all(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                out.append(canonical_load(line))
            except ValueError:
                break
        return out

    def verify_chain(self) -> tuple[bool, str]:
        """Recompute seq continuity, the prev pointer and each record digest.

        Malformed lines (torn tail, hand edits) fail closed instead of being
        silently dropped: an unparseable record is an unverifiable action.
        """
        if not self.path.is_file():
            return True, "ok (0 actions)"
        prev = ZERO_HASH
        expect_seq = 1
        for lineno, line in enumerate(
                self.path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = canonical_load(line)
            except ValueError:
                return False, "malformed record at line %d" % lineno
            if int(rec.get("seq", -1)) != expect_seq:
                return False, "seq gap at %r (expected %d)" % (rec.get("seq"), expect_seq)
            if rec.get("prev_sha256") != prev:
                return False, "prev_sha256 mismatch at seq %d" % expect_seq
            body = {k: v for k, v in rec.items() if k != "record_sha256"}
            digest = "sha256:" + _sha256_text(canonical_json(body))
            if rec.get("record_sha256") != digest:
                return False, "record_sha256 mismatch at seq %d" % expect_seq
            prev = _sha256_text(canonical_json(rec))
            expect_seq += 1
        return True, "ok (%d actions)" % (expect_seq - 1)


def canonical_load(line: str) -> dict:
    """Parse one ledger line; raises ``ValueError`` on malformed JSON or shape."""
    import json

    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("action record must be an object")
    return data
