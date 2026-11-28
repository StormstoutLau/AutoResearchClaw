---
id: arc-research-evidence-export-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-research-evidence-export-IMPLEMENTATION]
upstream: arc-research-evidence-export-IMPLEMENTATION
---

# 检查表：调研证据出口规范化（P-225）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | S0/S1/S2 三档成文 | SPEC_PROCESS 含「调研强度分级」小节与最小来源列 | ✅ |
| C-2 | 模板有档位槽位 | RESEARCH_TEMPLATE §2.3 存在，含豁免说明行 | ✅ |
| C-3 | 模板有降级链槽位 | RESEARCH_TEMPLATE §2.4 存在，含「目标→实际→结果」表 | ✅ |
| C-4 | 来源字段含层与版本 | §3 来源格式含 `Layer` 与 `日期 / 版本` | ✅ |
| C-5 | 执行进入验收面 | CHECKLIST_TEMPLATE §1.1 含档位/降级链自证行 | ✅ |
| C-6 | 入口文档同步 | AGENTS 五步第 2 步含档位与 `metadata.sources` | ✅ |
| C-7 | 零新增门禁 | `.pre-commit-config.yaml` 与 `spec_runner.py` diff 为空 | ✅ |
| C-8 | 本批自证 | 本 feature RESEARCH §2.3 = S1 且含豁免说明，§2.4 有降级链 | ✅ |
| C-9 | 无回归 | DC / console / rework / pre-commit 全通过 | ✅ |
