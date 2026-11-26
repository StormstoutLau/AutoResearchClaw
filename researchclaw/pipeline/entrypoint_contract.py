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

    has_guard = False
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
            has_guard = True
            break

    issues: list[str] = []
    if not has_guard:
        issues.append('main.py missing `if __name__ == "__main__":` block')
    if "METRIC_DEF" not in code:
        issues.append("main.py never prints METRIC_DEF")
    return issues


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
) -> str:
    """Prompt asking the model for one complete, runnable ``main.py``."""
    modules = summarize_modules(files)
    plan_excerpt = (exp_plan or "").strip()[:3000]
    parts = [
        "Write ONLY the file `main.py` for an experiment package.",
        "",
        f"Research topic: {topic}",
        f"Primary metric: {metric}",
        "",
        "The other generated modules are:",
        modules,
        "",
        "HARD REQUIREMENTS (the file is rejected if any is missing):",
        '1. End with an `if __name__ == "__main__":` block that calls a real '
        'function, e.g. `if __name__ == "__main__":\\n    main()`.',
        "2. Print exactly one machine-readable line describing the metric, "
        f"starting with `METRIC_DEF:` — e.g. "
        f'print("METRIC_DEF: {metric} | direction=higher | desc=...").',
        f"3. Print the final value as `{metric}: <float>` so it can be parsed.",
        "4. Import the existing modules listed above instead of re-implementing "
        "their classes/functions.",
        "5. The file MUST be complete: no placeholders, no TODO, no truncated "
        "string literals, and no trailing unfinished statement.",
        "6. Keep it runnable on CPU with the packages already used by the "
        "other modules (numpy/scipy/pandas by default).",
        "7. Output a single ```python code block containing the whole file.",
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
