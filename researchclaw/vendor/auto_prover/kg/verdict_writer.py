"""verdict_writer.py — JSONL append-only 写入器 (O4 方案 B)

永不截断,永不覆盖。每行一个 verdict JSON。
崩溃安全: append 是 OS 原子操作 (≤ 4KB 单次 write)。

依据: DESIGN_ATLAS_PHASE_5B.md §4.3.2 / O4 方案 B / IMPL_ATLAS_PHASE_5B.md §2.5
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path

from ..datatypes import AssertionVerdict


class VerdictWriter:
    """JSONL append-only 写入器

    文件命名: verdicts_<YYYYMMDD>.jsonl (按日切分)
    写入模式: "a" (append), 永不截断
    """

    def __init__(self, output_dir: str = ""):
        """初始化写入器

        Args:
            output_dir: 输出目录, 空字符串时使用默认路径
                        (proof_pipeline/output/)
        """
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self) -> Path:
        """按日切分文件路径"""
        date_str = datetime.now().strftime("%Y%m%d")
        return self.output_dir / f"verdicts_{date_str}.jsonl"

    async def write(self, verdict: AssertionVerdict) -> str:
        """异步写入 verdict 到 JSONL (append-only)

        Args:
            verdict: AssertionVerdict 实例

        Returns:
            verdict_id (基于 assertion MD5 hash, 确定性幂等键)
        """
        record = self._verdict_to_record(verdict)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        await asyncio.to_thread(self._append_line, line)
        return record["verdict_id"]

    def _append_line(self, line: str) -> None:
        """同步追加一行 (Windows OS 保证 append 原子性)"""
        with open(self._file_path(), "a", encoding="utf-8") as f:
            f.write(line)

    def _verdict_to_record(self, verdict: AssertionVerdict) -> dict:
        """AssertionVerdict → JSONL record dict"""
        verdict_id = f"v_{hashlib.md5(verdict.assertion.encode('utf-8')).hexdigest()[:12]}"
        return {
            "verdict_id": verdict_id,
            "timestamp": datetime.now().isoformat(),
            "assertion": verdict.assertion,
            "citation_label": verdict.citation_label.value,
            "policy_version": verdict.policy_version,
            "verdict_reason": verdict.verdict_reason,
            "verdict_evidence": verdict.verdict_evidence,
            "confidence": {
                "latex": verdict.latex_confidence,
                "numerical": verdict.numerical_confidence,
                "formal": verdict.formal_confidence,
                "complete": verdict.complete_confidence,
            },
            "stopped_at": verdict.stopped_at.value,
            "lean_code": verdict.lean_code,
        }