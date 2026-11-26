---
id: arc-stage10-entrypoint-contract-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-repair-merge]
upstream: arc-master-roadmap
---

# 调研：Stage 10 入口契约与专用 main.py 生成（B-29）

> **背景**：B-28（P-190）修复了 repair 截断覆盖后，B 站 Stage 10 仍失败，但失败形态已改变。本报告定位新一层根因。

## 1. 现场证据（B 站，2026-11-26T01:36Z）

| 事实 | 读数 |
|---|---|
| Stage 10 | failed，14563.7s，3 次 attempt |
| 失败原因 | `generated entrypoint is not runnable: main.py missing if __name__ == "__main__" block; main.py never prints METRIC_DEF` |
| 最终 `main.py` | 3809B，末尾停在 `state = alpha`，无 `__main__`、无 `METRIC_DEF` |
| 其他文件 | `config.py` 5841B、`data.py` 2490B、`metrics.py` 1709B、`models.py` 21591B |
| B-28 生效证据 | 日志出现 `repair: response truncated — retrying with 32768`、`ignoring syntax-invalid main.py` |
| 次级异常 | `BUG-184: data.py imports 'config' which is not in generated files` |

## 2. 根因（两层）

**R-1 入口契约缺失**：`ast.parse` 只保证语法合法。截断点恰在函数体中间时（`state = alpha`），代码仍可解析，B-28 的 AST 过滤因此放行；但文件没有 `__main__` 守卫，也不打印 `METRIC_DEF`，Stage 12 无法取数。

**R-2 首个文件提升破坏模块集**：`code_agent.py` 在无 `main.py` 时执行
`generated_files["main.py"] = generated_files.pop(first_key)`。
本次 `first_key = config.py`，于是：
- `config.py` 从文件集消失，`data.py` 的 `from config import Config` 变成悬空导入（BUG-184 的直接原因）；
- 新的 `main.py` 其实是配置模块，天然不含入口守卫；
- 后续 repair 只能围绕这个错误入口反复修补。

## 3. 代码锚点

| 位置 | 现状 |
|---|---|
| `researchclaw/pipeline/code_agent.py`（"promoting first file" 段） | 重命名首个文件为 `main.py` |
| `researchclaw/pipeline/stage_impls/_code_generation.py` 出口门 | 仅在阶段末尾检查 `_entrypoint_issues`，失败即整段重跑 |
| 同文件 repair 路径 | 只做 `ast.parse`，不校验入口契约 |

## 4. 结论

B-29 = 三层修复：
1. **不再提升**：保留原文件名，缺失 `main.py` 时专用生成；
2. **专用入口生成**：给出现有模块清单 + 指标名，要求 `__main__` 守卫与 `METRIC_DEF`，32768 tokens、2 次、截断重试；
3. **契约前置**：repair 拒绝不合契约的 `main.py`；校验前与出口门前各做一次 `_ensure_entrypoint`，把失败从"4 小时后"提前到"分钟级"。
