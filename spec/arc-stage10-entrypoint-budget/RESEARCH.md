---
id: arc-stage10-entrypoint-budget-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-entrypoint-contract]
upstream: arc-master-roadmap
---

# 调研：专用入口生成的预算、约束与兜底（B-30）

> **背景**：B-29 落地后，B 站 Stage 10 不再被“提升首个文件”误导，入口契约检测按预期触发（`entrypoint contract unmet ... generating main.py`）。但专用生成连续两次失败，阶段仍在同一位置阻塞。

## 1. 现场证据（B 站，2026-11-26T07:21Z，第 1 次 attempt 已跑 2h30m）

```
Stage 10: entrypoint contract unmet (main.py missing `if __name__ == "__main__":` block; main.py never prints METRIC_DEF); generating main.py
Stage 10: entrypoint attempt 1 truncated — retrying
Stage 10: entrypoint attempt 1 rejected: main.py has a syntax error: '[' was never closed (line 517)
Stage 10: entrypoint attempt 2 truncated — retrying
Stage 10: entrypoint attempt 2 rejected: main.py has a syntax error: '(' was never closed (line 517)
Stage 10: dedicated entrypoint generation failed (...)
Repair attempt returned invalid Python for data.py, keeping original   ×4
```

## 2. 三个缺陷

| ID | 缺陷 | 证据 |
|---|---|---|
| D-1 | **截断后同额度重试**：两次都按 32768 重试，输出在第 517 行仍未闭合 | 日志两行 `truncated — retrying` 后同样越界 |
| D-2 | **提示未约束体量**：模型把模块逻辑重新写进 `main.py`，单文件 500+ 行 | `line 517` 越界位置 |
| D-3 | **无兜底路径**：模型连续失败后没有确定性方案，只能等阶段末尾失败 | `dedicated entrypoint generation failed` 后无后续动作 |
| D-4 | **repair 空转**：同一文件连续 4 次返回非法 Python，仍耗尽 5 个 repair 槽 | `Repair attempt returned invalid Python for data.py` ×4 |

## 3. 约束

- 不能放宽入口契约（否则 Stage 12 仍拿不到指标）。
- 不能让兜底写入伪造指标：仅调用现成函数，取不到数值时打印 `nan`。
- 不改 Stage 12 解析与阶段重试次数。

## 4. 结论

B-30 = 四项：
1. **预算升级**：32768 → 65536（不再同额度重试）；
2. **体量约束**：`≤150 行`、只 import 并调用、`exp_plan` 摘要 3000 → 1200 字符；
3. **确定性兜底**：从已有模块挑 `main/run/train/...`，生成薄驱动；
4. **repair 止损**：连续 2 次不可用响应即停止该文件重试并记录。
