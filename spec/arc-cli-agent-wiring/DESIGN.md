---
id: arc-cli-agent-wiring-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-wiring-RESEARCH]
upstream: arc-cli-agent-wiring-RESEARCH
---

# 设计：CLI 代码代理的收口与接线

> 输入：[RESEARCH.md](RESEARCH.md) §3（问题链）、§4（路线选项）、§6（约束与未决项）。
> 本文件只给设计，不含实现；代码改动需另开实施批次。

## 1. 设计不变量

1. **默认后端不变**：未显式配置 `cli_agent.provider` 时，Stage 10/13 行为与今天完全一致（API-first，Q17）。
2. **单一真值源**：后端选择只由 `experiment.cli_agent` 决定；`experiment.code_agent` 只保留阶段开关。
3. **prompt 不进 argv**：任何 CLI 传输必须走 stdin / SDK / ACP；Windows 下不得依赖 `.CMD` 参数传递。
4. **失败可回退**：CLI 后端缺失、超时、非零退出时，自动回退 LLM 路径并记录降级原因。
5. **审计可追溯**：每次后端调用写入 `code_agent_log.json`（provider/transport/耗时/退出码/文件数/输出摘要）。
6. **阶段出口不变**：不新增/删除 Stage，不改变 Stage 10/13 的产物契约。

## 2. 决策表

| # | 决策 | 选择 | 被拒绝的替代方案 | 拒绝理由 | 代价 |
|---|---|---|---|---|---|
| D-1 | 配置收口 | `experiment.cli_agent` 为唯一后端配置；`experiment.code_agent` 只留阶段开关 | 新增 `agent_backend` 块 | 迁移成本高，且与现有示例/部署映射冲突 | 需兼容旧键并给弃用提示 |
| D-2 | 配置类去重 | 以 `config.py` 的 `CodeAgentConfig` 为规范定义；`pipeline/code_agent.py` 改为导入 | 保留两份同名 dataclass | 字段漂移不可见，鸭子类型掩盖错误 | 一次性 import 调整 |
| D-3 | 接线协议 | 复用 `CodeAgentProvider`（generate/refine/repair）+ `create_code_agent()` 工厂 | 直接在各阶段 `if provider == ...` 分支 | 分支散落，新增后端需改多处 | 工厂需感知 stage 上下文 |
| D-4 | 接线点 | Stage 10 生成、Stage 13 改进/修复共用工厂；Stage 10 顺序：显式 provider → Beast → 多阶段 LLM → 单发 | 只接 Stage 10 | Stage 13 仍会绕过配置，语义不一致 | 需在 `_execution.py` 增加工厂调用 |
| D-5 | 传输策略 | Claude Code：stdin 文本；Codex：`exec -` stdin；ACP：JSON-RPC；SDK 仅作后续候选 | prompt 作为 argv；把换行扁平化为空格 | argv 受 cmd.exe/8191 长度限制；扁平化丢失结构 | Codex 路径需同步改造 |
| D-6 | 默认与显式 | 默认 `llm`；`claude_code`/`codex` 必须显式配置且通过二进制探测 | 按 PATH 自动探测并切换 | 隐式行为不可审计，环境差异导致结果漂移 | 无 |
| D-7 | 未接线期策略 | 在 R-3 落地前，`provider != llm` 一律 fail-fast，提示“已声明未接线” | 静默忽略（现状） | 用户被误导，且测试无法发现 | 已写配置会立即报错（可接受） |
| D-8 | 接线治理 | 新增静态检查：配置暴露的每个 provider 必须有工厂分支 + 阶段消费者；缺失即 CI 失败 | 仅靠 code review | 本问题已证明 review 会漏 | 新增 1 个零依赖脚本 |
| D-9 | 回退粒度 | 单次调用级回退：CLI 失败 → 同阶段 LLM；不重跑整个 Stage | 整个 Stage 重跑 | 成本高、可能重复副作用 | 需在阶段内捕获异常 |

## 3. 接口与数据流

### 3.1 后端协议（已存在，不改签名）

```python
class CodeAgentProvider(Protocol):
    @property
    def name(self) -> str: ...
    def generate(self, *, exp_plan, topic, metric_key, pkg_hint,
                 compute_budget, extra_guidance, workdir,
                 timeout_sec=600) -> CodeAgentResult: ...
    def refine(self, *, current_files, run_summaries, metric_key,
               metric_direction, topic, extra_hints, workdir,
               timeout_sec=600) -> CodeAgentResult: ...
    def repair(self, *, files, issues, workdir,
               timeout_sec=300) -> CodeAgentResult: ...
```

### 3.2 工厂（语义修正）

```python
def create_code_agent(config: RCConfig, llm=None, prompts=None) -> CodeAgentProvider:
    """按 config.experiment.cli_agent.provider 返回后端；llm 为默认。"""
```

- `provider == "llm"`：返回 `LlmCodeAgent`（现有 LLM 路径）。
- `provider in {"claude_code", "codex"}`：探测二进制；缺失时抛 `RuntimeError`，文案指向 `experiment.cli_agent.binary_path`。
- 未知 provider：`ValueError`（与 `validate_config` 双重把守）。

### 3.3 配置（唯一真值源）

```yaml
experiment:
  cli_agent:
    provider: "llm"            # llm | claude_code | codex
    binary_path: ""            # 空 = PATH 探测
    model: ""                  # 空 = 后端默认
    max_budget_usd: 5.0        # 单次 CLI 调用上限，不是 run 预算
    timeout_sec: 600
    env_extra: {}
  code_agent:
    enabled: true              # 只保留阶段开关，不承载 provider
```

### 3.4 数据流

```
Stage 10 (_execute_code_generation)
  └─ if cli_agent.provider != "llm":
        agent = create_code_agent(config, llm, prompts)
        result = agent.generate(...)          # stdin / ACP / HTTP
        if not result.ok: fallback -> pipeline.CodeAgent -> legacy
  └─ 写 stage-10/code_agent_log.json

Stage 13 (_execute_iterative_refine)
  └─ 与 Stage 10 同一工厂；refine/repair 使用同一 provider
  └─ 失败回退 _chat_with_prompt（现有路径）
```

## 4. 失败与回退矩阵

| 场景 | 行为 | 日志 |
|---|---|---|
| 配置了 `claude_code` 但二进制缺失 | `validate_config`/`doctor` fail-fast | 指出缺失命令与配置键 |
| CLI 超时 | 杀进程树，标记 `timed_out`，回退 LLM | 记录耗时与 stderr 尾部 |
| CLI 非零退出且无文件 | 回退 LLM | 记录退出码 |
| CLI 产出部分文件 | 先校验；缺 `main.py` 则回退；否则进入 repair | 记录文件清单 |
| stdin 写入失败 | 视为后端失败，回退 | 记录异常 |
| 后端返回空 content | 按失败处理（现有 `reasoning_content` 回退仍保留） | 记录响应长度 |

## 5. 影响面与兼容

- **代码落点（预计）**：
  - `researchclaw/config.py`：校验与去重（D-1/D-2/D-7）。
  - `researchclaw/experiment/code_agent.py`：工厂文案、Codex stdin（D-3/D-5）。
  - `researchclaw/pipeline/stage_impls/_code_generation.py`：Stage 10 分支（D-4）。
  - `researchclaw/pipeline/stage_impls/_execution.py`：Stage 13 分支（D-4）。
  - `scripts/code_agent_wiring_check.py`：适应度函数（D-8）。
  - `tests/`：契约与集成测试。
- **配置兼容**：`experiment.code_agent.provider` 从未被解析，无需迁移；只需在文档中删除该写法。
- **阶段契约**：Stage 10/13 的产物名与指标格式不变。
- **回滚**：按提交粒度 revert；CLI 路径为 opt-in，默认路径不受影响。

## 6. 测试策略（供 CHECKLIST 使用）

1. **契约测试（红→绿）**：用 Python 假 CLI 读取 stdin、写 `main.py`，断言 `ClaudeCodeAgent.generate` 的 stdin 传递与文件收集。
2. **接线测试**：monkeypatch `create_code_agent`，断言 Stage 10 在 `provider=claude_code` 时调用它；`provider=llm` 时不调用。
3. **回退测试**：假 CLI 超时/非零退出，断言 Stage 10 回退到 `pipeline.CodeAgent` 并记录降级原因。
4. **适应度函数**：`scripts/code_agent_wiring_check.py` 静态断言 provider 集合 = 工厂分支 = 阶段消费点；CI fail-closed。
5. **Windows 专项**：多行/中文 prompt 经 `.CMD` 仍完整（stdin），超时后无残留进程。

## 7. 影响评估

| 维度 | 评估 |
|---|---|
| 用户 | 配置不再静默失效；未接线期会得到明确错误 |
| 维护 | 配置类去重、三路径收敛为“协议 + 适配器” |
| 审计 | 统一日志字段；CLI 原始输出仍为文本，需在 U-4 闭合前限制高审计 run 使用 |
| 成本 | 默认路径零变化；CLI 仅显式开启时产生外部调用 |
| 进度 | R-4 可独立先做；R-3 以 U-1 的 A/B 为开工门槛 |

## 8. 未决项

引用 RESEARCH §6.4 的 U-1..U-4，不重复定义。设计侧新增：

- **U-5 Stage 13 的 CLI 使用边界**
  - **判据**：明确 refine 是否允许改动实验设计（而非仅修 bug），以及预算上限。
  - **触发条件**：R-3 进入 Stage 13 接线时。
  - **当前倾向**：Stage 13 只允许修复与参数级改进，不允许重写实验设计。
  - **证据等级**：E1（无实测）。
