#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console_gen 项目控制台生成器（P-043 建立，P-044 增补描述列与 per-feature 流程，P-047 增补锚点与映射收敛，
P-084 列头即状态行——C-40 Layer-0 首项 / A-19 落地）。

把 per-feature / per-P / 决策链 / 架构流程四类真值源压缩为**多视图只读控制台**——
输出为**纯派生产物** docs/CONSOLE.md（100% 机器生成，无人工内容；重跑即刷新）。

权威源：spec/project-console/DESIGN.md §3-§7（D1-D14 + I-1~I-10）
       + spec/project-console/RESEARCH.md（裁定 C-5 派生状态机 / C-6 双主键 / C-7 承载 /
         C-8 依赖图 / C-9 描述列 / C-10 架构·流程·交互 / C-12 架构图口径 /
         C-13 hook 链表形态 / C-14 步骤级动态描述 / C-15 锚点双属性 / C-16 映射语义与收敛）

不变式（DESIGN §3.3）：
  I-1 单写路径（只写 docs/CONSOLE.md）/ I-2 确定性（禁 wall clock，同源双跑字节一致）
  I-3 幂等（内容未变不写盘）/ I-4 零依赖（stdlib only）
  I-5 纯派生（可重生成，覆盖无需备份）/ I-6 不增真值（不复制他处真值，只引用指针）
  I-7 词表对齐（状态只用 PROGRESS 原词，不重贴标签；P2b 开关 --derived 开启时执行态改采机器派生、
      决策态仍为原词 → 词表对齐不变，见 DESIGN §5.3 / 本文件 I-7 声明行随开关态分流）
  I-8 显式缺口（派生不出的关系必须显式列出，不得静默省略——缺映射 `—` / 未声明脚本清单）
  I-9 承载安全（外部文本入表格单元格一律过 `_cell()`；长无断点 token 不入表格单元格）
  I-10 语义同源（feature ↔ P 映射只有一份实现：`spec_map`，两处复用，禁双实现）

退出码：0 正常 / 1 `--check` 失配（控制台过期）/ 2 工具自身错误。

用法：
  python scripts/console_gen.py              # 生成并写 docs/CONSOLE.md
  python scripts/console_gen.py --stage      # 生成 + 变化时 git add（pre-commit L0 门禁用）
  python scripts/console_gen.py --stdout     # 仅打印，不写盘
  python scripts/console_gen.py --check      # 只读核对（过期则 exit 1，不写盘）
  python scripts/console_gen.py --selftest   # 内嵌自测（不触工作树）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 共享纯函数模块（同目录）
import spec_map   # noqa: E402  （C-16/I-10：feature ↔ P 映射的唯一实现）

ROOT = Path(__file__).resolve().parents[1]
PROGRESS = ROOT / "docs" / "PROGRESS.md"
SESSIONS = ROOT / "tools" / "spec_runner" / "sessions"
CONSOLE = ROOT / "docs" / "CONSOLE.md"
SPEC = ROOT / "spec"
SCRIPTS = ROOT / "scripts"
RUNNER = ROOT / "tools" / "spec_runner" / "spec_runner.py"
HOOKS = ROOT / ".pre-commit-config.yaml"
WIKI = ROOT / "CODE_WIKI.md"          # §9 索引行标注（C-16 映射第一来源）

P_ROW_RE = re.compile(r"^\|\s*(P-\d{3})\s*\|")
SESSION_PID_RE = re.compile(r"^specwf-(p\d{3})-")

# 状态词汇表 = PROGRESS 原词（I-7：不新增状态词）
STATUS_VOCAB = ("pending", "in-progress", "blocked", "done")
STEP_SEQUENCE = ("research", "design", "implement", "verify", "finalize")
ARTIFACT_ALTS = {
    "R": ("RESEARCH.md",),
    "D": ("DESIGN.md",),
    "I": ("IMPLEMENTATION.md",),
    "C": ("CHECKLIST.md", "CHECKLIST_FUNC.md"),
}
# 步骤 → 制品（C-14 回退常量；第一来源是文档自声明的 `> **Spec 步骤**: Step X-Y` 行）
STEP_ARTIFACT = {
    "research": ("R", "RESEARCH.md"),
    "design": ("D", "DESIGN.md"),
    "implement": ("I", "IMPLEMENTATION.md"),
    "verify": ("C", "CHECKLIST.md"),
    "finalize": ("", "—（finalize 不新增制品）"),
}
STEP_CAP = 48      # 步骤表「主题 / 简要描述」列字符上限（C-14；H6 渲染宽度校准待实测）
# 行动队列三级（RESEARCH A-8 的 Needs Attention → Ready to Verify → Recommended）
TIER_ORDER = ("Needs Attention", "Ready to Verify", "Recommended")
# 三档队列列头契约（C-40 Layer-0 首项 / A-19「列头即状态行」落地，P-084 → DESIGN D19 / RESEARCH §7.32）：
# 本仓 console 为 8 区块非 kanban（A-73）⇒「列」的最小对应物 = 三档行动队列（状态类别分组，A-21 同源）。
# 列头即状态行 = 词 + 机械计数 + DoR/DoD；DoR/DoD 为 DESIGN §5 状态表与 §5.2 判据表的**档级重投影**
# （与下方 derive_state 分支逐一对应；静态契约、不随数据漂移 ⇒ 不构成第二判定实现，守 I-10 精神）。
# limit / sum **不适用**（三档队列不设容量上限；本仓卡片无数值量纲，sum ≡ count）——显式不声称，防「照抄句式造假读数」。
TIER_CONTRACT = {
    "Needs Attention": (
        "`blocked`；或执行态但无 session（决策链缺失）",
        "阻塞解除（状态列改判）或决策链补齐（首个决策事件落盘）",
    ),
    "Ready to Verify": (
        "最新轮含 gate exit 2（软性存疑）；或五步完整待收（最远 step = `finalize`）",
        "新轮消解存疑（重跑 gate exit 0 或用户裁决）或收束（进已完成段）",
    ),
    "Recommended": (
        "未开工（`pending` 且无决策流）；或推进中（最远 step 未到链尾）",
        "推进至链尾（最远 step = `finalize`）或状态列改判（`blocked` / `done`）",
    ),
}

DONE_TAIL = 8      # 已完成段保留最近 N 条
ACTIVE_CAP = 7     # 活动区卡片上限（RESEARCH A-22：5~7 项）
DESC_CAP = 40      # 描述列单行字符上限（C-9；H6 渲染宽度校准待实测——此值为设计时取值）

# 描述来源优先链（C-9/B6）：制品自身 H1 标题 → 关联 P 行「事项」列 → 目录名。
# 刻意**不引 CODE_WIKI §9 文本**——§9 属派生视图，引用会形成「视图依赖视图」（B6）。
DESC_ARTIFACT_ORDER = ("RESEARCH.md", "DESIGN.md", "CHECKLIST.md", "CHECKLIST_FUNC.md")
DESC_TITLE_PREFIX_CAP = 12   # 「调研文档：」这类前缀冒号的识别窗口

# C-12 架构图「显式关系」口径：
#   ① hook → script（`.pre-commit-config.yaml` 的 entry 直读）
#   ② script → 真值源（**显式架构契约常量**，Layer-0 文档化于 DESIGN §6；不新增采集面）
#   ③ import 边（ast 提取，有则绘、无则不占位）；未能归入①~③的脚本列入「未声明关系」（I-8）
TRUTH_NODES = {
    "TS_md": "docs/**/*.md（契约文档）",
    "TS_m7": "docs/M7_EVIDENCE_LOG.md",
    "TS_view": "CODE_WIKI.md + README + evidence.svg",
    "TS_progress": "docs/PROGRESS.md",
    "TS_sessions": "tools/spec_runner/sessions/",
    "TS_spec": "spec/<feature>/",
    "TS_wiki": "CODE_WIKI.md §9 索引（人工映射标注，C-16 第一来源）",
}
DECLARED_SOURCES = {
    "dc_validator": ("TS_md",),
    "m7_stats": ("TS_m7",),
    "repo_stats": ("TS_view",),
    "console_gen": ("TS_progress", "TS_sessions", "TS_spec", "TS_wiki"),
    "step_enforce": ("TS_progress", "TS_wiki"),
    "spec_map": ("TS_progress", "TS_wiki"),
}
ENTRY_SCRIPT_RE = re.compile(r"scripts/([A-Za-z0-9_]+)\.py")
H1_RE = re.compile(r"^#\s+(\S.*?)\s*$")


@dataclass(frozen=True)
class Task:
    pid: str
    title: str
    status: str
    priority: str


@dataclass(frozen=True)
class SessionInfo:
    sid: str
    last_step: str
    soft: bool
    last_ts: str
    steps: tuple = ()
    # C-14：step 级记录 = (轮次标签, step_id, ts, scenario, outcome)，按「文件名序 → seq 序」稳定排列
    records: tuple = ()


@dataclass(frozen=True)
class Derived:
    status: str      # PROGRESS 原词
    basis: str       # 派生依据（机械可判）
    tier: str        # 行动档（""=无）


# ---------------------------------------------------------------- 解析（只读）

def parse_progress(text: str) -> list:
    """P 行 → Task（列序：ID | 事项 | 依据 | 状态 | 优先级 | 验收标准）。"""
    tasks = []
    for line in text.splitlines():
        if not P_ROW_RE.match(line):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 6:
            continue
        tasks.append(Task(cells[1], cells[2], cells[4], cells[5]))
    return tasks


def read_sessions(sessions_dir: Path) -> dict:
    """每 P：**最新一轮**的最远 step / 软性 / 末 ts / 步序列；并累积**全部轮次**的 step 级记录（C-14）。

    轮次标签 = 该 P 的 `specwf-pNNN-*` 文件按名排序序号（`#1`/`#2`/…）——同源双跑稳定（I-2）。
    """
    out = {}
    if not sessions_dir.is_dir():
        return out
    acc = {}
    for path in sorted(sessions_dir.glob("specwf-p*.jsonl")):
        m = SESSION_PID_RE.match(path.name)
        if not m:
            continue
        pid = m.group(1).upper().replace("P", "P-", 1)  # p043 → P-043
        rows = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # 容错：坏行跳过（DESIGN §7）
        except OSError:
            continue
        last_step, soft, last_ts, steps, recs = "—", False, "—", [], []
        for r in rows:
            ts = r.get("ts")
            if ts:
                last_ts = ts
            if r.get("event") == "decision":
                inp = r.get("input") or {}
                md = inp.get("metadata") or {}
                step = md.get("step_id")
                if step:
                    last_step = step
                    steps.append(step)
                    recs.append((step, ts or "—",
                                 str(inp.get("scenario") or ""), str(inp.get("outcome") or "")))
            if r.get("event") == "gate":
                g = r.get("gate") or {}
                if g.get("exit") == 2:
                    soft = True
        acc.setdefault(pid, []).append((path.stem, last_step, soft, last_ts, tuple(steps), tuple(recs)))
    for pid, rounds in acc.items():
        sid, last_step, soft, last_ts, steps, _ = rounds[-1]
        flat = tuple((i, step, ts, sc, oc)
                     for i, rnd in enumerate(rounds, 1)
                     for (step, ts, sc, oc) in rnd[5])
        out[pid] = SessionInfo(sid, last_step, soft, last_ts, steps, flat)
    return out


def artifact_map(feature_dir: Path) -> dict:
    """四文档存在性（后缀匹配，兼容遗留前缀命名）。"""
    names = [p.name for p in feature_dir.glob("*.md")] if feature_dir.is_dir() else []
    out = {}
    for key, alts in ARTIFACT_ALTS.items():
        out[key] = any(n == a or n.endswith("_" + a) for n in names for a in alts)
    return out


def list_features(spec_dir: Path) -> list:
    if not spec_dir.is_dir():
        return []
    return sorted(n for n in os.listdir(spec_dir)
                  if n != "templates" and (spec_dir / n).is_dir())


def first_h1(path: Path) -> str:
    """文档首个 H1 标题（front-matter 与代码块内的 `#` 均在首个 H1 之后，天然排除）。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = H1_RE.match(line)
            if m:
                return m.group(1)
    except OSError:
        return ""
    return ""


def _strip_tail_group(s: str) -> str:
    """去掉结尾的**配对**括号组（`独立验证（出路 C——…）` → `独立验证`）。"""
    if not s or s[-1] not in "）)":
        return s
    close = s[-1]
    open_ch = "（" if close == "）" else "("
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == close:
            depth += 1
        elif s[i] == open_ch:
            depth -= 1
            if depth == 0:
                return s[:i].rstrip()
    return s


def shorten_title(text: str, cap: int = DESC_CAP) -> str:
    """标题/事项 → 单行主名（C-9）。

    ① 去「调研文档：」类前缀 → ② 交替剥「尾括号组」与断「——」直至稳定 → ③ 截断。
    ② 须交替：`ARC 升级实施（…）——调研输入引用` 与 `独立验证（出路 C——…）` 两种形态都要能收敛。
    """
    s = text.strip()
    for sep in ("：", ":"):
        i = s.find(sep)
        if 0 <= i <= DESC_TITLE_PREFIX_CAP:
            s = s[i + 1:].strip()
            break
    for _ in range(4):
        before = s
        s = _strip_tail_group(s)
        if "——" in s:
            s = s.split("——")[0].strip()
        if s == before:
            break
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > cap:
        s = s[:cap] + "…"
    return s


def feature_desc(feature: str, mapping: dict, tasks_by_pid: dict, spec_dir: Path) -> str:
    """描述来源优先链（C-9/B6）：① 制品 H1 → ② 关联 P 行「事项」→ ③ 目录名。"""
    fdir = spec_dir / feature
    if fdir.is_dir():
        for name in DESC_ARTIFACT_ORDER:
            hits = [p for p in sorted(fdir.glob("*.md"))
                    if p.name == name or p.name.endswith("_" + name)]
            for p in hits:
                cand = shorten_title(first_h1(p))
                if cand:
                    return cand
    task = tasks_by_pid.get(mapping.get(feature, ""))
    if task and task.title:
        cand = shorten_title(task.title)
        if cand:
            return cand
    return feature


# P-068（U-6 裁决 A′，RESEARCH §7.29）：结构性豁免面的统一依据文案。豁免面**无派生输入面**
# ⇒ 派生态下不派生、保原词；**不得**沿用「执行态派生：决策链五步完整」（那会声称一个不存在的证据）。
EXEMPT_BASIS = "结构性豁免面（P-027 不追溯；无决策流）"


def _eff_status(task, sess, derived: bool) -> str:
    """有效状态（P2b，DESIGN §5.3 裁定一/二）：非派生模式 = `PROGRESS` 原词（I-7 现形）；派生模式 = 执行态机器派生。

    DC2.1 值域分流（S-2）：**决策态**（`pending` / `blocked`）不可派生 ⇒ **保留人工原词**；
    **执行态**（`done` / `in-progress`）可派生 ⇒ `done` = 最远 step == `finalize`，否则 `in-progress`。
    **结构性豁免面**（P ≤ P-019，P-027 不追溯）**无派生输入面** ⇒ 落定义域之外，**保原词**（P-068）。
    开关**默认关**（= 现行为，回退点 R-1）；本函数是「迁移盲区」的统一判据——`derive_state` 与三处
    直取 `task.status` 的分区筛（`_active_table` / `_done_table` / `_trace_section`）**同源复用**（防视图分裂，A-61 含义二）。
    """
    if not derived:
        return task.status
    # P-068：豁免面判据**先于**执行态派生（边界单点复用 `spec_map`，不与 `step_enforce` 形成第二实现，守 I-10 / B26）
    if spec_map.is_historical_exempt(task.pid):
        return task.status
    if task.status in ("pending", "blocked"):
        return task.status
    if sess is not None and sess.last_step == "finalize":
        return "done"
    return "in-progress"


def derive_state(task: Task, sess, derived: bool = False) -> Derived:
    """派生状态机（DESIGN §5 / §5.3）：非派生模式状态取 `PROGRESS` 原词（守 I-7），派生的是依据与行动档。

    `derived=True`（P2b 开关）时**执行态第一参照改派生值**（`_eff_status`）——'状态来源迁移'；
    决策态仍为原词。默认 `False` = 现行为（回退点 R-1）。
    """
    st = _eff_status(task, sess, derived)
    if st == "done":
        if not derived:
            basis = "PROGRESS 状态列 = done"
        elif spec_map.is_historical_exempt(task.pid):
            basis = EXEMPT_BASIS          # P-068：豁免面不得声称「五步完整」
        else:
            basis = "执行态派生：决策链五步完整（最远 finalize）"
        return Derived("done", basis, "")
    if st == "blocked":
        return Derived("blocked", "PROGRESS 状态列 = blocked", "Needs Attention")
    if sess is None:
        # P2a（v1.11）：把「未开工（已登记、无决策流）」与「执行态确无 session（决策链缺失）」
        # 分开——前者是正常状态（Recommended），后者才是缺口（Needs Attention）。
        if derived and spec_map.is_historical_exempt(task.pid):
            # P-068：仅**派生态**适用——豁免面既非「未开工」也非「真缺口」⇒ 无行动档，依据如实标豁免；
            # 非派生态保持原判据（「未开工」文案），保 R-1 逐字节一致。
            return Derived(st, EXEMPT_BASIS, "")
        if st == "pending":
            return Derived("pending", "未开工（立项已登记，无决策流）", "Recommended")
        return Derived(st, "执行态但无 session（决策链缺失）", "Needs Attention")
    if sess.soft:
        return Derived(st, f"gate exit 2 软性存疑（最远 {sess.last_step}）", "Ready to Verify")
    if sess.last_step == "finalize":
        # 派生模式下 `finalize` 已在 `_eff_status` 判为 `done`（上方短路）⇒ 本支仅非派生模式可达
        return Derived(st, "决策链五步完整（最远 finalize）", "Ready to Verify")
    return Derived(st, f"最远 step = {sess.last_step}", "Recommended")


def next_step(last_step: str) -> str:
    if last_step in STEP_SEQUENCE:
        i = STEP_SEQUENCE.index(last_step) + 1
        return STEP_SEQUENCE[i] if i < len(STEP_SEQUENCE) else "（链已完整）"
    return "research"


# ---------------------------------------------------------------- 依赖图（D5）

def _known_modules(root: Path) -> set:
    known = set()
    for p in (root / "scripts").glob("*.py"):
        known.add(p.stem)
    known.add("spec_runner")
    return known


def dep_graph(paths, known: set):
    """stdlib ast 静态提边（不执行代码）+ importlib 字面量补提取（RESEARCH A-28）。"""
    edges, dyn = set(), set()
    for p in paths:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top in known and top != p.stem:
                        edges.add((p.stem, top))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in known and top != p.stem:
                        edges.add((p.stem, top))
            elif isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute) and f.attr == "import_module"
                        and isinstance(f.value, ast.Name) and f.value.id == "importlib"
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    top = node.args[0].value.split(".")[0]
                    if top in known and top != p.stem:
                        edges.add((p.stem, top))
                    dyn.add((p.stem, node.args[0].value))
    return sorted(edges), sorted(dyn)


HOOK_ID_RE = re.compile(r"^\s*-\s*id:\s*(\S+)\s*$")
HOOK_FIELD_RE = {
    "name": re.compile(r"^\s*name:\s*(.+?)\s*$"),
    "entry": re.compile(r"^\s*entry:\s*(.+?)\s*$"),
    "files": re.compile(r"^\s*files:\s*(.+?)\s*$"),
    "pass_filenames": re.compile(r"^\s*pass_filenames:\s*(\S+)\s*$"),
}


def hook_chain(path: Path) -> list:
    """极简行式解析 .pre-commit-config.yaml（不引入 YAML 库，I-4）。

    C-13：`name`（人类可读作用）是既有字段，必须取——它是「hook 链看得懂」的主要来源（A-39）。
    """
    if not path.exists():
        return []
    out, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = HOOK_ID_RE.match(line)
        if m:
            cur = {"id": m.group(1), "name": "—", "entry": "—", "files": "—", "pass_filenames": "—"}
            out.append(cur)
            continue
        if cur is None:
            continue
        for key, rx in HOOK_FIELD_RE.items():
            mm = rx.match(line)
            if mm:
                cur[key] = mm.group(1)
                break
    return out


def read_forks(root: Path) -> list:
    """登记返工边（真值源 `docs/rework-graph.json` 的 `forks`）——**确定性**输入。

    取代原 `git branch` 本地枚举（环境态，跨环境不可复现；P-070 追加轮方案 A）。
    **返回原始边对象列表**（U-9 / P-101：既供「⑂ fork / 支线」区渲染名称〔字段 = `new`〕，
    也供行动档映射 P 号——`name` 系 `non_rework` 字段，`forks` 用 `new`）。
    不可读 → 空列表（降级，I-8 显式缺口）。
    """
    try:
        data = json.loads((root / "docs" / "rework-graph.json").read_text(encoding="utf-8"))
        return [f for f in data.get("forks", []) if isinstance(f, dict)]
    except (OSError, ValueError):  # noqa: BLE001 —— 降级
        return []


FORK_ORIGIN_PID_RE = re.compile(r"^specwf-(p\d{3})")


def fork_rewrite_pids(forks: list) -> dict:
    """返工边 → `{P 号: 行动说明}`（U-9，P-101）。

    映射 = 边的 `origin` 会话名（`specwf-p<NNN>-<date>`）→ 该 **P 任务**（= 被推翻的上游）。
    正名 = **「待重写 / 待重入」**（上游文档待重写 + 该回边待重入）。
    只消费返工图**已登记**边（不重实现 `backflow-audit` 的待回写检测，守 I-10）；
    **零边 ⇒ 空 dict ⇒ 行动档逐字节不变**（回归安全）。
    """
    out: dict = {}
    for f in forks:
        m = FORK_ORIGIN_PID_RE.match(str(f.get("origin", "")))
        if not m:
            continue
        pid = "P-" + m.group(1)[1:]
        out.setdefault(pid, f"待重写 / 待重入（返工边 `{f.get('new', '—')}` ← `{f.get('origin', '—')}`）")
    return out


# ---------------------------------------------------------------- 渲染（纯函数）

def _tier_dor(tier: str, derived: bool) -> str:
    """DoR 文案（C-40 Layer-0 首项 / D19）：派生态下 Ready to Verify 的第二进入支
    （最远 step = `finalize`）已由 `_eff_status` 短路归 `done` ⇒ 文案随开关态分流
    （同 I-7 承载位点名族：声明须与开关态实现相符）。"""
    if tier == "Ready to Verify" and derived:
        return "最新轮含 gate exit 2（软性存疑）"
    return TIER_CONTRACT[tier][0]


def _tier_lines(tasks, sessions, derived, fork_pids=None) -> list:
    buckets = {t: [] for t in TIER_ORDER}
    fork_pids = fork_pids or {}
    for t in tasks:
        # U-9（P-101）：已登记返工边的**上游**任务 ⇒ 行动档「待重写 / 待重入」，
        # **先于** `done` 短路（回边存在即不得被 done 遮蔽；零边 ⇒ 本支不触发）
        if t.pid in fork_pids:
            buckets["Needs Attention"].append(f"- **{t.pid}** {t.title} —— {fork_pids[t.pid]}")
            continue
        d = derive_state(t, sessions.get(t.pid), derived)
        if d.tier:
            note = d.basis
            if d.tier == "Recommended" and sessions.get(t.pid):
                note += f"；下一步 = {next_step(sessions[t.pid].last_step)}"
            buckets[d.tier].append(f"- **{t.pid}** {t.title} —— {note}")
    lines = []
    for tier in TIER_ORDER:
        rows = buckets[tier]
        # 列头即状态行（A-19 / D19）：词 + 机械计数（count = len(rows)，声明 = 重数）+ DoR/DoD
        lines.append(f"**{tier}**（{len(rows)} 项）")
        lines.append(f"> DoR：{_tier_dor(tier, derived)} · DoD：{TIER_CONTRACT[tier][1]}")
        lines += rows if rows else ["（无）"]
        lines.append("")
    return lines


def feature_stage(am: dict) -> str:
    """生命周期阶段（由制品存在性推断，RESEARCH A-18 同构）。"""
    for key, label in (("C", "验收"), ("I", "实施"), ("D", "设计"), ("R", "调研")):
        if am[key]:
            return label
    return "未启动"


# ---------------------------------------------------------------- compact 当前状态（P-138 / D.5 方案 D）
COMPACT_STATUS_WORDS = ("done", "pending", "in-progress", "blocked")
COMPACT_STAGE_WORDS = ("调研", "设计", "实施", "验收", "未启动")


def _status_compact(tasks, sessions, features, spec_dir, fork_pids=None,
                    derived=False) -> list:
    """compact「当前状态」块（P-138 / D.5 方案 D）：**逐行纯机械派生，零判断性文案**。

    输入面（D.5 §3 限定）= `PROGRESS` 字节 + sessions 清单 + feature 四文档存在性；
    不新增真值源、不读 wall clock、不读 git（I-2 确定性）。五行分别可用
    `parse_progress` / `read_sessions` / `feature_stage` / `derive_state` 复算——
    行动队列与 §1 三档**同源判据**（`derive_state`+`TIER_ORDER`），防视图分裂（A-61 含义二）。
    """
    counts = {w: 0 for w in COMPACT_STATUS_WORDS}
    other = 0
    for t in tasks:
        if t.status in counts:
            counts[t.status] += 1
        else:
            other += 1
    other_seg = f" · 其他 {other}" if other else ""
    if tasks:
        latest = max(tasks, key=lambda x: int(x.pid[2:]))
        s = sessions.get(latest.pid)
        day = s.last_ts.split("T")[0] if s and s.last_ts != "—" else "—"
        latest_row = f"{latest.pid} {latest.status}（{day}）"
    else:
        latest_row = "—"
    stamps = sorted((s.last_ts, s.sid) for s in sessions.values() if s.last_ts != "—")
    sess_row = (f"{len(sessions)} 个 P（最近 {stamps[-1][1]} · {stamps[-1][0]}）"
                if stamps else "—")
    stages = {w: 0 for w in COMPACT_STAGE_WORDS}
    for name in features:
        stages[feature_stage(artifact_map(spec_dir / name))] += 1
    tiers = {w: 0 for w in TIER_ORDER}
    fork_pids = fork_pids or {}
    for t in tasks:
        if t.pid in fork_pids:
            tiers["Needs Attention"] += 1
            continue
        d = derive_state(t, sessions.get(t.pid), derived)
        if d.tier:
            tiers[d.tier] += 1
    return [
        "| 项 | 值 |",
        "|---|---|",
        f"| 在册批次 | {len(tasks)}（done {counts['done']} · pending {counts['pending']}"
        f" · in-progress {counts['in-progress']} · blocked {counts['blocked']}{other_seg}） |",
        f"| 最近批次 | {latest_row} |",
        f"| session 覆盖 | {sess_row} |",
        "| 行动队列 | " + " · ".join(f"{w} {tiers[w]}" for w in TIER_ORDER) + " |",
        f"| feature 阶段 | {len(features)}（"
        + " · ".join(f"{w} {stages[w]}" for w in COMPACT_STAGE_WORDS) + "） |",
    ]


def _cell(text: str) -> str:
    """表格单元格安全化（C-13 升为**通则**）：半角竖线会破坏表格结构（A-37 的直接成因）。

    凡进入表格单元格的外部文本（含真值源原样字符串）一律过此函数。
    """
    return re.sub(r"\s+", " ", str(text).replace("|", "／")).strip()


def _clip(text: str, cap: int = STEP_CAP) -> str:
    """列表/表格内的长文本截断（C-14；上限为扫描性取值，H6 渲染宽度校准待实测）。"""
    s = re.sub(r"\s+", " ", str(text)).strip()
    if not s:
        return "—"
    return s if len(s) <= cap else s[:cap] + "…"


def _feature_table(features, mapping, sessions, spec_dir, tasks_by_pid) -> list:
    if not features:
        return ["（无）"]
    lines = ["| feature | 描述 | 制品链 R/D/I/C | 阶段 | 关联 P | 最远 step |",
             "|---------|------|---------------|------|--------|----------|"]
    for name in features:
        am = artifact_map(spec_dir / name)
        chain = "".join(("✓" if am[k] else "—") for k in ("R", "D", "I", "C"))
        pid = mapping.get(name, "—")
        s = sessions.get(pid)
        desc = _cell(feature_desc(name, mapping, tasks_by_pid, spec_dir))
        lines.append(f"| {name} | {desc} | {chain} | {feature_stage(am)} | {pid} | {s.last_step if s else '—'} |")
    return lines


def _active_table(tasks, sessions, derived) -> list:
    # P2b（v1.22）迁移盲区 (b)：分区筛改走 `_eff_status`（与 `derive_state` 同源，A-61 含义二）
    active = [t for t in tasks if _eff_status(t, sessions.get(t.pid), derived) != "done"]
    if not active:
        return ["（无——PROGRESS 无活动事项）"]
    shown, hidden = active[:ACTIVE_CAP], active[ACTIVE_CAP:]
    # P2b 实施期发现（第三处 I-7 承载位点，见 IMPLEMENTATION DR-27）：表头文案须随开关态分流，
    # 否则派生态下「状态」列实为派生值却仍标「PROGRESS 原词」＝声明与实现不符
    st_hdr = "状态（PROGRESS 原词）" if not derived else "状态（执行态派生／决策态原词）"
    lines = [f"| P | 事项 | {st_hdr} | 派生依据 | 行动档 |",
             "|---|------|--------------------|---------|--------|"]
    for t in shown:
        d = derive_state(t, sessions.get(t.pid), derived)
        lines.append(f"| {t.pid} | {_cell(t.title)} | `{d.status}` | {_cell(d.basis)} | {d.tier or '—'} |")
    if hidden:
        lines.append(f"| … | **另有 {len(hidden)} 项活动事项已折叠**（活动区上限 {ACTIVE_CAP}） | — | — | — |")
    return lines


def _done_table(tasks, sessions, derived) -> list:
    # P2b（v1.22）迁移盲区 (b)：完成段分区筛改走 `_eff_status`（同源，A-61 含义二）
    done = sorted((t for t in tasks if _eff_status(t, sessions.get(t.pid), derived) == "done"),
                  key=lambda x: x.pid)
    if not done:
        return ["（无）"]
    lines = ["| P | 事项 | 最远 step | 上次事件 | 优先级 |",
             "|---|------|----------|---------|--------|"]
    for t in done[-DONE_TAIL:]:
        s = sessions.get(t.pid)
        ts = s.last_ts.split("T")[0] if s and s.last_ts != "—" else "—"
        lines.append(f"| {t.pid} | {_cell(t.title)} | {s.last_step if s else '—'} | {ts} | {t.priority} |")
    if len(done) > DONE_TAIL:
        lines.append(f"| … | **另有 {len(done) - DONE_TAIL} 条已完成折叠** | — | — | — |")
    return lines


def _state_machine(sessions) -> list:
    counts = {s: 0 for s in STEP_SEQUENCE}
    for info in sessions.values():
        for st in info.steps:
            if st in counts:
                counts[st] += 1
    lines = ["```mermaid", "stateDiagram-v2", "    [*] --> research"]
    for a, b in zip(STEP_SEQUENCE, STEP_SEQUENCE[1:]):
        lines.append(f"    {a} --> {b}")
    lines.append("    finalize --> [*]")
    lines.append("```")
    lines.append("")
    lines.append("各 step 到达数（由 sessions 决策链机械重数）："
                 + " / ".join(f"{k} {counts[k]}" for k in STEP_SEQUENCE))
    return lines


def _arch_section(edges, dyn, hooks, declared, script_names) -> list:
    """架构与流程（C-12「显式关系」口径）。

    ① hook → script（entry 直读）② script → 真值源（显式契约常量）③ import 边（有则绘）。
    归不入①②③的脚本列入「未声明关系」——**显式缺口优于静默省略**（I-8）。
    """
    hook_edges, hooked = [], set()
    for h in hooks:
        m = ENTRY_SCRIPT_RE.search(h.get("entry", ""))
        if m:
            hook_edges.append((h["id"], m.group(1)))
            hooked.add(m.group(1))
    src_edges = [(a, b) for a, deps in sorted(declared.items()) if a in set(script_names)
                 for b in deps]
    import_nodes = {n for e in edges for n in e}

    lines = ["```mermaid", "flowchart LR"]
    drawn = False
    for hid, script in hook_edges:
        nid = "H_" + hid.replace("-", "_")
        lines.append(f'    {nid}["hook · {hid}"] --> {script}[{script}]')
        drawn = True
    for a, b in src_edges:
        lines.append(f'    {a}[{a}] --> {b}["{TRUTH_NODES.get(b, b)}"]')
        drawn = True
    for a, b in edges:
        lines.append(f"    {a} --> {b}")
        drawn = True
    if not drawn:
        lines.append("    none[（无可绘关系）]")
    lines.append("```")
    lines.append("")
    lines.append("> 口径（RESEARCH C-12）：① `hook → script`（entry 直读）"
                 "② `script → 真值源`（**显式架构契约**，Layer-0 声明于 DESIGN §6）"
                 "③ `import` 边（`ast` 提取，**有则绘、无则不占位**）。")
    lines.append("- **仓内 import 边**："
                 + ("；".join(f"`{a}` → `{b}`" for a, b in edges) if edges else "（无仓内 import 边）"))
    lines.append("- **动态 import（字面量补提取）**："
                 + ("；".join(f"{a} → `{b}`" for a, b in dyn) if dyn else "（无）"))
    undeclared = [s for s in script_names
                  if s not in hooked and s not in declared and s not in import_nodes]
    lines.append("- **未声明关系的脚本（I-8 显式缺口）**："
                 + ("、".join(f"`{s}`" for s in undeclared) if undeclared else "（无）"))
    lines.append("- **hook 链**（`.pre-commit-config.yaml` 直读）：")
    lines.append("")
    lines.extend(_hook_list(hooks))
    return lines


def _hook_list(hooks) -> list:
    """hook 链（C-13）：**逐 hook 列表块**（弃表格）。

    形态理由（A-37 / A-38）：表格单元格按内容取宽，长无断点 token（正则）既撑宽本列又把后续列
    挤到 5–10px；且未转义竖线会被 GFM 当列分隔符而**破坏表格结构**。列表块让长 token 独占一行，
    从形态上同时消除这两类缺陷。
    """
    if not hooks:
        return ["- （不可读：`.pre-commit-config.yaml` 缺失或解析为空）"]
    lines = []
    for h in hooks:
        pf = h.get("pass_filenames", "—")
        if pf == "—":
            pf_txt = "未设（pre-commit 默认「是」）"
        else:
            pf_txt = {"true": "是", "false": "否"}.get(pf, pf)
        lines.append(f"- **{h['id']}** —— {h.get('name', '—')}")
        lines.append(f"  - 命令：`{h['entry']}`")
        lines.append(f"  - 触发范围（`files` 正则）：`{h['files']}`")
        lines.append(f"  - 传入文件名（`pass_filenames`）：{pf_txt}")
    return lines


def _feature_process_section(features, mapping, sessions, spec_dir, tasks_by_pid, derived) -> list:
    """per-feature 流程（C-10）：锚点目录 + 每 feature 一个默认折叠的 `<details>`。

    收敛策略（RESEARCH H7 待实测）：仅对「四文档不全 **或** 有关联 session」的 feature 出图，
    其余保留 §2 行——避免展开面无限膨胀。
    """
    picked = []
    for name in features:
        am = artifact_map(spec_dir / name)
        pid = mapping.get(name, "—")
        if not all(am.values()) or pid in sessions:
            picked.append((name, am, pid))
    if not picked:
        return ["（无）"]

    lines = [
        "> **默认展示上方「项目级」架构与流程**；下列 per-feature 流程各自独立折叠，"
        "点击摘要行展开。交互形态 = Markdown 原生折叠元素（`details` / `summary`）+ 锚点跳转，"
        "**不含 Mermaid `click`**（C-10：默认 `strict` 禁用，`loose` 属 XSS 载体）。",
        "",
        "锚点目录：" + " · ".join(f"[{n}](#feat-{n})" for n, _, _ in picked),
        "",
    ]
    for name, am, pid in picked:
        s = sessions.get(pid)
        task = tasks_by_pid.get(pid)
        d = derive_state(task, s, derived) if task else Derived("—", "无关联 P（映射缺口，见 §2「—」）", "")
        flow = " --> ".join(
            f'{k}["{label} {"✓" if am[k] else "—"}"]'
            for k, label in (("R", "RESEARCH"), ("D", "DESIGN"),
                             ("I", "IMPLEMENTATION"), ("C", "CHECKLIST")))
        rounds = max((rec[0] for rec in s.records), default=0) if s else 0
        tail = f" ｜ {rounds} 轮" if rounds > 1 else ""
        lines += [
            # C-15：锚点**双属性** `<a name=… id=…>`——覆盖「只认 name」（GitHub 官方背书，
            # 但不进 outline/TOC）与「只认 id」（HTML5 标准；GitHub 是否剥离存在冲突证据）两类
            # 渲染器；若宿主两者皆剥离，退化为「可折叠但不可跳转」（H8 真机存活率待验）。
            f'<a name="feat-{name}" id="feat-{name}"></a>',
            "<details>",
            f"<summary><b>{name}</b> ｜ {feature_stage(am)} ｜ {pid}{tail}</summary>",
            "",
            f"**派生状态**：`{d.status}` —— {d.basis}" + (f" · 行动档：{d.tier}" if d.tier else ""),
            "",
            "```mermaid",
            "flowchart LR",
            f"    {flow}",
            "```",
            "",
            "**步骤级动态描述**（C-14；来源 = 决策链事件流）：",
            "",
        ]
        lines += _step_table(s.records if s else (), am)
        lines += [
            "",
            "**决策链**（sessions 机械重数）："
            + (" → ".join(s.steps) if s and s.steps else "（无 session——决策链缺失）"),
            "",
            "</details>",
            "",
        ]
    return lines


def _step_table(records, am) -> list:
    """步骤级动态描述（C-14）：步骤 | 制品 | 主题 | 创建时间 | 简要描述 | 修改历史。

    来源链（C-14）：主题 ①`step.scenario`；创建时间 ①`step.ts`；简要描述 ①`step.outcome`；
    修改历史 = 该 step 在**各轮 session** 中的出现（轮次 + 日期）；同 step 多轮时**最新一轮胜出**。
    无 session → 单行**显式缺失**（I-8：不用稀薄的文档元数据「补得像有」）。
    """
    if not records:
        return ["`—` 无 session——**主题 / 创建时间 / 简要描述 / 修改历史 全缺**（决策链缺失，I-8）"]
    by_step = {}
    for rnd, step, ts, sc, oc in records:
        by_step.setdefault(step, []).append((rnd, ts, sc, oc))
    lines = ["| 步骤 | 制品 | 主题（本步做什么） | 创建时间 | 简要描述（本步结论） | 修改历史 |",
             "|------|------|--------------------|---------|--------------------|---------|"]
    for step in [s for s in STEP_SEQUENCE if s in by_step]:
        items = by_step[step]
        _, ts, sc, oc = items[-1]
        key, art = STEP_ARTIFACT.get(step, ("", "—"))
        art_cell = art if not key else f"{art} {'✓' if am.get(key) else '—'}"
        hist = " · ".join(f"#{r} {str(t)[:10]}" for r, t, _, _ in items)
        if len(items) > 1:
            hist = f"{len(items)} 轮：{hist}"
        lines.append("| " + " | ".join([
            _cell(step), _cell(art_cell), _cell(_clip(sc)),
            _cell(_fmt_ts(ts)), _cell(_clip(oc)), _cell(hist),
        ]) + " |")
    return lines


def _fmt_ts(ts) -> str:
    """`2026-09-11T15:00:00+08:00` → `2026-09-11 15:00`（不动其他形态）。"""
    s = str(ts)
    return s[:16].replace("T", " ") if len(s) >= 16 and s[10:11] == "T" else s


def _trace_section(tasks, sessions, features, mapping, derived) -> list:
    """§6 追溯覆盖：决策链完整性 + **缺映射清单**（I-8 显式缺口，C-16 ④ 要求「计入 §6」）。"""
    # P2b（v1.22）迁移盲区 (b)：活动集分区筛改走 `_eff_status`（同源，A-61 含义二）
    active = [t for t in tasks if _eff_status(t, sessions.get(t.pid), derived) != "done"]
    with_sess = [t for t in active if t.pid in sessions]
    complete = [t for t in with_sess if sessions[t.pid].last_step == "finalize"]
    # P2a（v1.11 / DR-23）：无 session 项按派生行动档分流——「pending = 未开工」不是缺口，
    # 与「执行态确无 session = 真缺口」分列，避免 §6 与行动档自相矛盾（I-8：两类都显式列出）
    no_sess = [t for t in active if t.pid not in sessions]
    gaps = [t.pid for t in no_sess if derive_state(t, None, derived).tier == "Needs Attention"]
    # P-068（U-6 裁决 A′）：无 session 项须**三分**——真缺口（Needs Attention）/ 未开工（Recommended）/
    # 结构性豁免面（tier=""，由下方豁免行单列）⇒ idle 判据由「非 Needs Attention」收窄为「== Recommended」，
    # 否则豁免面会被静默并入「未开工」清单（与豁免行自相矛盾）。
    idle = [t.pid for t in no_sess if derive_state(t, None, derived).tier == "Recommended"]
    # C-16 ④ / I-8：映射缺位（两源皆无）必须在此**显式列出**，不得静默省略
    unmapped = [f for f in features if f not in mapping]
    unmapped_line = ("- **缺映射（I-8 显式缺口）**：" + "、".join(f"`{f}`" for f in unmapped)
                     if unmapped
                     else f"- **缺映射（I-8 显式缺口）**：（无——{len(features)} 个 feature 全部有映射）")
    lines = [
        f"- 活动事项 {len(active)} / 有 session {len(with_sess)} / 五步完整 {len(complete)}",
        (f"- **决策链缺失（Needs Attention）**：{'、'.join(gaps)}" if gaps else "- 决策链缺失：无"),
        (f"- **未开工（立项已登记，无决策流）**：{'、'.join(idle)}" if idle
         else "- 未开工（立项已登记，无决策流）：无"),
    ]
    # P-068（U-6 裁决 A′，RESEARCH §7.29）：结构性豁免面**仅在派生态**显式登记（I-8 不静默省略）；
    # 非派生态不 emit ⇒ 默认输出与改造前逐字节一致（R-1 / I-2 / I-3）。
    if derived:
        exempt = [t.pid for t in tasks if spec_map.is_historical_exempt(t.pid)]
        lines.append(
            f"- **结构性豁免面（I-8 显式登记）**：{'、'.join(exempt)} 共 {len(exempt)} 条"
            "（P-027 不追溯，无决策流 ⇒ 依 B22 排除出派生态）" if exempt
            else "- 结构性豁免面（I-8 显式登记）：无")
    lines.append(unmapped_line)
    lines.append(
        "- 证据账本与三通道真值不在此复制（I-6 不增真值）："
        "[M7 证据账本](./M7_EVIDENCE_LOG.md)（由 `scripts/m7_stats.py` 看护）；"
        "契约/命名空间/视图层对账见 `scripts/dc_validator.py` + `scripts/repo_stats.py`")
    return lines


def _basis(tasks, sessions, features) -> str:
    ts = [s.last_ts for s in sessions.values() if s.last_ts and s.last_ts != "—"]
    return (f"源最大 ts = {max(ts) if ts else '—'}；"
            f"P 行 = {len(tasks)}；session = {len(sessions)}；feature = {len(features)}")


def render(tasks, sessions, features, mapping, edges, dyn, hooks, forks, spec_dir,
           tasks_by_pid, script_names, derived=False) -> str:
    # I-7（P2b 件③，只加不删）：开关关闭时本行与现行为**逐字节一致**；开启时**追加**执行态派生条款
    i7_line = "> 状态词表 = PROGRESS 原词（I-7）；本视图不重贴标签，只补派生依据与行动档"
    if derived:
        i7_line += "；**执行态**（`done` / `in-progress`）采**机器派生**（DC2.1 值域分流），**决策态**（`pending` / `blocked`）仍为 `PROGRESS` 原词"
    out = [
        "# CONSOLE｜项目控制台（派生视图）",
        "<!-- GENERATED by scripts/console_gen.py —— 纯派生产物，请勿手改；重跑即刷新 -->",
        f"> 生成基准：{_basis(tasks, sessions, features)}",
        i7_line,
        "",
        "## 当前状态（compact）",
    ]
    out += _status_compact(tasks, sessions, features, spec_dir,
                           fork_rewrite_pids(forks), derived)
    out += ["", "## ⚑ 需要你 / NEXT"]
    out += _tier_lines(tasks, sessions, derived, fork_rewrite_pids(forks))
    out += ["## feature 视图（分组键）"]
    out += _feature_table(features, mapping, sessions, spec_dir, tasks_by_pid)
    out += ["", f"## 事项视图（卡片键 · 活动区上限 {ACTIVE_CAP}）"]
    out += _active_table(tasks, sessions, derived)
    out += ["", "## 决策链状态机"]
    out += _state_machine(sessions)
    out += ["", "## 架构与流程"]
    out += _arch_section(edges, dyn, hooks, DECLARED_SOURCES, script_names)
    out += ["", "### per-feature 流程（默认折叠）"]
    out += _feature_process_section(features, mapping, sessions, spec_dir, tasks_by_pid, derived)
    out += ["", "## 追溯覆盖"]
    out += _trace_section(tasks, sessions, features, mapping, derived)
    out += ["", f"## ✅ 已完成（最近 {DONE_TAIL} 条）"]
    out += _done_table(tasks, sessions, derived)
    out += ["", "## ⑂ fork / 支线"]
    out += ["- 本地分支属**环境态**，不纳入派生视图（保证跨环境可复现；P-070 追加轮方案 A）",
            "- 回写支线真值源见 `docs/rework-graph.json`"]
    out += [f"- 登记返工支线：{f.get('new', '—')}" for f in forks] if forks else ["- 登记返工支线：（无）"]
    out += [""]
    return "\n".join(out)


# ---------------------------------------------------------------- 写盘（幂等）

def write_console(path: Path, content: str) -> bool:
    """内容未变则不写（I-3）；返回是否发生写入。"""
    old = None
    if path.exists():
        try:
            old = path.read_text(encoding="utf-8")
        except OSError:
            old = None
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def _stage(root: Path, rel: str) -> bool:
    try:
        p = subprocess.run(["git", "-C", str(root), "add", "--", rel],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _read_text(path: Path) -> str:
    """容错读文本（不可读 → 空串）：用于**可选**真值源（如 CODE_WIKI §9 映射标注）。

    退化必须显式可见（I-8）：缺 §9 标注时映射退回 PROGRESS 兜底，缺位在视图里以 `—` 呈现。
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def build(root: Path = ROOT, derived: bool = False) -> str:
    """从真值源构建控制台文本（纯读 + 纯函数）。"""
    try:
        prog = (root / "docs" / "PROGRESS.md").read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"PROGRESS.md 不可读：{e}") from e
    tasks = parse_progress(prog)
    tasks_by_pid = {t.pid: t for t in tasks}
    # C-16/I-10：映射唯一来源 = spec_map（§9 行标注优先 → PROGRESS 兜底 → `—`）
    mapping = spec_map.build_pid_map(prog, _read_text(root / "CODE_WIKI.md"))
    sessions = read_sessions(root / "tools" / "spec_runner" / "sessions")
    spec_dir = root / "spec"
    features = list_features(spec_dir)
    scripts = sorted((root / "scripts").glob("*.py"))
    runner = root / "tools" / "spec_runner" / "spec_runner.py"
    paths = scripts + ([runner] if runner.exists() else [])
    script_names = sorted(p.stem for p in scripts) + (["spec_runner"] if runner.exists() else [])
    edges, dyn = dep_graph(paths, _known_modules(root))
    hooks = hook_chain(root / ".pre-commit-config.yaml")
    forks = read_forks(root)
    return render(tasks, sessions, features, mapping, edges, dyn, hooks, forks, spec_dir,
                  tasks_by_pid, script_names, derived)


# ---------------------------------------------------------------- selftest

MINI_PROGRESS = """# Mini Progress

| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |
|----|------|------|------|--------|---------|
| P-001 | alpha 已完成 | — | done | — | ok |
| P-002 | beta 无 session | — | pending | — | ok |
| P-003 | gamma 进行中 | — | in-progress | — | ok |
| P-004 | delta 阻塞 | — | blocked | — | ok |
| P-005 | eps 软性存疑 | — | in-progress | — | ok |
| P-006 | zeta 完成待收 | — | in-progress | — | ok |
| P-007 | eta 活动 7 | — | pending | — | ok |
| P-008 | theta 活动 8 | — | pending | — | ok |
| P-009 | iota 活动 9 | — | pending | — | ok |
| P-010 | kappa 制品链 | [spec/alpha/](../spec/alpha/RESEARCH.md) | pending | — | ok |
| P-011 | beta 无制品目录（描述走 P 行回退） | [spec/beta/](../spec/beta/DESIGN.md) | pending | — | ok |
"""

# C-16 fixture：§9 索引行 = 映射**第一来源**（人工标注）。alpha 与 PROGRESS 一致（保持既有断言稳定）；
# epsilon 仅 §9 有标注 → 用于断言「§9 补 PROGRESS 映射洞」（真实仓对应 4 个空洞 → 0）。
MINI_CODE_WIKI = """# Mini Code Wiki

## 9. 文档索引

| 文件 | 一句话定位 |
|------|-----------|
| [spec/alpha/](./spec/alpha/) | P-010 alpha 制品链行（与 PROGRESS 标注一致） |
| [spec/epsilon/](./spec/epsilon/) | P-009 epsilon 仅 §9 有标注（补 PROGRESS 洞） |
| [spec/templates/RESEARCH_TEMPLATE.md](./spec/templates/RESEARCH_TEMPLATE.md) | Step 2 调研文档模板 |

## 10. 机读声明块（stats）

```json
{}
```
"""

MINI_HOOKS = """repos:
  - repo: local
    hooks:
      - id: demo-hook
        name: demo
        entry: python scripts/mod_a.py
        language: system
        files: \\.md$
      - id: demo-hook-2
        name: demo2
        entry: python scripts/mod_b.py --stage
        language: system
        pass_filenames: false
        files: ^docs/
"""


def _mini_session(pid: str, steps, soft: bool = False, tag: str = "") -> str:
    """迷你 session（C-14：每 step 独立 ts + scenario/outcome；scenario 内嵌半角竖线用于安全化断言）。"""
    stem = f"specwf-{pid}-20260911{tag}"
    rows = []
    for i, st in enumerate(steps, 1):
        rows.append({
            "ts": f"2026-09-11T{10 + i:02d}:00:00+08:00", "seq": i, "session": stem,
            "source": "assistant", "model": None, "provider": None, "event": "decision",
            "input": {"category": "c", "scenario": f"{st} 主题{tag}|注", "reasoning": "r",
                      "outcome": f"{st} 结论{tag}", "confidence": 0.9,
                      "metadata": {"step_id": st, "step_seq": STEP_SEQUENCE.index(st) + 1,
                                   "evidence": [{"grade": "E1", "anchor": "spec/x/DESIGN.md"}]}},
            "output": None, "gate": None})
    if soft:
        rows.append({
            "ts": "2026-09-11T09:05:00+08:00", "seq": len(rows) + 1,
            "session": stem, "source": "gate", "model": None, "provider": None,
            "event": "gate", "input": None, "output": None,
            "gate": {"name": "g", "cmd": "x", "exit": 2, "verdict": "fail", "stdout_tail": ""}})
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"


def _build_mini() -> Path:
    root = Path(tempfile.mkdtemp(prefix="console_gen_selftest_"))
    for d in ("docs", "tools/spec_runner/sessions", "spec/templates",
              "spec/alpha", "spec/beta", "spec/gamma", "spec/epsilon", "scripts"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "docs" / "PROGRESS.md").write_text(MINI_PROGRESS, encoding="utf-8")
    (root / "CODE_WIKI.md").write_text(MINI_CODE_WIKI, encoding="utf-8")
    sess = root / "tools" / "spec_runner" / "sessions"
    (sess / "specwf-p003-20260911.jsonl").write_text(
        _mini_session("p003", ("research", "design")), encoding="utf-8")
    (sess / "specwf-p005-20260911.jsonl").write_text(
        _mini_session("p005", ("research",), soft=True), encoding="utf-8")
    (sess / "specwf-p006-20260911.jsonl").write_text(
        _mini_session("p006", STEP_SEQUENCE), encoding="utf-8")
    # 多轮 fixture（C-14 修改历史）：p011 两轮——轮 1 到 design，轮 2 到 implement（末轮胜出）
    (sess / "specwf-p011-20260911.jsonl").write_text(
        _mini_session("p011", ("research", "design")), encoding="utf-8")
    (sess / "specwf-p011-20260911v2.jsonl").write_text(
        _mini_session("p011", ("research", "design", "implement"), tag="v2"), encoding="utf-8")
    # 制品链 fixture：alpha 仅 RESEARCH（H1 用于描述列 C-9）；beta 无制品（回退 P 行）；gamma 无任何来源
    (root / "spec" / "alpha" / "RESEARCH.md").write_text(
        "# 调研文档：alpha 功能——演示用（P-010）\n", encoding="utf-8")
    # 依赖图 fixture：mod_a 静态 import mod_b；mod_b 动态 importlib 字面量 mod_a；mod_c 无任何关系
    (root / "scripts" / "mod_a.py").write_text("import mod_b\n", encoding="utf-8")
    (root / "scripts" / "mod_b.py").write_text(
        "import importlib\nimportlib.import_module(\"mod_a\")\n", encoding="utf-8")
    (root / "scripts" / "mod_c.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(MINI_HOOKS, encoding="utf-8")
    return root


def run_selftest() -> int:
    failures, total, passed = [], 0, 0

    def check(name, cond):
        nonlocal total, passed
        total += 1
        passed += 1 if cond else 0
        if not cond:
            failures.append(name)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    print("console_gen selftest:")
    import shutil

    root = _build_mini()
    text = build(root)

    check("S1 P 行解析（11 条）", len(parse_progress(MINI_PROGRESS)) == 11)
    check("S2 词表对齐（含原词 pending，且不含升格标签）",
          "`pending`" in text and "待你审" not in text)
    check("S3 三级行动队列（Needs Attention / Ready to Verify / Recommended）",
          all(t in text for t in TIER_ORDER)
          and "**P-004** delta 阻塞" in text
          and "软性存疑" in text
          and "下一步 = implement" in text)
    check("S4 feature 视图含描述列 + 制品链投影（✓——— 且阶段=调研）",
          "| alpha | alpha 功能 | ✓——— | 调研 | P-010 | — |" in text)
    check(f"S5 活动区上限（上限 {ACTIVE_CAP} + 折叠提示）",
          f"另有 3 项活动事项已折叠" in text)
    check("S6 决策链 Mermaid（stateDiagram-v2 + 五步）",
          "stateDiagram-v2" in text and "verify --> finalize" in text)
    check("S7 依赖图 Mermaid（flowchart LR + 仓内边）",
          "flowchart LR" in text and "mod_a --> mod_b" in text)
    check("S8 动态 import 字面量补提取（mod_b → mod_a）",
          "mod_a" in text and "动态 import（字面量补提取）" in text
          and "mod_b → `mod_a`" in text)
    check("S9 hook 链解析（2 条 + name 作用 + pass_filenames 可读化）",
          "**demo-hook-2** —— demo2" in text
          and "传入文件名（`pass_filenames`）：否" in text
          and "传入文件名（`pass_filenames`）：未设（pre-commit 默认「是」）" in text)
    check("S10 禁 wall clock（基准取源最大 ts）",
          "源最大 ts = 2026-09-11T15:00:00+08:00" in text)
    check("S11 纯派生标注（请勿手改）", "请勿手改" in text)

    target = root / "docs" / "CONSOLE.md"
    first = write_console(target, text)
    second = write_console(target, text)
    check("S12 幂等（首写 True / 二次 False）", first and not second)
    check("S13 确定性（双跑字节一致）", build(root) == build(root))

    before = target.read_text(encoding="utf-8")
    target.write_text("SENTINEL", encoding="utf-8")
    main(["--stdout", "--root", str(root)])
    check("S14 --stdout 不写盘", target.read_text(encoding="utf-8") == "SENTINEL")
    target.write_text(before, encoding="utf-8")

    rc_ok = main(["--check", "--root", str(root)])
    target.write_text("STALE", encoding="utf-8")
    rc_stale = main(["--check", "--root", str(root)])
    check("S15 --check（一致 exit 0 / 过期 exit 1）", rc_ok == 0 and rc_stale == 1)

    snap = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "CONSOLE.md"}
    write_console(target, text + "\n<!-- touch -->")
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != "CONSOLE.md"}
    check("S16 I-1 单写路径（其余文件零变化）", snap == after)

    check("S17 描述列 H1 主名提取（去「调研文档：」前缀 + 断「——」+ 去尾括号）",
          "| alpha | alpha 功能 |" in text)
    check("S18 描述回退链②（无制品 → 关联 P 行「事项」列）",
          "| beta | beta 无制品目录 |" in text)
    check("S19 描述回退链③（无映射 → 目录名）", "| gamma | gamma |" in text)
    check("S20 per-feature 折叠（锚点目录 + <details> 双属性锚 + summary 三段式）",
          "[alpha](#feat-alpha)" in text
          and '<a name="feat-alpha" id="feat-alpha"></a>' in text
          and "<summary><b>alpha</b> ｜ 调研 ｜ P-010</summary>" in text)
    check("S21 默认项目级在前（§5 架构与流程 先于 §5.1 per-feature）",
          text.index("## 架构与流程") < text.index("### per-feature 流程"))
    check("S22 排除 Mermaid click（无 click 指令行）",
          not any(l.strip().startswith("click") for l in text.splitlines()))
    mini_arch = "\n".join(_arch_section(
        [], [], [{"id": "demo-hook", "entry": "python scripts/mod_a.py",
                  "files": "—", "pass_filenames": "—"}],
        {"mod_a": ("TS_progress",)}, ["mod_a", "mod_b"]))
    check("S23 C-12 ①hook→script ②script→真值源",
          'H_demo_hook["hook · demo-hook"] --> mod_a[mod_a]' in text
          and 'mod_a[mod_a] --> TS_progress["docs/PROGRESS.md"]' in mini_arch)
    check("S24 I-8 显式缺口（未声明关系的脚本清单）",
          "**未声明关系的脚本（I-8 显式缺口）**：`mod_c`" in text)
    check("S25 per-feature 流程图含四文档管道节点",
          'R["RESEARCH ✓"] --> D["DESIGN —"]' in text)
    check("S26 描述主名收敛（尾括号组 ×「——」交替剥）",
          shorten_title("调研文档：独立验证（出路 C——审查臂查系统真实状态）") == "独立验证"
          and shorten_title("调研文档：ARC 升级实施（吃狗粮模式，P-035）——调研输入引用") == "ARC 升级实施"
          and shorten_title("调研文档：项目控制台——可视化看板剥离与视图分层（P-042）") == "项目控制台")
    check(f"S27 描述截断上限（{DESC_CAP} + 省略号）",
          len(shorten_title("x" * 100)) == DESC_CAP + 1
          and shorten_title("x" * 100).endswith("…"))

    check("S28 hook 链改列表块（弃表格：hook 表头不复存在）",
          "| # | id | entry |" not in text
          and "- 命令：`python scripts/mod_a.py`" in text
          and "- 触发范围（`files` 正则）：`\\.md$`" in text)
    check("S29 步骤级动态描述表头（C-14 六列）",
          "| 步骤 | 制品 | 主题（本步做什么） | 创建时间 | 简要描述（本步结论） | 修改历史 |" in text)
    beta_row = "| research | RESEARCH.md — | research 主题v2／注 | 2026-09-11 11:00 | research 结论v2 | 2 轮：#1 2026-09-11 · #2 2026-09-11 |"
    check("S30 步骤表内容（最新一轮胜出 + 制品列 + 时间格式化 + 多轮历史）", beta_row in text)
    check("S31 无 session → 四字段显式缺失（I-8）",
          "无 session——**主题 / 创建时间 / 简要描述 / 修改历史 全缺**（决策链缺失，I-8）" in text)
    step_rows = [ln for ln in text.splitlines() if ln.startswith("| research | RESEARCH.md")]
    check("S32 单元格安全化通则（半角竖线→全角 + 列数守恒 6）",
          bool(step_rows) and all(len(ln.split("|")) - 2 == 6 for ln in step_rows))
    check("S33 多轮轮次进摘要（第 2 轮计数）",
          "<summary><b>beta</b> ｜ 未启动 ｜ P-011 ｜ 2 轮</summary>" in text)
    check("S34 时间格式化与截断（单元）",
          _fmt_ts("2026-09-11T15:00:00+08:00") == "2026-09-11 15:00"
          and _clip("") == "—"
          and len(_clip("x" * 100)) == STEP_CAP + 1
          and _clip("x" * 100).endswith("…"))
    check("S35 映射唯一实现与优先级（C-16/I-10：§9 行标注优先 → PROGRESS 兜底 → 皆无不入表）",
          spec_map.build_pid_map("| P-001 | x | [spec/a/](y) |",
                                 "## 9. 文档索引\n| [spec/a/](z) | P-002 标注 |\n## 10.\n") == {"a": "P-002"}
          and spec_map.build_pid_map("| P-001 | x | [spec/a/](y) |", "") == {"a": "P-001"}
          and spec_map.build_pid_map("| P-001 | x | — |", "") == {}
          and not hasattr(sys.modules[__name__], "feature_pid_map"))
    check("S36 §9 行标注补 PROGRESS 映射洞（C-16：§9 独有 → 关联 P 非 `—`）",
          "| epsilon | iota 活动 9 | ———— | 未启动 | P-009 | — |" in text)
    check("S37 §6 缺映射清单（I-8 显式缺口：有缺口列出 / 无缺口显式标无）",
          "- **缺映射（I-8 显式缺口）**：`gamma`" in text
          and any("（无——1 个 feature 全部有映射）" in ln for ln in
                  _trace_section([], {}, ["a"], {"a": "P-001"}, False)))

    _S = SessionInfo("specwf-p900", "design", False, "2026-09-11T10:00:00+08:00",
                    ("research", "design"), ())
    _d1 = derive_state(Task("P-900", "未开工项", "pending", "—"), None)
    _d2 = derive_state(Task("P-901", "未开工但已入流", "pending", "—"), _S)
    _d3 = derive_state(Task("P-902", "已完成项", "done", "—"), None)
    _d4 = derive_state(Task("P-903", "执行中但确无 session", "in-progress", "—"), None)
    check("S38 pending 且无 session → tier=Recommended（未开工，非缺口；A-55/F25）",
          _d1.status == "pending" and _d1.tier == "Recommended" and "未开工" in _d1.basis)
    check("S39 pending 且有 session → 走既有分支（Recommended，行为与拆支前一致；F26）",
          _d2.tier == "Recommended" and "最远 step" in _d2.basis)
    check("S40 done 无 session → 首分支短路早退 + 执行态无 session 仍判缺口（A-55/F27）",
          _d3.status == "done" and _d3.tier == "" and _d3.basis == "PROGRESS 状态列 = done"
          and _d4.tier == "Needs Attention" and "执行态" in _d4.basis)
    check("S41 §6 缺口行按行动档分流（DR-23：未开工与真缺口分列，二者皆显式列出）",
          "- **决策链缺失（Needs Attention）**：P-004" in text
          and "- **未开工（立项已登记，无决策流）**：P-002、P-007、P-008、P-009、P-010" in text)

    # --- P2b（v1.22）：状态来源迁移开关（件①）+ I-7 扩写（件③）---
    _S_full = SessionInfo("specwf-p902", "finalize", False, "2026-09-11T15:00:00+08:00",
                          STEP_SEQUENCE, ())
    check("S42 默认关 = 现行为（回退点 R-1）：build(root) 与显式 derived=False 逐字节一致",
          build(root, derived=False) == text and build(root, derived=True) != text)
    _d5 = derive_state(Task("P-904", "链已完整但状态列非 done", "in-progress", "—"), _S_full, True)
    check("S43 派生臂：执行态第一参照改派生值（最远 finalize ⇒ state=done，非 task.status；件①）",
          _d5.status == "done" and _d5.tier == "" and "执行态派生" in _d5.basis)
    _d6 = derive_state(Task("P-905", "阻塞项", "blocked", "—"), None, True)
    _d7 = derive_state(Task("P-906", "未开工项", "pending", "—"), None, True)
    check("S44 派生臂：决策态保原词（blocked / pending 人工面不可派生，守 DC2.1 S-2 与 I-7）",
          _d6.status == "blocked" and _d6.tier == "Needs Attention"
          and _d7.status == "pending" and _d7.tier == "Recommended")
    _d8 = derive_state(Task("P-907", "done 但确无证据", "done", "—"), None, True)
    _t_done_nosess = Task("P-908", "done 无 session", "done", "—")
    _t_cap = Task("P-909", "P 行状态列滞后", "in-progress", "—")
    check("S45 派生臂：执行态未 finalize ⇒ in-progress（done 无 session 暴露为缺口）+ `_eff_status` 为 (b) 同源唯一判据",
          _d8.status == "in-progress" and _d8.tier == "Needs Attention"
          and _eff_status(_t_done_nosess, None, True) == "in-progress"
          and _eff_status(_t_cap, _S_full, True) == "done"
          and _eff_status(_t_cap, _S_full, False) == "in-progress")
    text_d = build(root, derived=True)
    check("S46 I-7 扩写（只加不删）：原声明句保留 + 追加执行态派生条款 + §3 表头随开关态分流（件③）",
          "> 状态词表 = PROGRESS 原词（I-7）；本视图不重贴标签，只补派生依据与行动档" in text
          and "> 状态词表 = PROGRESS 原词（I-7）；本视图不重贴标签，只补派生依据与行动档；" in text_d
          and "采**机器派生**（DC2.1 值域分流）" in text_d
          and "状态（PROGRESS 原词）" in text and "状态（执行态派生／决策态原词）" in text_d)
    _tgt2 = root / "docs" / "CONSOLE_D.md"
    _w1 = write_console(_tgt2, text_d)
    _w2 = write_console(_tgt2, text_d)
    check("S47 派生态确定性与幂等（I-2 双跑一致 / I-3 首写 True 二次 False）",
          _w1 and not _w2 and build(root, derived=True) == text_d)

    # --- P-068（U-6 裁决 A′，RESEARCH §7.29）：结构性豁免面处置（判据 + 边界 + I-8 显式登记）---
    _t_exempt = Task("P-001", "豁免面 done", "done", "—")
    _d_ex = derive_state(_t_exempt, None, True)
    check("S48 派生臂：结构性豁免面保原词、无行动档、依据为豁免（不得声称「五步完整」）",
          _eff_status(_t_exempt, None, True) == "done"
          and _d_ex.status == "done" and _d_ex.tier == ""
          and _d_ex.basis == EXEMPT_BASIS and "五步完整" not in _d_ex.basis)
    _d_a = derive_state(Task("P-910", "非豁免执行态无 session", "done", "—"), None, True)
    _d_b = derive_state(Task("P-911", "非豁免有 finalize 链", "in-progress", "—"), _S_full, True)
    check("S49 派生臂：豁免未外溢——非豁免执行态无 session 仍判缺口；非豁免有 finalize 链仍派生 done",
          _d_a.status == "in-progress" and _d_a.tier == "Needs Attention"
          and _d_b.status == "done" and _d_b.tier == "" and "五步完整" in _d_b.basis
          and not spec_map.is_historical_exempt("P-910")
          and spec_map.is_historical_exempt("P-001") and spec_map.is_historical_exempt("P-019")
          and not spec_map.is_historical_exempt("P-020"))
    _m_ex = re.search(r"结构性豁免面（I-8 显式登记）\*\*：(.+?) 共 (\d+) 条", text_d)
    check("S50a 派生态 §6 含豁免面行，且声明条数 = 列举 P 号个数（I-8 不静默省略）",
          _m_ex is not None
          and int(_m_ex.group(2)) == len([x for x in _m_ex.group(1).split("、") if x.strip()]))
    check("S50b 派生态 §6：豁免面退出「未开工」清单；非豁免真缺口（P-004 blocked）仍单列",
          "- 未开工（立项已登记，无决策流）：无" in text_d
          and "- **决策链缺失（Needs Attention）**：P-004" in text_d)
    check("S50c 默认态（R-1）：输出既不含豁免面显式行、也不含豁免依据文案",
          "结构性豁免面" not in text)

    # --- P-084（C-40 Layer-0 首项 / A-19 落地）：三档队列列头即状态行（计数 + DoR/DoD）---
    check("S51 列头即状态行：三档列头承载机械计数（声明 = 重数；fixture 档位 1/2/7）",
          "**Needs Attention**（1 项）" in text
          and "**Ready to Verify**（2 项）" in text
          and "**Recommended**（7 项）" in text)
    check("S52 每列 DoR/DoD 齐备且为 derive_state 判据的档级重投影（静态契约）",
          "> DoR：" in text and "· DoD：" in text
          and "`blocked`；或执行态但无 session（决策链缺失）" in text
          and "最新轮含 gate exit 2（软性存疑）；或五步完整待收（最远 step = `finalize`）" in text
          and "未开工（`pending` 且无决策流）" in text)
    check("S53 派生态：Ready to Verify 第二进入支随开关态分流（finalize 已归 done ⇒ 不出现）",
          "或五步完整待收（最远 step = `finalize`）" in text
          and "或五步完整待收（最远 step = `finalize`）" not in text_d)

    # --- U-9（P-101）夹具：返工边 → 行动档「待重写 / 待重入」（真实仓 forks 为空 ⇒ 零变化）---
    root2 = _build_mini()
    (root2 / "docs" / "rework-graph.json").write_text(
        json.dumps({"forks": [{"new": "specwf-p003-rw-20260911",
                               "origin": "specwf-p003-20260911", "seq_from": 1,
                               "trigger_kind": "user-verdict", "reason": "夹具",
                               "provenance": "manual:fixture", "date": "2026-09-11"}]},
                   ensure_ascii=False), encoding="utf-8")
    text_rw = build(root2)
    check("S54 返工边 → 上游 P 任务进 Needs Attention「待重写 / 待重入」（先于 done 短路）",
          "- **P-003** gamma 进行中 —— 待重写 / 待重入（返工边 "
          "`specwf-p003-rw-20260911` ← `specwf-p003-20260911`）" in text_rw
          and "**Needs Attention**（2 项）" in text_rw)
    check("S55 零返工边 ⇒ 无 U-9 附加行（回归安全）",
          "待重写 / 待重入" not in text)
    check("S56 compact 当前状态块（五行全机械派生：状态分布 / 最近批次 / session / 队列 / feature 阶段）",
          "## 当前状态（compact）" in text
          and "| 在册批次 | 11（done 1 · pending 6 · in-progress 3 · blocked 1） |" in text
          and "| 最近批次 | P-011 pending（2026-09-11） |" in text
          and "| session 覆盖 | 4 个 P（最近 specwf-p006-20260911 · "
              "2026-09-11T15:00:00+08:00） |" in text
          and "| 行动队列 | Needs Attention 1 · Ready to Verify 2 · Recommended 7 |" in text
          and "| feature 阶段 | 4（调研 1 · 设计 0 · 实施 0 · 验收 0 · 未启动 3） |" in text)
    shutil.rmtree(root2, ignore_errors=True)

    shutil.rmtree(root, ignore_errors=True)
    print(f"selftest: {passed}/{total} PASS")
    if failures:
        print("FAILED:", "; ".join(failures))
        return 1
    return 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="项目控制台生成器（纯派生多视图，P-043）")
    parser.add_argument("--stdout", action="store_true", help="仅打印，不写盘")
    parser.add_argument("--check", action="store_true", help="只读核对（过期 exit 1）")
    parser.add_argument("--stage", action="store_true", help="变化时 git add（pre-commit L0）")
    parser.add_argument("--selftest", action="store_true", help="内嵌自测")
    parser.add_argument("--root", default=None, help="仓库根（selftest 用）")
    parser.add_argument("--derived", action="store_true",
                        help="派生态（P2b 开关）：执行态采机器派生（DC2.1）；默认关 = PROGRESS 原词")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = Path(args.root).resolve() if args.root else ROOT
    try:
        content = build(root, derived=args.derived)
    except Exception as e:  # noqa: BLE001 —— 顶层兜底（exit 2）
        print(f"[tool-error] {e}", file=sys.stderr)
        return 2

    if args.stdout:
        print(content, end="")
        return 0

    target = root / "docs" / "CONSOLE.md"
    if args.check:
        old = target.read_text(encoding="utf-8") if target.exists() else None
        if old != content:
            print("CONSOLE.md 已过期（源已变）——请重跑 console_gen")
            return 1
        print("CONSOLE.md 与源一致")
        return 0

    changed = write_console(target, content)
    if changed:
        rel = "docs/CONSOLE.md"
        if args.stage and not _stage(root, rel):
            print("[warn] git add 失败（控制台已生成但未暂存）", file=sys.stderr)
        print("console_gen: docs/CONSOLE.md 已刷新")
    else:
        print("console_gen: docs/CONSOLE.md 无变化")
    return 0


if __name__ == "__main__":
    sys.exit(main())
