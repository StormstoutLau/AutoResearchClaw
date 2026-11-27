---
id: arc-stage10-repair-guardrails-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-repair-guardrails-IMPLEMENTATION]
upstream: arc-stage10-repair-guardrails-IMPLEMENTATION
---

# 检查表：D-7 修复护栏离线基准（P-224）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 6 场景齐全 | `test_coverage_is_six_scenarios` 通过，名称前缀 01..06 | ✅ |
| C-2 | 语法错误拒收且保留原文 | `test_01` 断言 `syntax_error` + 逐字节一致 | ✅ |
| C-3 | 入口契约破坏拒收 | `test_02` 断言 `entrypoint_contract` + `main.py` 不变 | ✅ |
| C-4 | 符号回退拒收 | `test_03` 断言 `symbol_contract` + `data.py` 不变 | ✅ |
| C-5 | 截断升级一次 | `test_04` 断言 `[16384, 32768]` 且最终接受正确版本 | ✅ |
| C-6 | 未知模块不合并 | `test_05` 断言 `helpers.py` 不在输出 | ✅ |
| C-7 | 同因拒收基线可量化 | `test_06` 断言 5 条 hard_validation、4 次调用、0 接受 | ✅ |
| C-8 | 误接受率为 0 | 6 场 `accepted_bad` 全为 False | ✅ |
| C-9 | 相关回归无退化 | 三套 **71 passed**（另本文件 7 passed） | ✅ |
| C-10 | 零生产代码改动 | `git diff` 仅测试 + spec 文档 | ✅ |
| C-11 | 未触碰 B 站 | 未部署、未停止运行 L | ✅ |
