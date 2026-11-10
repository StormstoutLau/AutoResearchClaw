#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库规模统计（G0b A0-1 必需钩子之一）。

真值源 = 文件系统；docs/REPO_STATS.md 是**派生视图**（与 docs/CONSOLE.md 同构，禁止手改）。

语义（P-017 §7.2）：
  - 默认打印统计；
  - `--check` 与 docs/REPO_STATS.md 的五行声明比对，漂移 → exit 1；
  - 源目录缺失 / 视图缺失或不可解析 → exit 2。
用法：
  python scripts/spec/repo_stats.py            # 打印
  python scripts/spec/repo_stats.py --check    # 门禁
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VIEW = os.path.join(ROOT, "docs", "REPO_STATS.md")
PROGRESS = os.path.join(ROOT, "docs", "PROGRESS.md")

RE_DECL = re.compile(r"^-\s*(代码文件|代码行|测试文件|测试行|P 批次)\s*[：:]\s*(\d+)\s*$", re.M)
RE_P_ROW = re.compile(r"^\|\s*P-\d+\s*\|", re.M)


def _walk_py(base):
    files = lines = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            files += 1
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace") as fh:
                    lines += sum(1 for _ in fh)
            except OSError:
                return None
    return files, lines


def collect():
    """返回 dict；任一源缺失 → None。"""
    if not os.path.isdir(os.path.join(ROOT, "researchclaw")):
        return None
    code = _walk_py(os.path.join(ROOT, "researchclaw"))
    test = _walk_py(os.path.join(ROOT, "tests"))
    if code is None or test is None:
        return None
    try:
        with open(PROGRESS, encoding="utf-8", errors="replace") as fh:
            batches = len(RE_P_ROW.findall(fh.read()))
    except OSError:
        return None
    return {"代码文件": code[0], "代码行": code[1],
            "测试文件": test[0], "测试行": test[1], "P 批次": batches}


def render(stats):
    rows = "\n".join("- %s：%d" % (k, v) for k, v in stats.items())
    return (
        "# 仓库规模统计（派生视图）\n\n"
        "> 由 `scripts/spec/repo_stats.py` 机械生成，**禁止手改**；真值源 = 文件系统。\n"
        "> 校验：`python scripts/spec/repo_stats.py --check`（漂移即红）。\n\n"
        "## 统计\n\n%s\n" % rows
    )


def declare(stats):
    return dict(RE_DECL.findall(render(stats)))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="repo_stats", description="仓库规模统计（派生视图）")
    ap.add_argument("--check", action="store_true", help="与 docs/REPO_STATS.md 比对")
    ap.add_argument("--write", action="store_true", help="重写 docs/REPO_STATS.md")
    args = ap.parse_args(argv)
    stats = collect()
    if stats is None:
        print("repo_stats: 源目录或 docs/PROGRESS.md 缺失/不可读（exit 2）")
        return 2
    body = render(stats)
    if args.write:
        with open(VIEW, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        print("repo_stats: 已写入 %s" % os.path.relpath(VIEW, ROOT))
        return 0
    if not args.check:
        print("\n".join("%s=%d" % (k, v) for k, v in stats.items()))
        return 0
    if not os.path.exists(VIEW):
        print("repo_stats: 缺少 %s（先跑 --write）" % os.path.relpath(VIEW, ROOT))
        return 2
    with open(VIEW, encoding="utf-8", errors="replace") as fh:
        declared = dict(RE_DECL.findall(fh.read()))
    if not declared:
        print("repo_stats: %s 无可解析声明（exit 2）" % os.path.relpath(VIEW, ROOT))
        return 2
    drift = [(k, declared.get(k), v) for k, v in stats.items() if declared.get(k) != str(v)]
    if drift:
        for k, d, v in drift:
            print("repo_stats: 漂移 %s 声明=%s 实际=%s" % (k, d, v))
        print("repo_stats: 请重跑 `python scripts/spec/repo_stats.py --write`")
        return 1
    print("repo_stats: 一致（%s）" % ", ".join("%s=%d" % (k, v) for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
