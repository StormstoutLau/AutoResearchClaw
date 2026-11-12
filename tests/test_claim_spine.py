"""G3 M3: claim annotation, marker, export and trace/digest tests (A3-1/A3-3)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from researchclaw.evidence.claim_spine import (
    CLAIM_MARKER_RE,
    E_CLAIM_DIGEST_MISMATCH,
    E_CLAIM_TRACE_MISMATCH,
    MARKER_PLACEHOLDER,
    annotations_from_stage14,
    export_claim_labels,
    extract_claim_markers,
    verify_claim_digests,
    verify_claim_trace,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _claim(claim_id: str, statement: str) -> dict:
    return {
        "claim_id": claim_id,
        "claim_class": "C",
        "statement": statement,
        "status": "speculation",
    }


def _write_claims(run_dir: Path, claims: list[dict]) -> None:
    path = run_dir / "stage-09" / "claims.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(claim, ensure_ascii=False) + "\n" for claim in claims),
        encoding="utf-8",
    )


def _write_summary(run_dir: Path, payload: dict) -> Path:
    path = run_dir / "stage-14" / "experiment_summary.json"
    _write_json(path, payload)
    return path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _decision(status: str = "numerically_verified", **overrides) -> dict:
    decision = {
        "claim_id": "c-11111111",
        "status": status,
        "deliverable": True,
        "blocked_reasons": [],
        "downgraded": False,
        "capped": False,
        "cap_reasons": [],
        "problems": [],
        "findings": [],
    }
    decision.update(overrides)
    return decision


# ── annotations (F-1..F-5) ──────────────────────────────────────


def test_annotations_bind_metric_and_digest(tmp_path: Path) -> None:
    _write_claims(tmp_path, [_claim("c-11111111", "Our method improves accuracy.")])
    summary = _write_summary(
        tmp_path,
        {"metrics_summary": {"accuracy": {"mean": 0.95, "min": 0.9, "max": 0.99, "count": 5}}},
    )
    result = annotations_from_stage14(tmp_path)
    entry = result["c-11111111"]
    assert entry["metric"] == "accuracy"
    assert entry["value"] == 0.95
    assert entry["n"] == 5
    assert "ci" not in entry
    assert entry["source"] == "stage14"
    assert entry["evidence_locator"] == "stage-14/experiment_summary.json"
    assert entry["evidence_digest"] == _digest(summary)
    on_disk = json.loads(
        (tmp_path / "stage-14" / "claim_annotations.json").read_text(encoding="utf-8")
    )
    assert on_disk == result


def test_annotations_skip_unmatched_claim(tmp_path: Path) -> None:
    _write_claims(tmp_path, [_claim("c-11111111", "Latency drops below one second.")])
    _write_summary(
        tmp_path,
        {"metrics_summary": {"accuracy": {"mean": 0.95, "min": 0.9, "max": 0.99, "count": 5}}},
    )
    assert annotations_from_stage14(tmp_path) == {}


def test_annotations_use_condition_ci_and_external_override(tmp_path: Path) -> None:
    _write_claims(
        tmp_path,
        [
            _claim("c-11111111", "The baseline accuracy is strong."),
            _claim("c-22222222", "The accuracy improves further."),
        ],
    )
    _write_summary(
        tmp_path,
        {
            "metrics_summary": {
                "accuracy": {"mean": 0.95, "min": 0.9, "max": 0.99, "count": 5}
            },
            "condition_summaries": {
                "baseline": {
                    "metrics": {"accuracy": 0.9},
                    "n_seeds": 5,
                    "ci95_low": 0.88,
                    "ci95_high": 0.92,
                }
            },
        },
    )
    _write_json(
        tmp_path / "annotations.external.json",
        {"c-22222222": {"metric": "accuracy", "value": 0.97, "n": 9, "ci": [0.96, 0.98]}},
    )
    result = annotations_from_stage14(tmp_path)
    baseline = result["c-11111111"]
    assert baseline["condition"] == "baseline"
    assert baseline["value"] == 0.9
    assert baseline["n"] == 5
    assert baseline["ci"] == [0.88, 0.92]
    external = result["c-22222222"]
    assert external["value"] == 0.97
    assert external["n"] == 9
    assert external["ci"] == [0.96, 0.98]
    assert external["source"] == "external"


def test_annotations_use_longest_token_match(tmp_path: Path) -> None:
    _write_claims(tmp_path, [_claim("c-11111111", "Balanced accuracy improves.")])
    _write_summary(
        tmp_path,
        {
            "metrics_summary": {
                "accuracy": {"mean": 0.91, "min": 0.9, "max": 0.92, "count": 5},
                "balanced_accuracy": {"mean": 0.88, "min": 0.86, "max": 0.9, "count": 5},
            }
        },
    )
    assert annotations_from_stage14(tmp_path)["c-11111111"]["metric"] == "balanced_accuracy"


# ── markers (F-6/F-7) ───────────────────────────────────────────


def test_extract_markers_maps_sections() -> None:
    text = (
        "intro [c-11111111]\n\n"
        "# Title\n\n"
        "## 4.2 Results\n\n"
        "value [c-11111111] and [c-22222222].\n\n"
        "## Discussion\n\n"
        "more [c-33333333].\n"
    )
    assert extract_claim_markers(text) == {
        "c-11111111": ["§Preamble", "§4.2"],
        "c-22222222": ["§4.2"],
        "c-33333333": ["§Discussion"],
    }


def test_extract_markers_deduplicates() -> None:
    text = "## Results\n\nfirst [c-11111111].\n\nsecond [c-11111111].\n"
    assert extract_claim_markers(text) == {"c-11111111": ["§Results"]}


# ── P-085 / D-1: placeholder, fences and heading attribution ────


def test_stage17_prompt_example_is_non_matching_placeholder() -> None:
    assert CLAIM_MARKER_RE.findall(MARKER_PLACEHOLDER) == []
    source = (
        Path(__file__).resolve().parents[1]
        / "researchclaw" / "pipeline" / "stage_impls" / "_paper_writing.py"
    ).read_text(encoding="utf-8")
    assert "c-1a2b3c4d" not in source
    assert "MARKER_PLACEHOLDER" in source


def test_extract_markers_skips_code_fence_and_inline_code() -> None:
    text = (
        "## Method\n\n"
        "```python\n"
        "claim = \"[c-11111111]\"\n"
        "```\n\n"
        "Inline `[c-22222222]` is an example.\n\n"
        "Real [c-33333333].\n"
    )
    assert extract_claim_markers(text) == {"c-33333333": ["§Method"]}


def test_extract_markers_heading_applies_to_following_lines() -> None:
    text = "intro [c-11111111].\n## 4.2 Results\nvalue [c-22222222].\n"
    assert extract_claim_markers(text) == {
        "c-11111111": ["§Preamble"],
        "c-22222222": ["§4.2"],
    }


def test_extract_markers_ignores_heading_inside_fence() -> None:
    text = (
        "## Method\n\n"
        "```\n"
        "## Fake Section\n"
        "[c-11111111]\n"
        "```\n\n"
        "## Results\n\n"
        "[c-22222222]\n"
    )
    assert extract_claim_markers(text) == {"c-22222222": ["§Results"]}


# ── export (F-9..F-11) ──────────────────────────────────────────


def _write_gate(run_dir: Path, decisions: dict) -> None:
    _write_json(run_dir / "stage-20" / "claim_gate.json", {"decisions": decisions})


def _write_paper(run_dir: Path, text: str) -> None:
    path = run_dir / "stage-22" / "paper_final.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_export_excludes_unpublished_claim(tmp_path: Path) -> None:
    _write_gate(
        tmp_path,
        {
            "c-11111111": _decision(),
            "c-22222222": _decision(status="speculation", deliverable=False),
        },
    )
    _write_paper(tmp_path, "## Results\n\nOnly this [c-11111111].\n")
    result = export_claim_labels(tmp_path)
    assert set(result["claims"]) == {"c-11111111"}
    assert result["errors"] == []
    on_disk = json.loads(
        (tmp_path / "stage-22" / "claim_export.json").read_text(encoding="utf-8")
    )
    assert set(on_disk) == {"c-11111111"}


def test_export_maps_citation_label_and_cap_reasons(tmp_path: Path) -> None:
    _write_gate(
        tmp_path,
        {"c-11111111": _decision(status="latex_verified", cap_reasons=["AR-06:latex_verified"])},
    )
    _write_paper(tmp_path, "## 4.2 Results\n\nValue [c-11111111].\n")
    entry = export_claim_labels(tmp_path)["claims"]["c-11111111"]
    assert entry["status"] == "latex_verified"
    assert entry["citation_label"] == "latex_verified"
    assert entry["paragraph_refs"] == ["§4.2"]
    assert entry["deliverable"] is True
    assert entry["cap_reasons"] == ["AR-06:latex_verified"]
    assert "prompt_version" not in entry


def test_export_includes_stage17_prompt_version(tmp_path: Path) -> None:
    _write_gate(tmp_path, {"c-11111111": _decision()})
    _write_paper(tmp_path, "## Results\n\n[c-11111111]\n")
    _write_json(
        tmp_path / "stage-17" / "claim_prompt_versions.json",
        {"prompt_version": "sha256:abc", "claims": ["c-11111111"]},
    )
    entry = export_claim_labels(tmp_path)["claims"]["c-11111111"]
    assert entry["prompt_version"] == "sha256:abc"


def test_export_reports_unpublished_citation(tmp_path: Path) -> None:
    _write_gate(
        tmp_path,
        {
            "c-11111111": _decision(),
            "c-22222222": _decision(status="speculation", deliverable=False),
        },
    )
    _write_paper(tmp_path, "## Results\n\nBad [c-22222222].\n")
    result = export_claim_labels(tmp_path)
    assert {"claim_id": "c-22222222", "reason": "unpublished_claim_cited"} in result["errors"]


# ── trace / digest (F-12..F-14, E-1..E-5) ───────────────────────


def _write_export(run_dir: Path, payload: dict) -> None:
    _write_json(run_dir / "stage-22" / "claim_export.json", payload)


def test_verify_trace_detects_status_mismatch(tmp_path: Path) -> None:
    _write_gate(tmp_path, {"c-11111111": _decision(status="numerically_verified")})
    _write_export(
        tmp_path,
        {
            "c-11111111": {
                "status": "latex_verified",
                "citation_label": "latex_verified",
                "paragraph_refs": [],
                "deliverable": True,
                "cap_reasons": [],
            }
        },
    )
    result = verify_claim_trace(tmp_path, require_export=True)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == E_CLAIM_TRACE_MISMATCH
    assert result["errors"][0]["claim_id"] == "c-11111111"


def test_verify_trace_requires_export_when_enabled(tmp_path: Path) -> None:
    _write_gate(tmp_path, {"c-11111111": _decision()})
    assert verify_claim_trace(tmp_path)["ok"] is True
    result = verify_claim_trace(tmp_path, require_export=True)
    assert result["ok"] is False
    assert result["errors"][0]["detail"] == "claim_export_missing"


def test_verify_trace_tolerates_corrupt_gate(tmp_path: Path) -> None:
    path = tmp_path / "stage-20" / "claim_gate.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    result = verify_claim_trace(tmp_path, require_export=True)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == E_CLAIM_TRACE_MISMATCH


def test_verify_digests_detects_tampered_summary(tmp_path: Path) -> None:
    _write_claims(tmp_path, [_claim("c-11111111", "Our method improves accuracy.")])
    summary = _write_summary(
        tmp_path,
        {"metrics_summary": {"accuracy": {"mean": 0.95, "min": 0.9, "max": 0.99, "count": 5}}},
    )
    annotations_from_stage14(tmp_path)
    summary.write_text('{"metrics_summary": {}}', encoding="utf-8")
    result = verify_claim_digests(tmp_path)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == E_CLAIM_DIGEST_MISMATCH
    assert result["errors"][0]["claim_id"] == "c-11111111"


def test_verify_digests_skips_pointer_evidence(tmp_path: Path) -> None:
    claim = _claim("c-11111111", "Pointer evidence stays external.")
    claim["evidence"] = [
        {
            "evidence_id": "e-001",
            "kind": "pointer",
            "locator": "Table 3",
            "digest": "sha256:" + "a" * 64,
        }
    ]
    _write_claims(tmp_path, [claim])
    result = verify_claim_digests(tmp_path)
    assert result["ok"] is True
    assert result["checked"] == 0
    assert result["skipped"] == 1
