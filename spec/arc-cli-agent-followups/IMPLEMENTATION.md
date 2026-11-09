---
id: arc-cli-agent-followups-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-followups-DESIGN]
upstream: arc-cli-agent-followups-DESIGN
---

# 实施记录：U-3/U-5 收口与 U-4 前移

> 输入：[DESIGN.md](DESIGN.md) §2-§4。E-* 为实际落点，V-* 为可重放验证。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | U-3 裁决：Stage 10/13 用 CLI-stdin；ACP 保持 LLM 层；SDK 暂缓 | [RESEARCH.md](RESEARCH.md) §3.3、[DESIGN.md](DESIGN.md) D-1 |
| E-2 | U-5 边界常量 `_STAGE13_CLI_BOUNDARY` | `researchclaw/pipeline/stage_impls/_execution.py:44-51` |
| E-3 | 边界注入 CLI refine 的 `extra_hints` | `_execution.py:1479-1486` |
| E-4 | 审计字段 `cli_agent.boundary="repair_and_tune"` | `_execution.py:1345-1351` |
| E-5 | 适应度函数新增边界断言 | `scripts/code_agent_wiring_check.py:67-74` |
| E-6 | 2 个边界测试（声明 + 接线） | `tests/test_cli_agent_wiring.py::TestStage13CliBoundary` |
| E-7 | U-4 前移登记 | RESEARCH §6.2、CHECKLIST §6 |
| E-8 | P-011 §5.3 处置记录 | 本文件 §3 |

## 2. 验证

```bash
# V1 边界测试
python -m pytest tests/test_cli_agent_wiring.py -q

# V2 相关回归
python -m pytest tests/test_cli_agent_wiring.py tests/test_rc_stages.py \
  tests/test_code_agent.py -q

# V3 全量回归（排除缺失 mcp 依赖的两个文件）
python -m pytest -q --ignore=tests/test_mcp.py --ignore=tests/test_mcp_protocol.py

# V4 结构适应度函数
python scripts/code_agent_wiring_check.py

# V5 文档/派生视图
python scripts/dc_validator.py spec/arc-cli-agent-followups/RESEARCH.md \
  spec/arc-cli-agent-followups/DESIGN.md spec/arc-cli-agent-followups/IMPLEMENTATION.md \
  spec/arc-cli-agent-followups/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python scripts/console_gen.py --check

# V6 批次声明
python scripts/step_enforce.py --base HEAD \
  spec/arc-cli-agent-followups/RESEARCH.md spec/arc-cli-agent-followups/DESIGN.md \
  spec/arc-cli-agent-followups/IMPLEMENTATION.md spec/arc-cli-agent-followups/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p013-arc-cli-agent-followups.jsonl
```

## 3. 结果（2026-11-10）

- V1：**18 passed**（原 16 + 新增 2）。
- V2：**130 passed**。
- V3：**3032 passed, 7 failed, 100 skipped**。7 个失败与 P-012 全量回归一致，均为环境/既有问题（Windows `.sh`、Keras 3、bash 路径、web 默认绑定），与本批改动文件无交集。
- V4：`code_agent_wiring_check: PASS (providers=claude_code,codex,llm)`。
- V5：`DC 契约校验通过：6 文件，2 结果，0 违规`；`CONSOLE.md 与源一致`。
- V6：`step-enforce: mode=batch pid=P-013 ... exit 0`。

### P-011 §5.3 处置

| 原项 | 处置 |
|---|---|
| P-007 文档“Claude Code 接入”表述 | **superseded**：P-012 已把 CLI 后端接入 Stage 10/13，原表述不再需要勘误 |
| 示例配置 `cli_agent` 标注“实验态/未接线” | **superseded**：P-012 已接线，示例注释“Stages 10/13 可选后端”准确 |
| X-4/X-5/X-11 正文未抓取 | **保留**：仍为非阻塞的引用置信度问题 |

## 4. 行为边界

- 默认 `provider="llm"`：Stage 13 的 LLM prompt 与调用序列不变。
- 边界提示只进入 CLI refine 的 `extra_hints`；不影响 LLM refine。
- 边界为提示级约束 + 审计字段，不是条件集硬门；硬门由 U-6 跟踪。
- 预算沿用 `experiment.cli_agent.timeout_sec`/`max_budget_usd` 与 Stage 13 wall-clock cap。

## 5. 未执行

- U-1 跨后端 A/B。
- U-2 Windows 版本/编码矩阵。
- U-4 归一化工具调用日志。
- U-6 Stage 13 CLI 边界硬门。
