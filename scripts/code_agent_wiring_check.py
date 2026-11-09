#!/usr/bin/env python3
"""Structural guard: CLI code agent config, factory and stage wiring stay connected.

Exit 1 if any provider exposed in config has no factory branch, if Stage 10/13
stop consulting the factory, or if a prompt is passed through argv.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def main(root: Path | None = None) -> int:
    root = root or ROOT
    errors: list[str] = []

    config_text = _read(root, "researchclaw/config.py")
    factory_text = _read(root, "researchclaw/experiment/code_agent.py")
    stage10_text = _read(root, "researchclaw/pipeline/stage_impls/_code_generation.py")
    stage13_text = _read(root, "researchclaw/pipeline/stage_impls/_execution.py")
    pipeline_agent_text = _read(root, "researchclaw/pipeline/code_agent.py")

    match = re.search(r"CLI_AGENT_PROVIDERS\s*=\s*\{([^}]*)\}", config_text)
    if not match:
        errors.append("config.py: CLI_AGENT_PROVIDERS not found")
        providers: set[str] = set()
    else:
        providers = set(re.findall(r'"([a-z_]+)"', match.group(1)))

    for provider in sorted(providers):
        if f'provider == "{provider}"' not in factory_text:
            errors.append(
                f"experiment/code_agent.py: no factory branch for provider {provider!r}"
            )

    if "class CodeAgentConfig" in pipeline_agent_text:
        errors.append(
            "pipeline/code_agent.py: duplicate CodeAgentConfig definition "
            "(import it from researchclaw.config instead)"
        )
    if "from researchclaw.config import CodeAgentConfig" not in pipeline_agent_text:
        errors.append(
            "pipeline/code_agent.py: CodeAgentConfig is not imported from config"
        )

    if "_try_cli_code_agent(" not in stage10_text:
        errors.append("Stage 10: _try_cli_code_agent() call missing")
    if '_cli_agent_used' not in stage10_text:
        errors.append("Stage 10: _cli_agent_used guard missing")
    if "cli_agent" not in stage10_text:
        errors.append("Stage 10: config.experiment.cli_agent not consulted")

    for helper in ("_try_agent_refine(", "_try_agent_repair("):
        if helper not in stage13_text:
            errors.append(f"Stage 13: {helper}) call missing")
    if "cli_agent" not in stage13_text:
        errors.append("Stage 13: config.experiment.cli_agent not consulted")
    if stage13_text.count("_STAGE13_CLI_BOUNDARY") < 2:
        errors.append(
            "Stage 13: _STAGE13_CLI_BOUNDARY must be declared and passed to refine"
        )
    if '"boundary": "repair_and_tune"' not in stage13_text:
        errors.append(
            "Stage 13: refinement log must record boundary=repair_and_tune"
        )

    claude_start = factory_text.find("class ClaudeCodeAgent")
    codex_start = factory_text.find("class CodexAgent")
    claude_text = factory_text[claude_start:codex_start] if claude_start >= 0 else ""
    codex_text = factory_text[codex_start:] if codex_start >= 0 else ""
    if '"-p", prompt' in claude_text:
        errors.append(
            "ClaudeCodeAgent: prompt is passed through argv; use stdin_text"
        )
    if '"exec", "-"' not in codex_text:
        errors.append('CodexAgent: expected "exec", "-" (stdin prompt transport)')
    if '"exec", prompt' in codex_text:
        errors.append("CodexAgent: prompt is passed through argv; use stdin_text")

    if errors:
        print("code_agent_wiring_check: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "code_agent_wiring_check: PASS "
        f"(providers={','.join(sorted(providers))})"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="", help="override repository root (tests)")
    args = parser.parse_args()
    sys.exit(main(Path(args.root) if args.root else None))
