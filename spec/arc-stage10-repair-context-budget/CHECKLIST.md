---
id: arc-stage10-repair-context-budget-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-repair-context-budget-IMPLEMENTATION]
upstream: arc-stage10-repair-context-budget-IMPLEMENTATION
---

# 检查表：修复上下文的预算、遥测与截断止损（P-228）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 中间截断可识别 | `_middle_truncate` 保留头尾，标记含省略字符/行数与原始长度 | ✅ |
| C-2 | 短文本不变 | 未超限时逐字返回 | ✅ |
| C-3 | 预算内全量 | `_format_files` 在预算内与旧行为一致 | ✅ |
| C-4 | 超预算摘要化 | 未受影响文件出现 `# [summary`，keep 文件保留，总长下降 | ✅ |
| C-5 | usage 遥测 | trace 含 `prompt_tokens/completion_tokens/total_tokens/finish_reason` | ✅ |
| C-6 | 摘要模式可观测 | trace `summary_mode=True` | ✅ |
| C-7 | 二次截断止损 | 两轮共 4 次调用、`truncated_after_escalation`、streak=2 | ✅ |
| C-8 | 阶段深修有预算 | 阶段级上下文 80 000 上限 | ✅ |
| C-9 | 回归 | 四套 **61 passed** | ✅ |
| C-10 | 零部署 | B 站未改动 | ✅ |
