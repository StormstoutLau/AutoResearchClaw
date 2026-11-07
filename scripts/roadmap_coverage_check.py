#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总纲覆盖率门禁（D-6，P-005）。

校验 arc-master-roadmap.md 的每条验收 ID 要么被 §5 C 套件覆盖，
要么显式出现在 §5「覆盖范围声明」中；否则视为漂移。

不变式：I-1 只读 / I-2 确定性（同输入同输出）/ I-3 零新规则
       （口径 = 总纲自身声明，不引入外部清单）/ I-4 与 §5 文本单一真值源。
退出码：0 全覆盖 / 1 存在未声明缺口 / 2 解析错误（fail-closed）。

用法：
  python scripts/roadmap_coverage_check.py            # 打印差集（诊断）
  python scripts/roadmap_coverage_check.py --check    # 门禁模式：差集非空 → exit 1
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROADMAP = os.path.join(ROOT, "arc-master-roadmap.md")

# 与总纲 §4/§5 的 ID 词表一致（不含不变量 I-*，其归属在声明中以文字承载）
PREFIX = r"(?:A0a|A0|A1|A2|A3|A4|A5|A6|A7|A8a|A8b|AN|FC|FA|GQ|OB|H)"
ID_RX = re.compile(r"\b(%s)-(\d+)(?:\s*\.\.\s*(?:%s-)?(\d+))?" % (PREFIX, PREFIX))
SUITE_ROW_RX = re.compile(r"^\|\s*\*{0,2}C-\d")


def expand(text: str) -> set:
    """把 'A1-9..A1-12' / 'H-6..H-8' / 'A5-6' 展开为完整 ID 集。"""
    out = set()
    for m in ID_RX.finditer(text):
        pre, a, b = m.group(1), int(m.group(2)), m.group(3)
        if b is not None:
            out.update("%s-%d" % (pre, i) for i in range(a, int(b) + 1))
        else:
            out.add("%s-%d" % (pre, a))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="门禁模式：差集非空 → exit 1")
    args = ap.parse_args()

    try:
        text = io.open(ROADMAP, encoding="utf-8").read()
        s4 = text.split("## 4.")[1].split("## 5.")[0]
        s5 = text.split("## 5.")[1].split("## 6.")[0]
    except (OSError, IndexError) as exc:
        print("roadmap-coverage: 解析失败（fail-closed）: %s" % exc)
        return 2

    accept = expand(s4)
    if not accept:
        print("roadmap-coverage: §4 未解析到任何验收 ID（fail-closed）")
        return 2

    suite = set()
    for ln in s5.splitlines():
        if SUITE_ROW_RX.match(ln):
            suite |= expand(ln)

    declared = set()
    if "覆盖范围声明" in s5:
        declared = expand(s5.split("覆盖范围声明", 1)[1])

    missing = sorted(accept - suite - declared)
    print("roadmap-coverage: accept=%d suite=%d declared=%d missing=%d"
          % (len(accept), len(suite), len(declared), len(missing)))
    if missing:
        print("  未覆盖且未声明: %s" % ", ".join(missing))
    if args.check and missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
