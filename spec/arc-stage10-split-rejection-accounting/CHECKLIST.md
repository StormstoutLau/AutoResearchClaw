---
id: arc-stage10-split-rejection-accounting-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-29
depends: [arc-stage10-split-rejection-accounting-IMPLEMENTATION]
upstream: arc-stage10-split-rejection-accounting-IMPLEMENTATION
---

# 检查表：拆分修复的拒收记账（P-233）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 接受即不拒收 | 单文件接受 → `rejected == {}` | ✅（`test_accepted_file_is_not_recorded_as_rejected`） |
| C-2 | 不变式 | 任何路径下 `set(fixed) & set(rejected) == ∅` | ✅（读码 #L1941-L1951） |
| C-3 | 止损不误触发 | 拆分轮全部接受 → `_repeated_rejection() is None` | ✅（`test_split_round_does_not_trip_stop_loss`） |
| C-4 | 真失败仍止损 | 同一文件连续两次真实拒收 → P-226 仍停 | ✅（`test_truncated_twice_drops_round_and_hits_stop_loss` 保留） |
| C-5 | 既有拆分用例不变 | P-231 的 `test_split_repairs_one_file_per_request` 仍过 | ✅ |
| C-6 | 回归 | 五套定向 **115 passed**；全量 `pytest tests` **4262 passed / 6 failed**（6 项均为环境类） | ✅ |
| C-7 | 零部署副作用 | 运行 Q 已停止；无新增写盘/子进程 | ✅ |
