#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spec_map —— feature ↔ P 编号映射的**唯一实现**（P-047，裁定 C-16 ②）。

权威源：spec/project-console/DESIGN.md §6.8（D14 / I-10）
       + spec/project-console/RESEARCH.md §7.10（C-16：映射来源语义与收敛）

语义优先级（**§9 优先**，RESEARCH C-16 ①）：
  ① `CODE_WIKI.md §9 文档索引` 行标注——**人工维护索引（真值源侧）**，优先级最高
  ② `docs/PROGRESS.md` P 行内**首个** `spec/<feature>/` 链接——兜底（末行胜出）
  ③ 两者皆无 → **不入表**（调用方以 `—` 显式缺口呈现，I-8；并计入缺映射清单）

为何反转（A-33 的直接成因）：旧语义只认 ②，而 P 行的依据列常**引用上游 feature** 作为论证
来源（实测 `P-009/P-010/P-011/P-016`），致 4 个 feature 永远拿不到 P，且两处实现**同错**
——一致性对账抓不住该类缺陷。故本模块是**唯一**映射实现（I-10 语义同源）。

确定性（I-2）：纯函数、纯字符串输入、无 wall clock / 无环境读取；同源双跑结果一致。
零依赖（I-4）：仅 stdlib `re`。
"""

from __future__ import annotations

import re

# §9 索引行形态：`| [spec/<feature>/](./spec/<feature>/) | <正文（含 P-0xx）> |`
WIKI_ROW_RE = re.compile(r"^\|\s*\[spec/([a-z0-9-]+)/\]\([^)]*\)\s*\|(.*)$")
WIKI_PID_RE = re.compile(r"P-(\d{3})")
# PROGRESS P 行形态：`| P-0xx | 事项 | … |`，取行内**首个** spec/<feature>/ 链接
PROGRESS_ROW_RE = re.compile(r"^\|\s*(P-\d{3})\s*\|.*?spec/([a-z0-9-]+)/")

# §9 章节边界（缺失时 wiki_pid_map 返回空表 → 调用方自然退回 ② 兜底）
SECTION9_HEAD = "## 9. 文档索引"
SECTION10_HEAD = "## 10."


def _section(text: str, head: str, tail: str) -> str:
    """截取 [head, tail) 之间的文本（head 缺失 → 空串；tail 缺失 → 取到文末）。"""
    i = text.find(head)
    if i < 0:
        return ""
    j = text.find(tail, i + len(head))
    return text[i:j] if j >= 0 else text[i:]


def wiki_pid_map(text: str) -> dict:
    """`CODE_WIKI.md` §9 索引行 → {feature: "P-0xx"}（仅收 `spec/<feature>/` 目录行）。

    取该行正文中**首个** `P-\\d{3}`（= 该 feature 的**主 P**，人工索引标注）。
    无 P 标注的行（如 `spec/templates/*` 模板行、纯描述行）不入表 → 交由 ② 兜底。
    """
    mapping = {}
    for line in _section(text, SECTION9_HEAD, SECTION10_HEAD).splitlines():
        m = WIKI_ROW_RE.match(line)
        if not m:
            continue
        pid = WIKI_PID_RE.search(m.group(2))
        if pid:
            mapping[m.group(1)] = f"P-{pid.group(1)}"
    return mapping


def progress_pid_map(text: str) -> dict:
    """`docs/PROGRESS.md` → {feature: "P-0xx"}（行内首个 `spec/<feature>/` 链接；末行胜出）。

    **仅作兜底**：该位置在历史批次中被用于引用上游依据（A-33），语义易被劫持，
    故不得优先于 ① `CODE_WIKI §9` 行标注。
    """
    mapping = {}
    for line in text.splitlines():
        m = PROGRESS_ROW_RE.search(line)
        if m:
            mapping[m.group(2)] = m.group(1)
    return mapping


def build_pid_map(progress_text: str, wiki_text: str = "") -> dict:
    """合并映射：**§9 行标注优先** → PROGRESS 兜底 → 缺位不入表（I-8 显式缺口）。

    `wiki_text` 为空串 / `CODE_WIKI.md` 不可读时，退化为「仅 PROGRESS 兜底」——
    退化是**显式**的（缺口在视图中呈现为 `—`），不是静默补全。
    """
    merged = progress_pid_map(progress_text)
    merged.update(wiki_pid_map(wiki_text))
    return merged


# ---------------------------------------------------------------- 决策流纪律边界
# P-027 裁定：决策流纪律自 P-020 起建立，**P-020 前批次不追溯强制**。该边界被两个消费者共享
# （`step_enforce.py` feature 级豁免 / `console_gen.py` P 行级豁免面），故在此**单点定义**
# （I-10 语义同源 / B25·B26）：凡第二处再写字面量，即构成「两实现同错」风险。
DECISION_STREAM_MIN_P = 20


def is_historical_exempt(pid: str) -> bool:
    """P-027 豁免面：`P-020` 之前的批次（决策流纪律建立前，结构性无派生输入面）。

    解析失败（非 `P-\\d{3}` 形态）落**非豁免**侧——绝不因解析失败而放宽约束。
    """
    m = re.search(r"P-(\d{3})", pid or "")
    return bool(m) and int(m.group(1)) < DECISION_STREAM_MIN_P


# ---------------------------------------------------------------- P 行结构与批次声明（P-130 / U-1 O3）
# P 行前四列：`| P-xxx | 事项 | 依据 | status |`；只取前四列，避免描述列中的 `|` 干扰。
# 注意：**不得复用** `PROGRESS_ROW_RE`——那是 `progress_pid_map` 的 feature 捕获形态，
# 两者语义不同（A-33 教训：同名常量覆写会静默改变旧函数行为）。
P_ROW_RE = re.compile(
    r"^\|\s*(P-\d{3})\s*\|([^|]*)\|([^|]*)\|\s*([^|]*)\|")
SPEC_LINK_RE = re.compile(r"spec/([a-z0-9-]+)/")


def parse_progress_rows(text: str) -> dict[str, dict]:
    """P-xxx -> {"status": str, "features": tuple[str, ...]}（保序去重）。"""
    rows = {}
    for line in text.splitlines():
        m = P_ROW_RE.match(line)
        if not m:
            continue
        pid = m.group(1)
        status = m.group(4).replace("*", "").strip()
        features = tuple(dict.fromkeys(SPEC_LINK_RE.findall(line)))
        rows[pid] = {"status": status, "features": features}
    return rows


def changed_pids(old_text: str, new_text: str) -> list[str]:
    """新增 P 行，或 status 列变化；按新文本顺序返回。"""
    old, new = parse_progress_rows(old_text), parse_progress_rows(new_text)
    return [pid for pid, row in new.items()
            if pid not in old or old[pid]["status"] != row["status"]]
