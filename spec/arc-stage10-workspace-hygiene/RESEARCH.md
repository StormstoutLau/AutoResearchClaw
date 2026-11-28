---
id: arc-stage10-workspace-hygiene-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-stop-loss]
upstream: arc-master-roadmap
---

# 调研：Stage 10 工作区卫生与失败面前移（P-227）

> **档位**：S1 缺陷型（§2.3）。三条根因均可由运行 L 的日志与仓内代码直接复现。

## 1. 问题

运行 L 的 Stage 10 最终成功了，但代价 5 小时 27 分、3 次 attempt，且交付目录里混入了 attempt 1 的孤儿文件 `data_generator.py`。三次失败分别暴露了三个可修复的工程缺口。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | attempt 1 产物 `data_generator.py`（02:49）未被蓝图声明、无人 import，却留在最终 `experiment/` | [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md#L329) |
| L-2 | 对齐重生成 prompt 只含 topic/critique/plan，无蓝图文件与符号清单，且要求整项目重写 | [\_code_generation.py#L2084](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2084) |
| L-3 | 重生成直接 `files = regen_files`，磁盘旧文件从不清理 | 同上 #L2132 |
| L-4 | 符号契约只在生成边界与出口门检查；attempt 2 丢失 data.py 7/9 符号，153 分钟后才失败 | [codegen_evidence.py#L295](../../researchclaw/pipeline/codegen_evidence.py#L295) |
| L-5 | 深修 `fixed 0/4` 后无任何反馈进入下一轮（运行 L 05:22） | [\_code_generation.py#L1808](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1808) |

## 2.3 调研档位

- **档位**：S1 缺陷型。
- **最小来源**：E1 ≥2 —— L-1..L-5 均为现场日志或代码路径。
- **豁免说明**：本批是运行 L 的直接后果，外部检索无法提供比本地日志更强的证据；方法论对照见 §3。

## 2.4 降级链

| 目标通道 | 实际走到 | 结果 |
|---|---|---|
| MCP 学术检索 | 未调用（S1 豁免） | 不适用 |
| 现场产物 | `ls`/`grep` stage-10 | 命中 L-1 |
| 仓内代码 | 读 `_code_generation.py` | 命中 L-2/L-3/L-5 |
| 出口门代码 | 读 `codegen_evidence.py` | 命中 L-4 |

## 3. 社区对照

- **Reflexion**（arXiv 2303.11366）：重试收益取决于反馈是否具体；泛化「再试一次」无效 → 重生成必须带蓝图约束。
- **Self-Refine**（arXiv 2303.17651）：无新信息的迭代会收敛到同一错误 → 深修第二轮必须带「上轮未修」清单，且零进展即停。
- **Agentless**（arXiv 2407.01489）：修复后必须有独立验证；越早越便宜 → 符号契约前移。
- **干净构建**（CI 通行原则，idempotent/hermetic build）：产物目录每次重建，不跨 attempt 复用 → 隔离孤儿文件。

## 4. 结论

四项修复：F-1 工作区隔离、F-2 符号前移、F-3 重生成蓝图锚定、F-4 深修反馈与零进展止损。

## 5. 来源

- [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md)
- [P-226 RESEARCH](../arc-stage10-repair-stop-loss/RESEARCH.md)
- [P-223 RESEARCH §2.2](../arc-stage10-repair-guardrails/RESEARCH.md)
