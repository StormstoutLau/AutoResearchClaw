---
id: arc-cli-agent-seam-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-seam-DESIGN]
upstream: arc-cli-agent-seam-DESIGN
---

# 实施记录：R-3 统一接缝

> 输入：[DESIGN.md](DESIGN.md) §2-§5。E-* 为实际落点，V-* 为可重放验证。

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-1 | 配置类去重：pipeline 导入 `config.CodeAgentConfig` | `researchclaw/pipeline/code_agent.py` |
| E-2 | 工厂报错路径改为 `experiment.cli_agent.binary_path` | `researchclaw/experiment/code_agent.py` |
| E-3 | Codex 改为 `codex exec -` + stdin prompt | `researchclaw/experiment/code_agent.py` |
| E-4 | Stage 10 显式 provider 优先 + `cli_agent_log.json` + 回退 | `_code_generation.py::_try_cli_code_agent`、`:729-755`、`:874-879` |
| E-5 | Stage 13 refine/repair 优先 CLI + 回退 + `refinement_log.cli_agent` | `_execution.py::_try_agent_refine/_try_agent_repair`、`:1318-1345`、`:1460-1505`、`:1544-1585`、`:1688-1726` |
| E-6 | Doctor 新增 `cli_agent` 检查 | `researchclaw/health.py::check_cli_agent`、`run_doctor` |
| E-7 | 适应度函数 + pre-commit + CI | `scripts/code_agent_wiring_check.py`、`.pre-commit-config.yaml`、`.github/workflows/ci.yml` |
| E-8 | 契约/接线/回退/传输/doctor 测试 16 个 | `tests/test_cli_agent_wiring.py` |
| E-9 | Doctor 计数断言同步（9→10、7→8） | `tests/test_rc_health.py` |

## 2. 验证

```bash
# V1 新契约测试
python -m pytest tests/test_cli_agent_wiring.py -q

# V2 相关回归
python -m pytest tests/test_cli_agent_wiring.py tests/test_rc_health.py \
  tests/test_code_agent.py tests/test_rc_stages.py -q

# V3 全量回归（排除缺失 mcp 依赖的两个文件）
python -m pytest -q --ignore=tests/test_mcp.py --ignore=tests/test_mcp_protocol.py

# V4 结构适应度函数
python scripts/code_agent_wiring_check.py

# V5 私网/密钥扫描（本批改动文件）
python scripts/private_config_check.py researchclaw/config.py researchclaw/health.py \
  researchclaw/experiment/code_agent.py researchclaw/pipeline/code_agent.py \
  researchclaw/pipeline/stage_impls/_code_generation.py \
  researchclaw/pipeline/stage_impls/_execution.py \
  scripts/code_agent_wiring_check.py tests/test_cli_agent_wiring.py

# V6 批次声明覆盖（工作树模式）
python scripts/step_enforce.py --base HEAD \
  spec/arc-cli-agent-seam/RESEARCH.md spec/arc-cli-agent-seam/DESIGN.md \
  spec/arc-cli-agent-seam/IMPLEMENTATION.md spec/arc-cli-agent-seam/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p012-arc-cli-agent-seam.jsonl
```

## 3. 结果（2026-11-10）

- V1：**16 passed**。
- V2：**171 passed**。
- V3：**3030 passed, 7 failed, 100 skipped**。7 个失败均为环境/既有问题：`test_hitl_advanced`（Windows 执行 `.sh`）、`test_memory_system`（Keras 3）、`test_rc_sentinel`（bash 路径）、`test_web_platform`（默认绑定与断言不一致）；与本批改动文件无交集。
- V4：`code_agent_wiring_check: PASS (providers=claude_code,codex,llm)`。
- V5：exit 0（0 违规）。
- V6（真实端到端）：`_try_cli_code_agent` + 真实 Claude Code CLI + B 站端点，**35.16s** 返回 4 个文件（`main.py`、`dataset.py`、`normalize.py`、`classifier.py`），`cli_agent_log.json` 记录 `ok=true`；生成的 `main.py` 输出：
  ```text
  condition=baseline accuracy: 0.9167
  condition=zscore accuracy: 0.9522
  ```
- V7：`step-enforce --base HEAD` → `mode=batch pid=P-011,P-012 ... exit 0`。

## 4. 行为边界

- 默认 `provider="llm"`：Stage 10/13 调用序列不变；`cli_agent_log.json` 不生成。
- CLI 超时/异常/空文件：记录告警并回退，不改变阶段状态。
- Stage 13 的 `llm is None` 早退保留；CLI 路径不会在无 LLM 时单独启动。
- Stage 13 的后续 LLM 重生成/运行时修复仅在 CLI 失败时触发；CLI 成功时优先使用 CLI 产出。
- 工作树另含上一轮 Claude Code prompt stdin 化与 Windows 进程树清理（`tests/test_b_station_provider.py` 覆盖）；本批 Codex 同步采用 stdin。

## 5. 未执行

- U-1 跨后端 A/B（成功率/耗时/成本）。
- U-2 Windows 版本矩阵与编码矩阵。
- U-3 Agent SDK / ACP 作为 Stage 10/13 传输的实测。
- U-5 Stage 13 的“允许改什么”边界裁决。
- 未修改 `arc-master-roadmap.md`；未新增阶段或改变阶段出口。
