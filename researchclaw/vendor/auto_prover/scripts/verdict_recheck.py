"""W1 / B-52: 旧 verdict 正式标签的只读回溯复核。

用法:
    py -3.12 scripts/verdict_recheck.py --root output [--output recheck.json]

行为:
  - 只读扫描 `*.jsonl`，不修改任何源文件；
  - 仅登记正式标签（formally_verified / partially_formalized）；
  - `policy_version < 2` ⇒ recheck；`>=2` 且带 verdict_evidence ⇒ current；
    否则 unverifiable。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FORMAL_LABELS = {"formally_verified", "partially_formalized"}
CURRENT_POLICY_VERSION = 2


def classify(record: dict) -> dict:
    label = record.get("citation_label", "")
    try:
        version = int(record.get("policy_version", 1))
    except (TypeError, ValueError):
        version = 1
    evidence = record.get("verdict_evidence") or {}
    if version < CURRENT_POLICY_VERSION:
        recommendation = "recheck"
    elif evidence:
        recommendation = "current"
    else:
        recommendation = "unverifiable"
    return {
        "assertion": record.get("assertion", ""),
        "citation_label": label,
        "policy_version": version,
        "recommendation": recommendation,
        "has_compile_evidence": bool(evidence.get("compile")),
    }


def scan_paths(paths) -> dict:
    records: list[dict] = []
    files = 0
    lines = 0
    malformed = 0
    for path in paths:
        path = Path(path)
        if not path.exists() or not path.is_file():
            continue
        files += 1
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                lines += 1
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if record.get("citation_label") not in FORMAL_LABELS:
                    continue
                item = classify(record)
                item.update({"file": str(path), "line": lineno})
                records.append(item)

    summary = {
        "files": files,
        "lines": lines,
        "formal_records": len(records),
        "needs_recheck": sum(r["recommendation"] == "recheck" for r in records),
        "unverifiable": sum(r["recommendation"] == "unverifiable" for r in records),
        "current": sum(r["recommendation"] == "current" for r in records),
        "malformed_lines": malformed,
    }
    return {"summary": summary, "records": records}


def _collect(root: Path, output: Path | None) -> list[Path]:
    paths = sorted(root.rglob("*.jsonl")) if root.is_dir() else [root]
    if output is not None:
        paths = [p for p in paths if p.resolve() != output.resolve()]
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="只读回溯复核正式 verdict 标签")
    parser.add_argument("--root", required=True,
                        help="JSONL 文件或扫描目录")
    parser.add_argument("--output", default="",
                        help="可选：复核报告 JSON 输出路径（不复写源文件）")
    args = parser.parse_args(argv)

    root = Path(args.root)
    out = Path(args.output) if args.output else None
    report = scan_paths(_collect(root, out))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(
        "recheck: files={files} formal={formal_records} "
        "recheck={needs_recheck} unverifiable={unverifiable} "
        "current={current} malformed={malformed_lines}".format(
            **report["summary"]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
