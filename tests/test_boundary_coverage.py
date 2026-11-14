"""Boundary registry guard (M4-D6).

AST scan of ``researchclaw/**`` cross-checked against
``tests/boundary_registry.yaml`` in both directions:

* R1 unregistered subprocess call -> red
* R2 stale registry entry -> red
* R3 ``shell=True`` -> red (no exemption channel)
* R4 ``env=`` shape disagrees with the registration -> red
* R5 unregistered dynamic write site -> red
* R6 meta test: removing one entry in memory must turn the guard red
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(__file__).resolve().parent / "boundary_registry.yaml"

_SUBPROCESS_METHODS = frozenset({"run", "Popen", "check_call", "check_output", "call"})
_WRITE_METHODS = frozenset({"write_text", "write_bytes"})
_COPY_METHODS = frozenset({"copy", "copy2", "copyfile", "copytree"})
_WRITE_MODE_CHARS = frozenset("wax+")
_ENV_BUILDER = "build_subprocess_env"
_MODULE_QUALNAME = "<module>"


@dataclass(frozen=True)
class Finding:
    relpath: str
    qualname: str
    ordinal: int
    lineno: int
    kind: str  # "subprocess" | "write"
    form: str  # inherit | allowlist | alias | sourced:<name> | other | dynamic | safe_join
    shell_true: bool
    first_line: str

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.relpath, self.qualname, self.ordinal)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _has_name(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) for n in ast.walk(node))


def _is_dynamic(target: ast.AST) -> bool:
    """U-9 predicate: the *name component* of a concatenation carries a Name.

    The base directory is itself a variable in virtually every write site, so
    it does not make a site dynamic by itself (``base / "paper.tex"`` writes a
    fixed name).  What matters for traversal is the name component: the right
    operand of ``/``, the arguments of ``join``/``joinpath`` and the f-string
    interpolations.
    """
    if isinstance(target, ast.BinOp) and isinstance(target.op, ast.Div):
        return _has_name(target.right)
    if isinstance(target, ast.BinOp) and isinstance(target.op, ast.Add):
        return _has_name(target.left) or _has_name(target.right)
    if (
        isinstance(target, ast.Call)
        and isinstance(target.func, ast.Attribute)
        and target.func.attr in {"join", "joinpath"}
    ):
        return any(_has_name(a) for a in target.args)
    if isinstance(target, ast.JoinedStr):
        return any(
            _has_name(v.value) for v in target.values if isinstance(v, ast.FormattedValue)
        )
    return False


def _is_safe_join_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == "safe_join"


def _shell_true(call: ast.Call) -> bool:
    for kw in call.keywords:
        if (
            kw.arg == "shell"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            return True
    return False


def _classify_env(call: ast.Call, aliases: dict[str, ast.AST]) -> str:
    env_kw = next((kw for kw in call.keywords if kw.arg == "env"), None)
    if env_kw is None:
        return "inherit"
    value = env_kw.value
    if isinstance(value, ast.Call):
        name = _call_name(value)
        if name == _ENV_BUILDER:
            return "allowlist"
        return f"sourced:{name}"
    if isinstance(value, ast.Name):
        assigned = aliases.get(value.id)
        if isinstance(assigned, ast.Call):
            name = _call_name(assigned)
            if name == _ENV_BUILDER:
                return "alias"
            return f"sourced:{name}"
    return "other"


def _mode_of(call: ast.Call, positional: int) -> str:
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    if len(call.args) > positional and isinstance(call.args[positional], ast.Constant):
        return str(call.args[positional].value)
    return "r"


def _write_target(call: ast.Call) -> ast.AST | None:
    """Return the path argument a write call mutates (None when not a write)."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        if _WRITE_MODE_CHARS & set(_mode_of(call, 1)):
            return call.args[0] if call.args else None
        return None
    if not isinstance(func, ast.Attribute):
        return None
    attr = func.attr
    if attr in _WRITE_METHODS:
        # ``path.write_text(data)`` — the mutated path is the receiver.
        return func.value
    if attr == "open":
        if _WRITE_MODE_CHARS & set(_mode_of(call, 0)):
            return func.value
        return None
    if attr in _COPY_METHODS and _root_name(func) == "shutil":
        return call.args[1] if len(call.args) >= 2 else None
    if attr == "replace" and _root_name(func) == "os":
        return call.args[1] if len(call.args) >= 2 else None
    return None


class _Collector(ast.NodeVisitor):
    def __init__(self, relpath: str, lines: list[str]) -> None:
        self.relpath = relpath
        self.lines = lines
        self.stack: list[str] = []
        self.func_stack: list[ast.AST] = []
        self.aliases: dict[int, dict[str, ast.AST]] = {}
        self.subprocess_calls: list[tuple[str, ast.Call, int | None]] = []
        self.write_calls: list[tuple[str, ast.Call]] = []

    # -- scope tracking ----------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.func_stack.append(node)
        self.aliases.setdefault(id(node), {})
        self.generic_visit(node)
        self.func_stack.pop()
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if self.func_stack and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                self.aliases[id(self.func_stack[-1])][target.id] = node.value
        self.generic_visit(node)

    # -- call collection ---------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        qualname = ".".join(self.stack) or _MODULE_QUALNAME
        func = node.func
        is_subprocess = (
            isinstance(func, ast.Attribute)
            and func.attr in _SUBPROCESS_METHODS
            and _root_name(func) == "subprocess"
        ) or (isinstance(func, ast.Name) and func.id == "Popen")
        if is_subprocess:
            func_id = id(self.func_stack[-1]) if self.func_stack else None
            self.subprocess_calls.append((qualname, node, func_id))
        if _write_target(node) is not None:
            self.write_calls.append((qualname, node))
        self.generic_visit(node)

    # -- findings ----------------------------------------------------------
    def collect(self) -> tuple[list[Finding], list[Finding]]:
        subprocess: list[Finding] = []
        grouped: dict[str, list[tuple[ast.Call, int | None]]] = {}
        for qualname, node, func_id in self.subprocess_calls:
            grouped.setdefault(qualname, []).append((node, func_id))
        for qualname, pairs in grouped.items():
            pairs.sort(key=lambda p: (p[0].lineno, p[0].col_offset))
            for ordinal, (node, func_id) in enumerate(pairs, start=1):
                subprocess.append(
                    Finding(
                        relpath=self.relpath,
                        qualname=qualname,
                        ordinal=ordinal,
                        lineno=node.lineno,
                        kind="subprocess",
                        form=_classify_env(node, self.aliases.get(func_id, {})),
                        shell_true=_shell_true(node),
                        first_line=self._line(node.lineno),
                    )
                )

        writes: list[Finding] = []
        by_qualname: dict[str, list[ast.Call]] = {}
        for qualname, node in self.write_calls:
            by_qualname.setdefault(qualname, []).append(node)
        for qualname, nodes in by_qualname.items():
            nodes.sort(key=lambda n: (n.lineno, n.col_offset))
            ordinal = 0
            for node in nodes:
                target = _write_target(node)
                if target is None:
                    continue
                if _is_safe_join_call(target):
                    form = "safe_join"
                elif _is_dynamic(target):
                    form = "dynamic"
                else:
                    continue
                ordinal += 1
                writes.append(
                    Finding(
                        relpath=self.relpath,
                        qualname=qualname,
                        ordinal=ordinal,
                        lineno=node.lineno,
                        kind="write",
                        form=form,
                        shell_true=False,
                        first_line=self._line(node.lineno),
                    )
                )
        return subprocess, writes

    def _line(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load the registry; missing file / bad version is fail-closed."""
    if not path.exists():
        raise FileNotFoundError(f"boundary registry missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"boundary registry is not a mapping: {path}")
    if data.get("version") != 1:
        raise ValueError(f"unsupported boundary registry version: {data.get('version')!r}")
    if not isinstance(data.get("scan"), dict) or not data["scan"].get("roots"):
        raise ValueError("boundary registry scan.roots is required")
    for section in ("subprocess_calls", "write_sites"):
        seen: set[tuple[str, str, int]] = set()
        for entry in data.get(section) or []:
            key = (str(entry["relpath"]), str(entry["qualname"]), int(entry["ordinal"]))
            if key in seen:
                raise ValueError(f"duplicate boundary registry key in {section}: {key}")
            seen.add(key)
    return data


def _relpath(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan(
    roots: list[str] | tuple[str, ...],
    exclude: tuple[str, ...] = (),
) -> tuple[list[Finding], list[Finding]]:
    """AST-scan ``roots`` and return (subprocess findings, write findings)."""
    subprocess: list[Finding] = []
    writes: list[Finding] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.is_absolute():
            root_path = REPO_ROOT / root_path
        for path in sorted(root_path.rglob("*.py")):
            try:
                rel_to_root = path.relative_to(root_path).as_posix()
            except ValueError:
                rel_to_root = path.name
            if any(rel_to_root.startswith(prefix) for prefix in exclude):
                continue
            source = path.read_text(encoding="utf-8")
            collector = _Collector(_relpath(path), source.splitlines())
            collector.visit(ast.parse(source, filename=str(path)))
            sub_findings, write_findings = collector.collect()
            subprocess.extend(sub_findings)
            writes.extend(write_findings)
    return subprocess, writes


def _registry_index(entries: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, Any]]:
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for entry in entries:
        key = (str(entry["relpath"]), str(entry["qualname"]), int(entry["ordinal"]))
        index[key] = entry
    return index


def _env_matches(registered: str, form: str) -> bool:
    if registered == "inherit":
        return form == "inherit"
    if registered in {"allowlist", "overrides"}:
        return form in {"allowlist", "alias"}
    if registered.startswith("sourced:"):
        return form == registered
    if registered == "prefix":
        return form == "inherit"
    return False


def _check_exemption(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = f"{entry.get('id', '?')} ({entry.get('relpath')}:{entry.get('qualname')}#{entry.get('ordinal')})"
    for field in ("reason", "owner", "expires"):
        if not entry.get(field):
            errors.append(f"exempt entry missing {field}: {label}")
    expires = entry.get("expires")
    if expires:
        try:
            if date.fromisoformat(str(expires)) < date.today():
                errors.append(f"exempt entry expired ({expires}): {label}")
        except ValueError:
            errors.append(f"exempt entry has invalid expires ({expires!r}): {label}")
    return errors


def check(
    registry: dict[str, Any],
    findings: tuple[list[Finding], list[Finding]],
) -> list[str]:
    """Pure two-way consistency check; empty list means green."""
    subprocess_findings, write_findings = findings

    # R3 first: shell=True has no exemption channel.
    shell_hits = sorted(f for f in subprocess_findings if f.shell_true)
    if shell_hits:
        return [
            f"shell=True forbidden at {f.relpath}:{f.lineno} ({f.qualname}#{f.ordinal})"
            for f in shell_hits
        ]

    errors: list[str] = []
    sub_registry = _registry_index(registry.get("subprocess_calls") or [])
    actual = {f.key: f for f in subprocess_findings}

    # R1: every AST call must be registered.
    for key, finding in actual.items():
        if key not in sub_registry:
            errors.append(
                "unregistered subprocess call at "
                f"{finding.relpath}:{finding.qualname}#{finding.ordinal} "
                f"(line {finding.lineno}: {finding.first_line})"
            )

    # R2: every registration must exist in the AST.
    known_by_qualname: dict[tuple[str, str], list[int]] = {}
    for key in sorted(actual):
        known_by_qualname.setdefault((key[0], key[1]), []).append(key[2])
    for key, entry in sub_registry.items():
        if key not in actual:
            qualname_key = (key[0], key[1])
            ordinals = known_by_qualname.get(qualname_key, [])
            detail = (
                f"known ordinals={ordinals} under {key[1]!r}"
                if ordinals
                else f"no subprocess calls found under {key[1]!r}"
            )
            hint = " (suspected ordinal drift)" if ordinals else ""
            errors.append(
                f"stale registry entry {entry.get('id', '?')} "
                f"({key[0]}:{key[1]}#{key[2]}){hint}; {detail}"
            )

    # R4: env shape must agree with the registration.
    for key, finding in actual.items():
        entry = sub_registry.get(key)
        if entry is None:
            continue
        registered = str(entry.get("env", "inherit"))
        if not _env_matches(registered, finding.form):
            errors.append(
                f"env from unregistered source at {finding.relpath}:{finding.qualname}"
                f"#{finding.ordinal}: expected {registered!r}, got {finding.form!r} "
                f"(line {finding.lineno})"
            )

    # R5: dynamic write sites, both directions.
    write_registry = _registry_index(registry.get("write_sites") or [])
    write_actual = {f.key: f for f in write_findings}
    for key, finding in write_actual.items():
        if key not in write_registry:
            errors.append(
                "unregistered dynamic write at "
                f"{finding.relpath}:{finding.qualname}#{finding.ordinal} "
                f"(line {finding.lineno}: {finding.first_line})"
            )
    for key, entry in write_registry.items():
        finding = write_actual.get(key)
        label = f"{entry.get('id', '?')} ({key[0]}:{key[1]}#{key[2]})"
        if finding is None:
            errors.append(f"stale write-site entry {label}")
            continue
        policy = str(entry.get("policy", ""))
        if policy not in {"safe_join", "exempt"}:
            errors.append(f"write-site entry has invalid policy {policy!r}: {label}")
        if policy == "safe_join" and finding.form != "safe_join":
            errors.append(f"registered safe_join but target is still dynamic: {label}")
        if policy == "exempt":
            errors.extend(_check_exemption(entry))
    return errors


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _write_module(tmp_path: Path, name: str, body: str) -> Path:
    module = tmp_path / name
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(body, encoding="utf-8")
    return module


def _registry_for(
    findings: tuple[list[Finding], list[Finding]],
    *,
    env: str = "inherit",
    policy: str = "safe_join",
) -> dict[str, Any]:
    subprocess_findings, write_findings = findings
    return {
        "version": 1,
        "scan": {"roots": [], "exclude": []},
        "subprocess_calls": [
            {
                "id": f"S-{i:03d}",
                "relpath": f.relpath,
                "qualname": f.qualname,
                "ordinal": f.ordinal,
                "category": "A",
                "env": env,
                "reason": "",
                "owner": "P-106",
                "expires": None,
            }
            for i, f in enumerate(subprocess_findings, start=1)
        ],
        "write_sites": [
            {
                "id": f"W-{i:03d}",
                "relpath": f.relpath,
                "qualname": f.qualname,
                "ordinal": f.ordinal,
                "policy": policy,
                "reason": "synthetic",
                "owner": "P-106",
                "expires": None,
            }
            for i, f in enumerate(write_findings, start=1)
        ],
    }


def test_t5_unregistered_subprocess_is_red(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        "import subprocess\n\n\ndef run():\n    return subprocess.run(['echo', 'hi'])\n",
    )
    registry = {
        "version": 1,
        "scan": {"roots": [], "exclude": []},
        "subprocess_calls": [],
        "write_sites": [],
    }
    errors = check(registry, scan([str(tmp_path)]))
    assert any("unregistered subprocess call" in e for e in errors)


def test_t6_stale_entry_is_red(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        "import subprocess\n\n\ndef run():\n    return subprocess.run(['echo'])\n",
    )
    findings = scan([str(tmp_path)])
    registry = _registry_for(findings)
    registry["subprocess_calls"].append(
        {
            "id": "S-999",
            "relpath": findings[0][0].relpath,
            "qualname": findings[0][0].qualname,
            "ordinal": 7,
            "category": "A",
            "env": "inherit",
            "reason": "",
            "owner": "P-106",
            "expires": None,
        }
    )
    errors = check(registry, findings)
    assert any("stale registry entry" in e for e in errors)
    assert any("ordinal drift" in e for e in errors)


def test_t7_shell_true_is_red_without_exemption(tmp_path: Path) -> None:
    real_sub, _ = scan(["researchclaw"])
    assert [f for f in real_sub if f.shell_true] == []

    _write_module(
        tmp_path,
        "pkg/mod.py",
        "import subprocess\n\n\ndef run(cmd):\n    return subprocess.run(cmd, shell=True)\n",
    )
    findings = scan([str(tmp_path)])
    registry = _registry_for(findings, env="allowlist")
    errors = check(registry, findings)
    assert errors and all("shell=True forbidden" in e for e in errors)


def test_t8_dynamic_write_is_red_but_literal_is_not(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "from pathlib import Path\n\n\n"
            "def write(base: Path, name: str) -> None:\n"
            "    (base / name).write_text('x')\n"
            "    (base / 'fixed.txt').write_text('y')\n"
        ),
    )
    findings = scan([str(tmp_path)])
    assert len(findings[1]) == 1
    errors = check(
        {"version": 1, "scan": {}, "subprocess_calls": [], "write_sites": []},
        findings,
    )
    assert any("unregistered dynamic write" in e for e in errors)


def test_t9_guard_is_not_vacuous(tmp_path: Path) -> None:
    registry = load()
    findings = scan(registry["scan"]["roots"], tuple(registry["scan"].get("exclude") or ()))
    assert check(registry, findings) == []

    trimmed = dict(registry)
    trimmed["subprocess_calls"] = list(registry["subprocess_calls"])[1:]
    assert trimmed["subprocess_calls"], "registry must have at least two entries"
    assert check(trimmed, findings) != []


def test_r4_inline_allowlist_is_green(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "import subprocess\n"
            "from researchclaw.utils.env import build_subprocess_env\n\n\n"
            "def run(cmd):\n"
            "    return subprocess.run(cmd, env=build_subprocess_env({'A': '1'}))\n"
        ),
    )
    findings = scan([str(tmp_path)])
    assert check(_registry_for(findings, env="allowlist"), findings) == []


def test_r4_single_level_alias_is_green(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "import subprocess\n"
            "from researchclaw.utils.env import build_subprocess_env\n\n\n"
            "def run(cmd):\n"
            "    env = build_subprocess_env()\n"
            "    return subprocess.run(cmd, env=env)\n"
        ),
    )
    findings = scan([str(tmp_path)])
    assert check(_registry_for(findings, env="allowlist"), findings) == []


def test_r4_environ_copy_is_red(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "import os\nimport subprocess\n\n\n"
            "def run(cmd):\n"
            "    env = os.environ.copy()\n"
            "    return subprocess.run(cmd, env=env)\n"
        ),
    )
    findings = scan([str(tmp_path)])
    errors = check(_registry_for(findings, env="inherit"), findings)
    assert any("env from unregistered source" in e for e in errors)


def test_r4_sourced_callable_is_green(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "import subprocess\n\n\n"
            "def _build_env():\n"
            "    return {}\n\n\n"
            "def run(cmd):\n"
            "    return subprocess.run(cmd, env=_build_env())\n"
        ),
    )
    findings = scan([str(tmp_path)])
    assert check(_registry_for(findings, env="sourced:_build_env"), findings) == []


def test_t12_safe_join_escapes() -> None:
    from researchclaw.utils.paths import safe_join

    base = Path(__file__).resolve().parent
    assert safe_join(base, "child.txt") == (base / "child.txt").resolve()
    with pytest.raises(ValueError):
        safe_join(base, "..", "escape.txt")
    with pytest.raises(ValueError):
        safe_join(base, str(base.parent / "escape.txt"))
    link = base / "_symlink_escape_probe"
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(base.parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    try:
        with pytest.raises(ValueError):
            safe_join(base, "_symlink_escape_probe", "escape.txt")
    finally:
        link.unlink()


def test_load_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "missing.yaml")

    bad_version = tmp_path / "v2.yaml"
    bad_version.write_text("version: 2\nscan:\n  roots: [researchclaw]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load(bad_version)

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        "version: 1\n"
        "scan:\n"
        "  roots: [researchclaw]\n"
        "subprocess_calls:\n"
        "  - {relpath: a.py, qualname: f, ordinal: 1}\n"
        "  - {relpath: a.py, qualname: f, ordinal: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load(duplicate)


def test_registry_schema() -> None:
    registry = load()

    subprocess_entries = registry["subprocess_calls"]
    write_entries = registry["write_sites"]
    assert subprocess_entries and write_entries

    for section, entries in (("subprocess", subprocess_entries), ("write", write_entries)):
        keys = [(str(e["relpath"]), str(e["qualname"]), int(e["ordinal"])) for e in entries]
        assert len(set(keys)) == len(keys), f"duplicate key in {section}"

    allowed_env = {"inherit", "allowlist", "prefix"}
    for entry in subprocess_entries:
        label = entry["id"]
        assert entry["category"] in {"A", "B", "C"}, label
        env = str(entry["env"])
        assert env in allowed_env or env.startswith("sourced:"), (label, env)
        assert env != "overrides", label
        assert entry["owner"] == "P-106", label
        assert entry["reason"], label
        if entry["category"] == "B" and env != "allowlist":
            # Allowed: a self-built allowlist source, the U-5 SSH prefix form,
            # or a container-side call whose env only reaches the docker client
            # (documented in ``reason``).
            if env.startswith("sourced:") or env == "prefix":
                continue
            assert env == "inherit", (label, env)
            assert "container" in str(entry["reason"]).lower(), (label, env)

    for entry in write_entries:
        label = entry["id"]
        assert entry["policy"] in {"safe_join", "exempt"}, label
        if entry["policy"] == "exempt":
            for field in ("reason", "owner", "expires"):
                assert entry[field], (label, field)

    exempt = [e for e in write_entries if e["policy"] == "exempt"]
    assert len(exempt) == 1, [e["id"] for e in exempt]


def test_expired_exemption_is_red(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "from pathlib import Path\n\n\n"
            "def write(base: Path, name: str) -> None:\n"
            "    (base / name).write_text('x')\n"
        ),
    )
    findings = scan([str(tmp_path)])
    registry = _registry_for(findings, policy="exempt")
    for entry in registry["write_sites"]:
        entry["expires"] = "2000-01-01"
    errors = check(registry, findings)
    assert any("expired" in e for e in errors)


def test_registry_is_consistent() -> None:
    registry = load()
    findings = scan(registry["scan"]["roots"], tuple(registry["scan"].get("exclude") or ()))
    assert check(registry, findings) == []


def test_t14_alias_spawn_is_outside_scan(tmp_path: Path) -> None:
    """Lock the R1 alias blind spot (DESIGN §4.6 R1 / §13.3 N-1 / §13.7 F-1).

    ``researchclaw/runtime/supervisor.py:71`` stores ``spawn or
    subprocess.Popen`` on ``self._spawn`` and calls it at :102 — the AST
    predicate only sees the ``_spawn`` attribute name, so the live call site
    yields zero findings and stays outside the registry (threat surface =
    default ``worker_cmd``, cli.py:491; human review is the compensating
    control).

    Red condition: extending the predicate to resolve alias forms turns this
    test red, forcing a registry rework before such a change may ship.
    """
    real_sub, _ = scan(["researchclaw"])
    live = [f for f in real_sub if f.relpath == "researchclaw/runtime/supervisor.py"]
    assert live == [], "supervisor alias site must remain outside the registry"

    _write_module(
        tmp_path,
        "pkg/mod.py",
        (
            "import subprocess\n\n\n"
            "class Sup:\n"
            "    def __init__(self, spawn=None):\n"
            "        self._spawn = spawn or subprocess.Popen\n\n"
            "    def _run_once(self):\n"
            "        return self._spawn(['worker'])\n"
        ),
    )
    findings = scan([str(tmp_path)])
    assert findings[0] == [], "alias-form spawn must stay invisible to R1"
    assert check(
        {"version": 1, "scan": {}, "subprocess_calls": [], "write_sites": []},
        findings,
    ) == []


# E-1..E-7 registry ids that must carry an *inline* allowlist.
_ALLOWLIST_ENTRY_IDS = {"S-002", "S-016", "S-018", "S-019", "S-035", "S-042", "S-054"}


def test_t10_seven_sites_use_inline_allowlist() -> None:
    registry = load()
    entries = {entry["id"]: entry for entry in registry["subprocess_calls"]}
    findings = scan(registry["scan"]["roots"], tuple(registry["scan"].get("exclude") or ()))
    forms = {finding.key: finding.form for finding in findings[0]}
    assert _ALLOWLIST_ENTRY_IDS <= set(entries)
    for entry_id in sorted(_ALLOWLIST_ENTRY_IDS):
        entry = entries[entry_id]
        assert entry["env"] == "allowlist", entry_id
        key = (entry["relpath"], entry["qualname"], int(entry["ordinal"]))
        assert forms[key] == "allowlist", (entry_id, forms[key])


def test_t10_env_is_closed_over_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    from researchclaw.utils.env import SAFE_ENV_KEYS, build_subprocess_env

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sentinel-value")
    env = build_subprocess_env({"MAGNUS_ADDRESS": "addr", "RC_STAGE_NUM": "3"})
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["MAGNUS_ADDRESS"] == "addr"
    assert env["RC_STAGE_NUM"] == "3"
    extra = set(env) - SAFE_ENV_KEYS - {"MAGNUS_ADDRESS", "RC_STAGE_NUM"}
    assert all(key.startswith("LC_") for key in extra), extra
