#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DC 契约校验器（DC1-DC5 + R7）——契约的机器可读定义。

权威源：spec/doc-contract/PLAN.md §1 DC1-DC5（DC5 = v1.9 P-106）
       + adr/ADR-0007 D4/D5 + docs/ASSERTION_EVIDENCE_FRAMEWORK.md v1.4 R7。
词表常量逐字符复制自 spec/precommit-dc-validator/DESIGN.md §6.3（I-4 单一真值源）。

不变式（DESIGN §8）：I-1 只读 / I-2 确定性 / I-3 零新规则 / I-4 单一真值源 / I-5 异构于生成端
       / I-6 版本引用对账面（DC5）不受 staged 子集限制（全仓扫描）。
退出码：0 全部通过 / 1 发现契约违规 / 2 工具自身错误。

用法：
  python scripts/dc_validator.py                     # 全仓全检查（默认 --check-all）
  python scripts/dc_validator.py file1.md file2.md   # 指定文件（pre-commit staged 语义）
  python scripts/dc_validator.py --check-namespace   # 单项组合
  python scripts/dc_validator.py --selftest          # 内嵌自测（fixture 见 IMPLEMENTATION §8.1）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

# --- 仓库根（脚本位于 <root>/scripts/，与 cwd 无关，I-2） ---
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- DC2 词表（DESIGN §6.3；权威源 PLAN v1.6 §1 DC2 + ADR-0007 D4/D5） ---
TYPE_VOCAB = {
    "adr":              {"proposed", "accepted", "superseded", "deferred"},
    "discovery":        {"open", "resolved", "toolized"},
    "process-spec":     {"active", "deprecated"},
    "framework":        {"active", "deprecated"},
    "template":         {"draft", "in-review", "verified"},
    "design":           {"draft", "in-review", "verified", "superseded"},  # 一般设计文档（id 不含 CHECKLIST 段）；superseded 由 P-050 交付 B 增补（ADR-0007 D4 追记）
}
# 副轴（PLAN v1.6 DC2 消歧；P-052 扩宽）：id 含 CHECKLIST 段（"-" 分隔）的 design 文档用 CHECKLIST 词表——
#   覆盖 "-CHECKLIST" 后缀（独立验证等）与 "-CHECKLIST-<变体>"（step-gate-CHECKLIST-FUNC / defect-fixes-CHECKLIST-FUNC）
CHECKLIST_STATUS_VOCAB = {"pending", "accepting", "accepted"}

SEVEN_FIELDS = ("id", "type", "version", "status", "date", "depends", "upstream")
FM_WINDOW = 10                          # DR-1：front-matter 围栏检测窗口（前 N 行）
TIER_PREFIXES = ("源项目·", "外部·", "本地工具·")   # DC3 档 2-4 标注前缀
QUOTE_MARKERS = ("引文:", '"quote":')             # M5：引文行（源仓库路径空间）
TEMPLATE_DIR = os.path.join("spec", "templates")  # DR-3：模板占位链接排除

UNPARSABLE = "UNPARSABLE"  # front-matter 存在但结构不可解析的哨兵


@dataclass(frozen=True)
class CheckResult:
    check_id: str      # "dc1" | "dc2" | "dc4" | "r7" | "dc3"
    file: str          # 相对路径
    severity: str      # "P1" | "P2" | "P3" | ""（空 = skip，非违规）
    message: str
    line: int | None = None


class Summary:
    """DESIGN §6.2：violations = severity 非空的结果。"""

    def __init__(self, results):
        self.results = list(results)

    @property
    def violations(self):
        return [r for r in self.results if r.severity]

    @property
    def passed(self):
        return not self.violations


# ---------------------------------------------------------------- M2 frontmatter

def parse_frontmatter(text):
    """返回 (fm_dict, close_line) / (None, None) 无 front-matter / (UNPARSABLE, None) 结构错误。

    检测窗口 = 前 FM_WINDOW 行（DR-1：覆盖首行式与标题后式两种实测形态）。
    值形态：单行 key: value / 流式数组 [a, b] / null / 裸标量（IMPLEMENTATION §2.1）。
    """
    lines = text.splitlines()
    open_idx = None
    for i, ln in enumerate(lines[:FM_WINDOW]):
        if ln.strip() == "---":
            open_idx = i
            break
    if open_idx is None:
        return None, None
    fm = {}
    kv_count = 0
    for j in range(open_idx + 1, len(lines)):
        ln = lines[j]
        if ln.strip() == "---":
            if kv_count == 0:
                return None, None  # 装饰性分隔线（README/CODE_WIKI 场景），非 front-matter
            return fm, j
        if not ln.strip():
            continue
        m = re.match(r"^([A-Za-z_-]+):\s?(.*)$", ln)
        if not m:
            if kv_count == 0:
                return None, None  # 开围栏后首个非空行非 key: value → 非 front-matter
            return UNPARSABLE, None  # 围栏内出现无 key: 结构的行
        fm[m.group(1)] = m.group(2).strip()
        kv_count += 1
    return (UNPARSABLE, None) if kv_count else (None, None)  # 未闭合


def check_frontmatter(file, text):
    """M2：DC1 七字段 + DC2 词表（design 二档判定 = id 含 CHECKLIST 段，P-052 扩宽）。"""
    fm, _ = parse_frontmatter(text)
    if fm == UNPARSABLE:
        return [CheckResult("dc1", file, "P1", "front-matter 非合法 YAML: 围栏内存在无 key: value 结构的行")]
    if fm is None:
        return [CheckResult("dc1", file, "", "不在 DC 契约范围（无 front-matter）")]
    results = []
    for k in SEVEN_FIELDS:
        if k not in fm:
            results.append(CheckResult("dc1", file, "P1", "DC1 缺失字段: %s" % k))
    t, s = fm.get("type"), fm.get("status")
    if t is not None and t not in TYPE_VOCAB:
        results.append(CheckResult("dc2", file, "P1",
                                   "DC2 非法 type: %r（允许: %s）" % (t, "/".join(sorted(TYPE_VOCAB)))))
    elif t is not None and s is not None:
        vocab = (CHECKLIST_STATUS_VOCAB
                 if t == "design" and "CHECKLIST" in fm.get("id", "").split("-")
                 else TYPE_VOCAB.get(t, set()))
        if s not in vocab:
            results.append(CheckResult("dc2", file, "P1",
                                       "DC2 非法 status: %r（type %s 允许: %s）" % (s, t, "/".join(sorted(vocab)))))
    return results


# ---------------------------------------------------------------- M3 namespace

def check_namespace(files, root=ROOT):
    """M3：DC4 id 全仓唯一（输入必须为全仓 .md 集，非 staged-only）。重复方全部报告。"""
    seen = {}
    for f in files:
        full = os.path.normpath(os.path.join(root, f))
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        fm, _ = parse_frontmatter(text)
        if isinstance(fm, dict) and "id" in fm:
            seen.setdefault(fm["id"], []).append(f)
    results = []
    for doc_id, paths in sorted(seen.items()):
        if len(paths) > 1:
            for p in paths:
                results.append(CheckResult("dc4", p, "P1", "DC4 重复 id %r: %s" % (doc_id, paths)))
    return results


# ---------------------------------------------------------------- M4 counting

RE_STAT_ROW = {
    "A": re.compile(r"^\|\s*A\s*事实类\s*\|\s*(\d+)"),
    "B": re.compile(r"^\|\s*B\s*推断类\s*\|\s*(\d+)"),
    "H": re.compile(r"^\|\s*假设区\s*\|\s*(\d+)"),
}
RE_A_MARK = re.compile(r"(?:^|\|\s*)【A】", re.M)   # 行首 + 表格单元格内（IMPLEMENTATION §3.4）
RE_B_ID = re.compile(r'"id":\s*"B\d+"')             # 附录 B 机读登记
RE_H_ITEM = re.compile(r"\[H\d+\]")                 # 附录 C 假设区条目
RE_STAT_SECTION = re.compile(r"^##\s*0[\.、]?\s*断言统计表", re.M)
# C 类首版不对账（DR-2：标记格式无统一契约——原生文档行首标记 vs 吸收文档语义计数）

# --- M4 分支②：CHECKLIST §10.1 验收统计（P-050 交付 A，DESIGN §4-§5） ---
RE_CL_STAT_HEAD = re.compile(r"^###\s*10\.1\s*验收统计\s*$", re.M)           # 规范标题（精确）
RE_CL_STAT_ANY = re.compile(r"^#{2,4}\s*\d+\.\d+\s*验收统计\s*(?:[（(].*)?$", re.M)  # 异形标题探测（须含 major.minor，且「验收统计」后仅容许括注/行尾）
CL_CATEGORIES = ("文档一致性", "功能", "接口", "不变式",
                 "错误处理", "性能", "兼容性", "ADD 审计")
RE_CL_INT = re.compile(r"\d+")


def _strip_fences(text):
    """丢弃 ``` 围栏块内内容（只认正文；避免文档自我演示规范形态时误触本校验）。"""
    out, in_fence = [], False
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(ln)
    return "\n".join(out)


def _cl_int(cell):
    """单元格 → int（纯十进制整数，允许 **加粗**）/ None（含非整数内容）。"""
    s = cell.replace("*", "").strip()
    return int(s) if RE_CL_INT.fullmatch(s) else None


def parse_checklist_stats(body):
    """解析 §10.1 表体（规范标题行之后）。返回 (rows, total)。

    rows  = [(类别, (总数, 通过, 失败, 待办))]，仅 CL_CATEGORIES 行，保序
    total = (总数, 通过, 失败, 待办) | None
    单元格：纯整数 → int；含非整数内容 → None（触发异形 skip）。
    """
    rows, total, started = [], None, False
    for ln in body.splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            if started:
                break
            continue
        started = True
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5:
            continue
        label = cells[0].replace("*", "").strip()
        if not label or set(label) <= set("-: "):
            continue
        vals = tuple(_cl_int(c) for c in cells[1:5])
        if label == "总计":
            total = vals
        elif label in CL_CATEGORIES:
            rows.append((label, vals))
    return rows, total


def _counting_assertions(file, text):
    """M4 分支①：R7——§0 统计表声明计数 = 机械重数（A/B/H 三类）。"""
    if not RE_STAT_SECTION.search(text):
        return []
    declared = {}
    for ln in text.splitlines():
        s = ln.strip()
        for k, rx in RE_STAT_ROW.items():
            m = rx.match(s)
            if m:
                declared[k] = int(m.group(1))
    actual = {
        "A": len(RE_A_MARK.findall(text)),
        "B": len(RE_B_ID.findall(text)),
        "H": len(RE_H_ITEM.findall(text)),
    }
    results = []
    for k in ("A", "B", "H"):
        if k in declared and declared[k] != actual[k]:
            results.append(CheckResult("r7", file, "P1",
                                       "§0 %s 类声明 %d 实为 %d" % (k, declared[k], actual[k])))
    return results


def _counting_checklist(file, text):
    """M4 分支②（P-050 交付 A）：CHECKLIST §10.1 验收统计 声明 = 机械重数（渐进）。

    判定（DESIGN §4.3，只认规范形态）：
      规范标题 + 模板 8 类行 + 总计行 + 全整数 + 两条算术自洽 → 通过（无结果）
      规范标题 + 全整数 + 算术不自洽 → P1（真阻断）
      规范标题 + 非整数单元格 / 未按模板 8 类行 → skip（severity=""，历史不追溯）
      异形标题（非精确匹配）→ skip
      均未命中 → 无结果
    """
    text = _strip_fences(text)   # 围栏内为示例/代码，不参与形态判定
    head = RE_CL_STAT_HEAD.search(text)
    if not head:
        any_head = RE_CL_STAT_ANY.search(text)
        if any_head:
            return [CheckResult("r7", file, "",
                                "§10.1 标题形态异形（不适用本校验；新批次请依模板）: %s"
                                % any_head.group(0).strip()[:60])]
        return []
    rows, total = parse_checklist_stats(text[head.end():])
    if total is None or {lb for lb, _ in rows} != set(CL_CATEGORIES):
        return [CheckResult("r7", file, "",
                            "§10.1 未按模板 8 类行/缺总计行（不适用本校验；新批次请依模板）")]
    if any(v is None for v in total) or any(v is None for _, vals in rows for v in vals):
        return [CheckResult("r7", file, "",
                            "§10.1 单元格非纯整数（不适用本校验；新批次请依模板）")]
    results = []
    for cat, vals in rows:
        n, p, f, t = vals
        if n != p + f + t:
            results.append(CheckResult("r7", file, "P1",
                                       "§10.1 行「%s」总数 %d ≠ 通过+失败+待办 %d" % (cat, n, p + f + t)))
    sums = [sum(vals[i] for _, vals in rows) for i in range(4)]
    for i, name in enumerate(("总数", "通过", "失败", "待办")):
        if total[i] != sums[i]:
            results.append(CheckResult("r7", file, "P1",
                                       "§10.1 总计列 %s %d ≠ 类行求和 %d" % (name, total[i], sums[i])))
    return results


def check_counting(file, text):
    """M4：R7——① §0 断言统计表（A/B/H）② CHECKLIST §10.1 验收统计（P-050 交付 A）。"""
    return _counting_assertions(file, text) + _counting_checklist(file, text)


# ---------------------------------------------------------------- M5 linkcheck

RE_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


_ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def strip_inline_code(line):
    """剔除行内代码跨度（P-090：M5 第四排除上下文）。

    CommonMark 反引号配对标（markdown-it-py 实测核定语义）：
    - 起始反引号：**反斜杠转义的标点被先行消费为字面量** ⇒ 该位反引号不能开跨度；
    - 收尾扫描：**按原文找等长游程**（代码跨度内反斜杠不转义，故收尾反引号前的反斜杠不阻止收尾）；
    - **未配对游程视为普通字符**（例：行内字面量 ``` 后接成对单反引号）。
    配对成功的跨度整体替换为**单个空格**——既排除跨度内的相邻形态字面量，又防止两端文本
    拼合新造该形态（naive 奇偶剥离两端都做不到）。
    """
    if "`" not in line:
        return line
    out, i, n = [], 0, len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n and line[i + 1] in _ASCII_PUNCT:
            out.append(line[i:i + 2])
            i += 2
            continue
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = j - i
            k, close = j, -1
            while k < n:
                if line[k] == "`":
                    m = k
                    while m < n and line[m] == "`":
                        m += 1
                    if (m - k) == run:
                        close = m
                        break
                    k = m
                else:
                    k += 1
            if close < 0:
                out.append(line[i:j])
                i = j
            else:
                out.append(" ")
                i = close
            continue
        out.append(line[i])
        i += 1
    return "".join(out)


def check_links(file, text, root=ROOT):
    """M5：DC3 档 1——仓库内相对链接可解析。

    排除上下文（DR-3）：fenced code block / 引文行（引文: 或 "quote":）/ spec/templates/。
    P-090 增第四排除上下文：行内代码跨度（strip_inline_code，CommonMark 反引号配对标）。
    档 2-4 标注（链接文本前缀 源项目·/外部·/本地工具·）不跨仓解析。
    """
    if file.replace("\\", "/").startswith(TEMPLATE_DIR.replace("\\", "/")):
        return []
    results = []
    in_fence = False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if any(mk in ln for mk in QUOTE_MARKERS):
            continue
        for m in RE_MD_LINK.finditer(strip_inline_code(ln)):
            label, tgt = m.group(1).strip(), m.group(2).strip()
            if tgt.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if label.startswith(TIER_PREFIXES):
                continue
            p = tgt.split("#")[0].strip()
            if not p:
                continue
            base = os.path.dirname(os.path.normpath(os.path.join(root, file)))
            if not os.path.exists(os.path.normpath(os.path.join(base, p))):
                results.append(CheckResult("dc3", file, "P2", "档 1 相对链接不可解析: %s" % tgt, i))
    return results


# ---------------------------------------------------------------- M6 version-refs

# DC5（P-106）：只认「头部声明行」六类标签；版本写法两种（label 内 / 链接后）
RE_REF_HEADER = re.compile(
    r"^\s*>?\s*\*\*(?:基于实施|基于设计|基于调研|设计来源|设计依据|被验收物)\*\*\s*:")
RE_VER_IN_LABEL = re.compile(r"v(\d+\.\d+)\s*$")
RE_VER_AFTER_LINK = re.compile(r"^\s*\**\s*v(\d+\.\d+)")


def check_version_refs(files, root=ROOT):
    """M6：DC5 版本引用一致性——头部声明行内的版本 = 目标文档 front-matter `version`。

    判据面（刻意收窄，防假阳性）：
    - 行首（允许 `>`）为 `**基于实施|基于设计|基于调研|设计来源|设计依据|被验收物**` + `:`；
    - 版本写法 = 链接文本尾部 `vX.Y` 或链接右括号后紧邻 `vX.Y`（可带 `**`）；
    - 目标须为仓内 `.md` 且带 front-matter `version`（缺则**不判定**，非违规）；
    - 代码围栏与行内代码跨度不参与（同 M5）。

    调用面 = 全仓（I-6）：pre-commit 的 staged 子集不足以检出「改 A 的 version、未改引用 A 的 B」。
    """
    results = []
    for f in files:
        full = os.path.normpath(os.path.join(root, f))
        try:
            text = _read(full)
        except OSError:
            continue
        base = os.path.dirname(full)
        in_fence = False
        for i, ln in enumerate(text.splitlines(), 1):
            if ln.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not RE_REF_HEADER.match(ln):
                continue
            scanned = strip_inline_code(ln)
            for m in RE_MD_LINK.finditer(scanned):
                label, tgt = m.group(1).strip(), m.group(2).strip()
                if tgt.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                p = tgt.split("#")[0].strip()
                if not p.endswith(".md"):
                    continue
                target = os.path.normpath(os.path.join(base, p))
                if not os.path.exists(target):
                    continue                      # 断链归 M5
                vm = RE_VER_IN_LABEL.search(label)
                ver = vm.group(1) if vm else None
                if ver is None:
                    am = RE_VER_AFTER_LINK.match(scanned[m.end():])
                    ver = am.group(1) if am else None
                if ver is None:
                    continue                      # 无版本写法 ⇒ 不在 DC5 判据面
                tfm, _ = parse_frontmatter(_read(target))
                if not isinstance(tfm, dict) or "version" not in tfm:
                    continue                      # 目标无 version ⇒ 不可判
                actual = tfm["version"].strip()
                if actual != ver:
                    results.append(CheckResult(
                        "dc5", f, "P2",
                        "版本引用过期: 「%s」写 v%s，目标 %s 的 front-matter 为 v%s"
                        % (label, ver, p, actual), i))
    return results


# ---------------------------------------------------------------- M1 CLI

# 目录排除（M1）。`.arc` = ARC 图存储（P-035，同 `.git` 先例）。
# P-049 单点化修复：原排除**只作用于 os.walk**，pre-commit 显式传参（staged 列表）绕过它，
# 致 tools/arc/data/.arc/decisions/*.md 被当 DC 契约对象校验（47 处误判）。
# 现将判定抽为 EXCLUDE_DIRS + is_excluded()，**遍历与显式传参共用同一份判定**（I-10 语义同源）。
EXCLUDE_DIRS = (".git", "__pycache__", ".arc")


def is_excluded(rel):
    """相对路径是否落在排除目录内（任一路径段命中 EXCLUDE_DIRS；末段为文件名，不参与）。"""
    parts = str(rel).replace("\\", "/").split("/")
    return any(p in EXCLUDE_DIRS for p in parts[:-1])


def gather_md_files(root=ROOT):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(out)


def _read(full):
    with open(full, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def run_checks(files, checks, root=ROOT):
    """逐文件检查（M2/M4/M5）+ 强制全仓 namespace（M3）。返回 list[CheckResult]。"""
    results = []
    for f in files:
        full = os.path.normpath(os.path.join(root, f))
        try:
            text = _read(full)
        except OSError as e:
            results.append(CheckResult("dc1", f, "P2", "文件不可读: %s" % e))
            continue
        if "frontmatter" in checks:
            results += check_frontmatter(f, text)
        if "counting" in checks:
            results += check_counting(f, text)
        if "links" in checks:
            results += check_links(f, text, root)
    if "namespace" in checks:
        results += check_namespace(gather_md_files(root), root)
    if "version_ref" in checks:
        results += check_version_refs(gather_md_files(root), root)   # I-6：全仓，不受 staged 子集限制
    return results


ALL_CHECKS = ("frontmatter", "namespace", "counting", "links", "version_ref")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="dc_validator", description="DC 契约校验器（DC1-DC4 + R7）")
    ap.add_argument("--check-all", action="store_true", help="全部检查（默认）")
    ap.add_argument("--check-frontmatter", action="store_true", help="DC1 七字段 + DC2 词表")
    ap.add_argument("--check-namespace", action="store_true", help="DC4 id 全仓唯一")
    ap.add_argument("--check-counting", action="store_true", help="R7 计数 = 机械重数")
    ap.add_argument("--check-links", action="store_true", help="DC3 档 1 相对链接")
    ap.add_argument("--check-version-ref", action="store_true", help="DC5 版本引用一致性（全仓）")
    ap.add_argument("--selftest", action="store_true", help="内嵌自测（IMPLEMENTATION §8.1）")
    ap.add_argument("files", nargs="*", help="目标 .md（缺省 = 全仓；pre-commit 传入 staged 列表）")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()

    selected = {c for c in ALL_CHECKS if getattr(args, "check_" + c)}
    if args.check_all or not selected:
        selected = set(ALL_CHECKS)

    try:
        chosen = args.files if args.files else gather_md_files()
        files = [f for f in chosen if not is_excluded(f)]   # P-049：显式传参与遍历同判
        results = run_checks(files, selected)
    except Exception as e:  # 工具自身错误 ≠ 校验通过（DESIGN §3.4 补注）
        sys.stderr.write("[tool-error] %s: %s\n" % (type(e).__name__, e))
        return 2

    summary = Summary(results)
    for r in summary.results:
        tag = "[%s]" % r.severity if r.severity else "[skip]"
        loc = " (L%d)" % r.line if r.line else ""
        print("%s %s: %s%s" % (tag, r.file, r.message, loc))
    if summary.passed:
        print("DC 契约校验通过：%d 文件，%d 结果，0 违规" % (len(files), len(summary.results)))
        return 0
    print("DC 契约校验失败：%d 违规（P1=%d P2=%d）" % (
        len(summary.violations),
        sum(1 for r in summary.violations if r.severity == "P1"),
        sum(1 for r in summary.violations if r.severity == "P2")))
    return 1


# ---------------------------------------------------------------- selftest

FM_OK = ("---\nid: selftest-ok-RESEARCH\ntype: design\nversion: 1.0\n"
         "status: draft\ndate: 2026-08-19\ndepends: [x]\nupstream: null\n---\n\n# t\n")


def run_selftest():
    """内嵌自测（fixture 见 IMPLEMENTATION §8.1；F11 = P-049 单点化，F12-F16 = P-050 交付 A §10.1），tempfile 构造于系统临时目录（I-1 不触工作树）。"""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="dcv_selftest_")
    fails = []
    total = [0]  # 机械计数（R7 同构：计数由 expect 调用自增，不手填）

    def expect(cond, msg):
        total[0] += 1
        print("  %s %s" % ("PASS" if cond else "FAIL", msg))
        if not cond:
            fails.append(msg)

    def w(name, content):
        p = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return os.path.relpath(p, tmp)

    try:
        # F1 七字段缺失 depends
        f1 = w("f1.md", FM_OK.replace("depends: [x]\n", ""))
        r = check_frontmatter(f1, _read(os.path.join(tmp, f1)))
        expect(any(x.severity == "P1" and "depends" in x.message for x in r), "F1 DC1 缺字段报 P1")

        # F2 围栏内结构错误
        f2 = w("f2.md", "---\nid: x\nbroken line no colon\n---\n")
        r = check_frontmatter(f2, _read(os.path.join(tmp, f2)))
        expect(any(x.severity == "P1" and "非合法 YAML" in x.message for x in r), "F2 yaml-unparsable 报 P1")

        # F3 status 词表非法
        f3 = w("f3.md", FM_OK.replace("status: draft", "status: bogus"))
        r = check_frontmatter(f3, _read(os.path.join(tmp, f3)))
        expect(any(x.severity == "P1" and "非法 status" in x.message for x in r), "F3 DC2 词表报 P1")

        # F3b CHECKLIST 副轴：id 尾缀 -CHECKLIST 时 pending 合法、draft 非法
        f3b = w("f3b.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: x-CHECKLIST")
                .replace("status: draft", "status: pending"))
        r = check_frontmatter(f3b, _read(os.path.join(tmp, f3b)))
        expect(not any("status" in x.message for x in r), "F3b CHECKLIST 词表 pending 合法")
        f3c = w("f3c.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: x-CHECKLIST"))
        r = check_frontmatter(f3c, _read(os.path.join(tmp, f3c)))
        expect(any("非法 status" in x.message for x in r), "F3c CHECKLIST 词表 draft 非法")

        # F4 §0 计数差
        f4 = w("f4.md", FM_OK + "\n## 0. 断言统计表\n\n| 级别 | 条数 |\n|---|---|\n| A 事实类 | 3 |\n\n【A】x\n【A】y\n")
        r = check_counting(f4, _read(os.path.join(tmp, f4)))
        expect(any(x.severity == "P1" and "声明 3 实为 2" in x.message for x in r), "F4 R7 计数差报 P1")

        # F5 无 front-matter → skip
        f5 = w("f5.md", "# plain doc\n")
        r = check_frontmatter(f5, _read(os.path.join(tmp, f5)))
        expect(len(r) == 1 and r[0].severity == "" and "不在 DC 契约范围" in r[0].message, "F5 范围外 [skip]")

        # F6 id 重复（双方各报）
        w("f6a.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: dup-id"))
        w("f6b.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: dup-id"))
        r = check_namespace(["f6a.md", "f6b.md"], root=tmp)
        expect(len(r) == 2 and all(x.severity == "P1" for x in r), "F6 DC4 重复双方各报 P1")

        # F7 不可读文件 → P2 不崩溃
        r = run_checks(["no_such_file.md"], {"frontmatter"}, root=tmp)
        expect(any(x.severity == "P2" and "不可读" in x.message for x in r), "F7 不可读文件报 P2")

        # F8 断链 / 档 2 标注 / 引文行三分流
        w("f8_target.md", FM_OK)
        f8 = w("f8.md", FM_OK + "\n[missing](./nope.md)\n[源项目·p](../anywhere.md)\n"
                             "> 引文: [q](./also-missing.md)\n[ok](./f8_target.md)\n")
        r = check_links(f8, _read(os.path.join(tmp, f8)), root=tmp)
        expect(len(r) == 1 and r[0].severity == "P2" and "nope.md" in r[0].message, "F8 仅真断链报 P2")

        # F8b templates 排除
        f8b = w(os.path.join("spec", "templates", "f8b.md"), FM_OK + "\n[t](./nope.md)\n")
        r = check_links(f8b, _read(os.path.join(tmp, f8b)), root=tmp)
        expect(len(r) == 0, "F8b templates 占位链接排除")

        # F9 合规文件零误报（含 §0 对账一致）
        f9 = w("f9.md", FM_OK + "\n## 0. 断言统计表\n\n| 级别 | 条数 |\n|---|---|\n| A 事实类 | 1 |\n\n【A】one\n")
        text = _read(os.path.join(tmp, f9))
        r = check_frontmatter(f9, text) + check_counting(f9, text) + check_links(f9, text, root=tmp)
        expect(not any(x.severity for x in r), "F9 合规文件零违规")

        # F10 无 front-matter 但含装饰性 --- 分隔线（dry-run 首跑 5 误报回归）
        f10 = w("f10.md", "# 标题\n\n---\n\n正文段落，非 key: value。\n")
        r = check_frontmatter(f10, _read(os.path.join(tmp, f10)))
        expect(len(r) == 1 and r[0].severity == "" and "不在 DC 契约范围" in r[0].message,
               "F10 装饰性 --- 分隔线判为范围外 [skip]")

        # F11 .arc 排除单点化（P-049）：显式传参路径与遍历共用同一判定
        arc = w(os.path.join("tools", "arc", "data", ".arc", "decisions", "D-001.md"),
                FM_OK + "\n[bad](./nope.md)\n")
        expect(is_excluded(arc) and is_excluded(os.path.join(".arc", "x.md")),
               "F11 .arc 显式路径判为排除")
        expect(not is_excluded("docs/PROGRESS.md") and not is_excluded("spec/a/RESEARCH.md"),
               "F11b 常规路径不排除")
        expect(all(not is_excluded(f) for f in gather_md_files(tmp)),
               "F11c 遍历结果零排除项（.arc fixture 未入列）")

        # --- P-050 交付 A：M4 分支② CHECKLIST §10.1 验收统计 ---
        cl_head = ("\n## 10. 验收结论\n\n### 10.1 验收统计\n\n"
                   "| 类别 | 总数 | 通过 | 失败 | 待办 |\n"
                   "|------|------|------|------|------|\n")
        cl_rows_ok = "".join("| %s | 1 | 1 | 0 | 0 |\n" % c for c in CL_CATEGORIES)
        cl_total_ok = "| **总计** | 8 | 8 | 0 | 0 |\n"

        # F12 规范标题 + 8 类行 + 算术自洽 → 零违规
        f12 = w("f12.md", FM_OK + cl_head + cl_rows_ok + cl_total_ok)
        r = check_counting(f12, _read(os.path.join(tmp, f12)))
        expect(len(r) == 0, "F12 §10.1 规范+自洽 零违规")

        # F13 规范标题 + 总计列与类行求和不符 → P1
        f13 = w("f13.md", FM_OK + cl_head + cl_rows_ok + "| **总计** | 9 | 8 | 0 | 0 |\n")
        r = check_counting(f13, _read(os.path.join(tmp, f13)))
        expect(any(x.severity == "P1" and "总计列 总数" in x.message for x in r),
               "F13 §10.1 总计列错报 P1")

        # F13b 规范标题 + 行内 总数 ≠ 通过+失败+待办 → P1
        cl_rows_bad = "".join("| %s | %d | 1 | 0 | 0 |\n" % (c, 2 if c == "功能" else 1)
                              for c in CL_CATEGORIES)
        f13b = w("f13b.md", FM_OK + cl_head + cl_rows_bad + cl_total_ok)
        r = check_counting(f13b, _read(os.path.join(tmp, f13b)))
        expect(any(x.severity == "P1" and "行「功能」" in x.message for x in r),
               "F13b §10.1 行内算术错报 P1")

        # F14 规范标题 + 非整数单元格（文字算术）→ skip（severity=""）
        f14 = w("f14.md", FM_OK + cl_head + cl_rows_ok + "| **总计** | **8 项 + 0 发现** | 8 | 0 | 0 |\n")
        r = check_counting(f14, _read(os.path.join(tmp, f14)))
        expect(len(r) == 1 and r[0].severity == "" and "非纯整数" in r[0].message,
               "F14 §10.1 非整数单元格 skip")

        # F15 异形标题（§8.1）→ skip
        f15 = w("f15.md", FM_OK + "\n## 8. 验收结论\n\n### 8.1 验收统计\n\n"
                                 "| 类别 | 总数 | 通过 | 失败 | 待办 |\n")
        r = check_counting(f15, _read(os.path.join(tmp, f15)))
        expect(len(r) == 1 and r[0].severity == "" and "标题形态异形" in r[0].message,
               "F15 §10.1 异形标题 skip")

        # F16 无 §10.1 → 无结果（不误判散文族）
        f16 = w("f16.md", FM_OK + "\n## 1. 功能验收\n\n**验收统计**: A1-A6 全部通过。\n")
        r = check_counting(f16, _read(os.path.join(tmp, f16)))
        expect(len(r) == 0, "F16 无 §10.1 无结果")

        # F17 围栏内示例形态 → 不触发（文档自我演示规范形态）
        f17 = w("f17.md", FM_OK + "\n```\n### 10.1 验收统计\n\n"
                                 "| 类别 | 总数 | 通过 | 失败 | 待办 |\n| 功能 | N | N | N | N |\n```\n")
        r = check_counting(f17, _read(os.path.join(tmp, f17)))
        expect(len(r) == 0, "F17 围栏内示例不触发")

        # F18 正文含「验收统计」的普通小节标题 → 不误判为异形
        f18 = w("f18.md", FM_OK + "\n### 3.1 验收统计形态三族与子偏差\n\n正文。\n")
        r = check_counting(f18, _read(os.path.join(tmp, f18)))
        expect(len(r) == 0, "F18 普通小节标题不误判")

        # F19-F21 P-052 DC2 扩宽：CHECKLIST 段判别（含 -CHECKLIST-<变体>），且为「段」而非「子串」
        f19 = w("f19.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: x-CHECKLIST-FUNC")
                .replace("status: draft", "status: accepting"))
        r = check_frontmatter(f19, _read(os.path.join(tmp, f19)))
        expect(not any("status" in x.message for x in r), "F19 CHECKLIST 段判别 accepting 合法")
        f20 = w("f20.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: x-CHECKLIST-FUNC"))
        r = check_frontmatter(f20, _read(os.path.join(tmp, f20)))
        expect(any("非法 status" in x.message for x in r), "F20 CHECKLIST 段判别 draft 非法")
        f21 = w("f21.md", FM_OK.replace("id: selftest-ok-RESEARCH", "id: x-FOOCHECKLIST"))
        r = check_frontmatter(f21, _read(os.path.join(tmp, f21)))
        expect(not any("status" in x.message for x in r), "F21 段判别非子串（x-FOOCHECKLIST 走一般档）")

        # --- P-090 方向 B：M5 第四排除上下文「行内代码跨度」（CommonMark 反引号配对标） ---
        # F22 行内代码跨度内的链接字面量 → 零违规（本批新增的行为能力）
        f22 = w("f22.md", FM_OK + "\n示例：`[text](./nope.md)` 与 ``[a](./nope2.md)``\n")
        r = check_links(f22, _read(os.path.join(tmp, f22)), root=tmp)
        expect(len(r) == 0, "F22 行内代码跨度内链接零违规")

        # F23 未配对反引号游程视为普通字符（naive 奇偶剥离会吞掉其后的真实断链）
        f23 = w("f23.md", FM_OK + "\n统计升 ```hits 块 + `scripts/m7_stats.py` 见 [bad](./nope.md)\n")
        r = check_links(f23, _read(os.path.join(tmp, f23)), root=tmp)
        expect(len(r) == 1 and "nope.md" in r[0].message, "F23 未配对游程不吞真实链接")

        # F24 反斜杠转义的反引号不参与配对（escape-blind 配对会吞掉其后的真实断链）
        f24 = w("f24.md", FM_OK + "\n来源 x \\` [bad](./nope.md) `y`\n")
        r = check_links(f24, _read(os.path.join(tmp, f24)), root=tmp)
        expect(len(r) == 1 and "nope.md" in r[0].message, "F24 转义反引号不参与配对")

        # F25 代码跨度整体替换为空格 ⇒ 不跨边界新造 `](` 相邻位点
        f25 = w("f25.md", FM_OK + "\n正文 x]`code`(y) 结束\n")
        r = check_links(f25, _read(os.path.join(tmp, f25)), root=tmp)
        expect(len(r) == 0, "F25 跨度边界不新造链接位点")

        # F26 收尾反引号前有反斜杠（Windows 路径形态）：跨度正常收尾，其后真实链接仍检出
        f26 = w("f26.md", FM_OK + "\n路径 `D:\\Art\\wp\\` 见 [bad](./nope.md)\n")
        r = check_links(f26, _read(os.path.join(tmp, f26)), root=tmp)
        expect(len(r) == 1 and "nope.md" in r[0].message, "F26 跨度正常收尾不吞其后链接")

        # --- P-106 DC5：M6 版本引用对账（头部声明行 × 目标 front-matter version） ---
        # F27 链接后版本写法且一致 → 零违规
        w("tgt27.md", FM_OK)
        f27 = w("f27.md", FM_OK + "\n> **基于设计**: [DESIGN.md](./tgt27.md) v1.0\n")
        r = check_version_refs([f27], root=tmp)
        expect(len(r) == 0, "F27 版本一致（链接后写法）零违规")

        # F28 链接后版本陈旧且带 ** → P2
        f28 = w("f28.md", FM_OK + "\n> **基于设计**: [DESIGN.md](./tgt27.md) **v1.1**\n")
        r = check_version_refs([f28], root=tmp)
        expect(len(r) == 1 and r[0].severity == "P2" and "版本引用过期" in r[0].message,
               "F28 版本过期（链接后写法）报 P2")

        # F29 label 内版本写法陈旧 → P2
        w("tgt29.md", FM_OK)
        f29 = w("f29.md", FM_OK + "\n> **设计来源**: [RESEARCH v9.9](./tgt29.md)\n")
        r = check_version_refs([f29], root=tmp)
        expect(len(r) == 1 and r[0].severity == "P2" and "v9.9" in r[0].message,
               "F29 版本过期（label 内写法）报 P2")

        # F30 无版本写法 → 不判定（不在判据面）
        f30 = w("f30.md", FM_OK + "\n> **基于设计**: [DESIGN.md](./tgt27.md)（说明文字）\n")
        r = check_version_refs([f30], root=tmp)
        expect(len(r) == 0, "F30 无版本写法不判定")

        # F31 一行双链接：仅第二个陈旧 → 恰 1 条且指向第二个
        w("tgt31.md", FM_OK)
        w("tgt31b.md", FM_OK)
        f31 = w("f31.md", FM_OK + "\n> **被验收物**: [DESIGN v1.0](./tgt31.md) + [IMPLEMENTATION v9.9](./tgt31b.md)\n")
        r = check_version_refs([f31], root=tmp)
        expect(len(r) == 1 and "tgt31b.md" in r[0].message, "F31 双链接仅陈旧项报 P2")

        # F32 非头部声明行（普通正文）→ 不在判据面
        f32 = w("f32.md", FM_OK + "\n正文引用 [DESIGN.md](./tgt27.md) v9.9\n")
        r = check_version_refs([f32], root=tmp)
        expect(len(r) == 0, "F32 普通正文不计入 DC5")

        # F33 围栏内示例头部行 → 不触发
        f33 = w("f33.md", FM_OK + "\n```\n> **基于设计**: [DESIGN.md](./tgt27.md) v9.9\n```\n")
        r = check_version_refs([f33], root=tmp)
        expect(len(r) == 0, "F33 围栏内示例不触发")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print("selftest: %d/%d FAILED" % (len(fails), total[0]))
        return 1
    print("selftest: %d/%d PASS" % (total[0], total[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
