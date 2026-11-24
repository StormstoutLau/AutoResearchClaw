"""Pipeline-as-skill manifest (P-146, design frozen in P-145).

Exports a successful run into a skill directory:

    <skill>/SKILL.md      # frontmatter: metadata.kind=pipeline, metadata.manifest=pipeline.json
    <skill>/pipeline.json # stages, tools, hashes, provenance

The manifest is inert: loading validates it, nothing executes.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

import yaml

from researchclaw.runtime.action_ledger import ActionLedger, hash_path
from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.skills.loader import load_skill_from_skillmd
from researchclaw.skills.schema import STAGE_NAME_TO_NUMBER

MANIFEST_NAME = "pipeline.json"
SKILL_NAME = "SKILL.md"
MANIFEST_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
KIND = "pipeline-skill"
SUCCESS_CRITERIA = ("run.completed", "no_stage_failed", "stage23.completed")


class ManifestExportError(ValueError):
    """Run cannot be exported (criteria unmet, chain broken, bad paths)."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _stage_of(event: Mapping[str, Any]) -> int | None:
    payload = event.get("payload") or {}
    value = payload.get("stage", event.get("stage"))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _relative_path(raw: str, run_dir: Path) -> str | None:
    """Manifest stores run-relative POSIX paths; anything outside is dropped."""
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = run_dir / candidate
        rel = candidate.resolve().relative_to(run_dir.resolve())
    except (OSError, ValueError):
        return None
    return rel.as_posix()


def _collect_stages(events: list[dict]) -> list[dict]:
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    attempts: dict[int, int] = {}
    for event in events:
        stage = _stage_of(event)
        if stage is None:
            continue
        kind = event.get("type")
        seq = int(event.get("seq", 0))
        if kind == "stage.started":
            attempts[stage] = attempts.get(stage, 0) + 1
            starts.setdefault(stage, seq)
        elif kind in ("stage.retried",):
            attempts[stage] = attempts.get(stage, 0) + 1
        elif kind == "stage.completed":
            ends[stage] = seq
    return [
        {
            "stage": stage,
            "name": _name_for(stage),
            "attempts": attempts.get(stage, 0) or 1,
            "event_seq": [starts.get(stage, ends[stage]), ends[stage]],
            "actions": [],
            "outputs": {},
        }
        for stage in sorted(ends)
    ]


def _name_for(stage: int) -> str:
    for name, number in STAGE_NAME_TO_NUMBER.items():
        if number == stage:
            return name
    return ""


def export_manifest(
    run_dir: str | Path,
    skill_dir: str | Path,
    *,
    name: str,
    description: str = "",
    repo_commit: str = "",
    tool_versions: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
) -> dict:
    """Export a successful run into ``skill_dir``; returns the manifest dict.

    ``config_path`` (P-148) adds a sanitized config snapshot and bumps the
    manifest to v2. Without it the export stays v1 (no config, no re-run).
    """
    run_dir = Path(run_dir).resolve()
    skill_dir = Path(skill_dir).resolve()
    log = EventLog(run_dir, run_dir.name)
    ok, message = log.verify_chain()
    if not ok:
        raise ManifestExportError("event chain invalid: %s" % message)
    events = log.read_all()
    if not any(e.get("type") == "run.completed" for e in events):
        raise ManifestExportError("run.completed missing")
    if any(e.get("type") == "stage.failed" for e in events):
        raise ManifestExportError("stage.failed present")
    stages = _collect_stages(events)
    if not any(node["stage"] == 23 for node in stages):
        raise ManifestExportError("stage 23 did not complete")
    if not name.startswith("pipeline-"):
        raise ManifestExportError("pipeline skill name must start with 'pipeline-'")

    actions = ActionLedger(run_dir, run_dir.name).read_all()
    stage_by_seq = {
        node["event_seq"][0]: node["stage"] for node in stages if node["event_seq"][0]
    }
    seqs = sorted(stage_by_seq)
    for action in actions:
        seq = action.get("event_seq_call")
        if not isinstance(seq, int):
            continue
        owner = None
        for start in seqs:
            if start <= seq:
                owner = stage_by_seq[start]
            else:
                break
        if owner is None:
            continue
        node = next(n for n in stages if n["stage"] == owner)
        node["actions"].append(str(action.get("action_id", "")))
        for raw, digest in (action.get("outputs") or {}).items():
            rel = _relative_path(raw, run_dir)
            if rel is not None and isinstance(digest, str):
                node["outputs"][rel] = digest

    env_keys = sorted({key for action in actions for key in (action.get("env") or {})})
    tool_names = sorted({str(action.get("tool", "")) for action in actions if action.get("tool")})
    versions = dict(tool_versions or {})
    tools = [{"name": t, "version": str(versions.get(t, ""))} for t in tool_names]

    readpoints = []
    summary = run_dir / "pipeline_summary.json"
    if summary.is_file():
        readpoints.append({
            "stage": 23,
            "artifact": "pipeline_summary.json",
            "digest": hash_path(summary),
        })

    body = {
        "manifest_version": 1,
        "kind": KIND,
        "name": name,
        "description": description,
        "created_at": _now_iso(),
        "arc": {
            "repo_commit": repo_commit,
            "stage_map": {str(k): v for k, v in STAGE_NAME_TO_NUMBER.items()},
        },
        "success": {
            "run_id": str((events[0] or {}).get("run_id", "")),
            "criteria": list(SUCCESS_CRITERIA),
            "completed_at": str(next(
                (e.get("ts", "") for e in reversed(events) if e.get("type") == "run.completed"), "")),
        },
        "stages": stages,
        "tools": tools,
        "env_keys": env_keys,
        "readpoints": readpoints,
    }
    if config_path is not None:
        from researchclaw.skills.config_sanitizer import write_sanitized_snapshot

        body["manifest_version"] = 2
        body["config"] = write_sanitized_snapshot(config_path, skill_dir)
    integrity = "sha256:" + _sha256_text(canonical_json(body))
    manifest = dict(body)
    manifest["integrity"] = {"algorithm": "sha256", "manifest_sha256": integrity}
    _atomic_write(skill_dir / MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    header = {
        "name": name,
        "description": description,
        "metadata": {"kind": "pipeline", "manifest": MANIFEST_NAME},
    }
    skill_md = "---\n%s\n---\n\n%s\n" % (
        yaml.safe_dump(header, sort_keys=False, allow_unicode=True).strip(),
        "Pipeline skill exported from run `%s`; inert until explicitly invoked." % run_dir.name,
    )
    _atomic_write(skill_dir / SKILL_NAME, skill_md)
    return manifest


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    stage_map: Mapping[str, int] | None = None,
    tool_versions: Mapping[str, str] | None = None,
    skill_dir: str | Path | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)``; errors are fail-closed."""
    errors: list[str] = []
    warnings: list[str] = []
    data = dict(manifest)
    version = data.get("manifest_version")
    if version not in SUPPORTED_VERSIONS:
        errors.append("manifest_version must be one of %s" % (SUPPORTED_VERSIONS,))
    if data.get("kind") != KIND:
        errors.append("kind must be %r" % KIND)

    integrity = data.get("integrity") or {}
    body = {k: v for k, v in data.items() if k != "integrity"}
    expected = "sha256:" + _sha256_text(canonical_json(body))
    if integrity.get("manifest_sha256") != expected:
        errors.append("manifest_sha256 mismatch")

    current = dict(stage_map or STAGE_NAME_TO_NUMBER)
    declared = (data.get("arc") or {}).get("stage_map") or {}
    if {str(k): str(v) for k, v in declared.items()} != {str(k): str(v) for k, v in current.items()}:
        errors.append("stage_map mismatch")

    stages = data.get("stages") or []
    numbers = [node.get("stage") for node in stages]
    if numbers != sorted(set(int(n) for n in numbers if isinstance(n, int))):
        errors.append("stages must be ascending and unique")
    for node in stages:
        stage = node.get("stage")
        if not isinstance(stage, int) or not 1 <= stage <= 23:
            errors.append("stage out of range: %r" % (stage,))
        for raw in (node.get("outputs") or {}):
            if Path(raw).is_absolute() or ".." in Path(raw).parts or ":" in raw:
                errors.append("output path must be relative: %r" % raw)

    tools = data.get("tools") or []
    if tool_versions is not None:
        current_tools = dict(tool_versions)
        for tool in tools:
            name = str(tool.get("name", ""))
            if name not in current_tools:
                errors.append("unknown tool: %r" % name)
            elif str(tool.get("version", "")) != str(current_tools[name]):
                warnings.append("tool version drift: %s (%s != %s)"
                                % (name, tool.get("version"), current_tools[name]))

    if version == 2:
        errors.extend(_validate_config(data, skill_dir))
    return errors, warnings


def _validate_config(data: Mapping[str, Any], skill_dir: str | Path | None) -> list[str]:
    """v2 must carry a sanitized config snapshot whose hash still matches."""
    from researchclaw.skills.config_sanitizer import SNAPSHOT_NAME

    errors: list[str] = []
    config = data.get("config")
    if not isinstance(config, dict):
        return ["config snapshot block is missing for manifest v2"]
    pointer = str(config.get("pointer", ""))
    path = Path(pointer)
    if not pointer or path.is_absolute() or ".." in path.parts:
        errors.append("config pointer must stay inside the skill directory")
        return errors
    if path.name != SNAPSHOT_NAME:
        errors.append("config pointer must reference %s" % SNAPSHOT_NAME)
    if skill_dir is not None:
        target = Path(skill_dir) / path
        if not target.is_file():
            errors.append("config snapshot missing: %s" % pointer)
        else:
            actual = hash_path(target)
            if actual != config.get("sha256"):
                errors.append("config snapshot hash mismatch")
    redacted = config.get("redacted_keys") or []
    if not isinstance(redacted, list):
        errors.append("config.redacted_keys must be a list")
    return errors


def load_pipeline_skill(skill_dir: str | Path) -> tuple[dict | None, list[str]]:
    """Load a pipeline skill via SKILL.md; returns ``(manifest, errors)``."""
    skill_dir = Path(skill_dir).resolve()
    skill = load_skill_from_skillmd(skill_dir / SKILL_NAME)
    if skill is None:
        return None, ["SKILL.md missing or invalid"]
    if skill.metadata.get("kind") != "pipeline":
        return None, ["SKILL.md metadata.kind is not 'pipeline'"]
    raw = skill.metadata.get("manifest") or MANIFEST_NAME
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None, ["manifest path must stay inside the skill directory"]
    manifest_path = skill_dir / path
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, ["manifest unreadable: %s" % exc]
    if not isinstance(data, dict):
        return None, ["manifest must be an object"]
    try:
        from researchclaw.tools.registry import load_registry

        registry = load_registry()
        tool_versions = {tool.name: str(getattr(tool, "version", "")) for tool in registry.tools}
    except Exception:  # noqa: BLE001 - registry is optional for pure discovery
        tool_versions = None
    errors, _warnings = validate_manifest(data, tool_versions=tool_versions,
                                         skill_dir=skill_dir)
    return (None, errors) if errors else (data, [])
