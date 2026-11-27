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
import io
import json
import re
import tokenize
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from researchclaw.utils.paths import safe_join

EVIDENCE_NAME = "codegen_evidence.json"
BLUEPRINT_NAME = "architecture_spec.yaml"

_METRIC_DEF_MARK = "METRIC_DEF:"
# B-34 (F-3): stop only at the format separators (whitespace, ``|``, ``;``).
# The previous class also excluded ``)`` and ``]``, so names such as
# ``auroc(delta)`` and ``hit@k[5]`` were cut in half and failed the gate.
_METRIC_DEF_RE = re.compile(r"METRIC_DEF:\s*([^\s|;]+)")
_METRIC_KEYS = ("primary_metric", "metric", "metric_name")
_DATA_SOURCE_KEYS = ("data_source", "dataset_source")
_SOURCE_KEYS = ("source", "sources", "provider")
_FILE_NAME_KEYS = ("name", "path", "filename", "file")
_CONFIG_SUFFIXES = ("Config", "Settings", "Params")
_NON_COMPUTE_NAMES = {"main", "cli", "parse_args", "get_config", "load_config"}
_NON_COMPUTE_PREFIXES = ("check_", "validate_", "test_", "assert_")
# A continuation line such as ``nested: value`` (or ``key:``) means the item
# is a mapping, not prose (P-202 F-3).
_MAPPING_LINE_RE = re.compile(r"^[^\s:#][^:]*:(?:\s|$)")
_MAX_SOURCE_DEPTH = 4


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


def _collect_sources(
    node: Mapping[str, Any], keys: tuple[str, ...], depth: int = 0,
) -> list[str]:
    """Collect leaf strings under ``keys``.

    P-202 (F-2): containers are walked down to their leaves instead of being
    stringified, so a ``sources: [{provider: x}]`` declaration yields ``"x"``
    rather than ``"{'provider': 'x'}"``.
    """
    found: list[str] = []
    for key in keys:
        found.extend(_leaf_strings(node.get(key), depth))
    return found


def _leaf_strings(value: Any, depth: int = 0) -> list[str]:
    """Leaf strings of a nested YAML/JSON value (depth-capped)."""
    if depth > _MAX_SOURCE_DEPTH:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_leaf_strings(item, depth + 1))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_leaf_strings(item, depth + 1))
        return out
    return []


def _find_data_sources(node: Any, depth: int = 0) -> list[str]:
    """Collect declared data sources (``data.source`` / ``data_source``)."""
    if depth > 3 or not isinstance(node, dict):
        return []
    found = _collect_sources(node, _DATA_SOURCE_KEYS, depth)
    for container in ("data", "dataset", "input"):
        child = node.get(container)
        if isinstance(child, dict):
            found.extend(_collect_sources(child, _SOURCE_KEYS, depth + 1))
            found.extend(_find_data_sources(child, depth + 1))
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    found.extend(_collect_sources(item, _SOURCE_KEYS, depth + 1))
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


_SYMBOL_KEYS = ("symbols", "required_symbols", "classes", "functions")


def _declared_symbols(
    blueprint: Mapping[str, Any],
) -> list[tuple[str, str]]:
    """Blueprint-declared ``(file, symbol)`` pairs (B-34 M4).

    Only entries that also carry ``generation_order`` participate, matching
    ``_declared_files``.  ``symbols``/``required_symbols`` accept plain
    strings or ``{name: ...}`` mappings; ``classes``/``functions`` accept
    strings or ``{name: ...}`` too, so all four spellings work.
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
    out: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "generation_order" not in entry:
            continue
        file_name = _basename(next(
            (_as_text(entry.get(key)) for key in _FILE_NAME_KEYS
             if _as_text(entry.get(key))),
            "",
        ))
        if not file_name:
            continue
        for key in _SYMBOL_KEYS:
            value = entry.get(key)
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                if isinstance(item, str):
                    symbol = item.strip()
                elif isinstance(item, Mapping):
                    symbol = _as_text(item.get("name"))
                else:
                    symbol = ""
                if symbol:
                    out.append((file_name, symbol))
    return out


def _defined_names(code: str) -> set[str]:
    """Top-level and nested class/function names defined by one module."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def check_symbol_contract(
    blueprint: Mapping[str, Any], files: Mapping[str, str],
) -> list[EvidenceFailure]:
    """Declared symbols of a delivered file must exist in that file's AST.

    A file-level gate cannot tell "module delivered" from "module delivered
    but hollow"; this is the cheap structural check that closes that gap.
    Missing files are left to ``check_declared_files`` so a single root cause
    is not reported twice.
    """
    declared = _declared_symbols(blueprint)
    if not declared:
        return []
    delivered = {_basename(name): code for name, code in files.items()}
    missing: list[str] = []
    for file_name, symbol in declared:
        code = delivered.get(file_name)
        if code is None:
            continue
        if symbol not in _defined_names(code):
            missing.append(f"{file_name}:{symbol}")
    if not missing:
        return []
    return [EvidenceFailure(
        code="blueprint_symbols_missing",
        detail="declared symbols not found in the delivered code: "
        + ", ".join(sorted(set(missing))),
    )]


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


def _metric_from_text(text: str) -> str:
    match = _METRIC_DEF_RE.search(str(text or ""))
    return match.group(1).rstrip(".,;:'\"") if match else ""


def entrypoint_metric_name(code: str) -> str:
    """Metric name printed by ``main.py``.

    P-202 (F-1): the previous version regex-scanned the whole file, so a
    commented-out or docstring mention could hijack the gate.  Prefer the
    literal actually passed to ``print(...)`` (AST drops comments and keeps
    docstrings out of ``Call.args``), then fall back to a line scan that
    skips comment lines.
    """
    text = str(code or "")
    if not text.strip():
        return ""
    tree: ast.Module | None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found = _metric_from_text(arg.value)
                    if found:
                        return found
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        found = _metric_from_text(line)
        if found:
            return found
    return ""


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


def _strip_comments(text: str) -> str:
    """Drop ``#`` comments while leaving code and string literals intact.

    B-34 (F-1/F-5): comments are a lexical category, so a source name that
    only appears in a comment must not satisfy the data-source gate, and
    ``np.random`` mentioned in a comment must not mark the delivery as
    synthetic.  The text is returned unchanged whenever it cannot be
    tokenised — a gate must not change behaviour just because a file does
    not parse (the entrypoint would already fail elsewhere).
    """
    source = str(text or "")
    if not source.strip():
        return source
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source
    columns: dict[int, int] = {}
    for token in tokens:
        if token.type == tokenize.COMMENT:
            row, col = token.start
            columns[row] = min(col, columns.get(row, col))
    if not columns:
        return source
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    for index, line in enumerate(lines, start=1):
        col = columns.get(index)
        if col is None:
            out.append(line)
            continue
        out.append(line[:col].rstrip() + ("\n" if line.endswith("\n") else ""))
    return "".join(out)


def check_data_source(
    blueprint: Mapping[str, Any], files: Mapping[str, str],
) -> tuple[list[str], bool]:
    """Return ``(warnings, synthetic_data)`` for declared data sources."""
    sources = _find_data_sources(blueprint)
    if not sources:
        return [], False
    blob = "\n".join(_strip_comments(code) for code in files.values()).lower()
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


def _class_has_behavior(node: ast.ClassDef) -> bool:
    """True when a class defines a method with a non-trivial body.

    B-34 (F-2): a suffix alone does not make a class configuration.  A
    ``KernelConfig`` that implements ``compute`` is real compute, while a
    declarative class only carries fields, docstrings and ``pass`` bodies.
    """
    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for stmt in item.body:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue  # docstring
            return True
    return False


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
                if _is_config_name(node.name) and not _class_has_behavior(node):
                    continue
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


def collect_delivered(
    files: Mapping[str, str], delivered_dir: Path | None = None,
) -> dict[str, str]:
    """Files the stage is about to ship.

    P-202 (N-1): the gate used to read only the in-memory mapping, so a stale
    ``experiment/main.py`` left over from an earlier run could be judged while
    the mapping said otherwise.  Disk wins whenever the file exists.
    """
    merged = dict(files)
    if delivered_dir is None:
        return merged
    base = Path(delivered_dir)
    if not base.is_dir():
        return merged
    for path in sorted(base.glob("*.py")):
        try:
            merged[path.name] = path.read_text(encoding="utf-8")
        except OSError:  # noqa: PERF203 - one unreadable file must not abort
            continue
    return merged


def evaluate_stage10_evidence(
    *,
    stage_dir: Path,
    files: Mapping[str, str],
    metric: str,
    delivered_dir: Path | None = None,
) -> EvidenceReport:
    """Run all M2 gates and return the aggregate report."""
    report = EvidenceReport()
    delivered = collect_delivered(files, delivered_dir)
    blueprint = load_blueprint(stage_dir)
    if blueprint is None:
        report.warnings.append(
            "blueprint unavailable — file/metric/data gates skipped (see "
            "codegen_decision.json)"
        )
    else:
        report.failures.extend(check_declared_files(blueprint, delivered))
        report.failures.extend(check_symbol_contract(blueprint, delivered))
        declared_metric = _find_metric(blueprint) or str(metric or "")
        report.failures.extend(check_metric_consistency(declared_metric, delivered))
        warnings, synthetic = check_data_source(blueprint, delivered)
        report.warnings.extend(warnings)
        report.synthetic_data = synthetic
    report.failures.extend(check_compute_presence(delivered))
    return report


def write_evidence_report(stage_dir: Path, report: EvidenceReport) -> Path:
    """Persist the report; failures stay readable after the stage fails."""
    path = safe_join(stage_dir, EVIDENCE_NAME)
    path.write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
