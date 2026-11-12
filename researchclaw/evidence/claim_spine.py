"""G3 M3 claim spine: annotations, markers, export, trace and digest checks.

Pure-ish helpers over existing pipeline artifacts. ``annotations_from_stage14``
and ``export_claim_labels`` write under the run directory; the two ``verify_*``
entries are read-only. No pipeline imports, no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

E_CLAIM_TRACE_MISMATCH = "E_CLAIM_TRACE_MISMATCH"
E_CLAIM_DIGEST_MISMATCH = "E_CLAIM_DIGEST_MISMATCH"

ANNOTATIONS_NAME = "claim_annotations.json"
EXPORT_NAME = "claim_export.json"

CLAIM_MARKER_RE = re.compile(r"\[(c-[0-9a-f]{8})\]", re.IGNORECASE)
# P-085 / D-1: non-hex placeholder. ``x`` never matches ``[0-9a-f]``, so a
# prompt example can never be mistaken for a real claim id. ``x``/``X`` also
# never matches ``[0-9a-fA-F]`` (P-094 / F-4: extraction is case-insensitive).
MARKER_PLACEHOLDER = "[c-xxxxxxxx]"
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$")
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)")
_CLAIM_ID_RE = re.compile(r"^c-[0-9a-f]{8}$")
_VERSION_RE = re.compile(r"_v(\d+)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INDENT_CODE_RE = re.compile(r"^ {4,}\S")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


# ---------------------------------------------------------------- io helpers
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _same_digest(declared: Any, actual: str) -> bool:
    text = str(declared or "").strip()
    if not text:
        return False
    return text.removeprefix("sha256:") == actual.removeprefix("sha256:")


def _live_or_latest(run_dir: Path, prefix: str, filename: str) -> Path | None:
    """Live ``stage-NN`` first, then versioned dirs newest-first (D-1 semantics)."""
    live = run_dir / prefix / filename
    if live.is_file():
        return live
    candidates: list[tuple[int, int, str, Path]] = []
    for path in run_dir.glob(f"{prefix}*/{filename}"):
        if not path.is_file():
            continue
        match = _VERSION_RE.search(path.parent.name)
        version = int(match.group(1)) if match else -1
        candidates.append((1, -version, path.parent.name, path))
    candidates.sort()
    return candidates[0][3] if candidates else None


def _read_claims(path: Path, *, strict: bool) -> list[dict]:
    if not path.is_file():
        return []
    claims: list[dict] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if strict:
                raise ValueError(f"{path}:{line_no}: {exc.msg}") from exc
            continue
        if isinstance(item, dict):
            claims.append(item)
    return claims


# ---------------------------------------------------------------- annotations
def _normalize(text: str) -> str:
    return re.sub(r"[_\-/]+", " ", text.lower()).strip()


def _has_token(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _match_metric(statement: str, prepared: list[tuple[int, str, str]]) -> str | None:
    normalized = _normalize(statement)
    matches = [
        (length, key) for length, name, key in prepared if _has_token(normalized, name)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1]))
    return matches[0][1]


def _prepare_metric_names(metrics: Mapping[str, Any]) -> list[tuple[int, str, str]]:
    prepared: list[tuple[int, str, str]] = []
    for key in metrics:
        names = {_normalize(str(key)), _normalize(str(key).rsplit("/", 1)[-1])}
        prepared.extend((len(name), name, str(key)) for name in names if name)
    return prepared


def _prepare_condition_names(conditions: Mapping[str, Any]) -> list[tuple[int, str, str]]:
    prepared: list[tuple[int, str, str]] = []
    for name in conditions:
        normalized = _normalize(str(name))
        if normalized:
            prepared.append((len(normalized), normalized, str(name)))
    prepared.sort(key=lambda item: (-item[0], item[1]))
    return prepared


def _match_condition(statement: str, prepared: list[tuple[int, str, str]]) -> str | None:
    normalized = _normalize(statement)
    for _length, name, key in prepared:
        if _has_token(normalized, name):
            return key
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _annotation_for(
    claim: Mapping[str, Any],
    metrics: Mapping[str, Any],
    conditions: Mapping[str, Any],
    summary_path: Path,
    *,
    prepared_metrics: list[tuple[int, str, str]],
    prepared_conditions: list[tuple[int, str, str]],
) -> dict | None:
    statement = claim.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        return None
    metric_key = _match_metric(statement, prepared_metrics)
    if metric_key is None:
        return None
    metric_value = metrics[metric_key]
    mean = _as_float(metric_value.get("mean") if isinstance(metric_value, dict) else metric_value)
    if mean is None:
        return None
    count = metric_value.get("count") if isinstance(metric_value, dict) else None
    annotation: dict[str, Any] = {
        "metric": metric_key,
        "value": mean,
        "source": "stage14",
        "evidence_digest": _digest_file(summary_path),
    }
    # P-094 / D-3: a missing count must never be reported as ``n=1`` (a
    # fabricated sample size); omit the field like ``ci`` does.
    if isinstance(count, int) and count > 0:
        annotation["n"] = int(count)
    condition = _match_condition(statement, prepared_conditions)
    if condition is not None:
        data = conditions.get(condition)
        if isinstance(data, dict):
            annotation["condition"] = condition
            cond_metrics = data.get("metrics")
            cond_value = None
            if isinstance(cond_metrics, dict):
                raw_value = cond_metrics.get(metric_key)
                if raw_value is None:
                    raw_value = cond_metrics.get(metric_key.rsplit("/", 1)[-1])
                cond_value = _as_float(raw_value)
            if cond_value is not None:
                annotation["value"] = cond_value
            seeds = data.get("n_seeds")
            if isinstance(seeds, int) and seeds > 0:
                annotation["n"] = seeds
            low = _as_float(data.get("ci95_low"))
            high = _as_float(data.get("ci95_high"))
            if low is not None and high is not None:
                annotation["ci"] = [low, high]
    return annotation


def annotations_from_stage14(run_dir: Path) -> dict[str, dict]:
    """Bind Stage 9 claims to Stage 14 metrics and write the annotation table."""
    run_dir = Path(run_dir)
    claims = _read_claims(run_dir / "stage-09" / "claims.jsonl", strict=True)
    summary_path = _live_or_latest(run_dir, "stage-14", "experiment_summary.json")
    metrics: Mapping[str, Any] = {}
    conditions: Mapping[str, Any] = {}
    if summary_path is not None:
        summary = _read_json(summary_path, {})
        if isinstance(summary, dict):
            raw_metrics = summary.get("metrics_summary")
            metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
            raw_conditions = summary.get("condition_summaries")
            conditions = raw_conditions if isinstance(raw_conditions, dict) else {}
    annotations: dict[str, dict] = {}
    prepared_metrics = _prepare_metric_names(metrics)
    prepared_conditions = _prepare_condition_names(conditions)
    for claim in claims:
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not _CLAIM_ID_RE.fullmatch(claim_id):
            continue
        if summary_path is None:
            continue
        annotation = _annotation_for(
            claim,
            metrics,
            conditions,
            summary_path,
            prepared_metrics=prepared_metrics,
            prepared_conditions=prepared_conditions,
        )
        if annotation is not None:
            annotation["evidence_locator"] = (
                summary_path.resolve().relative_to(run_dir.resolve()).as_posix()
            )
            annotations[claim_id] = annotation
    external = _read_json(run_dir / "annotations.external.json", {})
    if isinstance(external, dict):
        for claim_id, entry in external.items():
            if isinstance(entry, dict):
                override = dict(entry)
                override["source"] = "external"
                annotations[str(claim_id)] = override
    # P-094 / D-4: annotations always land in the live ``stage-14`` directory
    # even when the summary was read from a versioned dir, so Stage 20/23 (and
    # ``verify_claim_digests``) never silently miss them. The locator still
    # points at the summary actually read.
    _write_json(run_dir / "stage-14" / ANNOTATIONS_NAME, annotations)
    return annotations


# ---------------------------------------------------------------- markers
def _heading_ref(heading: str) -> str:
    text = heading.strip().strip("#").strip()
    numbered = _NUMBERED_HEADING_RE.match(text)
    if numbered:
        return "§" + numbered.group(1)
    return "§" + text if text else "§Preamble"


def _strip_inline_code(line: str) -> str:
    """Remove inline code spans; a dangling backtick hides the rest of the line.

    P-094 / O-3: an unclosed inline span is code until end of line, so text
    after the last unmatched backtick is dropped (single-direction: only
    removes candidate markers).
    """
    cleaned = _INLINE_CODE_RE.sub("", line)
    if cleaned.count("`") % 2 == 1:
        cleaned = cleaned[: cleaned.rfind("`")]
    return cleaned


def extract_claim_markers(text: str) -> dict[str, list[str]]:
    """Map ``[c-xxxxxxxx]`` to the nearest preceding Markdown heading.

    P-085 / D-1: fenced blocks and inline code spans are examples, not
    citations, so they are skipped. Headings apply to following lines only
    (a heading never re-attributes an earlier line).
    P-094 / D-6: markers are matched case-insensitively and keyed lowercase.
    P-094 / O-2: 4-space indented code blocks are examples too and are
    skipped (a blank line does not close the block; a non-blank line with
    less indentation does). Fence handling keeps P-085 semantics and runs
    before the indented-block state.
    """
    markers: dict[str, list[str]] = {}
    current = "§Preamble"
    in_fence = False
    in_indent = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue                     # blank lines never close an indented block
        if in_fence:
            if _FENCE_RE.match(raw):
                in_fence = False
            continue
        if _FENCE_RE.match(raw):
            in_fence = True
            in_indent = False
            continue
        if _INDENT_CODE_RE.match(raw):
            in_indent = True
            continue
        in_indent = False
        heading = _HEADING_RE.match(line)
        if heading:
            current = _heading_ref(heading.group(1))
            continue
        cleaned = _strip_inline_code(raw)
        for claim_id in CLAIM_MARKER_RE.findall(cleaned):
            refs = markers.setdefault(claim_id.lower(), [])
            if current not in refs:
                refs.append(current)
    return markers


# ---------------------------------------------------------------- export
def _load_decisions(run_dir: Path) -> dict[str, dict]:
    payload = _read_json(run_dir / "stage-20" / "claim_gate.json", {})
    if not isinstance(payload, dict):
        raise ValueError("claim_gate.json is not an object")
    decisions = payload.get("decisions", {})
    if not isinstance(decisions, dict):
        raise ValueError("claim_gate.json decisions is not an object")
    return {
        str(claim_id): dict(entry)
        for claim_id, entry in decisions.items()
        if isinstance(entry, dict)
    }


def _paper_text(run_dir: Path) -> str:
    # P-094 / D-5: the revised draft (Stage 19) is always newer than the
    # Stage 17 draft, so it must win when the final paper is missing.
    for relative in (
        "stage-22/paper_final.md",
        "stage-19/paper_revised.md",
        "stage-17/paper_draft.md",
    ):
        path = run_dir / relative
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return ""


def _claim_prompt_version(run_dir: Path) -> str:
    """P-089/A3-7: read the Stage 17 prompt version used for claim generation."""
    path = run_dir / "stage-17" / "claim_prompt_versions.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(data.get("prompt_version", "")) if isinstance(data, dict) else ""


def export_claim_labels(run_dir: Path) -> dict:
    """Write the publishable claim export; return claims plus trace errors."""
    run_dir = Path(run_dir)
    decisions = _load_decisions(run_dir)
    markers = extract_claim_markers(_paper_text(run_dir))
    prompt_version = _claim_prompt_version(run_dir)
    claims: dict[str, dict] = {}
    errors: list[dict] = []
    for claim_id in sorted(decisions):
        decision = decisions[claim_id]
        if not bool(decision.get("deliverable")):
            if claim_id in markers:
                errors.append({"claim_id": claim_id, "reason": "unpublished_claim_cited"})
            continue
        status = decision.get("status")
        entry = {
            "status": status,
            "citation_label": status,
            "paragraph_refs": list(markers.get(claim_id, [])),
            "deliverable": True,
            "cap_reasons": list(decision.get("cap_reasons") or []),
        }
        if prompt_version:
            entry["prompt_version"] = prompt_version
        claims[claim_id] = entry
    for claim_id in markers:
        if claim_id not in decisions:
            errors.append({"claim_id": claim_id, "reason": "unknown_claim_marker"})
    _write_json(run_dir / "stage-22" / EXPORT_NAME, claims)
    return {"claims": claims, "errors": errors}


# ---------------------------------------------------------------- verify
def _error(code: str, claim_id: str | None, field: str, detail: str) -> dict:
    return {"code": code, "claim_id": claim_id, "field": field, "detail": detail}


def verify_claim_trace(run_dir: Path, *, require_export: bool = False) -> dict:
    """Compare Stage 20 decisions, Stage 22 export and Stage 23 audit."""
    run_dir = Path(run_dir)
    errors: list[dict] = []
    try:
        decisions = _load_decisions(run_dir)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "checked": 0,
            "errors": [
                _error(E_CLAIM_TRACE_MISMATCH, None, "claim_gate", f"claim_gate_unreadable: {exc}")
            ],
        }
    if not decisions:
        return {"ok": True, "checked": 0, "errors": []}
    export_path = run_dir / "stage-22" / EXPORT_NAME
    export: dict[str, dict] | None
    if export_path.is_file():
        try:
            raw_export = _read_json(export_path, {})
        except (OSError, ValueError) as exc:
            return {
                "ok": False,
                "checked": 0,
                "errors": [
                    _error(
                        E_CLAIM_TRACE_MISMATCH,
                        None,
                        "claim_export",
                        f"claim_export_unreadable: {exc}",
                    )
                ],
            }
        export = raw_export if isinstance(raw_export, dict) else {}
    else:
        export = None
        if require_export:
            errors.append(
                _error(E_CLAIM_TRACE_MISMATCH, None, "claim_export", "claim_export_missing")
            )
    audit: dict[str, dict] | None = None
    consistency_path = run_dir / "stage-23" / "claim_consistency.json"
    if consistency_path.is_file():
        try:
            consistency = _read_json(consistency_path, {})
            raw_audit = consistency.get("audit") if isinstance(consistency, dict) else None
            audit = raw_audit if isinstance(raw_audit, dict) else {}
        except (OSError, ValueError) as exc:
            errors.append(
                _error(
                    E_CLAIM_TRACE_MISMATCH,
                    None,
                    "claim_consistency",
                    f"claim_consistency_unreadable: {exc}",
                )
            )
    checked = 0
    for claim_id, decision in sorted(decisions.items()):
        checked += 1
        deliverable = bool(decision.get("deliverable"))
        if not deliverable:
            if export is not None and claim_id in export:
                errors.append(
                    _error(E_CLAIM_TRACE_MISMATCH, claim_id, "claim_export", "unpublished_claim_exported")
                )
            continue
        if export is not None:
            entry = export.get(claim_id)
            if not isinstance(entry, dict):
                errors.append(
                    _error(E_CLAIM_TRACE_MISMATCH, claim_id, "claim_export", "claim_export_missing_entry")
                )
            else:
                if entry.get("status") != decision.get("status"):
                    errors.append(
                        _error(E_CLAIM_TRACE_MISMATCH, claim_id, "status", "status_mismatch")
                    )
                if list(entry.get("cap_reasons") or []) != list(decision.get("cap_reasons") or []):
                    errors.append(
                        _error(E_CLAIM_TRACE_MISMATCH, claim_id, "cap_reasons", "cap_reasons_mismatch")
                    )
        if audit and claim_id in audit:
            audit_entry = audit.get(claim_id)
            if isinstance(audit_entry, dict) and audit_entry.get("status") != decision.get("status"):
                errors.append(
                    _error(E_CLAIM_TRACE_MISMATCH, claim_id, "audit", "audit_status_mismatch")
                )
    if export is not None:
        for claim_id in sorted(set(export) - set(decisions)):
            errors.append(
                _error(E_CLAIM_TRACE_MISMATCH, claim_id, "claim_export", "orphan_export_claim")
            )
        markers = extract_claim_markers(_paper_text(run_dir))
        for claim_id in sorted(set(markers) - set(export)):
            errors.append(
                _error(E_CLAIM_TRACE_MISMATCH, claim_id, "paragraph_refs", "claim_marker_not_exported")
            )
    return {"ok": not errors, "checked": checked, "errors": errors}


def verify_claim_digests(
    run_dir: Path, *, annotations: Mapping[str, Mapping] | None = None
) -> dict:
    """Recompute evidence digests for local-file evidence only."""
    run_dir = Path(run_dir)
    errors: list[dict] = []
    checked = 0
    skipped = 0
    if annotations is None:
        path = run_dir / "stage-14" / ANNOTATIONS_NAME
        try:
            raw = _read_json(path, {})
        except (OSError, ValueError) as exc:
            return {
                "ok": False,
                "checked": 0,
                "skipped": 0,
                "errors": [
                    _error(
                        E_CLAIM_DIGEST_MISMATCH,
                        None,
                        "claim_annotations",
                        f"claim_annotations_unreadable: {exc}",
                    )
                ],
            }
        annotations = raw if isinstance(raw, Mapping) else {}
    for claim_id, annotation in sorted(annotations.items()):
        if not isinstance(annotation, Mapping):
            errors.append(_error(E_CLAIM_DIGEST_MISMATCH, str(claim_id), "annotation", "not_object"))
            continue
        locator = annotation.get("evidence_locator")
        if not locator and annotation.get("source") == "stage14":
            locator = "stage-14/experiment_summary.json"
        declared = annotation.get("evidence_digest")
        if not locator or not declared:
            skipped += 1
            continue
        path = run_dir / str(locator)
        if not path.is_file():
            errors.append(_error(E_CLAIM_DIGEST_MISMATCH, str(claim_id), "evidence_locator", "evidence_missing"))
            continue
        checked += 1
        actual = _digest_file(path)
        if not _same_digest(declared, actual):
            errors.append(_error(E_CLAIM_DIGEST_MISMATCH, str(claim_id), "evidence_digest", "digest_mismatch"))
    claims_path = run_dir / "stage-20" / "claims.jsonl"
    if not claims_path.is_file():
        claims_path = run_dir / "stage-09" / "claims.jsonl"
    for claim in _read_claims(claims_path, strict=False):
        claim_id = str(claim.get("claim_id"))
        evidence = claim.get("evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            if item.get("kind") == "pointer":
                skipped += 1
                continue
            locator = item.get("locator")
            declared = item.get("digest")
            if not declared:
                continue
            if not isinstance(locator, str) or not locator.strip():
                skipped += 1
                continue
            path = run_dir / locator
            if not path.is_file():
                skipped += 1
                continue
            checked += 1
            actual = _digest_file(path)
            if not _same_digest(declared, actual):
                errors.append(_error(E_CLAIM_DIGEST_MISMATCH, claim_id, "evidence_digest", "digest_mismatch"))
    return {"ok": not errors, "checked": checked, "skipped": skipped, "errors": errors}
