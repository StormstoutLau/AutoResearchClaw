---
id: arc-stage10-repair-guardrails-DESIGN
type: design
version: 1.0
status: draft
date: 2026-11-28
depends: [arc-stage10-repair-guardrails-RESEARCH]
upstream: arc-stage10-repair-guardrails-RESEARCH
---

# 设计：Stage 10 修复护栏优化方案（B-36 P1，P-223）

> **范围**：只出方案，零代码。P-222 已落地静态三闸门；本方案按社区经验补「止损、还原点、执行验证、反馈闭环、策略切换、基准」，供后续批次实施。
> **依据**：[RESEARCH](RESEARCH.md) §1 本地缺口（L-1..L-6）与 §2 社区证据。

## 1. 设计原则

1. **验证独立于生成**（Agentless）：修复是否被接受，不得由生成模型自评。
2. **不得变坏**（P-222 已立）：修复只能减少问题，不能减少符号、破坏入口或引入语法错误。
3. **反馈可执行**（Huang/Olausson）：下一轮必须知道上一轮**为什么**被拒，否则只是同一请求重采样。

## 2. 决策

| ID | 决策 | 社区依据 | 被拒替代 | 优先级 |
|---|---|---|---|---|
| D-1 | 同一文件同一拒收原因连续 2 次 → 停止该文件的定向修复，写 `repeated_rejection` 事件并交给阶段层/显式失败 | Cline v3.54 防无限重试；wally #195 自纠循环 | 继续跑满 4 轮 | P0 |
| D-2 | `agent_repair` 增修复前后 `digest/lines/kept`：被拒时记录保留版本摘要，形成逐文件还原点读数 | Cline Checkpoints；aider `/undo` | 只记 accepted 名称 | P0 |
| D-7 | 离线 fixture 基准：语法/入口/符号/截断/未知文件/重复拒收 6 场景，比较修复成功率、墙钟、误接受率 | AlphaCodium 的 flow 对照 | 只看现场单次结果 | P0（基准先行） |
| D-3 | 执行级验收：静态闸门通过后，在沙箱 `py_compile` + `import <module>` 冒烟（不执行训练），失败即拒收；无沙箱时 `verify=skipped` | Agentless patch validation；AlphaCodium 测试迭代 | 纯 AST 静态验收 | P1 |
| D-4 | 下一轮修复提示注入 `rejected_reasons` 与上一响应 digest（只进摘要，不落正文） | Huang/Olausson：外部反馈决定修复收益 | 同一 prompt 重采样（运行 I 实测 sha 相同） | P1 |
| D-5 | 同一文件连续 2 次拒收后，第 3 轮改「最小 unified diff 修补」，仍失败则显式失败 | Cursor 行号编辑；Cline diff 应用 | 永远整文件重写 | P2 |
| D-6 | 仅当模块目录存在 `tests/` 且配置开启时跑 pytest；对 `test_*.py` 的修复写入一律拒收 | agent 改测试作弊案例；Agentless 验证 | 默认跑测试/允许改测试 | P2 |

## 3. 分级与验收

**P0（低成本、直接止损 / 基准）**

- D-1：同一 `(file, reason)` 连续 2 次后不再进入下一轮；`repair_trace` 有 `repeated_rejection`；运行 K 型场景单文件墙钟 ≤ 一半（4 轮 ≈ 16 min → ≤ 8 min）。
- D-2：每次 `agent_repair` 带 `before/after` digest 与行数；被拒时 `kept` 指向原文件 digest；凭 trace 可回答「保留的是哪一版」。
- D-7：6 场景 fixture 回归；报告修复成功率、wall-clock、误接受率（目标接近 0）。

**P1（判别力）**

- D-3：修复回复通过沙箱 import 冒烟才合并；无沙箱时 `verify=skipped` 且日志可见；单轮额外成本 ≤ 1 次沙箱运行。
- D-4：被拒文件下一轮 prompt 必含 `rejected_reasons` 与上一响应 sha；prompt digest 必须与上一轮不同。

**P2（策略与测试）**

- D-5：diff 修补在 fixture 上可应用；应用失败不改变原文件；连续失败转显式失败。
- D-6：有 tests 时验收跑测试；`test_*.py` 的修复写入一律拒收（`test_file_write`）。

## 4. 接口草案

```python
# repair_trace 新字段（extra）
{"phase": "agent_repair", "reason": "rejected_all",
 "accepted": [], "rejected": ["data.py"],
 "rejected_reasons": {"data.py": "symbol_contract: loses ..."},
 "before": {"data.py": {"sha256": "...", "lines": 214, "missing_symbols": 0}},
 "after":  {"data.py": {"sha256": "...", "lines": 88,  "missing_symbols": 7}},
 "kept":   {"data.py": "sha256:..."},            # D-2
 "verify": "exec_ok|exec_failed|skipped",         # D-3
 "repeated_rejection": {"data.py": 2}}            # D-1
```

配置键（默认保守，全部可关，实施时按 fixture 结果再放开）：

- `repair_stop_after_rejections: 2`（D-1）
- `repair_exec_verify: false`（D-3）
- `repair_diff_fallback: false`（D-5）
- `repair_run_tests: false`（D-6）

## 5. 非目标

- 不提高生成预算与修复轮数上限；不改出口门判据；不做 N 倍采样或自由 agent 循环。
- 不自动删除/重命名模块；不允许修改测试文件。
- 不以「修复成功率提升」作为承诺——目标是降低无效轮次与误接受率，并让每次保留有据可查。

## 6. 实施顺序

D-7（fixture）→ D-1 + D-2（止损与还原点）→ D-3 + D-4（执行验证与反馈闭环）→ D-5 → D-6。每步独立可回退，均以 `repair_trace.jsonl` 为验收证据。
