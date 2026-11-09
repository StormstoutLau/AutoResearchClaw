#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Private endpoint / credential guard (pre-commit).

Blocks staged text files from carrying:
  - RFC1918 IPv4 addresses (10/8, 172.16/12, 192.168/16)
  - user@<private-ip> SSH targets
  - common API-key shapes (sk-, ghp_, AKIA, xox[baprs]-)

Placeholders such as ``<B_STATION_HOST>`` and reserved TLDs (``.test``)
are allowed by construction. Add an inline ``private-config: allow`` marker
on a line that legitimately needs a private address (e.g. SSRF fixtures).

Usage: python scripts/private_config_check.py [files...]
Exit codes: 0 clean / 1 violations / 2 tool error.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files that legitimately contain private ranges as test fixtures.
ALLOW_PATHS = {
    os.path.join("tests", "test_web_crawler.py"),
    os.path.join("scripts", "private_config_check.py"),
}

TEXT_EXT = (".py", ".yaml", ".yml", ".md", ".json", ".jsonl", ".txt", ".env")

PATTERNS = (
    ("rfc1918-ip",
     re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                r"|192\.168\.\d{1,3}\.\d{1,3}"
                r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("ssh-user@ip",
     re.compile(r"\b[\w.-]+@(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("api-key-sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("api-key-gh", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("api-key-aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("api-key-slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

ALLOW_MARKER = "private-config: allow"


def _norm(path: str) -> str:
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    return rel.replace("/", os.sep)


def check_file(path: str) -> list[str]:
    rel = _norm(path)
    if rel in ALLOW_PATHS or not rel.lower().endswith(TEXT_EXT):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return ["%s: cannot read (%s)" % (rel, exc)]

    hits: list[str] = []
    for lineno, line in enumerate(lines, 1):
        if ALLOW_MARKER in line:
            continue
        for name, rx in PATTERNS:
            match = rx.search(line)
            if not match:
                continue
            token = match.group(0)
            if name.startswith("api-key"):
                body = re.sub(
                    r"^(?:sk-|ghp_|AKIA|xox[baprs]-)", "", token
                ).lower()
                if body and set(body) <= {"x"}:
                    continue  # documented placeholder, e.g. sk-xxxxxxxx
            hits.append("%s:%d: %s -> %s" % (rel, lineno, name, line.strip()[:120]))
            break
    return hits


def main(argv: list[str]) -> int:
    targets = argv[1:]
    if not targets:
        # No args: scan the working tree (useful for manual runs).
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [
                d for d in dirnames
                if d not in {".git", "__pycache__", ".venv", "node_modules"}
            ]
            for fn in filenames:
                targets.append(os.path.join(dirpath, fn))

    violations: list[str] = []
    for path in targets:
        violations.extend(check_file(path))
    if violations:
        print("private-config guard: %d violation(s)" % len(violations))
        for v in violations:
            print("  " + v)
        print("Placeholders (<HOST>), .test domains, or an inline "
              "'%s' marker are accepted." % ALLOW_MARKER)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
