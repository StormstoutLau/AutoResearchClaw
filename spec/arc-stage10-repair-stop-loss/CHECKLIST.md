---
id: arc-stage10-repair-stop-loss-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-repair-stop-loss-IMPLEMENTATION]
upstream: arc-stage10-repair-stop-loss-IMPLEMENTATION
---

# 检查表：Stage 10 重复拒收止损（P-226 / D-1）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 同因两次即停 | `test_06`：2 条 `hard_validation`、2 次调用、1 条 `agent_repair_stopped` | ✅ |
| C-2 | 原文件保留 | `test_06`：`out["data.py"] == SCOPING_BAD` | ✅ |
| C-3 | 停止事件可审计 | `agent_repair_stopped` 含 `file/reason/count=2/attempt` | ✅ |
| C-4 | 可关闭 | `test_07`：`repair_stop_after_rejections=0` → 5 行 / 4 调用 | ✅ |
| C-5 | 交替原因不误杀 | `test_08`：syntax→symbol 交替仍 5 行 / 4 调用，无 stopped | ✅ |
| C-6 | 闸门无回归 | 其余 5 场景 `kept=True`、`accepted_bad=False` | ✅ |
| C-7 | 相关回归 | 四套 **80 passed** | ✅ |
| C-8 | 零部署 | 未改 B 站代码，运行 L 未受扰动 | ✅ |
