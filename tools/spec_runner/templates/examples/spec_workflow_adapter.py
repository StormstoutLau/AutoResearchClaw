#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
<<< Spec_Runner 通用接入模板 >>>  v1.1 (2026-09-08)

把一个项目接入 Spec_Runner（薄壳 spec 工作流执行器，P-009 方案 B）的标准样板。
复制本文件到目标项目（如 scripts/spec_runner_adapter.py），
只改顶部「配置区」即可使用。零第三方依赖（Python >=3.8 stdlib，跨平台）。

=================================================================
本文件 = 「具体接入示例」——以 Spec_Workflow 自身自举的成品副本：
  · PREFIX = "specwf"          → session 前缀（如 specwf-dc-validator-YYYYMMDD）
  · CWD    = F:\Spec_Workflow  → gate 在方法论文档仓根执行
  · GATES  = Spec_Workflow 三校验器 + pre-commit（P-007/P-011/P-014 落地件）
其他项目接入时：复制 templates/spec_runner_adapter.py（未配置版），
照本文件改 RUNNER / PREFIX / CWD / GATES 即可。
=================================================================

=== 三步接入 ===
  1. 复制:   cp templates/spec_runner_adapter.py <你的项目>/scripts/
  2. 配置:   改 PREFIX（项目标识）/ GATES（你的门禁命令表）/ RUNNER（abs 路径）
  3. 验证:   python scripts/spec_runner_adapter.py probe
             → 内置探针 gate 入流即接入成功（事件流落在 runner 的 sessions/）

=== 命令面（编排壳，映射 Spec_Runner 五命令 + 便捷门禁）===
  python .../adapter.py gates                        # 列出 GATES 可用门禁
  python .../adapter.py gate <name> [--session S]
                                 # 从 GATES 取命令注入 Spec_Runner gate；exit 透传
  python .../adapter.py run --task T [--session S] --require-gate <g> ...
                                 # 透传 Spec_Runner run（未给 --session 时自动补）
  python .../adapter.py status [--session S]
  python .../adapter.py replay --session S
  python .../adapter.py fork --session S --seq N --new N2
  python .../adapter.py probe                        # 接入自检（echo 探针 gate）
  python .../adapter.py dry-run <任一子命令...>      # 打印将执行的命令，不实际运行

=== 自举示例（Spec_Workflow 用法）===
  python templates/examples/spec_workflow_adapter.py gates
  python templates/examples/spec_workflow_adapter.py dry-run gate dc-validator
  python templates/examples/spec_workflow_adapter.py gate dc-validator
      # → 事件流: F:\Spec_Runner\sessions\specwf-dc-validator-20260907.jsonl
  python templates/examples/spec_workflow_adapter.py gate pre-commit
      # → 四件套门禁（三校验器 + pre-commit）作为审查轮 E1 取证入流

=== 调研步可选接入：gpt-researcher（官方文档确认，2026-09-08 取证）===
  研调步（Spec 工作流 Step 1）弹药层候选——gpt-researcher 官方支持自定义
  OpenAI 兼容端点（OPENAI_BASE_URL 指向本地 OpenAI 兼容服务 + FAST_LLM/
  SMART_LLM=openai:<端点内模型名>），三机 LM Studio（OpenAI 兼容，
  P-009/P-010 已实测）可直接接，无需云端 key；搜索轴 TAVILY_API_KEY 可
  替换 duckduckgo/searx 等（免商业 key）；并提供 MCP 形态（规划者-执行者
  + 引用报告；多代理流水线含 Reviewer 研究-审核-修正循环）。接入形态 =
  MCP/HTTP 独立服务调用——不经本模板 gate（gate 的 verdict 仍是验证命令
  exit code 机械映射）。官方文档：https://docs.gptr.dev/docs/gpt-researcher/llms

=== 会话命名 ===
  gate 默认 session = {PREFIX}-{gate名}-{yyyymmdd}；显式 --session 覆盖；
  同 session 复用须 --resume（RULE-1 时序独立物理化——同会话既写又审不可表达）。

=== 设计边界 ===
  本模板只是编排壳：不复制 runner 逻辑、不改 gate 语义（verdict 仍是 exit
  code 机械映射、无 LLM 判断）、不引入依赖。事件流/CWD/端点全部由 runner 或
  本模板透传。詳见 Spec_Runner README 与 Spec_Workflow
  spec/spec-runner/SPEC_RUNNER_DESIGN.md（D1-D7）。
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# >>> 配置区（按项目修改）——本文件为 Spec_Workflow 自举成品 <<<
# ============================================================

# Spec_Runner 执行器路径（P-019 归巢：现位于本仓 tools/spec_runner/，不再指向外仓）
RUNNER = r"F:\Spec_Workflow\tools\spec_runner\spec_runner.py"

# 项目标识——session 命名前缀；建议用项目短名（小写字母/数字/连字符）
PREFIX = "specwf"

# gate 工作目录：None = 使用本模板所在目录的父目录（常见 scripts/ 场景）；
# 可改为项目根绝对路径
CWD = r"F:\Spec_Workflow"

# 门禁表：name -> 要执行的验证命令（shell 语法，如 pytest/ruff 等）
# 添加你的验证命令即可；verdict = 命令 exit code 的机械映射
GATES = {
    "probe": "echo Spec_Runner OK",
    # Spec_Workflow 自举：三校验器（P-007 dc_validator / P-011 m7_stats /
    # P-014 repo_stats）+ pre-commit 四件套，作为审查轮门禁
    "dc-validator": "python scripts/dc_validator.py --check-all",
    "m7-stats": "python scripts/m7_stats.py",
    "repo-stats": "python scripts/repo_stats.py",
    "pre-commit": "pre-commit run --all-files",
}

# LLM 臂（可选）：run 子命令需要。可留空并靠环境变量 SR_* 注入；
# 三机 LM Studio 端点 = OpenAI 兼容（P-009/P-010 已实测）——与研调步候选
# gpt-researcher 的 OPENAI_BASE_URL 同一语义（见 Docstring「调研步可选接入」）
ENDPOINT = os.environ.get("SR_ENDPOINT") or ""
MODEL = os.environ.get("SR_MODEL") or ""
PROVIDER = os.environ.get("SR_PROVIDER") or ""

# ============================================================
# >>> 以下无需修改 <<<
# ============================================================

BASE = Path(__file__).resolve().parent
DEFAULT_CWD = CWD or str(BASE.parent)


def _runner_cmd() -> list:
    return [sys.executable, RUNNER]


def _session_for(name: str) -> str:
    return f"{PREFIX}-{name}-{datetime.now():%Y%m%d}"


def _build_gate_cmd(args, name: str) -> list:
    if name not in GATES:
        print(f"gate: unknown '{name}'——可用: {', '.join(GATES)}", file=sys.stderr)
        sys.exit(2)
    return ([*_runner_cmd(), "gate", "--name", name, "--cmd", GATES[name],
             "--session", args.session or _session_for(name)] +
            (["--cwd", DEFAULT_CWD]))


def _build_run_cmd(args) -> list:
    sid = args.session or f"{PREFIX}-run-{datetime.now():%Y%m%d}"
    cmd = [*_runner_cmd(), "run", "--task", args.task, "--session", sid]
    if args.resume:
        cmd.append("--resume")
    for g in args.require_gate:
        cmd += ["--require-gate", g]
    if args.prompt:
        cmd += ["--prompt", args.prompt]
    if args.prompt_file:
        cmd += ["--prompt-file", args.prompt_file]
    for flag, val in (("--endpoint", ENDPOINT), ("--model", MODEL),
                      ("--provider", PROVIDER)):
        if val:
            cmd += [flag, val]
    return cmd


def _run(argv_override=None) -> int:
    p = argparse.ArgumentParser(prog="spec_runner_adapter",
                                description="Spec_Runner 通用接入模板",
                                add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gate", help="从 GATES 表执行门禁（exit 透传）")
    g.add_argument("name")
    g.add_argument("--session")
    g.add_argument("--resume", action="store_true")

    sub.add_parser("gates", help="列出可用门禁")

    r = sub.add_parser("run", help="透传 Spec_Runner run")
    r.add_argument("--task", required=True)
    r.add_argument("--session")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--require-gate", action="append", default=[])
    r.add_argument("--prompt")
    r.add_argument("--prompt-file")

    s = sub.add_parser("status", help="派生视图")
    s.add_argument("--session")

    v = sub.add_parser("replay", help="重放校验")
    v.add_argument("--session", required=True)

    f = sub.add_parser("fork", help="复制前 N seq 行至新流")
    f.add_argument("--session", required=True)
    f.add_argument("--seq", type=int, required=True, dest="seq_from")
    f.add_argument("--new", required=True)

    sub.add_parser("probe", help="接入自检（一个 echo 探针 gate）")

    d = sub.add_parser("dry-run", help="打印将执行的命令，不实际运行")
    d.add_argument("inner", nargs=argparse.REMAINDER,
                   help="如: dry-run gate unit-tests / dry-run gates")

    args = p.parse_args(argv_override)

    # dry-run：先重入解析内层参数，打印命令
    if args.cmd == "dry-run":
        inner = args.inner or ["gates"]
        inner_argv = inner[1:] if inner[0] == "--" else inner
        inner_args = p.parse_args(inner_argv)
        cmd = _action_cmd(inner_args)
        print("DRY-RUN:", " ".join(cmd))
        return 0

    if args.cmd == "gates":
        print("\n".join(f"{k:20s} {v}" for k, v in GATES.items()))
        return 0
    if args.cmd == "probe":
        # 复用 gates 表内的 probe 项（配置区已内置）
        return _exec_gate(argparse.Namespace(name="probe", session=None))
    if args.cmd == "gate":
        return _exec_gate(args)
    if args.cmd == "run":
        return _exec_run(args)
    # status / replay / fork：透传
    cmd = [*_runner_cmd(), args.cmd]
    for flag, val in (("--session", getattr(args, "session", None)),
                      ("--seq", getattr(args, "seq_from", None)),
                      ("--new", getattr(args, "new", None))):
        if val:
            cmd += [flag, str(val)]
    return _exec(cmd)


def _exec_gate(args) -> int:
    # gate 天然 append-only：对已存在 session 追加即可，无 L6 拒绝（那是 run 的检查）
    return _exec(_build_gate_cmd(args, args.name))


def _exec_run(args) -> int:
    return _exec(_build_run_cmd(args))


def _exec(cmd: list) -> int:
    print("+", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=DEFAULT_CWD, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        print(f"exec: 找不到 {cmd[1]}——请检查 RUNNER 配置", file=sys.stderr)
        return 127
    return proc.returncode  # 透传（可嵌套 pre-commit/CI）


def _action_cmd(args) -> list:
    """把解析后的子命令参数还原为将执行的命令（供 dry-run 用）。"""
    if args.cmd == "gate":
        return _build_gate_cmd(args, args.name)
    if args.cmd == "run":
        return _build_run_cmd(args)
    if args.cmd == "gates":
        return ["(列出 GATES 表)"]
    if args.cmd == "probe":
        probe = argparse.Namespace(cmd="gate", name="probe", session=None,
                                   resume=False)
        return _build_gate_cmd(probe, "probe")
    cmd = [*_runner_cmd(), args.cmd]
    for flag, val in (("--session", getattr(args, "session", None)),
                      ("--seq", getattr(args, "seq_from", None)),
                      ("--new", getattr(args, "new", None))):
        if val:
            cmd += [flag, str(val)]
    return cmd


if __name__ == "__main__":
    sys.exit(_run())