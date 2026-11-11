"""W2 / B-55: Lean 危险构造过滤（LLM 产出代码写盘前）。

依据: spec/sandbox-isolation/DESIGN.md D11–D12

范围与边界（诚实标注）:
  · 黑名单是**构造级**过滤，不做 Lean 语法分析（语法面过大，D11）；
  · 宏 / import 间接触发的副作用拦不住（B-61）；
  · `#print axioms` 探针（W1 证据层，本仓生成）**不在**黑名单内，
    且调用点必须先过滤 LLM 代码、再追加探针（D12）。
"""
from __future__ import annotations

# 危险构造（唯一真值表）：命中即拒。
#   #eval / #exec     —— Lean 顶层求值指令，可执行任意 IO
#   run_cmd           —— `#eval` 家族的进程执行入口
#   implemented_by    —— 用外部程序替换常量/函数实现
#   @[extern         —— 绑定外部 C 符号
#   unsafe (声明)     —— 绕过内核检查
#   IO.              —— IO 调用（含 IO.Process）
DANGEROUS_LEAN_TOKENS: tuple[str, ...] = (
    "#eval", "#exec", "run_cmd", "implemented_by", "@[extern", "unsafe ", "IO.",
)


def strip_comments(code: str) -> str:
    """剥除 Lean 注释（`--` 行注释 / `/- -/` 块注释，支持嵌套）。

    实现方式: 把注释字符替换为空格、**保留换行** ⇒ 行号与原文一一对应，
    `scan_dangerous_commands` 报的行号即原文行号。
    """
    out: list[str] = []
    i = 0
    size = len(code)
    in_line_comment = False
    block_depth = 0
    while i < size:
        ch = code[i]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if block_depth > 0:
            if code.startswith("/-", i):
                block_depth += 1
                out.extend(("  "))
                i += 2
                continue
            if code.startswith("-/", i):
                block_depth -= 1
                out.extend(("  "))
                i += 2
                continue
            out.append(ch if ch == "\n" else " ")
            i += 1
            continue
        if code.startswith("--", i):
            in_line_comment = True
            out.extend(("  "))
            i += 2
            continue
        if code.startswith("/-", i):
            block_depth = 1
            out.extend(("  "))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def scan_dangerous_commands(code: str) -> list[str]:
    """返回命中的危险构造（带行号），空列表 = 通过。

    注释内的同串不算命中（先 :func:`strip_comments`）。
    """
    if not code:
        return []
    sanitized = strip_comments(code)
    hits: list[str] = []
    for lineno, line in enumerate(sanitized.splitlines(), start=1):
        for token in DANGEROUS_LEAN_TOKENS:
            if token in line:
                hits.append(f"{token} (line {lineno})")
    return hits
