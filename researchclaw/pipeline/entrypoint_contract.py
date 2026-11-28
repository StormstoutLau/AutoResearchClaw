"""Stage 10 entrypoint contract (B-29).

``main.py`` is the only file Stage 12 executes.  A module can be valid Python
and still be useless as an entrypoint: without an ``if __name__ == "__main__"``
guard nothing runs, and without a ``METRIC_DEF`` line Stage 12 collects zero
metrics.  ``ast.parse`` accepts both cases, so the contract must be checked
explicitly.

Both ``code_agent`` (sequential generation) and ``_code_generation`` (repair
paths) use these helpers; keeping them in a neutral module avoids a circular
import between the two.
"""

from __future__ import annotations

import ast
from typing import Mapping

# A main.py rarely needs more than a few thousand tokens; 32768 leaves room
# for models that emit long preamble before the code block.
ENTRYPOINT_MAX_TOKENS = 32768
# B-30: some models re-implement every module inside main.py and blow past
# 32768 tokens twice.  Escalate once instead of retrying at the same budget.
ENTRYPOINT_RETRY_MAX_TOKENS = 65536
MAX_ENTRYPOINT_LINES = 150

_ENTRY_CALLABLES = (
    "main",
    "run",
    "run_experiment",
    "train",
    "evaluate",
    "experiment",
    "execute",
)


def _has_main_guard(tree: ast.AST) -> bool:
    """True when the module already has an ``if __name__ == "__main__"``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            return True
    return False


def _required_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Positional parameters that have no default (call with zero args)."""
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    return max(0, len(positional) - len(args.defaults))


def _entry_callable(tree: ast.AST) -> str | None:
    """Module-level entry callable that can be invoked with no arguments."""
    defined = {
        node.name: node
        for node in getattr(tree, "body", [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in _ENTRY_CALLABLES:
        node = defined.get(name)
        if node is not None and _required_args(node) == 0:
            return name
    return None


def entrypoint_issues(main_code: str) -> list[str]:
    """Reasons why ``main.py`` cannot serve as an experiment entrypoint.

    Empty list means the file satisfies the contract:
    it parses, has a ``__main__`` guard, and prints ``METRIC_DEF``.
    """
    code = str(main_code or "")
    if not code.strip():
        return ["main.py is empty or missing"]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"main.py has a syntax error: {exc.msg} (line {exc.lineno})"]

    issues: list[str] = []
    if not _has_main_guard(tree):
        issues.append('main.py missing `if __name__ == "__main__":` block')
    if "METRIC_DEF" not in code:
        issues.append("main.py never prints METRIC_DEF")
    return issues


def patch_entrypoint_guard(code: str, metric: str) -> str | None:
    """P-231 (D-1): append the missing guard instead of regenerating main.py.

    Regenerating a blueprint-complete ``main.py`` with a "thin driver" prompt
    destroys the symbols the blueprint declares for that file (run O: a
    362-line file that satisfied the symbol contract was replaced by a
    101-line stub).  Adding ``if __name__ == "__main__": <entry>()`` is a
    structural fix that costs no tokens and cannot remove code.

    Returns ``None`` when no safe patch exists — the file does not parse,
    already has a guard, or exposes no module-level zero-argument entry
    callable — so the caller falls back to the LLM regeneration path.

    ``METRIC_DEF`` is only injected as a *definition* line.  The measured
    value is printed only when the entry callable returns a mapping that
    actually contains the metric; a fabricated number would let a broken
    experiment pass the evidence gate.
    """
    source = str(code or "")
    if not source.strip():
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if _has_main_guard(tree):
        return None
    entry = _entry_callable(tree)
    if entry is None:
        return None

    if "METRIC_DEF" in source:
        block = f'\n\nif __name__ == "__main__":\n    {entry}()\n'
    else:
        block = (
            "\n\nif __name__ == \"__main__\":\n"
            f"    _result = {entry}()\n"
            f"    print(\"METRIC_DEF: {metric} | direction=higher "
            "| desc=auto-guard\")\n"
            f"    if isinstance(_result, dict) and {metric!r} in _result:\n"
            f"        print(f\"{metric}: {{float(_result[{metric!r}]):.6f}}\")\n"
        )
    return source.rstrip("\n") + block


def summarize_modules(
    files: Mapping[str, str], *, max_names: int = 40,
) -> str:
    """List top-level names per module so the entrypoint can import them."""
    lines: list[str] = []
    for name, code in files.items():
        if name == "main.py" or not name.endswith(".py") or not code:
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            lines.append(f"- {name}: <syntax error>")
            continue
        names: list[str] = []
        for node in tree.body:
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                names.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        names.append(target.id)
        lines.append(f"- {name}: " + (", ".join(names[:max_names]) or "(no top-level names)"))
    return "\n".join(lines) or "(no modules)"


def build_entrypoint_prompt(
    *,
    topic: str,
    metric: str,
    files: Mapping[str, str],
    exp_plan: str = "",
    previous_issues: list[str] | None = None,
    symbol_contract: str = "",
) -> str:
    """Prompt asking the model for one complete, runnable ``main.py``.

    ``symbol_contract`` is the blueprint's declared-symbol block for this file
    (P-231 D-2).  Without it the model cannot know which names the file must
    define, and the "thin driver" rule below makes losing them unavoidable.
    """
    modules = summarize_modules(files)
    plan_excerpt = (exp_plan or "").strip()[:1200]
    parts = [
        "Write ONLY the file `main.py` for an experiment package.",
        "",
        f"Research topic: {topic}",
        f"Primary metric: {metric}",
        "",
        "The other generated modules are:",
        modules,
    ]
    if symbol_contract:
        parts += [
            "",
            "SYMBOL CONTRACT — `main.py` MUST define every name below in this "
            "file; the blueprint assigns them to main.py, so they are not "
            "available from the other modules:",
            symbol_contract,
        ]
    parts += [
        "",
        "HARD REQUIREMENTS (the file is rejected if any is missing):",
        '1. End with an `if __name__ == "__main__":` block that calls a real '
        'function, e.g. `if __name__ == "__main__":\\n    main()`.',
        "2. Print exactly one machine-readable line describing the metric, "
        f"starting with `METRIC_DEF:` — e.g. "
        f'print("METRIC_DEF: {metric} | direction=higher | desc=...").',
        f"3. Print the final value as `{metric}: <float>` so it can be parsed.",
        (
            "4. Import the existing modules listed above and CALL their "
            "functions instead of copying their code. The SYMBOL CONTRACT is "
            "the exception: names listed there belong to main.py and must be "
            "implemented here."
            if symbol_contract else
            "4. Import the existing modules listed above and CALL their "
            "functions. Do NOT re-implement their classes or copy their code "
            "— this file is only a thin driver."
        ),
        f"5. Keep the file at most {MAX_ENTRYPOINT_LINES} lines. A longer file "
        "will be truncated and rejected.",
        "6. The file MUST be complete: no placeholders, no TODO, no truncated "
        "string literals, and no trailing unfinished statement.",
        "7. Keep it runnable on CPU with the packages already used by the "
        "other modules (numpy/scipy/pandas by default).",
        "8. Output a single ```python code block containing the whole file.",
    ]
    if plan_excerpt:
        parts += ["", "Experiment plan excerpt:", plan_excerpt]
    if previous_issues:
        parts += [
            "",
            "Your previous attempt was rejected for these reasons:",
            *[f"- {issue}" for issue in previous_issues],
            "Return a corrected, complete file.",
        ]
    return "\n".join(parts)


_SYNTH_TEMPLATE = '''"""Auto-generated entrypoint (B-30 fallback).

The model did not produce a runnable main.py, so this thin driver imports
`%(module)s` and calls `%(fn)s`.
"""
from __future__ import annotations

import %(module)s as _impl

METRIC = %(metric_repr)s


def main() -> None:
    print("METRIC_DEF: " + METRIC + " | direction=higher | desc=auto-generated driver")
    value = None
    fn = getattr(_impl, %(fn_repr)s, None)
    if callable(fn):
        value = fn()
    if isinstance(value, dict):
        value = value.get(METRIC, next(iter(value.values()), float("nan")))
    try:
        print(f"{METRIC}: {float(value):.6f}")
    except (TypeError, ValueError):
        print(METRIC + ": nan")


if __name__ == "__main__":
    main()
'''


def synthesize_entrypoint(
    files: Mapping[str, str], metric: str,
) -> str | None:
    """B-30: build a minimal driver when the model cannot produce ``main.py``.

    Picks the first module exposing a conventional entry function
    (``main``/``run``/``train``/...) and calls it.  Returns ``None`` when no
    module exposes one, so callers keep failing loudly instead of shipping a
    fake entrypoint.
    """
    candidates: list[tuple[int, str, str]] = []
    for name, code in files.items():
        if name == "main.py" or not name.endswith(".py") or not code:
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        funcs = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for rank, fn in enumerate(_ENTRY_CALLABLES):
            if fn in funcs:
                candidates.append((rank, name[:-3], fn))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _, module, fn = candidates[0]
    return _SYNTH_TEMPLATE % {
        "module": module,
        "fn": fn,
        "fn_repr": repr(fn),
        "metric_repr": repr(metric),
    }
