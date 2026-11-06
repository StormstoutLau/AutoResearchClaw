#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spec_Runner — 薄壳 spec 工作流 runner（P-009 方案 B，DESIGN v1.0 D1-D7）。

零框架依赖（Python stdlib only，D6）。事件流 = 唯一 state（L1 append-only JSONL）。
门禁 = 流程门禁执行器（D3：subprocess 执行 + exit 透传，verdict 纯机械映射）。
端点 = 运行时注入 + 就绪门控（D5：预检不可达即 exit 1，不发起主调用）。
adapter 开放结构（D4：NativeHTTPAdapter 默认，DshSDKAdapter 为实测后候选）。

命令面（D7）：run / gate / status / replay / fork（search = grep，零代码）。
P-089：fork 另支持可选「注册三件」（--reason / --trigger-kind / --provenance，
all-or-none）——fork 成功后追加一条返工图登记（docs/rework-graph.json）。
用法示例见 README.md；selftest：python spec_runner.py selftest。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.11.0"
ROOT = Path(__file__).resolve().parent

# ---- 事件行 schema（DESIGN §3 十字段，写入端单点把守） ----
SOURCES = ("system", "user", "assistant", "tool", "gate")
EVENTS = ("session_start", "prompt", "llm_request", "llm_response", "tool",
          "gate", "decision", "endpoint_unreachable", "session_end")
LLM_EVENTS = ("llm_request", "llm_response")  # model/provider 必填非空
SID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
GATE_STDOUT_TAIL = 2000
EXIT_USAGE, EXIT_GATE_MISSING, EXIT_ENDPOINT = 2, 3, 1
# P-022 懒加载门控：会话目录注入 + git 快照 opt-in（ADR-0010 Q3 借懒加载原则）
SESSIONS_ENV = "SR_SESSIONS_DIR"
GIT_AUTOCOMMIT_ENV = "SR_GIT_AUTOCOMMIT"
# P-069 返工图真值源注入（同 SESSIONS_ENV 先例：selftest 隔离，默认 <repo>/docs/rework-graph.json）
REGISTRY_ENV = "SR_REWORK_REGISTRY"


def sessions_dir() -> Path:
    """会话目录：env SR_SESSIONS_DIR 可注入（selftest 用），默认 <repo>/sessions。"""
    return Path(os.environ.get(SESSIONS_ENV, ROOT / "sessions"))


def registry_path() -> Path:
    """返工图真值源路径：env SR_REWORK_REGISTRY 可注入，默认 <repo>/docs/rework-graph.json。"""
    return Path(os.environ.get(REGISTRY_ENV) or (ROOT.parent.parent / "docs" / "rework-graph.json"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---- 模块 1：事件流写入器（L1/L2/L3/L7——唯一写路径，无 rewrite 代码路径） ----
class SessionParseError(ValueError):
    """session JSONL 解析失败（DR-19 方向 B，P-042 v1.18）。

    异常消息**自带上游定位** `<文件路径>:<文件行号>: <msg>`。
    背景 = DR-19 实录：坏行只报**被解析行内**偏移（`line 1 column 834`），
    不报文件名与文件行号 ⇒ 与「line 1」的字面直觉冲突，定位须逐行试错。
    """


class EventWriter:
    def __init__(self, base: Path):
        self.base = base

    def path(self, sid: str) -> Path:
        return self.base / f"{sid}.jsonl"

    def _validate(self, sid, source, event, model, provider, gate):
        if not SID_RE.match(sid or ""):
            raise ValueError(f"bad session id: {sid!r}")
        if source not in SOURCES:
            raise ValueError(f"bad source: {source!r}")
        if event not in EVENTS:
            raise ValueError(f"bad event: {event!r}")
        if event in LLM_EVENTS and not (model and provider):
            raise ValueError(f"{event} requires non-empty model/provider")
        if event == "gate" and not gate:
            raise ValueError("gate event requires gate payload")

    def _read_rows(self, path: Path):
        """逐行解析（DR-19 方向 B：坏行异常附 `<路径>:<行号>`，不再只给行内偏移）。"""
        rows = []
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise SessionParseError(
                        f"{path}:{lineno}: {e.msg} (col {e.colno})") from e
        return rows

    def next_seq(self, sid: str) -> int:
        rows = self._read_rows(self.path(sid))
        return (rows[-1].get("seq", 0) if rows else 0) + 1

    def append(self, sid, source, event, input_=None, output=None,
               gate=None, model=None, provider=None):
        """append-only 写入：校验 → 取 seq → 单行 write + flush。"""
        self._validate(sid, source, event, model, provider, gate)
        row = {"ts": now_iso(), "seq": self.next_seq(sid), "session": sid,
               "source": source, "model": model, "provider": provider,
               "event": event, "input": input_, "output": output, "gate": gate}
        p = self.path(sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:  # 唯一写路径：mode="a"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
        return row

    def read(self, sid):
        return self._read_rows(self.path(sid))


# ---- 模块 6：git 持久化薄封装（P-022 A+B 修复——opt-in 默认关 + 精确 sid 文件 + 会话目录所在 git 根） ----
def _git_root() -> Path | None:
    """会话目录所在 git 根（P-022 F1 修复：从 sessions_dir 而非 ROOT 派生，隔离天然成立）。"""
    try:
        p = subprocess.run(["git", "-C", str(sessions_dir()), "rev-parse",
                            "--show-toplevel"], capture_output=True, text=True,
                           timeout=30)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    out = p.stdout.strip()
    return Path(out) if out else None


def git_snapshot(sid: str, message: str):
    """gate/run 后事件流持久化快照（P-022 A+B）。

    - A 门控：`SR_GIT_AUTOCOMMIT != "1"` 即早退——未激活零副作用（借 ADR-0010 Q3）
    - B 范围：只 add 本次实际写入的 `<sid>.jsonl`（相对会话目录所在 git 根）；
      会话目录不在 git 仓内 → 静默跳过（注释与行为一致）
    - commit 带 `--no-verify`：透明持久化快照不被仓级 pre-commit 三校验器的中间态打断
    """
    if os.environ.get(GIT_AUTOCOMMIT_ENV) != "1":
        return
    try:
        root = _git_root()
        if root is None:
            return  # 非 git 环境——事件流文件本身已是持久化
        target = sessions_dir() / f"{sid}.jsonl"
        rel = target.resolve().relative_to(root.resolve())  # 越界即 ValueError → 跳过
        add = subprocess.run(["git", "add", "--", str(rel)], cwd=root,
                             capture_output=True, timeout=30)
        if add.returncode != 0:
            return
        subprocess.run(["git", "commit", "-m", message, "--quiet", "--no-verify"],
                       cwd=root, capture_output=True, timeout=30)
    except Exception:
        pass


# ---- 模块 2：gate 执行器（D3——verdict = exit code 机械映射，无 LLM 判断） ----
def cmd_gate(args) -> int:
    w = EventWriter(sessions_dir())
    proc = subprocess.run(args.cmd, shell=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          cwd=args.cwd or None)
    stdout_tail = (proc.stdout or "")[-GATE_STDOUT_TAIL:]
    verdict = "pass" if proc.returncode == 0 else "fail"
    w.append(args.session, "gate", "gate",
             input_={"cmd": args.cmd, "cwd": args.cwd},
             output={"stdout_tail": stdout_tail, "exit": proc.returncode},
             gate={"name": args.name, "cmd": args.cmd, "exit": proc.returncode,
                   "verdict": verdict, "stdout_tail": stdout_tail})
    git_snapshot(args.session, f"gate:{args.name}:{verdict} (session {args.session})")
    print(f"gate[{args.name}] verdict={verdict} exit={proc.returncode}")
    return proc.returncode  # 透传（可嵌套 pre-commit/CI）


def gate_passed(w: EventWriter, sid: str, name: str) -> bool:
    """派生视图查询：流中是否存在该 gate 的 pass 事件（D3 前置检查）。"""
    return any(r.get("gate", {}) and r["gate"].get("name") == name
               and r["gate"].get("verdict") == "pass" for r in w.read(sid))


# ---- 模块 2b：step-gate 决策产物管线校验（P-020，CER §3.5——只读校验，三类规则分级 exit） ----
STEP_SEQUENCE = ("research", "design", "implement", "verify", "finalize")
DREQ = ("category", "scenario", "reasoning", "outcome", "confidence")
# U-8（P-092）：finalize 步「上游影响」三态**封闭集**。
# 裁定（DESIGN §10.6）= **代码常量**（与 `DREQ` / `STEP_SEQUENCE` 同类——decision schema 的
# 封闭枚举）；**不入返工图**——返工图是「返工边」真值源、非 decision schema 真值源，
# 故与 I-17「触发枚举单一真值源」**无冲突**（该条只约束 `trigger_kinds`）。
IMPACT_STATES = ("none", "partial", "overturned")
# U-8 **过渡期判据（机械边界）**：仅 P 编号 ≥ 本值的批次 session 受新硬性组约束。
# 依据（E1，2026-10-13 实测）= 115 session 中 **103 含 finalize 决策**、其中带
# `metadata.upstream_impact` 者 **0 例**、P 编号 ≥ P-092 者 **0 例** ⇒ 无过渡期时
# 103 个历史 session 会被判硬性（**门禁链断裂**）；设 92 后存量零回归，且**本批自证**
# （P-092 自身须带该字段——吃狗粮）。同 V1a′ 先例「机械边界 = P 编号 ≥ 某号」。
FINALIZE_IMPACT_MIN_P = 92
BATCH_SID_RE = re.compile(r"^specwf-p(\d{3})-")
# P-064「§ 编号空间收口」：J1（ANCHOR_RE）与 J2（_resolve_anchor）的**交集口径单点定义**——
# 数字，或「字母 + 可选数字」，点分隔分段（`3.5` / `B` / `B4` / `D1` / `B4.2`）；
# **大小写敏感**（与标题 token 逐字符一致）；**多字母词形不受理**（`§selftest` 仍属形态不可解析）。
# 两处**共用本常量** ⇒ 「两实现漂移」在构造上不可发生（B25 / I-10 / A-33 教训）。
# 注：**「是否要求定位符」**属**唯一的差集口径**，仍由两处各自显式表达（B19 正确分工）。
# P-091「候选扩权」：J1 **去前缀白名单**（原 `(?:spec|adr|docs|tools|scripts)/` 只存在于 J1，
# 致根级权威源载体 `CODE_WIKI.md` / `SPEC_PROCESS.md` / `AGENTS.md` 上的定位符锚点被判 soft→阻断
# 而 J2 判真实 = 不变量 `J2 ⊆ J1` 的唯一方向性偏离 d 类）；J1 与 J2 的路径字符类**逐字对齐**
# （`[A-Za-z0-9_./\-]+\.(?:md|py|jsonl)`）⇒ 不变量自此**在构造上成立**，`anchor-audit` 的差集读数
# 语义随之由「候选扩权触发条件」改为「**不变量违反 = 缺陷**」。
SECTION_ID = r"(?:[0-9]+|[A-Za-z][0-9]*)(?:\.(?:[0-9]+|[A-Za-z][0-9]*))*"
ANCHOR_RE = re.compile(
    r"^(https?://\S+|"
    r"[A-Za-z0-9_./\-]+(?:\.(?:md|py|jsonl))?"
    r"(?:#[L]\d+|L\d+|\s*§" + SECTION_ID + r")?)$")


def _decision_chain(decisions):
    """决策链机械解析（step-gate 与 backflow-audit **共用同一实现**，守 I-10/B25）。

    规则（DESIGN §6.2 + P-069 回边受理）：
      - 硬性 schema：DREQ 八字段齐 + metadata.step_id/step_seq + evidence 非空
      - 硬性 位错：step_id ∉ 序表 或 step_seq ≠ 序表位
      - 硬性 同位重复：sseq == 前步（非回退、非推进）——**仍判硬性**（回边受理不豁免真重复）
      - **受控回边（P-069）**：sseq < 前步（回退到上游步位）⇒ 受理，记入 back_edges
      - 软性 锚点：evidence[].anchor 形态可解析（正则）
    返回 (hard, soft, seen, back)：
      seen = {step_id: seq}（首现插入序，供 --expect 比对）
      back = [(seq, step_id)] 受控回边
    """
    hard, soft, seen, back, prev = [], [], {}, [], None
    for r in decisions:
        inp = r.get("input") if isinstance(r.get("input"), dict) else {}
        md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
        missing = [k for k in DREQ if k not in inp]
        if not md.get("step_id") or md.get("step_seq") is None:
            missing.append("metadata.step_id/step_seq")
        if not (isinstance(md.get("evidence"), list) and md["evidence"]):
            missing.append("metadata.evidence 非空")
        if missing:
            hard.append(f"seq{r.get('seq')} 缺字段: {missing}")
            continue
        sid_, sseq = md["step_id"], md["step_seq"]
        if sid_ not in STEP_SEQUENCE or sseq != STEP_SEQUENCE.index(sid_) + 1:
            hard.append(f"seq{r.get('seq')} step 位错 (step_id={sid_!r}, step_seq={sseq})")
            seen[sid_] = r.get("seq")
            continue
        if prev is not None and sseq < prev:
            back.append((r.get("seq"), sid_))          # 受控回边：受理
        elif prev is not None and sseq == prev:
            hard.append(f"seq{r.get('seq')} step_id 重复 {sid_!r}（同位重复，非受控回边）")
        prev = sseq
        seen[sid_] = r.get("seq")
        for ev in md["evidence"]:
            anchor = ev.get("anchor") if isinstance(ev, dict) else str(ev)
            if anchor and not ANCHOR_RE.match(anchor):
                soft.append(f"seq{r.get('seq')} 锚点形态存疑 {str(anchor)[:50]!r}")
    return hard, soft, seen, back


def _finalize_impact_check(decisions, sid, registered, registry_ok):
    """U-8 硬性组（P-092）：`finalize` 决策强制 `metadata.upstream_impact` 三态。

    规则（DESIGN §10.6 裁定）：
      - **过渡期判据（机械边界）**：仅 sid 形态 `specwf-p<NNN>-` 且 NNN ≥ `FINALIZE_IMPACT_MIN_P`
        时**适用**；形态不匹配 / 历史批次 ⇒ **不适用**（返回空——存量零回归）
      - **硬性-①**：finalize 决策须带 `metadata.upstream_impact` ∈ `IMPACT_STATES`
      - **硬性-②**：取值 ≠ `none` ⇒ 该 session 须**已登记返工图**（`registered` 来自
        `_registry_derive`，与 `backflow-audit` 的「待回写」判据**逐字同口径**，守 I-10/I-17）
      - **降级臂**：返工图不可用（`registry_ok` 为假）⇒ ② 转**软性**（人工复核），**不静默当作通过**
    返回 (hard, soft)。
    """
    m = BATCH_SID_RE.match(sid or "")
    if not m or int(m.group(1)) < FINALIZE_IMPACT_MIN_P:
        return [], []
    hard, soft = [], []
    for r in decisions:
        inp = r.get("input") if isinstance(r.get("input"), dict) else {}
        md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
        if md.get("step_id") != "finalize":
            continue
        v = md.get("upstream_impact")
        if v not in IMPACT_STATES:
            hard.append(f"seq{r.get('seq')} finalize 缺/非法 upstream_impact: {v!r}"
                        f"（须 ∈ {list(IMPACT_STATES)}）")
        elif v != "none":
            if not registry_ok:
                soft.append(f"seq{r.get('seq')} upstream_impact={v} 且返工图不可用"
                            "（非 none 耦合未判——人工复核）")
            elif sid not in registered:
                hard.append(f"seq{r.get('seq')} upstream_impact={v} 但该 session 未登记返工图"
                            "（非 none ⇒ 须有对应返工登记）")
    return hard, soft


def cmd_gate_step(args) -> int:
    """校验 session 内 decision 事件链——只读不写流。

    四类规则（DESIGN §6.2 + §10.6）：
      - 硬性-1 schema：八字段必填 + metadata.step_id/step_seq + evidence 非空
      - 硬性-2 秩序：step_id ∈ 序表、step_seq = 序表位、同位重复禁止、--expect 覆盖时全链一致
                    （**受控回边**：step_seq 回退到上游步位 = 受理并登记，见 `_decision_chain`）
      - 硬性-3（**U-8 / P-092**）：`finalize` 决策强制 `upstream_impact` 三态；非 `none` ⇒
                    该 session 须已登记返工图（**过渡期 = P 编号 ≥ 92**；见 `_finalize_impact_check`）
      - 软性-4 锚点：evidence[].anchor 形态可解析（正则）
    exit 0 / 1（硬性）/ 2（软性存疑；未显式声明 --expect / --legacy）。
    """
    w = EventWriter(sessions_dir())
    decisions = [r for r in w.read(args.session) if r.get("event") == "decision"]
    if not decisions:
        print(f"step-gate[{args.session}]: 无 decision 事件（决策记录纪律未执行）")
        return 1
    hard, soft, seen, back = _decision_chain(decisions)
    _, registered, regerr = _load_rework_registry()          # U-8（P-092）
    ui_hard, ui_soft = _finalize_impact_check(decisions, args.session, registered,
                                              regerr is None)
    hard += ui_hard
    soft += ui_soft
    got = list(seen)
    expect = tuple(args.expect) if args.expect else None
    legacy = bool(getattr(args, "legacy", False))
    if args.expect is not None and not args.expect:
        print(f"step-gate[{args.session}]: --expect 不得为空（显式完整链或 --legacy）")
        return 2
    if expect and legacy:
        print(f"step-gate[{args.session}]: --expect 与 --legacy 互斥")
        return 2
    if not expect and not legacy:
        print(f"step-gate[{args.session}]: 必须显式声明 --expect <steps> 或 --legacy"
              "（隐式 legacy 已移除；完整链校验请给 --expect）")
        return 2
    if expect:
        if len(got) != len(expect) or got != list(expect):
            hard.append(f"期望链 {list(expect)} ≠ 已登记 {got}")
    else:
        print(f"step-gate[{args.session}]: mode=legacy 已登记 {len(got)}/{len(STEP_SEQUENCE)} 步 ({got})"
              "（仅内部一致性，未声明完整链）")
    for seq, sid_ in back:
        print(f"  [REWORK] seq{seq} 受控回边（重入 {sid_}）——已受理；"
              "如属真实返工须经 backflow-audit + 返工图登记")
    for m in hard:
        print(f"  [HARD] {m}")
    for m in soft:
        print(f"  [SOFT] {m}")
    if hard:
        print(f"step-gate[{args.session}]: hard={len(hard)} soft={len(soft)} → exit 1")
        return 1
    if soft:
        print(f"step-gate[{args.session}]: soft={len(soft)} → exit 2（人工复核）")
        return 2
    print(f"step-gate[{args.session}]: 决策链一致 pass → exit 0")
    return 0


# ---- 模块 2c：step-enforce 批次级流程强制（P-024，ADR-0011 出路 A——只读校验：session 存在 + 决策流非空） ----
def cmd_step_enforce(args) -> int:
    """批次级流程强制：按 P 编号前缀定位 specwf-p0xx-* session，复用 step-gate 校验。

    只读零副作用（P-022 教训：不创建/修改/提交任何文件）。
    exit 0 = 决策流存在且通过 step-gate 基础校验；1 = 无 session / 空链 / 硬性违规；2 = 软性存疑。
    """
    w = EventWriter(sessions_dir())
    prefix = f"specwf-{args.pid.lower().replace('-', '')}-"
    matches = sorted(p.name for p in w.base.glob(f"{prefix}*.jsonl"))
    if not matches:
        print(f"step-enforce[{args.pid}]: 无 session 匹配 {prefix}*"
              "（决策记录纪律未执行——需先创建 session 并写入 ≥1 decision）")
        return 1
    sid = matches[-1][:-len(".jsonl")]  # 取最新（文件名排序末位）
    print(f"step-enforce[{args.pid}]: session 定位 {sid}")
    return cmd_gate_step(argparse.Namespace(session=sid, expect=None, legacy=True))


# ---- 模块 2d：verify-anchor 锚点真实性取证（P-025，ADR-0011 出路 C——只读取证：文件存在 + 章节精确匹配 + 行号上界） ----
ROOT_REPO = ROOT.parent.parent  # 仓库根（锚点路径相对仓库根解析；spec_runner 在 tools/spec_runner/）


def _resolve_anchor(anchor: str):
    """锚点解析 → (kind, path, loc)。kind ∈ section/line/url/unresolved。

    § 编号空间 = `SECTION_ID`（**与 `ANCHOR_RE` 共用同一常量**，P-064 收口）：
    数字或「字母 + 可选数字」、点分隔；大小写敏感；多字母词形不受理。
    """
    m = re.match(r"^([A-Za-z0-9_./\-]+\.(?:md|py|jsonl))\s*§("
                 + SECTION_ID + r")$", anchor)
    if m:
        return ("section", m.group(1), m.group(2))
    m = re.match(r"^([A-Za-z0-9_./\-]+\.(?:md|py|jsonl))#L(\d+)$", anchor)
    if m:
        return ("line", m.group(1), int(m.group(2)))
    if anchor.startswith(("http://", "https://")):
        return ("url", anchor, None)
    return ("unresolved", anchor, None)


def _check_anchor(path, kind, loc):
    """真实性核查 → None（真实）/ 硬性错误字符串 / 'soft'（URL 不可本地核）。"""
    if kind == "url":
        return "soft"
    if kind == "unresolved":
        return f"锚点形态不可解析: {path[:60]!r}"
    full = ROOT_REPO / path
    if not full.is_file():
        return f"文件不存在: {path}"
    text = full.read_text(encoding="utf-8", errors="replace")
    if kind == "section":
        # 章节标题精确匹配：标题首 token（去尾点，`4.` → `4`）== 锚点 N；
        # §3.5 只命中 token 3.5，不命中 3.5.1 或 3
        tok = loc.rstrip(".")
        pat = re.compile(r"^#{1,6}\s+(\S+)")
        if not any(m and m.group(1).rstrip(".") == tok
                   for m in (pat.match(line) for line in text.splitlines())):
            return f"章节不存在: {path} §{loc}"
    else:  # line
        total = len(text.splitlines())
        if loc > total:
            return f"行号越界: {path}#L{loc}（总行数 {total}）"
    return None


def cmd_verify_anchor(args) -> int:
    """审查取证：session 内 decision 锚点真实性核查——只读零副作用（P-022 教训）。

    exit 0 = 全部锚点真实；1 = 硬性（文件/章节/行号缺失）；2 = 软性（URL 或不可解析）。
    """
    w = EventWriter(sessions_dir())
    decisions = [r for r in w.read(args.session) if r.get("event") == "decision"]
    if not decisions:
        print(f"verify-anchor[{args.session}]: 无 decision 事件（无可验锚点）")
        return 1
    hard, soft, ok = [], [], 0
    details = []  # DR-21 方向 B(i)：开发期逐锚点明细（默认关闭，守 I-2 确定性）
    for r in decisions:
        inp = r.get("input") if isinstance(r.get("input"), dict) else {}
        md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
        for ev in md.get("evidence") or []:
            anchor = ev.get("anchor") if isinstance(ev, dict) else str(ev)
            if not anchor:
                continue
            kind, path, loc = _resolve_anchor(anchor)
            res = _check_anchor(path, kind, loc)
            if res == "soft":
                soft.append(f"seq{r.get('seq')} {anchor[:60]!r}（外部证据，本地不可核）")
                details.append((r.get("seq"), "软性", anchor, "外部证据，本地不可核"))
            elif res:
                hard.append(f"seq{r.get('seq')} {res}")
                details.append((r.get("seq"), "硬性", anchor, res))
            else:
                ok += 1
                details.append((r.get("seq"), "真实", anchor,
                                f"位置可达（{kind} {path}"
                                + (f" §{loc}" if kind == "section" else
                                   f"#L{loc}" if kind == "line" else "") + "）"))
    if getattr(args, "detail", False):
        for seq, verdict, anchor, why in details:
            print(f"  [DETAIL] seq{seq} {verdict} {anchor!r} —— {why}")
    for m in hard:
        print(f"  [HARD] {m}")
    for m in soft:
        print(f"  [SOFT] {m}")
    print(f"verify-anchor[{args.session}]: 锚点 {ok} 真实 / {len(hard)} 硬性 / {len(soft)} 软性")
    if hard:
        print(f"verify-anchor[{args.session}]: → exit 1（硬性违规——自报锚点指向不真实位置）")
        return 1
    if soft:
        print(f"verify-anchor[{args.session}]: → exit 2（软性存疑，人工复核）")
        return 2
    print(f"verify-anchor[{args.session}]: 全部锚点真实 → exit 0")
    return 0


# ---- 模块 2e：anchor-audit 锚点形态集合对账（P-042 v1.20，DR-25——只读诊断；不接门禁） ----
def cmd_anchor_audit(args) -> int:
    """锚点形态集合对账：列出 J2\\J1 实例——只读零副作用。

    J1 = ANCHOR_RE（step-gate 软性面；经 step_enforce.py 的「非 0 即 fail」升级为阻断级）
    J2 = _resolve_anchor 可解析的位置形态（section / line）
    不变量 J2 ⊆ J1（independent-verify DESIGN §4.1.2）：**P-091 起该不变量在构造上成立**
    （两处路径字符类逐字对齐、J1 无前缀白名单）⇒ 差集非空 = **不变量被违反 = 缺陷**，
    不再是「候选扩权触发条件」（扩权已于 P-091 实施；本命令转为该不变量的**机械守门**）。
    exit 0 = 不变量成立（差集空）；1 = 不变量被违反（列出实例）；2 = 目录无 session 文件
    （坏行沿用 EventWriter 语义：解析失败即中断并报 `<路径>:<行号>` → exit 1，不静默跳过）
    """
    w = EventWriter(sessions_dir())
    if getattr(args, "session", None):
        paths = [w.path(args.session)]
    else:
        paths = sorted(w.base.glob("*.jsonl"))
    total = j1_ok = j2_pos = j1_not_j2 = other = 0
    diff = []
    for p in paths:
        sid = p.name[:-len(".jsonl")]
        for r in w._read_rows(p):
            if r.get("event") != "decision":
                continue
            inp = r.get("input") if isinstance(r.get("input"), dict) else {}
            md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
            for ev in md.get("evidence") or []:
                a = ev.get("anchor") if isinstance(ev, dict) else str(ev)
                if not a:
                    continue
                total += 1
                m1 = bool(ANCHOR_RE.match(a))
                pos2 = _resolve_anchor(a)[0] in ("section", "line")
                if m1:
                    j1_ok += 1
                if pos2:
                    j2_pos += 1
                if pos2 and not m1:
                    diff.append((sid, r.get("seq"), a))
                elif m1 and not pos2:
                    j1_not_j2 += 1
                elif not m1 and not pos2:
                    other += 1
    print(f"anchor-audit: 扫描 {len(paths)} session / {total} 锚点")
    print(f"  J1 匹配（ANCHOR_RE）: {j1_ok}；J2 可解析（section/line）: {j2_pos}")
    print(f"  J2\\J1（取证放行但门禁不匹配 = **不变量被违反 · 缺陷**）: {len(diff)}")
    print(f"  J1\\J2（门禁放行但取证判硬性 = 正确分工面）: {j1_not_j2}；两处皆不支持: {other}")
    for sid, seq, a in diff:
        print(f"  [DEFECT] {sid} seq{seq} {a!r}")
    if diff:
        print(f"anchor-audit: **不变量 J2 ⊆ J1 被违反（{len(diff)} 例 = 缺陷）** → exit 1"
              "（须修判定面，使 J1 重新覆盖 J2）")
        return 1
    print("anchor-audit: 不变量 J2 ⊆ J1 成立（差集 0 例）→ exit 0")
    return 0


# ---- 模块 2f：backflow-audit 回写/回边待处理检测（P-069——只读诊断；不接门禁，同 anchor-audit 先例） ----
def _load_registry_raw():
    """返工图真值源**原文**加载 → (reg|None, err|None)。

    P-089：注册写入（cmd_fork）与只读派生（backflow-audit）**共用同一解析**。
    err = None（成功）/ 字符串（缺失或不可解析 ⇒ 调用方降级 exit 2，不当作通过）。
    """
    p = registry_path()
    if not p.is_file():
        return None, f"登记表缺失: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:                                          # noqa: BLE001
        return None, f"登记表不可解析: {type(e).__name__}: {e}"


def _registry_derive(reg):
    """从返工图原文派生 (trigger_kinds, registered, err)。

    registered = 已登记 session 名集（`forks[].new`/`.origin` + `non_rework[].name`）。
    **触发枚举只此一处来源**（守 I-10：绝不复制一份常量；P-089 注册前置校验同源复用）。
    """
    tk = reg.get("trigger_kinds")
    if not isinstance(tk, list) or not tk:
        return None, set(), "登记表 trigger_kinds 为空/非数组（无封闭集可判）"
    registered = set()
    for f in reg.get("forks") or []:
        if isinstance(f, dict):
            for k in ("new", "origin"):
                if isinstance(f.get(k), str) and f[k]:
                    registered.add(f[k])
    for x in reg.get("non_rework") or []:
        if isinstance(x, dict) and isinstance(x.get("name"), str) and x["name"]:
            registered.add(x["name"])
    return list(tk), registered, None


def _load_rework_registry():
    """读返工图真值源（`docs/rework-graph.json`）→ (trigger_kinds, registered, err)。

    err = None（成功）/ 字符串（缺失或不可解析 ⇒ 调用方降级 exit 2，不当作通过）。
    **触发枚举只此一处来源**（守 I-10：绝不复制一份常量）。
    """
    reg, err = _load_registry_raw()
    if err:
        return None, set(), err
    return _registry_derive(reg)


def cmd_backflow_audit(args) -> int:
    """回写/回边待处理检测——只读零副作用、**不接门禁**（同 anchor-audit 先例）。

    三个**机械可判**信号（真值源 = `docs/rework-graph.json` 的 `trigger_kinds`）：
      ① **待重入**：session 决策链含**受控回边**（step-gate 已受理），且该 session 未登记返工图；
      ② **待回写**：decision 携带 `metadata.trigger` ∈ `trigger_kinds`，但 session 未登记返工图；
      ③ **失败枚举**：`metadata.trigger` 取值 ∉ `trigger_kinds`（非法枚举值）。
    exit 0 = 无待处理；1 = 检出待回写/待重入/非法 trigger；2 = 无 session 或无登记（降级）。
    （坏行沿用 EventWriter 语义：解析失败即报 `<路径>:<行号>` → exit 1，不静默跳过）
    """
    kinds, registered, err = _load_rework_registry()
    if err:
        print(f"backflow-audit: {err} ⇒ exit 2（降级，不当作通过）")
        return 2
    w = EventWriter(sessions_dir())
    if getattr(args, "session", None):
        p = w.path(args.session)
        if not p.exists():
            print(f"backflow-audit: session 不存在: {args.session} ⇒ exit 2")
            return 2
        paths = [p]
    else:
        paths = sorted(w.base.glob("*.jsonl"))
        if not paths:
            print("backflow-audit: sessions 目录无会话文件 ⇒ exit 2")
            return 2
    pending, invalid = [], []
    for p in paths:
        sid = p.name[:-len(".jsonl")]
        decisions = [r for r in w._read_rows(p) if r.get("event") == "decision"]
        if not decisions:
            continue
        _, _, _, back = _decision_chain(decisions)
        if sid not in registered:
            for seq, step in back:
                pending.append((sid, "待重入", f"seq{seq} 受控回边（重入 {step}）未登记返工图"))
        for r in decisions:
            inp = r.get("input") if isinstance(r.get("input"), dict) else {}
            md = inp.get("metadata") if isinstance(inp.get("metadata"), dict) else {}
            trig = md.get("trigger")
            if trig is None:
                continue
            if trig not in kinds:
                invalid.append((sid, f"seq{r.get('seq')} trigger={trig!r} ∉ trigger_kinds"))
            elif sid not in registered:
                pending.append((sid, "待回写", f"seq{r.get('seq')} trigger={trig}（未登记返工图）"))
    print(f"backflow-audit: 扫描 {len(paths)} session；"
          f"trigger_kinds={kinds}（真值源 {registry_path()}）")
    for sid, kind, why in pending:
        print(f"  [PENDING] {sid} {kind} —— {why}")
    for sid, why in invalid:
        print(f"  [INVALID] {sid} —— {why}")
    if pending or invalid:
        print(f"backflow-audit: 待处理 {len(pending)} + 失败枚举 {len(invalid)}"
              " ⇒ exit 1（人工处置：登记返工图 / 订正 trigger 取值）")
        return 1
    print("backflow-audit: 无待回写/待重入（0 例）⇒ exit 0")
    return 0


# ---- 模块 3：adapter 接口 + NativeHTTP（D4/D5——stdlib urllib，预检门控 + 重试） ----
class LLMAdapter:
    """协议面（D4 开放结构单点）：chat / endpoint_ready。"""

    def chat(self, messages, **params):
        raise NotImplementedError

    def endpoint_ready(self) -> bool:
        raise NotImplementedError


class NativeHTTPAdapter(LLMAdapter):
    def __init__(self, endpoint, model, provider, timeout=60):
        self.endpoint = endpoint.rstrip("/")
        self.model, self.provider, self.timeout = model, provider, timeout

    def endpoint_ready(self) -> bool:
        try:
            req = urllib.request.Request(self.endpoint + "/v1/models")
            urllib.request.urlopen(req, timeout=3)
            return True
        except Exception:
            return False

    def chat(self, messages, **params):
        payload = json.dumps({"model": self.model, "messages": messages,
                              **params}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint + "/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        last_err = None
        for attempt in range(3):  # 超时重试 2 次
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:  # noqa: BLE001——薄壳统一异常面
                last_err = e
                if attempt < 2:
                    time.sleep(1)
        raise last_err


def make_adapter(args):
    endpoint = args.endpoint or os.environ.get("SR_ENDPOINT")
    model = args.model or os.environ.get("SR_MODEL")
    provider = args.provider or os.environ.get("SR_PROVIDER")
    missing = [n for n, v in (("endpoint", endpoint), ("model", model),
                              ("provider", provider)) if not v]
    if missing:
        print(f"run: missing {missing} (--flag 或 SR_* env 注入)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    return NativeHTTPAdapter(endpoint, model, provider)


# ---- 模块 4：run 命令（L2 装配后请求入流 / L6 新 sid 强制 / D5 门控） ----
def cmd_run(args) -> int:
    sid = args.session
    if not SID_RE.match(sid or ""):
        print(f"run: bad session id {sid!r} (^[a-z0-9-]+$ <=64)", file=sys.stderr)
        return EXIT_USAGE
    w = EventWriter(sessions_dir())
    exists = w.path(sid).exists()
    if exists and not args.resume:  # L6：RULE-1 物理化——同 sid 复用必须显式 --resume
        print(f"run: session {sid} exists (resume with --resume)", file=sys.stderr)
        return EXIT_USAGE
    for g in (args.require_gate or []):  # D3 前置检查：审查 gate 未过实施不可启动
        if not gate_passed(w, sid, g):
            print(f"run: required gate '{g}' not passed in {sid}", file=sys.stderr)
            return EXIT_GATE_MISSING
    adapter = make_adapter(args)
    if not exists:
        w.append(sid, "system", "session_start",
                 input_={"task": args.task, "model": adapter.model,
                         "provider": adapter.provider, "endpoint": adapter.endpoint})
    if not adapter.endpoint_ready():  # D5：预检不可达即 exit 1，不发起主调用
        w.append(sid, "tool", "endpoint_unreachable",
                 input_={"endpoint": adapter.endpoint, "checked_at": now_iso()})
        print(f"run: endpoint unreachable: {adapter.endpoint}", file=sys.stderr)
        return EXIT_ENDPOINT
    prompt_text = args.prompt
    if args.prompt_file:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    if not prompt_text:
        print("run: --prompt or --prompt-file required", file=sys.stderr)
        return EXIT_USAGE
    messages = [{"role": "user", "content": prompt_text}]
    w.append(sid, "user", "prompt", input_={"messages": messages})
    w.append(sid, "assistant", "llm_request",  # L2：记录装配后实际请求
             input_={"messages": messages, "params": {}},
             model=adapter.model, provider=adapter.provider)
    resp = adapter.chat(messages)
    w.append(sid, "assistant", "llm_response", output=resp,
             model=adapter.model, provider=adapter.provider)
    w.append(sid, "system", "session_end", output={"status": "done"})
    try:
        text = resp["choices"][0]["message"]["content"]
    except Exception:
        text = json.dumps(resp, ensure_ascii=False)
    print(text)
    git_snapshot(sid, f"run:{sid} (session appended)")
    return 0


# ---- 模块 5：status / replay / fork 派生件（L1 状态=派生 / L4 共享流） ----
def cmd_status(args) -> int:
    w = EventWriter(sessions_dir())
    sids = [args.session] if args.session else sorted(
        p.stem for p in sessions_dir().glob("*.jsonl"))
    for sid in sids:
        rows = w.read(sid)
        if not rows:
            continue
        gates = {r["gate"]["name"]: r for r in rows if r.get("gate")}
        print(f"session: {sid}  seq_max: {rows[-1]['seq']}  "
              f"last_event: {rows[-1]['event']}")
        for name, r in gates.items():
            print(f"  gate[{name}]: {r['gate']['verdict']} "
                  f"(seq {r['seq']}, exit {r['gate']['exit']})")
    return 0


def cmd_replay(args) -> int:
    """重放校验：seq 从 1 单调 + 每行可解析 + llm_request 装配载荷完整（ADD 复现）。"""
    w = EventWriter(sessions_dir())
    rows = w.read(args.session)
    errors = []
    for i, r in enumerate(rows, 1):
        if r.get("seq") != i:
            errors.append(f"seq {r.get('seq')} != expected {i}")
        if r.get("session") != args.session:
            errors.append(f"seq {i}: session mismatch")
        if r.get("event") == "llm_request":
            msgs = (r.get("input") or {}).get("messages")
            if not (isinstance(msgs, list) and msgs):
                errors.append(f"seq {i}: llm_request input.messages empty")
    if errors:
        for e in errors:
            print(f"replay: {e}", file=sys.stderr)
        return 1
    print(f"replay: {len(rows)} rows OK (seq monotonic, schema parseable)")
    return 0


def _fork_reg_validate(reg, kinds, registered, args) -> str | None:
    """P-089 写入端**最小前置校验**（fail-fast 子集）→ 错误串 / None。

    与对账器（`scripts/rework_graph_check.py`）的关系：**完整判定单点在对账器**；
    本函数只拦「确定会把无效值写进真值源」的输入（值域一律读真值源，守 I-17）——
      ① reason 非空白、禁禁用词 `unknown`；② trigger_kind ∈ 封闭集（读真值源）；
      ③ provenance 形态（含 `<前缀>:<载荷>` / 前缀 ∈ 封闭集 / 载荷非空）；
      ④ new 不在已登记名集（防与既有边 / 豁免歧义）。
    跨文件对账（对账器 C/D 段）**零复刻**；两处若漂移以对账器为准（它更严）。
    """
    def _blank(v) -> bool:
        t = v.strip() if isinstance(v, str) else ""
        return (not t) or t.lower() == "unknown"

    if _blank(args.reason):
        return "reason 空 / 仅空白 / 禁用词 unknown"
    if args.trigger_kind not in kinds:
        return f"trigger_kind 不在封闭集（真值源）: {args.trigger_kind!r}"
    prov = args.provenance
    if _blank(prov):
        return "provenance 空 / 仅空白 / 禁用词 unknown"
    if ":" not in prov:
        return "provenance 缺 <前缀>:<载荷> 形式"
    pref, _, payload = prov.partition(":")
    prefixes = reg.get("provenance_prefixes")
    if not isinstance(prefixes, list) or pref not in prefixes:
        return f"provenance 前缀 不在封闭集（真值源）: {pref!r}"
    if not payload.strip():
        return "provenance 载荷为空（有前缀没有内容）"
    if args.new in registered:
        return f"new 已在已登记名集（防歧义）: {args.new!r}"
    if not isinstance(reg.get("forks"), list):
        return "登记表 forks 字段缺失/非数组（先修表再注册）"
    return None


def cmd_fork(args) -> int:
    w = EventWriter(sessions_dir())
    # P-089：注册三件（可选；all-or-none。三件全缺 ⇒ 与 P-009 原行为逐字一致）
    given = [x for x in (args.reason, args.trigger_kind, args.provenance)
             if x is not None]
    if given and len(given) != 3:
        print("fork: 注册三件须齐给（all-or-none）：--reason / --trigger-kind / "
              "--provenance", file=sys.stderr)
        return EXIT_USAGE
    register = len(given) == 3
    src = w.read(args.session)
    if not src:
        print(f"fork: source session empty/missing: {args.session}", file=sys.stderr)
        return EXIT_USAGE
    if w.path(args.new).exists():
        print(f"fork: target session exists: {args.new}", file=sys.stderr)
        return EXIT_USAGE
    kept = [r for r in src if r["seq"] <= args.seq_from]
    if not kept:
        print(f"fork: no rows with seq <= {args.seq_from}", file=sys.stderr)
        return EXIT_USAGE
    reg = entry = None
    if register:  # 校验先于任何写入（fork 未执行即失败 ⇒ 无半成品）
        reg, err = _load_registry_raw()
        if err is None:
            kinds, registered, err = _registry_derive(reg)
        if err is None:
            err = _fork_reg_validate(reg, kinds, registered, args)
        if err:
            print(f"fork: 注册不可用：{err}（未执行 fork）", file=sys.stderr)
            return EXIT_USAGE
        today = datetime.now().strftime("%Y-%m-%d")
        # seq_from 登记 = **实际复制行数**（机械真值；请求 N 超出源末端时以实况为准）
        entry = {"new": args.new, "origin": args.session, "seq_from": len(kept),
                 "trigger_kind": args.trigger_kind, "reason": args.reason,
                 "provenance": args.provenance, "date": today}
    p = w.path(args.new)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:  # L4：fork = 从事件 i 复制出新流
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if register:  # fork 已落盘 → 追加登记（格式保真 dump；写入端单点）
        reg["forks"].append(entry)
        reg["updated"] = entry["date"]
        rp = registry_path()
        tmp = rp.with_suffix(rp.suffix + ".tmp")
        tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.replace(tmp, rp)
        print(f"register: forks += {args.new} <- {args.session} "
              f"(seq_from={entry['seq_from']}, {args.trigger_kind})")
    print(f"fork: {args.new} <- {args.session} (seq 1..{kept[-1]['seq']}, "
          f"{len(kept)} rows)")
    return 0


# ---- CLI 入口（模块 7 的一半；selftest 为另一半） ----
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spec_runner",
        description="薄壳 spec 工作流 runner（P-009 方案 B）")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="装配 prompt → LLM → 事件入流")
    r.add_argument("--task", required=True)
    r.add_argument("--session", required=True)
    r.add_argument("--prompt")
    r.add_argument("--prompt-file")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--require-gate", action="append", default=[],
                   help="启动前须已在流中 pass 的 gate 名（可多次）")
    for flag in ("endpoint", "model", "provider"):
        r.add_argument(f"--{flag}")
    r.set_defaults(func=cmd_run)
    g = sub.add_parser("gate", help="流程门禁执行器（exit 透传）")
    g.add_argument("--name", required=True)
    g.add_argument("--cmd", required=True)
    g.add_argument("--session", required=True)
    g.add_argument("--cwd", help="命令工作目录")
    g.set_defaults(func=cmd_gate)
    s = sub.add_parser("status", help="派生视图：gate 通过态 / seq / 末事件")
    s.add_argument("--session")
    s.set_defaults(func=cmd_status)
    v = sub.add_parser("replay", help="重放校验（seq 单调 + 行可解析）")
    v.add_argument("--session", required=True)
    v.set_defaults(func=cmd_replay)
    f = sub.add_parser("fork", help="复制前 N seq 行至新流（L4；+P-089 可选注册三件）")
    f.add_argument("--session", required=True)
    f.add_argument("--seq", type=int, required=True, dest="seq_from")
    f.add_argument("--new", required=True)
    f.add_argument("--reason", help="注册用：返工原因（非空，禁 unknown）")
    f.add_argument("--trigger-kind", help="注册用：触发种类（∈ 返工图 trigger_kinds）")
    f.add_argument("--provenance", help="注册用：<前缀>:<载荷>（前缀 ∈ provenance_prefixes）")
    f.set_defaults(func=cmd_fork)
    sg = sub.add_parser("step-gate", help="决策产物管线校验（P-020：schema/evidence/step 序，只读）")
    sg.add_argument("--session", required=True)
    sg.add_argument("--expect", nargs="*", default=None,
                    help="期望完整链 step_id 列表（与 --legacy 二选一；缺失即 exit 2）")
    sg.add_argument("--legacy", action="store_true",
                    help="显式 legacy：仅校验已登记链内部一致性（不要求完整链）")
    sg.set_defaults(func=cmd_gate_step)
    se = sub.add_parser("step-enforce", help="批次级流程强制（P-024：定位 specwf-p0xx-* session + 决策流校验，只读）")
    se.add_argument("--pid", required=True, help="P 编号（如 P-024）——session 前缀锚点")
    se.set_defaults(func=cmd_step_enforce)
    va = sub.add_parser("verify-anchor", help="锚点真实性取证（P-025，ADR-0011 出路 C：文件存在 + 章节/行号核查，只读）")
    va.add_argument("--session", required=True, help="目标 session")
    va.add_argument("--detail", action="store_true",
                    help="逐锚点明细（DR-21 方向 B：开发期定位用；默认关闭，守确定性 I-2）")
    va.set_defaults(func=cmd_verify_anchor)
    aa = sub.add_parser("anchor-audit",
                        help="锚点形态集合对账（P-042 v1.20，DR-25：J1/J2 差集 = 候选扩权触发条件；只读、不接门禁）")
    aa.add_argument("--session", help="仅审该 session（缺省 = 扫描 sessions 目录全部）")
    aa.set_defaults(func=cmd_anchor_audit)
    ba = sub.add_parser("backflow-audit",
                        help="回写/回边待处理检测（P-069：受控回边 + trigger 标记未登记；只读、不接门禁）")
    ba.add_argument("--session", help="仅审该 session（缺省 = 扫描 sessions 目录全部）")
    ba.set_defaults(func=cmd_backflow_audit)
    st = sub.add_parser("selftest", help="内置自测（stdlib mock server）")
    st.set_defaults(func=lambda a: run_selftest())
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SessionParseError as e:  # DR-19 方向 B：坏行报错含 <路径>:<行号>，退出码不变（1）
        print(f"spec_runner: session 解析失败 -> {e}", file=sys.stderr)
        print("spec_runner: 提示 = 该行须为合法 JSON（内嵌正则等反斜杠须按 JSON 转义；"
              "同一文件内写法不一致即此故障类）", file=sys.stderr)
        return 1


# ---- selftest（R7 同构：计数自增机械计数，不硬编码——样本⑨ 教训） ----
def _mock_server(port):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._json({"data": []} if self.path == "/v1/models" else {})

        def do_POST(self):
            self._json({"choices": [{"message": {"role": "assistant",
                                                 "content": "mock-ok"}}]}
                       if self.path == "/v1/chat/completions" else {})

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def run_selftest() -> int:
    import shutil
    import tempfile

    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + (f" — {detail}" if detail else ""))

    tmp = Path(tempfile.mkdtemp(prefix="sr_selftest_"))
    # P-022 修正：子进程 env 显式剥离 SR_GIT_AUTOCOMMIT——父环境即使已导也不泄漏
    # （审查 §1.4：L467 env=dict(os.environ,...) 整体拷贝是绕过点）
    env = {k: v for k, v in os.environ.items() if k != GIT_AUTOCOMMIT_ENV}
    env[SESSIONS_ENV] = str(tmp)
    # P-069：返工图真值源注入（与真表隔离）——trigger_kinds 两条封闭枚举 + 一条已登记返工边
    reg_file = tmp / "rework-graph.json"
    reg_file.write_text(json.dumps({
        "version": 1, "updated": "2026-10-03", "owner": "selftest",
        "truth_source": "registry",
        "trigger_kinds": ["user-verdict", "undecided"],
        "provenance_prefixes": ["manual", "tool"],
        "forks": [{"new": "bf-reg", "origin": "bf-origin", "seq_from": 1,
                   "trigger_kind": "user-verdict", "reason": "selftest 已登记返工",
                   "provenance": "manual:selftest", "date": "2026-10-03"}],
        "non_rework": []}, ensure_ascii=False), encoding="utf-8")
    env[REGISTRY_ENV] = str(reg_file)
    me = str(Path(__file__).resolve())

    def run_cli(*argv):
        return subprocess.run([sys.executable, me, *argv],
                              capture_output=True, text=True, env=env)

    print(f"selftest tmp dir: {tmp}")
    try:
        # F1-F5: gate 写入 + seq 单调 + exit 透传（pass/fail 两臂）+ schema
        p0 = run_cli("gate", "--name", "always-pass", "--session", "st-001",
                     "--cmd", "echo ok")
        check("F1 gate pass exit 透传", p0.returncode == 0)
        p5 = run_cli("gate", "--name", "always-fail", "--session", "st-001",
                     "--cmd", "exit 5")
        check("F2 gate fail exit 透传(=5)", p5.returncode == 5)
        w = EventWriter(tmp)
        rows = w.read("st-001")
        check("F3 事件流落盘可解析", len(rows) == 2)
        check("F4 seq 从 1 单调", [r["seq"] for r in rows] == [1, 2])
        check("F5 gate 事件 schema（name/exit/verdict）",
              all(r["gate"]["name"] and isinstance(r["gate"]["exit"], int)
                  and r["gate"]["verdict"] in ("pass", "fail") for r in rows))

        # F6/F7: schema 拒绝（写入端单点把守）——进程内直调
        for bad in (("bad-source", "tool", None),
                    ("st-x", "system", "no-such-event")):
            try:
                EventWriter(tmp).append(bad[0], bad[1], bad[2])
                check(f"F6 schema 拒绝 {bad}", False)
            except ValueError:
                check(f"F6 schema 拒绝 {bad}", True)
        try:
            EventWriter(tmp).append("st-x", "assistant", "llm_request",
                                    model=None, provider="p")
            check("F7 LLM 事件缺 model 拒绝", False)
        except ValueError:
            check("F7 LLM 事件缺 model 拒绝", True)

        # F8: replay 一致性
        pr = run_cli("replay", "--session", "st-001")
        check("F8 replay exit 0", pr.returncode == 0)

        # F9/F10: fork 复制前 1 行
        pf = run_cli("fork", "--session", "st-001", "--seq", "1",
                     "--new", "st-001f")
        check("F9 fork exit 0", pf.returncode == 0)
        check("F10 fork 内容 = 前 1 行",
              [r["seq"] for r in w.read("st-001f")] == [1])

        # F11: L6 拒绝对已存在 sid 无 --resume 的 run
        p_dup = run_cli("run", "--task", "t", "--session", "st-001",
                        "--prompt", "x", "--endpoint", "http://127.0.0.1:1",
                        "--model", "m", "--provider", "p")
        check("F11 L6 同 sid 无 --resume 拒绝(exit 2)", p_dup.returncode == 2)

        # F12/F13: 端点不可达 → exit 1 + endpoint_unreachable 事件（新 sid）
        p_ep = run_cli("run", "--task", "t", "--session", "st-ep",
                       "--prompt", "x", "--endpoint", "http://127.0.0.1:1",
                       "--model", "m", "--provider", "p")
        check("F12 端点不可达 exit 1", p_ep.returncode == 1)
        check("F13 endpoint_unreachable 入流",
              any(r["event"] == "endpoint_unreachable" for r in w.read("st-ep")))

        # F14-F16: gate 建流 → run --resume 同流续写（require-gate 同流前置通过）
        port, srv = 18742, None
        try:
            p_gate = run_cli("gate", "--name", "pre-gate", "--session",
                             "st-run", "--cmd", "echo ok")
            check("F14a 前置 gate 建流", p_gate.returncode == 0)
            srv = _mock_server(port)
            p_run = run_cli("run", "--task", "demo", "--session", "st-run",
                            "--resume", "--prompt", "hello",
                            "--require-gate", "pre-gate",
                            "--endpoint", f"http://127.0.0.1:{port}",
                            "--model", "mock-model", "--provider", "mock")
            check("F14 run 全链路 exit 0（require-gate 同流前置通过）",
                  p_run.returncode == 0, p_run.stderr.strip()[:120])
            rows_run = w.read("st-run")
            evs = [r["event"] for r in rows_run]
            check("F15 事件序列完整（gate 建流 + resume 续写）",
                  evs == ["gate", "prompt", "llm_request", "llm_response",
                          "session_end"], str(evs))
            check("F16 L2 装配后请求入流",
                  len(rows_run) >= 3 and
                  rows_run[-3]["input"]["messages"][0]["content"] == "hello")
        finally:
            if srv:
                srv.shutdown()

        # F17: require-gate 未过 → exit 3
        p_rg = run_cli("run", "--task", "t", "--session", "st-rg",
                       "--prompt", "x", "--require-gate", "never-passed",
                       "--endpoint", f"http://127.0.0.1:{port}",
                       "--model", "m", "--provider", "p")
        check("F17 require-gate 未过 exit 3", p_rg.returncode == 3)

        # F18: status 派生视图
        p_st = run_cli("status", "--session", "st-001")
        check("F18 status exit 0 且含 gate 态",
              p_st.returncode == 0 and "gate[always-pass]: pass" in p_st.stdout
              and "gate[always-fail]: fail" in p_st.stdout)

        # F19: replay 对坏 seq 流拒绝（手工构造 seq 跳跃流）
        bad_sid = "st-badseq"
        base_row = {"ts": now_iso(), "session": bad_sid, "source": "system",
                    "model": None, "provider": None, "input": None,
                    "output": None, "gate": None}
        r1 = dict(base_row, seq=1, event="session_start")
        r5 = dict(base_row, seq=5, event="session_end")
        (tmp / f"{bad_sid}.jsonl").write_text(
            json.dumps(r1, ensure_ascii=False) + "\n"
            + json.dumps(r5, ensure_ascii=False) + "\n", encoding="utf-8")
        p_rp = run_cli("replay", "--session", bad_sid)
        check("F19 replay 坏 seq exit 1", p_rp.returncode == 1)

        # F20-F23: step-gate 决策产物管线（P-020，CER §3.5）
        p_sg0 = run_cli("step-gate", "--session", "st-nod", "--legacy")
        check("F20 空流无 decision → exit 1", p_sg0.returncode == 1)
        w_sg = EventWriter(tmp)
        for i, st in enumerate(["research", "design"], 1):
            w_sg.append("st-ok", "assistant", "decision", input_={
                "category": "feature-design", "scenario": "s", "reasoning": "r",
                "outcome": "o", "confidence": 0.9,
                "metadata": {"step_id": st, "step_seq": i,
                             "evidence": [{"grade": "E1", "anchor": "spec/step-gate/DESIGN.md §4"}]}})
        p_sg_ok = run_cli("step-gate", "--session", "st-ok",
                          "--expect", "research", "design")
        check("F21 完整链 --expect 一致 → exit 0", p_sg_ok.returncode == 0, p_sg_ok.stdout[-80:])
        w_sg.append("st-miss", "assistant", "decision", input_={
            "category": "feature-design", "scenario": "s",
            "metadata": {"step_id": "research", "step_seq": 1,
                         "evidence": [{"grade": "E1", "anchor": "spec/x.md"}]}})
        p_sg_miss = run_cli("step-gate", "--session", "st-miss", "--legacy")
        check("F22 缺 reasoning/outcome/confidence → exit 1", p_sg_miss.returncode == 1)
        w_sg.append("st-soft", "assistant", "decision", input_={
            "category": "c", "scenario": "s", "reasoning": "r", "outcome": "o",
            "confidence": 0.9, "metadata": {"step_id": "research", "step_seq": 1,
            "evidence": [{"grade": "E1", "anchor": "not a valid anchor !!"}]}})
        p_sg_soft = run_cli("step-gate", "--session", "st-soft", "--legacy")
        check("F23 锚点形态存疑 → exit 2", p_sg_soft.returncode == 2)
        w_sg.append("st-badd", "assistant", "decision", input_={
            "category": "c", "scenario": "s", "reasoning": "r", "outcome": "o",
            "confidence": 0.9, "metadata": {"step_id": "XXX", "step_seq": 9,
            "evidence": [{"grade": "E1", "anchor": "spec/x.md"}]}})
        p_sg_badd = run_cli("step-gate", "--session", "st-badd", "--legacy")
        check("F24 step_id 非法 → exit 1", p_sg_badd.returncode == 1)

        # F27-F29: step-enforce 批次级强制（P-024，ADR-0011 出路 A——只读零副作用）
        p_se0 = run_cli("step-enforce", "--pid", "P-999")
        check("F27 step-enforce 无 session → exit 1", p_se0.returncode == 1)
        w_se = EventWriter(tmp)
        w_se.append("specwf-p999-a", "system", "session_start")  # 有 session 无 decision
        p_se1 = run_cli("step-enforce", "--pid", "P-999")
        check("F28 step-enforce 空链（无 decision）→ exit 1", p_se1.returncode == 1,
              p_se1.stdout[-80:])
        w_se.append("specwf-p999-b", "assistant", "decision", input_={
            "category": "feature-design", "scenario": "s", "reasoning": "r",
            "outcome": "o", "confidence": 0.9,
            "metadata": {"step_id": "research", "step_seq": 1,
                         "evidence": [{"grade": "E1", "anchor": "spec/step-gate-enforcement/DESIGN.md §4"}]}})
        p_se2 = run_cli("step-enforce", "--pid", "P-999")
        check("F29 step-enforce 合法链 → exit 0", p_se2.returncode == 0, p_se2.stdout[-80:])

        # F30-F35: verify-anchor 锚点真实性取证（P-025，ADR-0011 出路 C——只读零副作用）
        w_va = EventWriter(tmp)
        def _va_d(anchor):
            return {"category": "c", "scenario": "s", "reasoning": "r",
                    "outcome": "o", "confidence": 0.9,
                    "metadata": {"step_id": "research", "step_seq": 1,
                                 "evidence": [{"grade": "E1", "anchor": anchor}]}}
        w_va.append("va-real", "assistant", "decision", input_=_va_d("spec/step-gate/DESIGN.md §4"))
        p_va0 = run_cli("verify-anchor", "--session", "va-real")
        check("F30 verify-anchor 真实锚点 → exit 0", p_va0.returncode == 0, p_va0.stdout[-80:])
        w_va.append("va-nofile", "assistant", "decision", input_=_va_d("spec/no-such-feature-xyz/NO.md §1"))
        p_va1 = run_cli("verify-anchor", "--session", "va-nofile")
        check("F31 verify-anchor 文件不存在 → exit 1", p_va1.returncode == 1)
        w_va.append("va-nosec", "assistant", "decision", input_=_va_d("spec/step-gate/DESIGN.md §99"))
        p_va2 = run_cli("verify-anchor", "--session", "va-nosec")
        check("F32 verify-anchor 章节不存在 → exit 1", p_va2.returncode == 1)
        w_va.append("va-noline", "assistant", "decision", input_=_va_d("spec/step-gate/DESIGN.md#L999999"))
        p_va3 = run_cli("verify-anchor", "--session", "va-noline")
        check("F33 verify-anchor 行号越界 → exit 1", p_va3.returncode == 1)
        w_va.append("va-url", "assistant", "decision", input_=_va_d("https://example.com/x"))
        p_va4 = run_cli("verify-anchor", "--session", "va-url")
        check("F34 verify-anchor URL soft → exit 2", p_va4.returncode == 2)
        w_va.append("va-sec5", "assistant", "decision", input_=_va_d("spec/independent-verify/RESEARCH.md §5"))
        p_va5 = run_cli("verify-anchor", "--session", "va-sec5")
        check("F35 verify-anchor §5 精确命中 → exit 0", p_va5.returncode == 0, p_va5.stdout[-80:])
        w_va.append("va-sec53", "assistant", "decision", input_=_va_d("spec/independent-verify/RESEARCH.md §5.3"))
        p_va6 = run_cli("verify-anchor", "--session", "va-sec53")
        check("F36 verify-anchor §5.3 精确命中子章节 → exit 0", p_va6.returncode == 0, p_va6.stdout[-80:])

        # F37-F41: DR-19 / DR-21 方向 B 回归（P-042 v1.18——报错定位 + 明细开关 + 锚点形态）
        bad = tmp / "bad-json.jsonl"
        bad.write_text('{"ts": "t", "seq": 1, "session": "bad-json", "event": "decision"}\n'
                       '{"broken": }\n', encoding="utf-8")
        p_b1 = run_cli("verify-anchor", "--session", "bad-json")
        check("F37 坏行报错含 <路径>:<行号>（verify-anchor，exit 1 不变）",
              p_b1.returncode == 1 and "bad-json.jsonl:2" in p_b1.stderr, p_b1.stderr[-100:])
        p_b2 = run_cli("step-gate", "--session", "bad-json", "--legacy")
        check("F38 同族命令报错一致（step-gate 亦给 <路径>:<行号>）",
              p_b2.returncode == 1 and "bad-json.jsonl:2" in p_b2.stderr, p_b2.stderr[-100:])
        w_va.append("va-detail", "assistant", "decision", input_=_va_d("spec/step-gate/DESIGN.md §4"))
        w_va.append("va-detail", "assistant", "decision", input_=_va_d("spec/step-gate/DESIGN.md §99"))
        p_d1 = run_cli("verify-anchor", "--session", "va-detail", "--detail")
        check("F39 --detail 逐锚点明细（真实 + 硬性 各一行）",
              p_d1.stdout.count("[DETAIL]") == 2 and "硬性" in p_d1.stdout, p_d1.stdout[-120:])
        p_d0 = run_cli("verify-anchor", "--session", "va-detail")
        check("F40 默认关闭：无 --detail 时明细零出现（守 I-2 确定性）",
              "[DETAIL]" not in p_d0.stdout)
        w_va.append("va-range", "assistant", "decision",
                    input_=_va_d("spec/independent-verify/RESEARCH.md#L1-L3"))
        p_r1 = run_cli("verify-anchor", "--session", "va-range")
        check("F41 行号区间形态 → 硬性 exit 1（隔离实测结论固化为回归）", p_r1.returncode == 1)

        # F42-F45: anchor-audit 锚点形态集合对账（P-042 v1.20，DR-25；P-091 候选扩权后
        # 语义改为「不变量守门」——原 d 类实例（根级载体 + 定位符）经扩权已不再偏离）
        w_va.append("aa-trigger", "assistant", "decision",
                    input_=_va_d("spec/step-gate/DESIGN.md §4"))
        w_va.append("aa-trigger", "assistant", "decision",
                    input_=_va_d("CODE_WIKI.md#L3"))
        p_aa1 = run_cli("anchor-audit", "--session", "aa-trigger")
        check("F42 原 d 类实例（根级载体 + 定位符）扩权后偏离清零 → 不变量成立 exit 0",
              p_aa1.returncode == 0 and "不变量 J2 ⊆ J1 成立" in p_aa1.stdout
              and bool(ANCHOR_RE.match("CODE_WIKI.md#L3")), p_aa1.stdout[-140:])
        p_aa2 = run_cli("anchor-audit", "--session", "va-real")
        check("F43 仅白名单 .md + §章节 → 差集空，不变量成立 exit 0",
              p_aa2.returncode == 0, p_aa2.stdout[-100:])
        w_va.append("aa-pure", "assistant", "decision",
                    input_=_va_d("scripts/spec_map.py"))
        p_aa3 = run_cli("anchor-audit", "--session", "aa-pure")
        check("F44 纯文件属正确分工面（J1 放行 / J2 硬性）→ exit 0 且分工面计数 1",
              p_aa3.returncode == 0 and "正确分工面）: 1；" in p_aa3.stdout,
              p_aa3.stdout[-140:])
        # 坏行 fixture 已由 F37/F38 用毕：全量扫描须在清洁目录上进行
        # （否则继承 EventWriter 的中断语义 → 报错定位 exit 1，掩盖差集读数）
        bad.unlink()
        p_aa4 = run_cli("anchor-audit")
        p_aa5 = run_cli("anchor-audit")
        check("F45 全量扫描（无 --session）：确定性双跑一致 + 差集 0 → exit 0",
              p_aa4.returncode == 0 and p_aa4.stdout == p_aa5.stdout,
              p_aa4.stdout[-140:])

        # F46-F52: `§` 编号空间收口（P-064——字母编号受理 / 词形不受理 / 大小写敏感 / 精确性 / 守门）
        w_va.append("p064-alpha", "assistant", "decision",
                    input_=_va_d("adr/ADR-0006-assertion-framework-dual-copy-authority.md §B4"))
        p_a1 = run_cli("verify-anchor", "--session", "p064-alpha")
        check("F46 字母 + 数字章节号受理（ADR-0006 §B4 真实）→ exit 0",
              p_a1.returncode == 0, p_a1.stdout[-100:])
        p_a2 = run_cli("step-gate", "--session", "p064-alpha", "--legacy")
        check("F47 同一锚点 step-gate 亦受理（两处同改收口，soft=0）→ exit 0",
              p_a2.returncode == 0, p_a2.stdout[-100:])
        _p064_samples = ["spec/project-console/RESEARCH.md §7.16",
                         "adr/ADR-0006-assertion-framework-dual-copy-authority.md §B4",
                         "adr/ADR-0007-unified-document-contract.md §D3",
                         "docs/PROGRESS.md#L3", "scripts/spec_map.py#L76"]
        check("F48 J2 ⊆ J1 机械守门（§ 编号空间同源：样本 J2 可解析 ⇒ J1 必匹配）",
              all(_resolve_anchor(a)[0] in ("section", "line") for a in _p064_samples)
              and all(ANCHOR_RE.match(a) for a in _p064_samples))
        w_va.append("p064-word", "assistant", "decision",
                    input_=_va_d("tools/spec_runner/spec_runner.py §selftest"))
        p_a3 = run_cli("verify-anchor", "--session", "p064-word")
        check("F49 多字母词形不受理（§selftest 仍不可解析）→ verify-anchor 硬性 exit 1",
              p_a3.returncode == 1)
        p_a4 = run_cli("step-gate", "--session", "p064-word", "--legacy")
        check("F50 同锚点 step-gate 形态存疑（soft）→ exit 2", p_a4.returncode == 2)
        w_va.append("p064-case", "assistant", "decision",
                    input_=_va_d("adr/ADR-0006-assertion-framework-dual-copy-authority.md §b4"))
        p_a5 = run_cli("verify-anchor", "--session", "p064-case")
        check("F51 大小写敏感（§b4 ≠ 标题 B4）→ verify-anchor 章节不存在 exit 1",
              p_a5.returncode == 1)
        w_va.append("p064-exact", "assistant", "decision",
                    input_=_va_d("adr/ADR-0006-assertion-framework-dual-copy-authority.md §B1"))
        p_a6 = run_cli("verify-anchor", "--session", "p064-exact")
        check("F52 精确匹配（§B1 不前缀命中 B/B2/B3/B4）→ exit 1", p_a6.returncode == 1)

        # F53-F61: backflow-audit 回写/回边待处理检测（P-069）——锚点/回边/失败枚举三臂
        w_bf = EventWriter(tmp)

        def _bf_d(step, step_seq, trigger=None):
            md = {"step_id": step, "step_seq": step_seq,
                  "evidence": [{"grade": "E1", "anchor": "spec/step-gate/DESIGN.md §4"}]}
            if trigger is not None:
                md["trigger"] = trigger
            return {"category": "c", "scenario": "s", "reasoning": "r",
                    "outcome": "o", "confidence": 0.9, "metadata": md}

        for st, sq in (("research", 1), ("design", 2), ("implement", 3),
                       ("verify", 4), ("finalize", 5)):          # 锚点臂：干净链
            w_bf.append("bf-clean", "assistant", "decision", input_=_bf_d(st, sq))
        p_bf0 = run_cli("backflow-audit", "--session", "bf-clean")
        check("F53 backflow-audit 干净链（无回边无 trigger）→ exit 0",
              p_bf0.returncode == 0 and "0 例" in p_bf0.stdout, p_bf0.stdout[-120:])

        for st, sq in (("research", 1), ("design", 2), ("implement", 3),
                       ("research", 1)):                           # 回边臂
            w_bf.append("bf-back", "assistant", "decision", input_=_bf_d(st, sq))
        p_bf1 = run_cli("backflow-audit", "--session", "bf-back")
        check("F54 backflow-audit 受控回边未登记 → exit 1 且 [PENDING] 待重入",
              p_bf1.returncode == 1 and "[PENDING]" in p_bf1.stdout
              and "待重入" in p_bf1.stdout, p_bf1.stdout[-160:])

        p_sg_back = run_cli("step-gate", "--session", "bf-back", "--legacy")
        check("F55 step-gate 受控回边受理 → exit 0 且打印 [REWORK]",
              p_sg_back.returncode == 0 and "[REWORK]" in p_sg_back.stdout,
              p_sg_back.stdout[-160:])

        w_bf.append("bf-dup", "assistant", "decision", input_=_bf_d("research", 1))
        w_bf.append("bf-dup", "assistant", "decision", input_=_bf_d("research", 1))
        p_sg_dup = run_cli("step-gate", "--session", "bf-dup", "--legacy")
        check("F56 step-gate 同位重复仍判硬性（回边受理未豁免真重复）→ exit 1",
              p_sg_dup.returncode == 1, p_sg_dup.stdout[-120:])

        w_bf.append("bf-trig", "assistant", "decision",
                    input_=_bf_d("research", 1, trigger="user-verdict"))   # 失败枚举臂
        p_bf2 = run_cli("backflow-audit", "--session", "bf-trig")
        check("F57 backflow-audit trigger 合法但未登记 → exit 1 且 待回写",
              p_bf2.returncode == 1 and "待回写" in p_bf2.stdout, p_bf2.stdout[-160:])

        w_bf.append("bf-bad", "assistant", "decision",
                    input_=_bf_d("research", 1, trigger="bogus-kind"))
        p_bf3 = run_cli("backflow-audit", "--session", "bf-bad")
        check("F58 backflow-audit trigger 非法枚举 → exit 1 且 [INVALID]",
              p_bf3.returncode == 1 and "[INVALID]" in p_bf3.stdout, p_bf3.stdout[-160:])

        for st, sq in (("research", 1), ("design", 2), ("research", 1)):  # 已登记返工
            w_bf.append("bf-reg", "assistant", "decision", input_=_bf_d(st, sq))
        p_bf4 = run_cli("backflow-audit", "--session", "bf-reg")
        check("F59 backflow-audit 已登记 session 的回边不报（返工图 = 真值源）→ exit 0",
              p_bf4.returncode == 0, p_bf4.stdout[-160:])

        p_bf5 = run_cli("backflow-audit", "--session", "bf-none")
        check("F60 backflow-audit session 不存在 → exit 2（降级）",
              p_bf5.returncode == 2, p_bf5.stdout[-120:])

        env_noreg = dict(env, **{REGISTRY_ENV: str(tmp / "no-such-registry.json")})
        p_bf6 = subprocess.run([sys.executable, me, "backflow-audit",
                                "--session", "bf-clean"],
                               capture_output=True, text=True, env=env_noreg)
        check("F61 backflow-audit 登记表缺失 → exit 2（降级不当作通过）",
              p_bf6.returncode == 2, p_bf6.stdout[-120:])

        # F72-F79: U-8 finalize upstream_impact 三态强制（P-092）——三态臂 / 耦合臂 / 过渡期臂 / 降级臂
        _UI_MISS = "__missing__"

        def _ui_d(step, step_seq, impact=None):
            md = {"step_id": step, "step_seq": step_seq,
                  "evidence": [{"grade": "E1", "anchor": "spec/step-gate/DESIGN.md §4"}]}
            if impact is not None:
                md["upstream_impact"] = impact
            return {"category": "c", "scenario": "s", "reasoning": "r",
                    "outcome": "o", "confidence": 0.9, "metadata": md}

        def _ui_chain(sid, impact=_UI_MISS):
            """干净五步链（唯一变量 = finalize 的 upstream_impact）。"""
            for st, sq in (("research", 1), ("design", 2), ("implement", 3), ("verify", 4)):
                w.append(sid, "assistant", "decision", input_=_ui_d(st, sq))
            w.append(sid, "assistant", "decision",
                     input_=_ui_d("finalize", 5,
                                  None if impact == _UI_MISS else impact))

        _ui_chain("specwf-p092-s1")
        p_u1 = run_cli("step-gate", "--session", "specwf-p092-s1", "--legacy")
        check("F72 finalize 缺 upstream_impact（P ≥ 92）→ 硬性 exit 1",
              p_u1.returncode == 1 and "upstream_impact" in p_u1.stdout, p_u1.stdout[-170:])

        _ui_chain("specwf-p092-s2", "bogus")
        p_u2 = run_cli("step-gate", "--session", "specwf-p092-s2", "--legacy")
        check("F73 非法 upstream_impact 取值 → 硬性 exit 1",
              p_u2.returncode == 1 and "bogus" in p_u2.stdout, p_u2.stdout[-170:])

        _ui_chain("specwf-p092-s3", "none")
        p_u3 = run_cli("step-gate", "--session", "specwf-p092-s3", "--legacy")
        check("F74 upstream_impact=none + 全链齐 → exit 0（吃狗粮形态）",
              p_u3.returncode == 0, p_u3.stdout[-170:])

        _ui_chain("specwf-p092-s4", "overturned")
        p_u4 = run_cli("step-gate", "--session", "specwf-p092-s4", "--legacy")
        check("F75 非 none 且该 session 未登记返工图 → 硬性 exit 1（耦合臂）",
              p_u4.returncode == 1 and "未登记返工图" in p_u4.stdout, p_u4.stdout[-170:])

        reg2 = tmp / "rework-graph-p092.json"
        reg2.write_text(json.dumps({
            "version": 1, "updated": "2026-10-13", "owner": "selftest",
            "truth_source": "registry",
            "trigger_kinds": ["user-verdict", "undecided"],
            "provenance_prefixes": ["manual", "tool"],
            "forks": [{"new": "specwf-p092-s5", "origin": "specwf-p092-s0",
                       "seq_from": 1, "trigger_kind": "user-verdict",
                       "reason": "selftest 已登记返工", "provenance": "manual:selftest-p092",
                       "date": "2026-10-13"}],
            "non_rework": []}, ensure_ascii=False), encoding="utf-8")
        _ui_chain("specwf-p092-s5", "partial")
        p_u5 = subprocess.run([sys.executable, me, "step-gate", "--session",
                               "specwf-p092-s5", "--legacy"], capture_output=True, text=True,
                              env=dict(env, **{REGISTRY_ENV: str(reg2)}))
        check("F76 非 none 且该 session 已登记返工图 → exit 0（耦合满足）",
              p_u5.returncode == 0, p_u5.stdout[-170:])

        _ui_chain("specwf-p091-hist")
        p_u6 = run_cli("step-gate", "--session", "specwf-p091-hist", "--legacy")
        check("F77 过渡期判据：历史批次（P=91）不适用 ⇒ 缺字段仍 exit 0（零回归边界）",
              p_u6.returncode == 0, p_u6.stdout[-170:])

        _ui_chain("notbatch-001")
        p_u7 = run_cli("step-gate", "--session", "notbatch-001", "--legacy")
        check("F78 sid 形态不匹配（非 specwf-pNNN-）⇒ 不适用 ⇒ exit 0",
              p_u7.returncode == 0, p_u7.stdout[-170:])

        p_u8 = subprocess.run([sys.executable, me, "step-gate", "--session",
                               "specwf-p092-s5", "--legacy"], capture_output=True, text=True,
                              env=dict(env, **{REGISTRY_ENV: str(tmp / "no-reg-ui.json")}))
        check("F79 非 none 且返工图不可用 → 耦合降级为软性（exit 2，不静默通过）",
              p_u8.returncode == 2, p_u8.stdout[-170:])

        # F80-F81: step-gate 显式声明守卫（P-132）——无声明 / 双声明两臂
        p_sg_nodecl = run_cli("step-gate", "--session", "st-ok")
        check("F80 未显式声明（既无 --expect 亦无 --legacy）→ exit 2",
              p_sg_nodecl.returncode == 2 and "必须显式声明" in p_sg_nodecl.stdout,
              p_sg_nodecl.stdout[-120:])
        p_sg_both = run_cli("step-gate", "--session", "st-ok",
                            "--expect", "research", "design", "--legacy")
        check("F81 --expect 与 --legacy 同时给出 → exit 2（互斥）",
              p_sg_both.returncode == 2 and "互斥" in p_sg_both.stdout,
              p_sg_both.stdout[-120:])

        # F62-F69: fork 注册扩展（P-089）——成功臂 / 零回归 / fail-fast 原子性
        p_r1 = run_cli("fork", "--session", "st-001", "--seq", "2",
                       "--new", "st-001r", "--reason", "selftest 返工样例",
                       "--trigger-kind", "user-verdict",
                       "--provenance", "manual:selftest-p089")
        reg1 = json.loads(reg_file.read_text(encoding="utf-8"))
        frk = [f for f in reg1["forks"] if f.get("new") == "st-001r"]
        check("F62 fork 注册成功（登记边字段齐 + 会话复制 + updated 盖戳）",
              p_r1.returncode == 0 and "register: forks +=" in p_r1.stdout
              and len(frk) == 1 and frk[0]["origin"] == "st-001"
              and frk[0]["seq_from"] == 2
              and frk[0]["trigger_kind"] == "user-verdict"
              and frk[0]["reason"] == "selftest 返工样例"
              and frk[0]["provenance"] == "manual:selftest-p089"
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}", frk[0]["date"]) is not None
              and reg1["updated"] == frk[0]["date"]
              and len(w.read("st-001r")) == 2)

        reg_after_r1 = reg_file.read_bytes()
        p_r2 = run_cli("fork", "--session", "st-001", "--seq", "1",
                       "--new", "st-001p")
        check("F63 无注册参数零回归（registry 字节不变 + 无 register 行）",
              p_r2.returncode == 0 and reg_file.read_bytes() == reg_after_r1
              and "register:" not in p_r2.stdout)

        p_r3 = run_cli("fork", "--session", "st-001", "--seq", "1",
                       "--new", "st-001x", "--reason", "只给一件")
        check("F64 注册三件缺件（all-or-none）→ exit 2 且零写入",
              p_r3.returncode == 2 and not w.path("st-001x").exists()
              and reg_file.read_bytes() == reg_after_r1)

        p_r4 = run_cli("fork", "--session", "st-001", "--seq", "1",
                       "--new", "st-001y", "--reason", "r",
                       "--trigger-kind", "no-such-kind",
                       "--provenance", "manual:x")
        check("F65 非法触发枚举 → exit 2 且零写入（校验先于 fork）",
              p_r4.returncode == 2 and not w.path("st-001y").exists()
              and reg_file.read_bytes() == reg_after_r1)

        ok66 = True
        for i, bad_prov in enumerate(("selftest-no-colon", "counted:xx", "manual:")):
            nm = f"st-001z{i}"
            p_r5 = run_cli("fork", "--session", "st-001", "--seq", "1",
                           "--new", nm, "--reason", "r",
                           "--trigger-kind", "undecided",
                           "--provenance", bad_prov)
            ok66 = ok66 and p_r5.returncode == 2 and not w.path(nm).exists()
        check("F66 provenance 形态非法三臂（缺冒号/前缀越界/载荷空）→ exit 2 且零写入",
              ok66 and reg_file.read_bytes() == reg_after_r1)

        p_r6 = run_cli("fork", "--session", "st-001", "--seq", "1",
                       "--new", "bf-origin", "--reason", "r",
                       "--trigger-kind", "user-verdict",
                       "--provenance", "manual:x")
        check("F67 new 已在已登记名集 → exit 2 且零写入",
              p_r6.returncode == 2 and not w.path("bf-origin").exists()
              and reg_file.read_bytes() == reg_after_r1)

        env_noreg2 = dict(env, **{REGISTRY_ENV: str(tmp / "no-such-registry2.json")})
        p_r7 = subprocess.run([sys.executable, me, "fork", "--session", "st-001",
                               "--seq", "1", "--new", "st-001m", "--reason", "r",
                               "--trigger-kind", "user-verdict",
                               "--provenance", "manual:x"],
                              capture_output=True, text=True, env=env_noreg2)
        check("F68 登记表缺失 ⇒ 前置失败 exit 2（fork 不发生）",
              p_r7.returncode == 2 and not w.path("st-001m").exists()
              and reg_file.read_bytes() == reg_after_r1)

        n_rows = len(w.read("st-001"))
        p_r8 = run_cli("fork", "--session", "st-001", "--seq", str(n_rows + 10),
                       "--new", "st-001q", "--reason", "r",
                       "--trigger-kind", "undecided",
                       "--provenance", "tool:selftest")
        reg2 = json.loads(reg_file.read_text(encoding="utf-8"))
        frk2 = [f for f in reg2["forks"] if f.get("new") == "st-001q"]
        check("F69 请求 seq 超出源末端 → seq_from 按实际复制行数登记（机械真值）",
              p_r8.returncode == 0 and len(frk2) == 1
              and frk2[0]["seq_from"] == n_rows
              and len(w.read("st-001q")) == n_rows)

        # F70-F71: §4.1.1 十例矩阵机械守门（P-091 候选扩权——把矩阵变断言，
        # 防两处正则再漂移；同 I-10「两实现同错、对账抓不住」教训）
        # 行 = (锚点, J1 匹配期望, J2 可解析期望)，逐例对齐 independent-verify DESIGN §4.1.1
        _mx = [("spec/project-console/RESEARCH.md §7.16", True, True),
               ("docs/PROGRESS.md#L3", True, True),
               ("scripts/spec_map.py#L76", True, True),
               ("docs/PROGRESS.md#L3-L5", False, False),
               ("scripts/spec_map.py#L76-L83", False, False),
               ("CODE_WIKI.md", True, False),
               ("CODE_WIKI.md#L3", True, True),
               ("scripts/spec_map.py", True, False),
               ("spec/project-console/RESEARCH.md", True, False),
               ("adr/ADR-0006-assertion-framework-dual-copy-authority.md §B4", True, True)]
        check("F70 §4.1.1 十例矩阵逐例一致（J1/J2 两处判定与 DESIGN §4.1.1 声明同步）",
              all(bool(ANCHOR_RE.match(a)) == m1
                  and (_resolve_anchor(a)[0] in ("section", "line")) == m2
                  for a, m1, m2 in _mx))
        check("F71 J2 ⊆ J1 不变量（十例全例成立；原 d 类根级载体偏离已清零）",
              all(not (m2 and not m1) for _, m1, m2 in _mx)
              and all(ANCHOR_RE.match(a) for a, _, m2 in _mx if m2))

        # F25-F26: git_snapshot 懒加载门控 + 精确范围（P-022 A+B，临时 git 仓实证）
        git_tmp = Path(tempfile.mkdtemp(prefix="sr_gittest_"))
        sdir = git_tmp / "sessions"
        sdir.mkdir()
        (sdir / "real-001.jsonl").write_text("a\n", encoding="utf-8")
        (sdir / "real-002.jsonl").write_text("b\n", encoding="utf-8")
        for c in (["init", "-q"], ["config", "user.email", "t@t"],
                  ["config", "user.name", "t"]):
            subprocess.run(["git", *c], cwd=git_tmp, capture_output=True)
        sv, ac = os.environ.get(SESSIONS_ENV), os.environ.get(GIT_AUTOCOMMIT_ENV)
        os.environ[SESSIONS_ENV] = str(sdir)
        os.environ.pop(GIT_AUTOCOMMIT_ENV, None)
        git_snapshot("real-001", "m1")  # 默认关 → 零提交
        cnt0 = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=git_tmp,
                              capture_output=True, text=True)
        check("F25 git_snapshot 默认关零提交", cnt0.returncode != 0)
        os.environ[GIT_AUTOCOMMIT_ENV] = "1"
        git_snapshot("real-001", "m1")  # 显式激活 → 只提交 real-001
        os.environ.pop(GIT_AUTOCOMMIT_ENV, None)
        cnt1 = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=git_tmp,
                              capture_output=True, text=True)
        files_p = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"],
                                 cwd=git_tmp, capture_output=True, text=True)
        files = [l for l in files_p.stdout.splitlines() if l.strip()]
        msg_p = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=git_tmp,
                               capture_output=True, text=True)
        check("F26 git_snapshot 精确提交单文件+消息一致",
              cnt1.returncode == 0 and cnt1.stdout.strip() == "1"
              and files == ["sessions/real-001.jsonl"]
              and msg_p.stdout.strip() == "m1")
        if sv is not None:
            os.environ[SESSIONS_ENV] = sv
        else:
            os.environ.pop(SESSIONS_ENV, None)
        shutil.rmtree(git_tmp, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for r in results if r)
    total = len(results)  # 机械计数（R7 同构，样本⑨ 教训）
    print(f"selftest: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
