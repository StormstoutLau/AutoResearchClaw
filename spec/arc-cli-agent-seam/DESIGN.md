---
id: arc-cli-agent-seam-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-seam-RESEARCH]
upstream: arc-cli-agent-seam-RESEARCH
---

# 设计：R-3 统一接缝的最小落地

> 输入：[RESEARCH.md](RESEARCH.md) §3 插入点与不变量；P-011 DESIGN D-1..D-9。
> 目标：显式配置 CLI 时真正生效；默认路径零变化；失败可回退；结构可机检。

## 1. 设计不变量

1. `provider="llm"` 时，Stage 10/13 行为与改动前一致。
2. CLI 分支只在 `provider != "llm"` 时进入，且先于 Beast Mode。
3. CLI 失败（异常/超时/空文件）不改变 Stage 状态，回退现有链路。
4. prompt 一律走 stdin；argv 只放标志。
5. 配置类单一定义；`experiment.cli_agent` 是唯一 provider 来源。
6. 新增日志字段只增不改；`refinement_log.json` 既有字段保持。

## 2. 决策表

| # | 决策 | 选择 | 拒绝的替代 | 理由 |
|---|---|---|---|---|
| E-1 | 配置类去重 | `config.py::CodeAgentConfig` 为规范定义；`pipeline/code_agent.py` 导入同名符号 | 保留两份 | 字段漂移不可见 |
| E-2 | Stage 10 接线 | 在 `:640` 前调用 `_try_cli_code_agent()`；成功则跳过 Beast/CodeAgent/Legacy | 改 Beast 分支内部 | 保持三条既有链路的原子性 |
| E-3 | Stage 10 回退 | helper 返回 `None` → 原链路继续 | 抛异常中止 Stage | CLI 是可选后端 |
| E-4 | Stage 13 改进 | 每轮优先 `agent.refine()`；失败回退 `_chat_with_prompt` | 重写整个 refine 循环 | 改动面最小 |
| E-5 | Stage 13 修复 | 校验失败时优先 `agent.repair()`；失败回退 LLM repair | 只接改进不接修复 | 语义一致 |
| E-6 | Codex 传输 | `codex exec -`，prompt 写 stdin | 维持 argv | 与 Claude 同风险 |
| E-7 | 工厂文案 | 错误指向 `experiment.cli_agent.binary_path` | 维持旧文案 | 旧文案指向不存在的键 |
| E-8 | Doctor | `provider != llm` 时检查二进制；缺失 fail | 仅在运行时报错 | 让用户开跑前发现 |
| E-9 | 结构检查 | 新增 `scripts/code_agent_wiring_check.py`，零依赖 | 只靠测试 | 防止再次“配置无消费者” |
| E-10 | 日志 | `cli_agent_log.json` + `refinement_log.cli_agent` | 只写 logger | 便于审计与回放 |

## 3. 接口

### 3.1 Stage 10 helper（模块级，可单测）

```python
def _try_cli_code_agent(
    config: RCConfig,
    llm: Any | None,
    prompts: Any | None,
    *,
    stage_dir: Path,
    topic: str,
    exp_plan: str,
    metric: str,
    pkg_hint: str,
    compute_budget: str,
    extra_guidance: str,
) -> dict[str, str] | None:
    """显式 CLI provider 时返回文件；未配置/失败返回 None。"""
```

行为：
- `provider` 取 `config.experiment.cli_agent.provider`，空值归一为 `llm`。
- `llm` → 立即返回 `None`（不创建实例）。
- 创建失败、`result.ok == False`、`files` 为空 → 写日志并返回 `None`。
- 成功 → 写 `stage_dir/cli_agent_log.json`，返回 `result.files`。

### 3.2 Stage 13 helpers（模块级，接收 `_refine_agent` 实例）

```python
_try_agent_refine(...) -> dict[str, str] | None
_try_agent_repair(...) -> dict[str, str] | None
```

- 代理实例在 `llm is None` 早退之后创建一次；创建失败仅告警，`_refine_agent=None`。
- 传入 `extra_hints` 组装现有条件覆盖/饱和/超时提示，不新增提示词语义。
- 失败返回 `None`，由调用点走原 LLM 分支。

### 3.3 适应度函数

`scripts/code_agent_wiring_check.py` 机械断言：

1. `CLI_AGENT_PROVIDERS` 中每个 provider 在 `experiment/code_agent.py` 工厂有分支。
2. `_code_generation.py` 与 `_execution.py` 均出现 `create_code_agent` 与 `cli_agent`。
3. `ClaudeCodeAgent._build_cmd` 不含 `"-p", prompt`；`CodexAgent` 使用 `"exec", "-"`。
4. 任一断言失败 → exit 1，输出文件名与原因。

接入：pre-commit 新增 `code-agent-wiring`；CI `roadmap-coverage` job 增加一步。

## 4. 失败与回退矩阵

| 场景 | Stage 10 | Stage 13 |
|---|---|---|
| provider=llm | 原链路 | 原链路 |
| 二进制缺失 | 告警 + 原链路 | 告警 + 原链路 |
| CLI 超时 | 告警 + 原链路 | 告警 + LLM 改进 |
| CLI 空文件 | 告警 + 原链路 | 告警 + LLM 改进 |
| CLI 部分文件 | 使用产出，进入既有校验/修复 | 与 `best_files` 合并后校验 |
| 修复失败 | 既有 LLM 修复 | 既有 LLM 修复 |

## 5. 测试策略（TDD）

1. `test_config_code_agent_single_definition`：两个模块的 `CodeAgentConfig` 是同一对象。
2. `test_factory_error_points_to_cli_agent_path`：缺二进制时报错含 `experiment.cli_agent.binary_path`。
3. `test_stage10_helper_skips_llm_provider`：provider=llm 时工厂不被调用。
4. `test_stage10_helper_returns_files_and_logs`：假代理成功 → 返回文件 + 日志含 provider。
5. `test_stage10_helper_falls_back_on_failure`：假代理抛异常 → 返回 None。
6. `test_stage13_refine_helper_uses_agent` / `test_stage13_refine_helper_fallback`：用假代理直接测 helper。
7. `test_codex_generate_uses_stdin`：捕获 `_run_subprocess(stdin_text=...)`。
8. `test_wiring_script_passes`：脚本 exit 0。

## 6. 影响面与回滚

- 代码：`config.py`、`pipeline/code_agent.py`、`experiment/code_agent.py`、`_code_generation.py`、`_execution.py`、`health.py`、`scripts/`、`tests/`。
- 默认行为：不变（provider=llm）。
- 产物：新增 `code_agent_log.json`（仅 CLI）与 `refinement_log.cli_agent`（仅 CLI）。
- 回滚：按提交 revert；CLI 为显式 opt-in。

## 7. 未决项

沿用 P-011 U-1..U-5；本批新增无。U-5 的边界在实现中通过“沿用现有 refine prompt”保持现状，待后续裁决。
