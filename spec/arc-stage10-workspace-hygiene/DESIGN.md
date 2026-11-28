---
id: arc-stage10-workspace-hygiene-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-workspace-hygiene-RESEARCH]
upstream: arc-stage10-workspace-hygiene-RESEARCH
---

# 设计：Stage 10 工作区卫生与失败面前移（P-227）

## 1. 决策

| ID | 决策 | 依据 | 被拒替代 |
|---|---|---|---|
| F-1 | 写盘前把 `experiment/` 中不在本次 `files` 里的 `.py` 移入 `stage-10/quarantine/<tag>/`（保留证据，不删除） | L-1 孤儿文件 | 直接删除（破坏审计） |
| F-2 | 深修前调用 `check_symbol_contract`，失败项并入 `critical_deep` 走同一修复 | L-4 出口太晚 | 另建一条修复通道 |
| F-3 | 重生成 prompt 注入蓝图文件+符号清单；输出按蓝图过滤，缺失文件保留旧版本 | L-2/L-3 | 允许模型自由增删模块 |
| F-4 | 深修最多 2 轮；第二轮带「STILL NOT FIXED」清单；`fixed == 0` 立即停 | L-5 与 Self-Refine | 无限重试 |

## 2. 行为细节

- `_quarantine_stale(exp_dir, stage_dir, keep, tag)`：只处理顶层 `.py`；非 Python 文件与子目录不动；同名冲突加 mtime 后缀。
- 重生成过滤：`allowed = 蓝图文件名 ∪ {main.py}`；`files = {**files, **filtered}`，避免模型漏写导致模块消失。
- 符号检查使用 `load_blueprint(stage_dir)`，无蓝图时 `check_symbol_contract({})` 返回空，不影响老流程。
- 深修轮次上限 2，`_baseline` 固定为首轮 warnings，日志口径为累计修复数。

## 3. 验收

- 孤儿 `.py` 被隔离且内容可在 quarantine 读回；声明文件保留；
- 符号缺失在深修前出现，并被并入修复 issue 列表；
- 重生成输出不含蓝图外模块，缺失的声明文件保留旧版本；
- 深修 `fixed 0` 时不进入第二轮；
- 新增 5 例 + 既有三套回归全部通过。

## 4. 非目标

- 不改出口证据门判据；
- 不清理 `agent_runs/` 历史日志；
- 不部署、不重跑 B 站。
