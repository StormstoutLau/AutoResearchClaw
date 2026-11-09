---
id: arc-cli-agent-followups-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-cli-agent-followups-IMPLEMENTATION]
upstream: arc-cli-agent-followups-IMPLEMENTATION
---

# 验收清单：U-3/U-5 收口

## 1. 收口验收

| # | 验收项 | DoR | DoD | 证据 |
|---|---|---|---|---|
| A-1 | U-3 有明确裁决 | 读到 P-012 实现 | Stage 10/13=CLI-stdin；ACP=LLM 层；SDK 暂缓 | RESEARCH §3.3、DESIGN D-1 |
| A-2 | U-5 边界已落地 | 常量存在 | CLI refine 的 `extra_hints` 含边界；日志含 `boundary` | `_execution.py:44-51/1345-1351/1479-1486` |
| A-3 | U-5 预算有明确口径 | 读配置 | 沿用 `cli_agent.timeout_sec`/`max_budget_usd` + wall-clock cap | DESIGN D-3 |
| A-4 | U-4 已前移 | 读 P-013 文档 | RESEARCH §6.2 + CHECKLIST §6 均出现 U-4 | 本文件 §6、RESEARCH §6.2 |
| A-5 | P-011 §5.3 有处置 | 读归档 | 两条 superseded、一条保留 | IMPLEMENTATION §3 |
| A-6 | U-1/U-2 保持 pending | 读四元块 | 触发条件未命中，未提前实现 | RESEARCH §6.2 |
| A-7 | U-6 已登记 | 读四元块 | 判据/触发/倾向/证据等级齐全 | RESEARCH §6.2 |

## 2. 代码与测试

- [x] `_STAGE13_CLI_BOUNDARY` 只进入 CLI refine，不改变默认 LLM 路径
- [x] `refinement_log.cli_agent.boundary` 写入 `repair_and_tune`
- [x] 适应度函数新增边界声明/使用/日志三项断言
- [x] 新增 2 个边界测试，`test_cli_agent_wiring.py` 共 18 passed
- [x] 相关回归 130 passed
- [x] 未修改 P-011/P-012 归档文档
- [x] 未修改 `arc-master-roadmap.md`
- [x] 新代码不含私网地址、真实端口或密钥

## 3. 机检

- [x] V1 `pytest tests/test_cli_agent_wiring.py` → 18 passed
- [x] V2 相关回归 → 130 passed
- [x] V3 全量回归 → 3032 passed / 7 既有失败 / 100 skipped
- [x] V4 `code_agent_wiring_check.py` → PASS
- [x] V5 `dc_validator` + `console_gen --check` → 0 违规 / 一致
- [x] V6 `step_enforce --base HEAD` → `mode=batch pid=P-013` exit 0

## 4. 未纳入本批

- U-1 跨后端 A/B
- U-2 Windows/编码矩阵
- U-4 归一化工具调用日志
- U-6 Stage 13 CLI 边界硬门
