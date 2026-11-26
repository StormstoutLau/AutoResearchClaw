"""Stage 10 evidence gates: blueprint vs. delivered artifacts (B-32 M2).

M1 made an existing blueprint parse; M2 makes Stage 10 answer the next
question: *did the code we are about to ship actually implement it?*  The
field failure was a blueprint declaring five files, six monitor classes and
an AUROC metric, while Stage 10 delivered ``config.py`` plus a config
self-check ``main.py`` and still reported DONE.

The gates here are deliberately read-only and side-effect free apart from
writing ``stage-10/codegen_evidence.json``.  They never repair artefacts:
a failing gate means the stage must fail, not that we should guess.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from researchclaw.utils.paths import safe_join

EVIDENCE_NAME = "codegen_evidence.json"
BLUEPRINT_NAME = "architecture_spec.yaml"

_METRIC_DEF_RE = re.compile(r"METRIC_DEF:\s*([A-Za-z0-9_.\-]+)")
_METRIC_KEYS = ("primary_metric", "metric", "metric_name")
_DATA_SOURCE_KEYS = ("data_source", "dataset_source")
_SOURCE_KEYS = ("source", "sources", "provider")
_FILE_NAME_KEYS = ("name", "path", "filename", "file")
_CONFIG_SUFFIXES = ("Config", "Settings", "Params")
_NON_COMPUTE_NAMES = {"main", "cli", "parse_args", "get_config", "load_config"}
_NON_COMPUTE_PREFIXES = ("check_", "validate_", "test_", "assert_")


@dataclass(frozen=True)
class EvidenceFailure:
    """One blocking reason why Stage 10 must not report DONE."""

    code: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass
class EvidenceReport:
    failures: list[EvidenceFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    synthetic_data: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failures": [f.as_dict() for f in self.failures],
            "warnings": list(self.warnings),
            "synthetic_data": self.synthetic_data,
            "at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Blueprint parsing
# ---------------------------------------------------------------------------


def load_blueprint(stage_dir: Path) -> dict[str, Any] | None:
    """Load ``architecture_spec.yaml`` if it parses to a mapping."""
    path = stage_dir / BLUEPRINT_NAME
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable blueprint is "unavailable"
        return None
    return data if isinstance(data, dict) else None


def _as_text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _find_metric(node: Any, depth: int = 0) -> str:
    """Recursively look for a metric name in the blueprint (depth ≤ 3)."""
    if depth > 3 or not isinstance(node, dict):
        return ""
    for key in _METRIC_KEYS:
        found = _as_text(node.get(key))
        if found:
            return found
    for value in node.values():
        if isinstance(value, dict):
            found = _find_metric(value, depth + 1)
            if found:
                return found
    return ""


def _collect_sources(node: Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            found.extend(str(v).strip() for v in value if str(v).strip())
        elif isinstance(value, dict):
            found.extend(str(v).strip() for v in value.values()
                         if isinstance(v, str) and v.strip())
    return found


def _find_data_sources(node: Any, depth: int = 0) -> list[str]:
    """Collect declared data sources (``data.source`` / ``data_source``)."""
    if depth > 3 or not isinstance(node, dict):
        return []
    found = _collect_sources(node, _DATA_SOURCE_KEYS)
    for container in ("data", "dataset", "input"):
        child = node.get(container)
        if isinstance(child, dict):
            found.extend(_collect_sources(child, _SOURCE_KEYS))
            found.extend(_find_data_sources(child, depth + 1))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    found.extend(_collect_sources(item, _SOURCE_KEYS))
                    found.extend(_find_data_sources(item, depth + 1))
    return found


def _declared_files(blueprint: Mapping[str, Any]) -> list[tuple[str, bool]]:
    """Blueprint files that are required, as ``(name, optional)`` tuples.

    Only entries carrying ``generation_order`` participate, matching the
    design's "the gate applies to ordered files only" rule.
    """
    entries = blueprint.get("files")
    if isinstance(entries, dict):
        entries = [
            {**_entry, "name": _entry.get("name") or str(key)}
            if isinstance(_entry, dict) else {"name": str(key)}
            for key, _entry in entries.items()
        ]
    if not isinstance(entries, list):
        return []
    out: list[tuple[str, bool]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "generation_order" not in entry:
            continue
        name = next(
            (_as_text(entry.get(key)) for key in _FILE_NAME_KEYS
             if _as_text(entry.get(key))),
            "",
        )
        if not name:
            continue
        out.append((name, bool(entry.get("optional"))))
    return out


def _basename(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip()


# ---------------------------------------------------------------------------
# Individual gates
# ---------------------------------------------------------------------------


def check_declared_files(
    blueprint: Mapping[str, Any], files: Mapping[str, str],
) -> list[EvidenceFailure]:
    """Every non-optional blueprint file must exist in the delivery."""
    delivered = {_basename(name) for name in files}
    missing = sorted(
        name for name, optional in _declared_files(blueprint)
        if not optional and _basename(name) not in delivered
    )
    if not missing:
        return []
    return [EvidenceFailure(
        code="blueprint_files_missing",
        detail="blueprint declares ordered files that were not delivered: "
        + ", ".join(missing),
    )]


def entrypoint_metric_name(code: str) -> str:
    match = _METRIC_DEF_RE.search(str(code or ""))
    return match.group(1) if match else ""


def normalize_metric(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", str(name or "").strip().lower())


def check_metric_consistency(
    declared: str, files: Mapping[str, str],
) -> list[EvidenceFailure]:
    """The entrypoint's ``METRIC_DEF`` must name the declared metric."""
    if not declared:
        return []
    main_code = files.get("main.py", "")
    actual = entrypoint_metric_name(main_code)
    if not actual:
        return [EvidenceFailure(
            code="metric_not_printed",
            detail="main.py does not print a parseable METRIC_DEF line",
        )]
    if normalize_metric(actual) != normalize_metric(declared):
        return [EvidenceFailure(
            code="metric_mismatch",
            detail=f"blueprint metric {declared!r} != METRIC_DEF {actual!r}",
        )]
    return []


def check_data_source(
    blueprint: Mapping[str, Any], files: Mapping[str, str],
) -> tuple[list[str], bool]:
    """Return ``(warnings, synthetic_data)`` for declared data sources."""
    sources = _find_data_sources(blueprint)
    if not sources:
        return [], False
    blob = "\n".join(files.values()).lower()
    warnings = [
        f"declared data source {source!r} not found in generated code"
        for source in sources if source.lower() not in blob
    ]
    if not warnings:
        return [], False
    synthetic = bool(re.search(r"np\.random|numpy\.random|random\.(?:rand|uniform|normal)",
                               blob))
    return warnings, synthetic


def _is_config_name(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _CONFIG_SUFFIXES)


def _is_non_compute_name(name: str) -> bool:
    return name in _NON_COMPUTE_NAMES or name.startswith(_NON_COMPUTE_PREFIXES)


def count_compute_units(files: Mapping[str, str]) -> int:
    """Count top-level classes/functions that are not configuration wrappers."""
    total = 0
    for name, code in files.items():
        if not name.endswith(".py") or not code:
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if not _is_config_name(node.name):
                    total += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not _is_non_compute_name(node.name) and not _is_config_name(node.name):
                    total += 1
    return total


def check_compute_presence(files: Mapping[str, str]) -> list[EvidenceFailure]:
    """A config-only package passes ``returncode == 0`` and proves nothing."""
    if count_compute_units(files) > 0:
        return []
    return [EvidenceFailure(
        code="no_compute_unit",
        detail="no non-Config class or function found — delivery looks like "
        "a configuration self-check, not an experiment",
    )]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def evaluate_stage10_evidence(
    *,
    stage_dir: Path,
    files: Mapping[str, str],
    metric: str,
) -> EvidenceReport:
    """Run all M2 gates and return the aggregate report."""
    report = EvidenceReport()
    blueprint = load_blueprint(stage_dir)
    if blueprint is None:
        report.warnings.append(
            "blueprint unavailable — file/metric/data gates skipped (see "
            "codegen_decision.json)"
        )
    else:
        report.failures.extend(check_declared_files(blueprint, files))
        declared_metric = _find_metric(blueprint) or str(metric or "")
        report.failures.extend(check_metric_consistency(declared_metric, files))
        warnings, synthetic = check_data_source(blueprint, files)
        report.warnings.extend(warnings)
        report.synthetic_data = synthetic
    report.failures.extend(check_compute_presence(files))
    return report


def write_evidence_report(stage_dir: Path, report: EvidenceReport) -> Path:
    """Persist the report; failures stay readable after the stage fails."""
    path = safe_join(stage_dir, EVIDENCE_NAME)
    path.write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
