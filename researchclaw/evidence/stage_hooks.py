"""Pipeline hooks for ClaimRecord (Stage 9/20/23, M4)."""
from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .claim_policy import audit_claim, build_claim_records, evaluate_claim


class ClaimStreamError(RuntimeError):
    """Raised when a claim/gate artifact cannot be read without losing records."""


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a sibling temp file + os.replace (D-2: never truncate in place)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _write_json(path: Path, payload: dict) -> None:
    _atomic_write_text(
        Path(path), json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def _read_json(path: Path, default: Any) -> Any:
    """Missing file -> default; unreadable/corrupt file -> fail closed (D-2)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimStreamError(f"{path}: unreadable JSON: {exc}") from exc


def _write_claims(path: Path, claims: list[dict]) -> None:
    _atomic_write_text(
        Path(path),
        "".join(json.dumps(claim, ensure_ascii=False) + "\n" for claim in claims),
    )


def write_stage9_claims(
    stage_dir: Path, hypotheses_text: str, plan: Mapping[str, Any] | None = None
) -> tuple[str, ...]:
    claims = build_claim_records(hypotheses_text, plan)
    _write_claims(Path(stage_dir) / "claims.jsonl", claims)
    return ("claims.jsonl",)


def _claims_candidates(run_dir: Path, stage_prefix: str) -> list[Path]:
    """Live (non-versioned) dir first, then versioned dirs newest-first (D-1)."""
    candidates: list[tuple[int, int, str, Path]] = []
    for path in Path(run_dir).glob(f"{stage_prefix}*/claims.jsonl"):
        if not path.is_file():
            continue
        name = path.parent.name
        _base, sep, version_text = name.rpartition("_v")
        version = int(version_text) if sep and version_text.isdigit() else -1
        # R14-2: non-versioned dirs are the live attempt; versions are history.
        candidates.append((1 if version >= 0 else 0, -version, name, path))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in candidates]


def load_claims(run_dir: Path, stage_prefix: str = "stage-09") -> list[dict]:
    candidates = _claims_candidates(Path(run_dir), stage_prefix)
    if not candidates:
        return []
    path = candidates[0]
    claims: list[dict] = []
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            # D-2: dropping a bad line would silently hide blocked claims.
            raise ClaimStreamError(
                f"{path}:{line_no}: invalid claim JSON: {exc.msg}"
            ) from exc
        if not isinstance(item, dict):
            raise ClaimStreamError(f"{path}:{line_no}: claim line is not an object")
        claims.append(item)
    return claims


def _annotations(run_dir: Path) -> dict[str, str]:
    """Merge annotations: stage-14 table < legacy root < external overrides."""
    result: dict[str, str] = {}
    stage14_path = Path(run_dir) / "stage-14" / "claim_annotations.json"
    stage14 = _read_json(stage14_path, {})
    if not isinstance(stage14, dict):
        raise ClaimStreamError(f"{stage14_path}: annotations payload is not an object")
    for key, value in stage14.items():
        if isinstance(value, dict):
            result[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    path = Path(run_dir) / "annotations.json"
    data = _read_json(path, {})
    if not isinstance(data, dict):
        raise ClaimStreamError(f"{path}: annotations payload is not an object")
    for key, value in data.items():
        if isinstance(value, (str, int, float)):
            result[str(key)] = str(value)
    external_path = Path(run_dir) / "annotations.external.json"
    external = _read_json(external_path, {})
    if not isinstance(external, dict):
        raise ClaimStreamError(f"{external_path}: annotations payload is not an object")
    for key, value in external.items():
        if isinstance(value, dict):
            result[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result


def _claim_key(claim: Mapping[str, Any], index: int) -> str:
    claim_id = claim.get("claim_id")
    if isinstance(claim_id, str) and claim_id:
        return claim_id
    return f"<invalid-{index + 1}>"


def run_stage20_gate(stage_dir: Path, run_dir: Path) -> dict:
    stage_dir = Path(stage_dir)
    run_dir = Path(run_dir)
    claims = load_claims(run_dir)
    annotations = _annotations(run_dir)
    decisions: dict[str, dict] = {}
    updated: list[dict] = []
    blocked: list[dict] = []
    missing_annotation: list[str] = []
    downgraded = False
    claim_keys = [_claim_key(claim, index) for index, claim in enumerate(claims)]
    duplicate_keys = sorted(
        key for key, count in Counter(claim_keys).items() if count > 1
    )
    for index, claim in enumerate(claims):
        claim_key = claim_keys[index]
        decision = evaluate_claim(claim, annotations.get(claim_key))
        updated.append(decision.claim)
        decisions[claim_key] = decision.as_dict()
        downgraded = downgraded or decision.downgraded
        if "missing_annotation" in decision.blocked_reasons:
            missing_annotation.append(claim_key)
        if not decision.deliverable:
            blocked.append({
                "claim_id": claim_key,
                "status": decision.claim.get("status"),
                "reasons": list(decision.blocked_reasons),
                "problems": list(decision.problems),
            })
    # P-065 D-4: duplicate claim ids collapse the decisions mapping; block the
    # whole gate instead of letting one decision stand in for several claims.
    for claim_key in duplicate_keys:
        blocked.append({
            "claim_id": claim_key,
            "status": None,
            "reasons": ["duplicate_claim_id"],
            "problems": ["duplicate_claim_id"],
        })
    _write_claims(stage_dir / "claims.jsonl", updated)
    if blocked:
        verdict = "block"
    elif downgraded:
        verdict = "downgraded"
    else:
        verdict = "pass"
    payload = {
        "decision": verdict,
        "total": len(claims),
        "blocked": blocked,
        "missing_annotation": missing_annotation,
        "duplicate_claim_ids": duplicate_keys,
        "decisions": decisions,
    }
    _write_json(stage_dir / "claim_gate.json", payload)
    return {"blocked": bool(blocked), "verdict": verdict, "payload": payload}


def compare_claims(
    claims: list[dict],
    production: Mapping[str, Any],
    annotations: Mapping[str, str],
) -> dict:
    """Shared dual-plane comparison (Stage 23 + offline audit, M5).

    Re-evaluates every claim with the production kernel (``audit_claim``) and
    compares against the recorded production decisions. Diff reasons:
    ``missing_production_decision`` | ``status_mismatch`` |
    ``deliverable_mismatch`` | ``duplicate_claim_id`` |
    ``orphan_production_decision``.

    Claims without any production decision (resumed runs that started after
    Stage 20) are skipped, mirroring the in-pipeline semantics. Duplicate and
    orphan checks are collection-level integrity checks and always run, even
    when the per-claim loop is skipped (P-067 D-5).
    """
    diffs: list[dict] = []
    audit: dict[str, dict] = {}
    skipped = ""
    keys = [_claim_key(claim, index) for index, claim in enumerate(claims)]
    counts = Counter(keys)
    for key in sorted(key for key, count in counts.items() if count > 1):
        diffs.append({"claim_id": key, "reason": "duplicate_claim_id"})
    if claims and not production:
        skipped = "no_production_gate"
    else:
        for index, claim in enumerate(claims):
            claim_key = _claim_key(claim, index)
            decision = audit_claim(claim, annotations.get(claim_key))
            audit[claim_key] = {
                "status": decision.claim.get("status"),
                "deliverable": decision.deliverable,
            }
            prod = production.get(claim_key)
            if not isinstance(prod, dict):
                diffs.append({"claim_id": claim_key, "reason": "missing_production_decision"})
                continue
            if prod.get("status") != audit[claim_key]["status"]:
                diffs.append({
                    "claim_id": claim_key,
                    "reason": "status_mismatch",
                    "production": prod.get("status"),
                    "audit": audit[claim_key]["status"],
                })
            elif bool(prod.get("deliverable")) != audit[claim_key]["deliverable"]:
                diffs.append({
                    "claim_id": claim_key,
                    "reason": "deliverable_mismatch",
                    "production": prod.get("deliverable"),
                    "audit": audit[claim_key]["deliverable"],
                })
    # Symmetric check (P-065 D-1): a production decision without a claim is an
    # orphan and must be visible instead of silently ignored.
    for key in sorted(set(production) - set(keys)):
        prod = production[key]
        diffs.append({
            "claim_id": key,
            "reason": "orphan_production_decision",
            "production": prod.get("status") if isinstance(prod, dict) else None,
        })
    return {"diffs": diffs, "audit": audit, "skipped": skipped}


def _load_production_gate(run_dir: Path) -> dict:
    """Read stage-20/claim_gate.json; missing -> {}, corrupt -> fail closed."""
    gate_path = Path(run_dir) / "stage-20" / "claim_gate.json"
    gate = _read_json(gate_path, {})
    if not isinstance(gate, dict):
        raise ClaimStreamError(f"{gate_path}: gate payload is not an object")
    production = gate.get("decisions", {})
    if not isinstance(production, dict):
        raise ClaimStreamError(f"{gate_path}: decisions is not an object")
    return production


def run_stage23_consistency(
    stage_dir: Path, run_dir: Path, *, require_export: bool = False
) -> dict:
    stage_dir = Path(stage_dir)
    run_dir = Path(run_dir)
    claims = load_claims(run_dir, stage_prefix="stage-20")
    if not claims:
        claims = load_claims(run_dir)
    production = _load_production_gate(run_dir)
    annotations = _annotations(run_dir)
    result = compare_claims(claims, production, annotations)
    from .claim_spine import verify_claim_digests, verify_claim_trace

    payload = {
        "consistent": not result["diffs"],
        "checked": len(claims),
        "diffs": result["diffs"],
        "production": production,
        "audit": result["audit"],
    }
    if result["skipped"]:
        payload["skipped"] = result["skipped"]
    # Write the current audit view first so the trace check compares against
    # this run's Stage 23 payload rather than a previous one.
    _write_json(stage_dir / "claim_consistency.json", payload)
    payload["trace"] = verify_claim_trace(run_dir, require_export=require_export)
    payload["digests"] = verify_claim_digests(run_dir)
    _write_json(stage_dir / "claim_consistency.json", payload)
    return {"consistent": not result["diffs"], "payload": payload}
