#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M7 证据账本门禁（G0b A0-1 必需钩子之一）。

输入：docs/M7_EVIDENCE_LOG.md（真值源）。
最小语义（P-017 §7.1）：
  - 无样本 → samples=0，exit 0（门禁为「结构有效 + 零样本可见」，不是永久 no-op）
  - 有样本 → §1 样本表数据行数 = 样本数；§2 若声明「合计」必须与样本数一致
  - 结构损坏（缺节/表头无「样本」列/列数不符）→ exit 1
  - 文件缺失 → exit 2
用法：python scripts/spec/m7_stats.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.path.join(ROOT, "docs", "M7_EVIDENCE_LOG.md")

EMPTY_MARK = "（暂无）"
RE_SECTION = re.compile(r"^##\s*(\d+)\s*[.、]\s*(样本|统计)\s*$")
RE_TOTAL = re.compile(r"合计\D{0,4}(\d+)")


def _split_sections(text):
    """返回 {'样本': body, '统计': body}；缺节则不出现。"""
    out, cur, buf = {}, None, []
    for ln in text.splitlines():
        m = RE_SECTION.match(ln.strip())
        if m:
            if cur:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(2), []
            continue
        if cur is not None and ln.startswith("## "):
            out[cur] = "\n".join(buf)
            cur, buf = None, []
            continue
        if cur is not None:
            buf.append(ln)
    if cur:
        out[cur] = "\n".join(buf)
    return out


def _table_rows(body):
    """解析 markdown 表体。返回 (header_cells, data_rows)；无表返回 ([], [])。"""
    header, rows = [], []
    for ln in body.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not header:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return header, rows


def check(path=LOG):
    """返回 (exit_code, message)。"""
    if not os.path.exists(path):
        return 2, "m7_stats: 缺少 %s" % os.path.relpath(path, ROOT)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return 2, "m7_stats: 读取失败 %s" % exc
    secs = _split_sections(text)
    if "样本" not in secs or "统计" not in secs:
        return 1, "m7_stats: §1 样本 / §2 统计 两节必须同时存在"
    sample_body = secs["样本"].strip()
    if EMPTY_MARK in sample_body:
        return 0, "m7_stats: samples=0（账本为空，结构有效）"
    header, rows = _table_rows(sample_body)
    if not header:
        return 1, "m7_stats: §1 样本 既非「%s」也无表格" % EMPTY_MARK
    if not any("样本" in c for c in header):
        return 1, "m7_stats: §1 表头缺「样本」列（实际 %s）" % header
    width = len(header)
    bad = [i for i, r in enumerate(rows, 1) if len(r) != width]
    if bad:
        return 1, "m7_stats: §1 第 %s 行列数与表头不符（%d != %d）" % (bad, len(rows[0]), width)
    samples = len(rows)
    stat_body = secs["统计"]
    m = RE_TOTAL.search(stat_body)
    if m and int(m.group(1)) != samples:
        return 1, "m7_stats: §2 声明合计 %s != 实际样本 %d" % (m.group(1), samples)
    return 0, "m7_stats: samples=%d（§1 表格 %d 行，§2 声明一致）" % (samples, samples)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="m7_stats", description="M7 证据账本结构门禁")
    ap.add_argument("--path", default=LOG, help="账本路径（默认 docs/M7_EVIDENCE_LOG.md）")
    args = ap.parse_args(argv)
    code, msg = check(args.path)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
