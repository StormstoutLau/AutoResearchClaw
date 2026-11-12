"""G3 M5: K5 reference grammar, resolution and check tests (A3-4)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.knowledge.k5_refs import (
    bib_keys_from_text,
    check_k5_refs,
    parse_refs,
    resolve_refs,
)


def test_parse_refs_reports_kind_key_and_line() -> None:
    text = "first tb:node-a\nsecond paper:smith2020.\n"
    refs = parse_refs(text)
    assert [(ref.kind, ref.key, ref.line) for ref in refs] == [
        ("tb", "node-a", 1),
        ("paper", "smith2020", 2),
    ]


def test_parse_refs_ignores_malformed_tokens() -> None:
    text = "bad tb:-x tb: paper:\n"
    assert parse_refs(text) == []


def test_resolve_paper_against_bib_keys() -> None:
    refs = parse_refs("paper:smith2020 paper:missing")
    unresolved = resolve_refs(refs, bib_keys={"smith2020"})
    assert [ref.raw for ref in unresolved] == ["paper:missing"]


def test_resolve_tb_against_nested_kb(tmp_path: Path) -> None:
    (tmp_path / "findings").mkdir()
    (tmp_path / "findings" / "node-a.md").write_text("body", encoding="utf-8")
    refs = parse_refs("tb:node-a tb:node-b")
    unresolved = resolve_refs(refs, kb_root=tmp_path)
    assert [ref.raw for ref in unresolved] == ["tb:node-b"]


def test_check_returns_file_line_ref(tmp_path: Path) -> None:
    unresolved = check_k5_refs(
        "intro\nsee paper:missing\n",
        kb_root=tmp_path,
        bib_keys=set(),
        file="paper_final.md",
    )
    assert unresolved == [
        {"file": "paper_final.md", "line": 2, "ref": "paper:missing"}
    ]


def test_bib_keys_from_text() -> None:
    bib = "@article{smith2020, title={T}}\n@book{doe2021, title={B}}\n"
    assert bib_keys_from_text(bib) == {"smith2020", "doe2021"}


def test_k5_report_is_json_serializable(tmp_path: Path) -> None:
    unresolved = check_k5_refs("paper:x", kb_root=tmp_path, file="p.md")
    assert json.loads(json.dumps(unresolved)) == unresolved
