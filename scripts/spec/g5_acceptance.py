"""P-155 G5 acceptance runner.

Runs the 28 planned tests (T01-T28) with pytest, parses the JUnit XML, and
reports per-test and per-acceptance status. Designed for the TDD red/green
record required by SPEC_PROCESS Step 9.

Usage:
    python scripts/spec/g5_acceptance.py --phase red
    python scripts/spec/g5_acceptance.py --phase green --json-out artifacts/p155.json
    python scripts/spec/g5_acceptance.py --selftest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: T01-T28 -> (acceptance id, test file, pytest function name).
CASES: tuple[tuple[str, str, str, str], ...] = (
    ("T01", "A5-2", "tests/test_paper_index.py", "test_paper_batch_selects_500"),
    ("T02", "A5-2", "tests/test_paper_index.py", "test_duplicate_doi_removed"),
    ("T03", "A5-2", "tests/test_paper_index.py", "test_duplicate_title_year_removed"),
    ("T04", "A5-2", "tests/test_paper_index.py", "test_confidence_normalized_from_percent"),
    ("T05", "A5-2", "tests/test_paper_index.py", "test_confidence_boundary_one"),
    ("T06", "ERR", "tests/test_paper_index.py", "test_corrupt_paper_jsonl_raises"),
    ("T07", "A5-3", "tests/test_textbook_kg.py", "test_textbook_kg_counts_15_17"),
    ("T08", "A5-3", "tests/test_textbook_kg.py", "test_illegal_relation_rejected"),
    ("T09", "A5-3", "tests/test_textbook_kg.py", "test_sample_queries_return_three_with_page"),
    ("T10", "ERR", "tests/test_textbook_kg.py", "test_corrupt_kg_json_raises"),
    ("T11", "A5-1", "tests/test_knowledge_store.py", "test_empty_kb_returns_empty"),
    ("T12", "A5-6", "tests/test_knowledge_store.py", "test_missing_index_marks_degraded"),
    ("T13", "ERR", "tests/test_knowledge_store.py", "test_unknown_kind_raises"),
    ("T14", "J-6", "tests/test_knowledge_store.py", "test_query_is_read_only"),
    ("T15", "A5-7", "tests/test_knowledge_store.py", "test_fulltext_false_and_citation_rejected"),
    ("T16", "A5-4", "tests/test_skillpack.py", "test_load_five_packs"),
    ("T17", "A5-8", "tests/test_skillpack.py", "test_tampered_pack_rejected"),
    ("T18", "A5-8", "tests/test_skillpack.py", "test_bad_signature_rejected"),
    ("T19", "A5-8", "tests/test_skillpack.py", "test_missing_key_fails_closed"),
    ("T20", "GQ-1", "tests/test_grounded_qa.py", "test_gq_disabled_writes_nothing"),
    ("T21", "GQ-2", "tests/test_grounded_qa.py", "test_citation_four_fields_digest_recomputes"),
    ("T22", "GQ-3", "tests/test_grounded_qa.py", "test_insufficient_without_evidence"),
    ("T23", "GQ-4", "tests/test_grounded_qa.py", "test_dependency_failure_degrades_not_fails"),
    ("T24", "GQ-5", "tests/test_grounded_qa.py", "test_contradiction_warn_and_block"),
    ("T25", "A5-9", "tests/test_read_position.py", "test_position_roundtrip"),
    ("T26", "A5-9", "tests/test_read_position.py", "test_restart_does_not_refetch"),
    ("T27", "A5-5", "tests/test_knowledge_counts.py", "test_knowledge_counts_single_source"),
    ("T28", "A5-5", "tests/test_knowledge_counts.py", "test_counts_mismatch_detected"),
)

ACCEPTANCE_IDS = tuple(
    dict.fromkeys(case[1] for case in CASES if case[1].startswith(("A5-", "GQ-")))
)


def _existing_files() -> list[str]:
    return [name for name in sorted({case[2] for case in CASES}) if (ROOT / name).is_file()]


def _run_pytest(files: list[str], junit_path: Path, extra: list[str]) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml",
        str(junit_path),
        *extra,
        *files,
    ]
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)


def _parse_junit(junit_path: Path) -> dict[tuple[str, str], str]:
    """Return ``{(file basename, test name): status}``."""
    if not junit_path.is_file():
        return {}
    try:
        tree = ET.parse(junit_path)
    except ET.ParseError:
        return {}
    results: dict[tuple[str, str], str] = {}
    for case in tree.getroot().iter("testcase"):
        file_attr = Path(case.get("file") or "").name
        classname = case.get("classname") or ""
        # pytest's JUnit XML omits ``file``; derive it from the module segment.
        module = next(
            (part for part in reversed(classname.split(".")) if part.startswith("test_")),
            "",
        )
        derived = module + ".py" if module else ""
        name = case.get("name") or ""
        status = "passed"
        for child in case:
            if child.tag == "failure":
                status = "failed"
            elif child.tag == "error":
                status = "error"
            elif child.tag == "skipped":
                status = "skipped"
        if file_attr:
            results[(file_attr, name)] = status
        if derived:
            results[(derived, name)] = status
    return results


def _collect(results: dict[tuple[str, str], str]) -> list[dict]:
    out: list[dict] = []
    for tid, acceptance, file_name, test_name in CASES:
        status = results.get((Path(file_name).name, test_name), "missing")
        out.append({
            "id": tid,
            "acceptance": acceptance,
            "file": file_name,
            "test": test_name,
            "status": status,
        })
    return out


def _summary(cases: list[dict]) -> dict:
    by_acceptance: "OrderedDict[str, dict]" = OrderedDict()
    for acceptance in ACCEPTANCE_IDS:
        rows = [case for case in cases if case["acceptance"] == acceptance]
        by_acceptance[acceptance] = {
            "total": len(rows),
            "passed": sum(row["status"] == "passed" for row in rows),
            "status": (
                "passed"
                if rows and all(row["status"] == "passed" for row in rows)
                else "pending"
            ),
        }
    return {
        "total": len(cases),
        "passed": sum(case["status"] == "passed" for case in cases),
        "failed": sum(case["status"] in ("failed", "error") for case in cases),
        "missing": sum(case["status"] == "missing" for case in cases),
        "skipped": sum(case["status"] == "skipped" for case in cases),
        "by_acceptance": by_acceptance,
    }


def _ok(phase: str, summary: dict, *, allow_missing: bool) -> bool:
    if phase == "green":
        return summary["passed"] == summary["total"]
    if phase == "red":
        # TDD red: no test may pass yet. Tests may be missing only when the
        # caller explicitly allows the pre-implementation state.
        if summary["passed"] > 0:
            return False
        if summary["missing"] == summary["total"] and not allow_missing:
            return False
        return True
    return summary["passed"] == summary["total"]


def _label(phase: str, summary: dict, ok: bool) -> str:
    if phase == "red":
        if summary["passed"] > 0:
            return "UNEXPECTED PASS"
        if summary["missing"] == summary["total"]:
            return "RED-PENDING (tests missing)"
        return "RED (expected failures)"
    return "GREEN" if ok else "NOT OK"


def _print_table(cases: list[dict], summary: dict, phase: str) -> None:
    print(f"phase={phase} total={summary['total']} passed={summary['passed']} "
          f"failed={summary['failed']} missing={summary['missing']} skipped={summary['skipped']}")
    for case in cases:
        print(f"  {case['id']:>3} {case['acceptance']:<5} {case['status']:<8} {case['test']}")
    print("acceptance:")
    for acceptance, row in summary["by_acceptance"].items():
        print(f"  {acceptance:<5} {row['passed']}/{row['total']} {row['status']}")


def _selftest() -> int:
    """Build a synthetic all-pass JUnit XML and verify the parser."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "selftest.xml"
        root = ET.Element("testsuites")
        suite = ET.SubElement(root, "testsuite")
        for _tid, _acc, file_name, test_name in CASES:
            ET.SubElement(
                suite,
                "testcase",
                {"file": file_name, "name": test_name, "classname": "selftest"},
            )
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        cases = _collect(_parse_junit(path))
        summary = _summary(cases)
        if summary["passed"] != len(CASES):
            print(f"selftest: FAILED ({summary['passed']}/{len(CASES)})")
            return 1
        print(f"selftest: ok ({len(CASES)} cases parsed)")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P-155 G5 acceptance runner")
    parser.add_argument("--phase", choices=("red", "green", "all"), default="all")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument("--json-out", default="", help="Write the report JSON to this path")
    parser.add_argument("--allow-missing", action="store_true",
                        help="Red phase only: missing tests do not fail the run")
    parser.add_argument("--selftest", action="store_true", help="Run the parser selftest")
    parser.add_argument("--pytest-arg", action="append", default=[],
                        help="Extra pytest argument (repeatable)")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    files = _existing_files()
    with tempfile.TemporaryDirectory() as tmp:
        junit_path = Path(tmp) / "junit.xml"
        pytest_rc = 0
        if files:
            proc = _run_pytest(files, junit_path, args.pytest_arg)
            pytest_rc = proc.returncode
            if proc.returncode not in (0, 1):
                print(proc.stdout, file=sys.stderr)
                print(proc.stderr, file=sys.stderr)
        results = _parse_junit(junit_path)

    cases = _collect(results)
    summary = _summary(cases)
    ok = _ok(args.phase, summary, allow_missing=args.allow_missing)

    report = {
        "feature": "P-155",
        "phase": args.phase,
        "ok": ok,
        "pytest_returncode": pytest_rc,
        "existing_files": files,
        **summary,
        "cases": cases,
    }

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(cases, summary, args.phase)
        print(f"report: {_label(args.phase, summary, ok)}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
