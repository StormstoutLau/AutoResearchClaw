---
id: arc-cli-agent-wiring-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-cli-agent-wiring-IMPLEMENTATION]
upstream: arc-cli-agent-wiring-IMPLEMENTATION
---

# 验收清单：CLI 代码代理接线断裂调研

## 1. 调研完整性

| # | 验收项 | DoR（开始条件） | DoD（通过条件） | 证据 |
|---|---|---|---|---|
| A-1 | 三条代理路径（ACP/OpenCode/CLI）有入口、实现、接线状态 | 读码完成 | 每条均有配置键、模块、是否接线 | RESEARCH §3.1.1 |
| A-2 | 配置面四问（定义/解析/校验/消费者）完整 | 读码完成 | 四个配置块逐项有结论 | RESEARCH §3.1.2 |
| A-3 | 问题链可复述为“配置→解析→校验→工厂→无调用方→阶段分支” | 事实齐备 | 六环均有代码位置或命令 | RESEARCH §3.1.2、§3.1.3 |
| A-4 | 历史追溯至少含引入与最近修改两个提交 | git 可用 | 提交哈希、时间、事实齐全 | RESEARCH §3.1.3 |
| A-5 | 外部锚点 ≥10 项，且 ≥2 个独立来源支持“prompt 不走 argv” | 检索完成 | 锚点表含 URL/ID 与验证状态 | RESEARCH §3.2 |
| A-6 | 社区解法 ≥5 种，含优缺点与代价 | 检索完成 | 矩阵列全 | RESEARCH §3.3 |
| A-7 | 路线 ≥3 条，含成本/收益/兼容/风险与推荐 | 调研完成 | 决策矩阵 + 明确建议 | RESEARCH §4.4 |
| A-8 | 未决项以四元块登记（判据/触发/倾向/证据等级） | 设计完成 | 每条四元齐全 | RESEARCH §6.4、DESIGN §8 |

## 2. 问题链与证据可复现

| # | 验收项 | DoR | DoD | 证据 |
|---|---|---|---|---|
| B-1 | `create_code_agent` 无生产调用方 | 仓库可 grep | 仅命中定义/docstring/测试 | V4 输出 |
| B-2 | Stage 10 不读取 `cli_agent.provider` | 读码 | 分支表无该字段 | `_code_generation.py:640-770` |
| B-3 | Stage 13 只走 `_chat_with_prompt` | 读码 | 无工厂调用 | `_execution.py:1366/1441/1566` |
| B-4 | `_parse_code_agent_config` 丢弃 `provider` | 读码 | 字段映射表无 provider | `config.py:1546-1566` |
| B-5 | `CodeAgentConfig` 存在两份定义 | 读码 | 两处均命中 | `config.py:466`、`pipeline/code_agent.py:41` |
| B-6 | `cli_agent.max_budget_usd` 被当作 run 预算 | 读码 | runner 读取点存在 | `runner.py:482` |
| B-7 | 示例配置公开了未接线能力 | 读文件 | `provider: "claude_code"` 示例存在 | `config.researchclaw.example.yaml:166-179` |
| B-8 | 现有测试不证明接线 | 读测试 | 无 Stage 10/13 断言 | `tests/test_b_station_provider.py:243-297` |

## 3. 设计与裁决输入

- [x] DESIGN 给出 D-1..D-9，且每条含被拒绝替代方案与理由
- [x] 配置唯一真值源、协议、接线点、传输、回退、日志、测试七项均有落点
- [x] 明确 R-4 可先做、R-3 以 U-1 为门槛、R-2 为兜底
- [x] 未把“建议”写成“已执行”；IMPLEMENTATION §4 明确未执行项
- [x] 与 Q17（API-first）、Q20（预算分层）口径一致

## 4. 边界与一致性

- [x] 未修改 `arc-master-roadmap.md`
- [x] 未修改 `researchclaw/` 代码（工作树中的 prompt 修复属上一轮，不计入本批）
- [x] 未修改 P-007 四文档；订正项登记在 RESEARCH §5.3
- [x] 新文档不含私网地址、真实端口、密钥
- [x] RESEARCH ↔ DESIGN ↔ IMPLEMENTATION ↔ CHECKLIST 的 F/D/E/U 编号互相引用且不悬空
- [x] 路线推荐与外部证据（X-9/X-11/X-13）对应，未把类比当实测

## 5. 机检

- [x] V1 `dc_validator`（spec 作用域）0 违规（6 文件，2 skip）
- [x] V2 `step-gate` 五步齐全（research/design/implement/verify/finalize，exit 0）
- [x] V3 `console_gen --check` 退出码 0（CONSOLE 与源一致）
- [x] V4 `create_code_agent` 调用方检查输出符合 B-1（仅 docstring L10/L12 + 定义 L771）
- [x] V5 本批文件边界与 IMPLEMENTATION §3 一致（新增 spec + session；改 PROGRESS/CONSOLE；无代码）
- [x] V6 `private_config_check.py` 对本批文档 exit 0

## 6. 未纳入本批

- R-4 fail-fast、R-3 接线、R-2 删除的代码改动
- 三种后端的 A/B（U-1）
- Windows 版本矩阵（U-2）
- SDK/ACP/CLI 传输选型的实测（U-3）
- 审计口径的归一化日志实现（U-4）
