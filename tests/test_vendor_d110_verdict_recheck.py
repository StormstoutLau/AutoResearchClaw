# SPDX-License-Identifier: Apache-2.0
# Vendored from Auto_Prover tests/test_d110_verdict_recheck.py at bd95f02.
# Modified by AutoResearchClaw on 2026-11-11: imports point at the vendored kernel.
"""W1: 旧 verdict 只读回溯复核脚本

TDD 红: 脚本尚未实现 ⇒ 载入失败。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "researchclaw" / "vendor" / "auto_prover" / "scripts" / "verdict_recheck.py"


def _load():
    spec = importlib.util.spec_from_file_location("verdict_recheck", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class TestVerdictRecheck:
    def _fixture(self, tmp_path):
        src = tmp_path / "verdicts_20261026.jsonl"
        rows = [
            {"assertion": "new", "citation_label": "formally_verified",
             "policy_version": 2, "verdict_evidence": {"compile": {"status": "success"}}},
            {"assertion": "old", "citation_label": "formally_verified"},
            {"assertion": "old-partial", "citation_label": "partially_formalized",
             "policy_version": 1},
            {"assertion": "numeric", "citation_label": "numerically_verified"},
        ]
        src.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
        return src

    def test_scan_classifies_and_does_not_modify_source(self, tmp_path):
        module = _load()
        src = self._fixture(tmp_path)
        before = _md5(src)
        report = module.scan_paths([src])
        assert _md5(src) == before
        by_assertion = {r["assertion"]: r for r in report["records"]}
        assert by_assertion["new"]["recommendation"] == "current"
        assert by_assertion["old"]["recommendation"] == "recheck"
        assert by_assertion["old-partial"]["recommendation"] == "recheck"
        assert "numeric" not in by_assertion  # 非正式标签不进入复核清单
        assert report["summary"]["formal_records"] == 3
        assert report["summary"]["needs_recheck"] == 2

    def test_main_writes_report_without_touching_source(self, tmp_path):
        module = _load()
        src = self._fixture(tmp_path)
        out = tmp_path / "report.json"
        before = _md5(src)
        code = module.main(["--root", str(tmp_path), "--output", str(out)])
        assert code == 0
        assert _md5(src) == before
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["needs_recheck"] == 2

    def test_malformed_line_is_reported_not_crashed(self, tmp_path):
        module = _load()
        src = tmp_path / "verdicts_bad.jsonl"
        src.write_text('{"citation_label": "formally_verified"}\nnot-json\n',
                       encoding="utf-8")
        report = module.scan_paths([src])
        assert report["summary"]["malformed_lines"] == 1
        assert report["records"][0]["recommendation"] == "recheck"
