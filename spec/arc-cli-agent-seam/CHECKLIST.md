---
id: arc-cli-agent-seam-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-cli-agent-seam-IMPLEMENTATION]
upstream: arc-cli-agent-seam-IMPLEMENTATION
---

# 验收清单：R-3 统一接缝

## 1. 功能验收

| # | 验收项 | DoR | DoD | 证据 |
|---|---|---|---|---|
| A-1 | `CodeAgentConfig` 只有一份定义 | 导入链可用 | `config.CodeAgentConfig is pipeline.CodeAgentConfig` | 测试 `test_config_code_agent_single_definition` |
| A-2 | 工厂报错指向 `experiment.cli_agent.binary_path` | 工厂可调用 | 缺失二进制时错误文案含该键 | `test_factory_error_points_to_cli_agent_path` |
| A-3 | Stage 10 显式 provider 先于 Beast/CodeAgent/Legacy | `provider != llm` | 成功时跳过三条旧链路 | `_code_generation.py:729-755`；helper 测试 |
| A-4 | Stage 10 失败回退 | 假代理异常/空结果 | 返回 None，旧链路继续 | `test_helper_falls_back_*` |
| A-5 | Stage 13 refine 优先 CLI | 代理存在 | 返回文件并计数 `refine_calls` | `test_refine_helper_uses_agent` |
| A-6 | Stage 13 repair 优先 CLI | 校验失败/运行期问题 | 成功时合并文件；失败回退 LLM | `_try_agent_repair` 测试 + 代码路径 |
| A-7 | Codex prompt 走 stdin | 构造命令 | `exec -`，prompt 不在 argv | `test_codex_prompt_goes_to_stdin` |
| A-8 | Doctor 检查 CLI 后端 | 配置 `provider=claude_code` | 二进制缺失 fail，显式路径 pass | `TestDoctorCliAgent` 3 用例 |
| A-9 | 默认 `llm` 零行为变化 | 未显式配置 | 工厂不被调用，Stage 走原链路 | `test_helper_skips_llm_provider`；V2/V3 回归 |
| A-10 | 真实 CLI 端到端 | 隧道与 CLI 可用 | 生成可运行项目并输出指标 | IMPLEMENTATION §3 V6 |

## 2. 结构治理

- [x] `scripts/code_agent_wiring_check.py` 零依赖、exit 语义明确
- [x] 检查覆盖：provider→工厂分支、Stage 10/13 消费点、prompt 不进 argv
- [x] 负向用例：未接线的 `ghost` provider 触发 exit 1
- [x] pre-commit 新增 `code-agent-wiring` 钩子
- [x] CI `roadmap-coverage` job 新增接线检查步骤

## 3. 测试与回归

- [x] 新增 16 个离线用例，全部通过
- [x] 相关回归 171 passed
- [x] 全量回归 3030 passed；7 个失败均为环境/既有问题（见 IMPLEMENTATION §3）
- [x] 真实 CLI + B 站端点 35.16s 返回 4 文件，`main.py` 可运行
- [x] `private_config_check` 对本批改动 0 违规

## 4. 边界与一致性

- [x] 默认 `provider=llm` 时 Stage 10/13 行为不变
- [x] 未新增阶段、未改变阶段出口或产物名
- [x] `refinement_log.json` 只新增 `cli_agent` 字段，未删旧字段
- [x] 未修改 `arc-master-roadmap.md`
- [x] 新代码不含私网地址、真实端口或密钥
- [x] `experiment.code_agent` 仍只承载阶段开关，provider 唯一来源为 `experiment.cli_agent`

## 5. 机检

- [x] V1 `pytest tests/test_cli_agent_wiring.py` → 16 passed
- [x] V2 相关回归 → 171 passed
- [x] V3 全量回归 → 3030 passed / 7 既有失败 / 100 skipped
- [x] V4 `code_agent_wiring_check.py` → PASS（providers=claude_code,codex,llm）
- [x] V5 `private_config_check.py` → exit 0
- [x] V6 真实 CLI 端到端 → 4 文件 + 两项 condition 指标输出
- [x] V7 `step_enforce --base HEAD` → `mode=batch pid=P-011,P-012` exit 0

## 6. 未纳入本批

- U-1 跨后端 A/B
- U-2 Windows/编码矩阵
- U-3 SDK/ACP 传输实测
- U-5 Stage 13 改动边界裁决
