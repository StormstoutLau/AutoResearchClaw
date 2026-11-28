---
id: arc-stage10-repair-minimal-edit-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-repair-minimal-edit-IMPLEMENTATION]
upstream: arc-stage10-repair-minimal-edit-IMPLEMENTATION
---

# 检查表：Stage 10 修复的作用域与最小改动（P-231）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 补丁优先 | 符号完整、仅缺 guard 的 main.py → `llm.calls == []`，两契约同时满足，原实现保留 | ✅（`test_patches_missing_guard_without_llm`） |
| C-2 | 补丁不造假数 | 注入 `METRIC_DEF` 定义行，数值行只在返回 dict 含该指标时打印；源码无 `nan` 兜底 | ✅（`test_injects_metric_def_without_fake_value`） |
| C-3 | 补丁边界 | 已有 guard / 无零参入口 / 语法坏 → 返回 `None`，走 LLM 路径 | ✅（3 例） |
| C-4 | 入口 prompt 带符号 | 有契约时 prompt 含声明名，「thin driver」措辞被替换 | ✅（`TestSymbolContractPrompt`） |
| C-5 | 候选丢符号即拒 | 第 1 次回缺符号 → 拒；第 2 次补齐 → 接受，且回传缺失名 | ✅（`TestEntrypointSymbolAware`） |
| C-6 | 一文件一请求 | 两文件缺符号 → 2 次调用，每次只贴/只要一个文件 | ✅（`test_one_request_per_affected_file`） |
| C-7 | 二次截断不重发 | 组合 16k→32k 后转按文件拆分；trace `split_per_file` | ✅（`TestRepairSplitOnSecondTruncation`、`TestTruncationStops`） |
| C-8 | 写前联合校验 | `_contract_issues` 同时报语法 / 入口 / 符号；干净文件返回空 | ✅（`TestContractIssues`） |
| C-9 | 对齐重生成可回滚 | 契约失败 → 磁盘与内存恢复旧文件 | ✅（读码 #L2437-L2469） |
| C-10 | 最小改动守卫 | 保留不足一半非空行 → `catastrophic_rewrite` 拒收 | ✅（`TestCatastrophicRewriteGuard`） |
| C-11 | 编译 + 导入冒烟 | 语法坏 → failure；第三方缺包 → warning；正常 → 无问题 | ✅（`TestSmokeModules` 3 例） |
| C-12 | 回归 | 六套定向 **127 passed**；全量 `pytest tests` **4257 passed / 6 failed**（6 项均为环境类：壳钩子、Keras 3、bash 路径） | ✅ |
| C-13 | 边界登记 | S-063（子进程）、W-034（回滚写盘）登记且 `test_boundary_coverage` 通过 | ✅ |
| C-14 | 零部署 | B 站停留在 P-230 快照；运行 O 已停止 | ✅ |
