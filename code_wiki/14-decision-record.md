# 14 · §15 八项决策评审裁定（Decision Record）

> 评审对象：[13-remediation-engineering-spec.md](13-remediation-engineering-spec.md) §15
> 评审日期：2026-10-29
> 状态：**全部裁定完成（Accepted / Accepted with conditions）**；代码尚未实施
> 证据等级：**E1 = 本机复现**；**E2 = 代码/官方文档确认**；**E3 = 社区案例/推断**

---

## 0. 裁定摘要

| # | 决策 | 裁定 | 关键理由 | 置信度 |
|---|------|------|----------|--------|
| D1 | MCP 实现路线 | **官方 MCP Python SDK v2 高层 `MCPServer`**；不自研 JSON-RPC 循环 | SDK v2 已是稳定线（2.3.0），官方 `MCPServer` 覆盖 tools/stdio；自研协议维护成本高且易偏离规范 | 高 |
| D2 | `review_paper` 是否实现 | **实现 MVP**，复用 Stage 18 评审逻辑；无 LLM 配置时返回 `CONFIG_REQUIRED`，不返回假成功 | 社区已有多个论文评审 MCP 服务；仓库已有独立 reviewer 与评审 prompt | 高 |
| D3 | 默认实验模式 | **默认 `sandbox`**，启动时 warning；`simulated` 必须显式设置 | 示例配置/README 都是真实执行；`simulated` 默认会静默产出假数据 | 中高 |
| D4 | `simulated` 论文逃生门 | **保留 `allow_simulated_paper`，默认 False**；放行时必须水印 + warning | 调试需要 simulated；但合成数据必须显著标注，不能伪装成真实实验 | 高 |
| D5 | 成本价格来源 | **混合**：provider `usage.cost` 优先；否则配置单价表；不内置厂商价格表 | OpenAI 只返回 token；OpenRouter 返回 cost；内置价格表会快速过时 | 高 |
| D6 | `event_log` / `pitfall_detector` | **删除两者**；保留 `cost_tracker` | 无消费者、无测试、调用参数不完整；属于死代码，不是缺失功能 | 中高 |
| D7 | OpenClaw 真实适配器 | **本轮不实现**；Recording 桩 + 宿主注入；文档改为扩展点 | 当前没有稳定 endpoint/协议；MCP 适配器也是桩，贸然接线会制造假能力 | 高 |
| D8 | Python 上界 | **不设上界**；保留 `>=3.11`；CI 3.11–3.13 阻断，3.14 非阻断 | PyPA 明确建议谨慎设置 upper bound；上界会阻止用户安装 | 高 |

### 一句话结论

本轮只做**能验证、能维护、不会伪造能力**的修复：MCP 用官方 SDK、评审用现有 reviewer、默认真实执行、模拟数据必须标记、成本按可得数据计算、删除死代码、OpenClaw 延后、Python 不设上界。

---

## 1. 评审方法与证据等级

1. **内部代码核验**：调用点、现有实现、测试 fixture。
2. **官方文档/规范**：MCP SDK v2、PyPA、Pydantic、OpenAI/OpenRouter/LiteLLM、OpenClaw。
3. **社区案例**：真实 MCP 论文评审服务、feature flag 清理实践、合成数据披露指南。
4. **裁定原则**：
   - 优先官方/参考实现，减少自研协议；
   - 不为未使用的能力补模块（YAGNI）；
   - 不伪造成功（fake success 视为缺陷）；
   - 默认行为必须可解释、可关闭、可审计；
   - 破坏性变更必须给迁移路径。

---

## 2. D1 · MCP 实现路线

### 2.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 官方 `mcp` SDK v2 高层 `MCPServer` | 协议由 SDK 维护；装饰器注册工具；stdio 一行 `run()` | 需接受 v2 API/协议变化 |
| B | 官方 SDK 低层 `Server` | 完全控制协议消息 | 代码多；需手写 `tools/list`/`tools/call`/错误映射 |
| C | 独立 FastMCP 3 | 功能多；Tasks 扩展可选 | 额外框架；与官方 SDK 版本耦合 |
| D | 继续自研 JSON-RPC | 无新依赖 | 当前实现连循环都没有；协议兼容风险最高 |

### 2.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [MCP Python SDK v2 安装文档](https://py.sdk.modelcontextprotocol.io/get-started/installation/) | v2 是当前稳定线；`pip install "mcp[cli]"`；Python 3.11+ |
| [PyPI mcp 2.1.0](https://pypi.org/project/mcp/2.1.0/) | 2026-08-24 发布；已有 2.3.0 |
| [MCP SDK v2 What's New](https://py.sdk.modelcontextprotocol.io/whats-new/) | v2 面向 2026-07-28 协议；**移除旧 handshake/session**；提供高层 `MCPServer` 与低层 `Server` |
| [MCP SDK 错误处理](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/) | `ToolError` 给模型看，`MCPError` 给协议看；普通异常是 crash |
| [MCP issue #3659](https://github.com/modelcontextprotocol/python-sdk/issues/3659) / [PR #3697](https://github.com/modelcontextprotocol/python-sdk/pull/3697) | 未知工具应走 `-32602`，不是普通成功结果 |
| [FastMCP 3 更新](https://gofastmcp.com/updates) | FastMCP 3 稳定；Tasks 需要额外 `fastmcp[tasks]` |
| [FastMCP Tasks](https://gofastmcp.com/servers/tasks) | 后台任务依赖 2026-07-28 协议协商 |

### 2.3 裁定

**采纳方案 A：官方 `mcp` SDK v2 高层 `MCPServer`。**

- 依赖：`mcp>=2.1,<3`；CI 锁定 `mcp==2.3.*`；
- 使用 `from mcp.server import MCPServer` + `@mcp.tool()`；
- 传输：stdio（默认）；SSE/HTTP 明确标记未实现；
- 长任务：**先不启用 Tasks 扩展**，`run_pipeline` 立即返回 `run_id`，客户端轮询 `get_pipeline_status`；
- 不用独立 FastMCP 3，避免额外框架；若未来必须 Tasks，再评估 `fastmcp[tasks]` 或 SDK 原生支持；
- 不再维护自研 `MCPClient`/SSE transport；删除或标记 internal。

**条件**：

- SDK v2 的协议不再有旧 handshake；测试不要断言旧 `initialize` 流程，改用 SDK client 的 `list_tools`/`call_tool`；
- 所有工具错误必须按 SDK 语义返回 `ToolError`/`isError`，未知工具走 `-32602`；
- 版本锁定到 2.3.x，升级需跑 MCP 全量测试。

### 2.4 影响与测试

- 更新 13 §1.3：`mcp = ["mcp>=2.1,<3"]`；
- 更新 13 §5.1/§11.4：MCP-01 改为「SDK client 连接 + `list_tools`」；
- 保留 MCP-02~MCP-12；
- 删除 `researchclaw/mcp/client.py` 的 stub 路径，或改为 SDK client 适配。

### 2.5 重新评估条件

- SDK v2 出现破坏性变更；
- 必须支持 Tasks 扩展且 SDK 不支持；
- 需要 SSE/HTTP 多租户。

---

## 3. D2 · `review_paper` 是否实现

### 3.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 实现 MVP，复用 Stage 18 | 真实能力；与论文流水线一致 | 需要 LLM 配置；有 token 成本 |
| B | 标记 `NOT_IMPLEMENTED` 并从工具列表移除 | 不伪造 | 用户看到 6 个工具但只有 5 个可用 |
| C | 保留 stub 返回固定评审 | 表面可用 | **假成功，必须禁止** |

### 3.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [Q1-Reviewer-MCP](https://lobehub.com/mcp/zaeyasa-q1-reviewer-mcp) | 真实 MCP 审稿服务：读取稿件、按 red-flag matrix 输出 decision letter |
| [openreview-mcp](https://www.opencodice.org/papers/oc-tr-2026-007-openreview-mcp.pdf) | 学术评审数据的 MCP 服务已有公开实现 |
| [paper-distill-mcp](https://pypi.org/project/paper-distill-mcp/) | 双 AI 盲审 + 主审汇总的 MCP 工具 |
| [MCP SDK 错误处理](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/) | 失败应显式报错，不能返回假结果 |
| 本仓库 `_review_publish.py:164-261`、`build_reviewer_llm` | Stage 18 已有独立 reviewer、评审 prompt、provenance |
| 本仓库 `prompts/ml.py:1095-1098` | 已有 `peer_review` prompt（≥3  reviewer perspectives） |

### 3.3 裁定

**采纳方案 A：实现 MVP，复用 Stage 18 评审核心。**

接口：

```python
@dataclass(frozen=True)
class ReviewResult:
    review_markdown: str
    model: str
    independent: bool
    prompt_tokens: int
    completion_tokens: int

def review_paper_text(
    config: RCConfig,
    draft: str,
    *,
    experiment_evidence: str = "",
    reviewer_llm: LLMClient | None = None,
    max_tokens: int = 4096,
) -> ReviewResult: ...
```

MCP 工具语义：

- 输入：`paper_path` 或 `run_id`（二选一）；`format` 默认 markdown；
- `paper_path` 必须位于 `artifacts/` 下；
- `run_id` 按 `get_paper` 的查找顺序解析；
- 输出：`{success:true, review_markdown, model, independent, tokens}`；
- 无 LLM 配置/无 API key → `CONFIG_REQUIRED`，**不返回固定评审**；
- 评审长度限制：输入 ≤ 200,000 字符；`max_tokens` 可配；
- 评审调用放线程池，避免阻塞 MCP 事件循环。

**条件**：

- 把 Stage 18 的评审核心抽到共享函数（`pipeline/review_service.py`），Stage 18 改为调用它；行为保持：
  - 独立 reviewer 优先；
  - 无 reviewer 时回退 generator；
  - 记录 provenance；
- 若抽取风险大，MCP MVP 可先复用 private helper，但必须加测试锁定行为。

### 3.4 测试

| ID | 期望 |
|----|------|
| MCP-09a | fake LLM → 返回 review_markdown，含 provenance |
| MCP-09b | 无 LLM 配置 → `CONFIG_REQUIRED`，非假成功 |
| MCP-09c | `paper_path` 非法/越界 → `INVALID_PATH` |
| MCP-09d | `run_id` → 解析到 `stage-22/paper_final.md` |
| MCP-09e | 超长论文 → 截断或 `INVALID_ARGUMENT`，不 OOM |

### 3.5 重新评估条件

- 评审成本过高 → 增加 `review_max_tokens`/异步任务；
- 需要多评审 persona → 复用 Debate 面板。

---

## 4. D3 · 默认实验模式

### 4.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 默认 `sandbox` + warning | 与示例/README 一致；真实执行 | 本地执行生成代码有风险 |
| B | 默认 `simulated` | 安全/便宜 | **静默假数据**，最危险 |
| C | 必须显式配置 `experiment.mode` | 最明确 | 破坏现有省略配置的用法 |
| D | 默认 `docker` | 隔离最好 | 无 Docker 时不可用 |

### 4.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [Pydantic Settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/) | 配置应在加载时验证；缺失/非法值立即 `ValidationError` |
| 本仓库 `config.researchclaw.example.yaml:94-120` | 示例模式是 `sandbox`/`docker`，不是 simulated |
| 本仓库 README Quick Start | 面向真实研究运行，不是 dry-run |
| 本仓库 `ExperimentConfig.mode` 默认 `"simulated"` | 与示例/README 矛盾 |

### 4.3 裁定

**采纳方案 A：默认 `sandbox`，但在配置缺失时 warning。**

- `ExperimentConfig.mode: str = "sandbox"`；
- `RCConfig.from_dict()` 若原始 dict 没有 `experiment.mode`：
  - 使用 `sandbox`；
  - `logger.warning("experiment.mode not set; defaulting to sandbox — set explicitly for reproducibility")`；
  - `ValidationResult.warnings` 增加一条；
- `simulated` 只能显式设置；
- Stage 12 `simulated` 分支写 `pipeline_summary.data_origin="simulated"`；
- `sandbox` 是本地 subprocess，文档必须提示：不可信代码请用 `docker`。

**拒绝**：

- 保持 `simulated` 默认：会静默产出假数据；
- 强制必填：对现有配置破坏性过大，且示例已提供 `sandbox`。

### 4.4 测试

| ID | 期望 |
|----|------|
| SIM-01a | 空配置 → mode=`sandbox` + warning |
| SIM-01b | 显式 `simulated` → 保留，不 warning |
| SIM-01c | 非法 mode → `ValidationError` |
| SIM-02 | simulated run → `data_origin=simulated` |

### 4.5 重新评估条件

- 安全评审要求默认 Docker；
- 大量用户无 GPU/本地环境，需要 simulated 快速试用（可提供 `--dry-run` 显式开关）。

---

## 5. D4 · `simulated` 论文逃生门

### 5.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 硬阻断：simulated 不能过 Stage 20 | 最安全 | 调试/演示不友好 |
| B | 默认阻断 + `allow_simulated_paper` 显式放行 + 水印 | 兼顾调试与诚信 | 需要实现水印/审计 |
| C | 无标记放行 | 简单 | 伪造风险，拒绝 |

### 5.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [ALSPAC 合成数据指南](https://pmc.ncbi.nlm.nih.gov/articles/PMC11809151/) | 合成数据必须附 disclaimer：「不是真实数据，不可用于后续研究」 |
| [JPE Data Policy](https://www.journals.uchicago.edu/journals/jpe/datapolicy) | 复现包可包含 synthetic/simulated 数据，但必须明确标注用途 |
| [Nature/Science 合成数据声明（社区总结）](https://theneuralbase.com/ai-for-research/learn/beginner/ai-generated-fake-data-concerns/) | 期刊要求在 methods/摘要显著标注 synthetic data |
| 本仓库 anti-fabrication 设计 | VerifiedRegistry + Stage 20 硬门 + Stage 23 引用验证 |

### 5.3 裁定

**采纳方案 B：默认阻断 + 显式逃生门 + 强制水印。**

配置：

```python
@dataclass(frozen=True)
class ResearchConfig:
    # ...
    allow_simulated_paper: bool = False
```

行为：

- `allow_simulated_paper=False`（默认）：
  - Stage 20 在 `data_origin == "simulated"` 时返回 `BLOCKED_APPROVAL`/`FAILED`，错误码 `E20_SIMULATED_DATA`；
  - 不进入 Stage 21–23；
- `allow_simulated_paper=True`：
  - Stage 20 放行，但写 `quality_warning.txt` 与 `pipeline_summary.data_origin="simulated"`；
  - Stage 22 在 Markdown 首行加：

```markdown
> **SIMULATED DATA — NOT FOR SUBMISSION**
```

  - LaTeX 增加 `\thanks{This manuscript uses simulated data and is not for submission.}` 或 `\usepackage{draftwatermark}`；
  - `deliverables/sanitization_report.json` 记录 `data_origin` 与 `allow_simulated_paper`。

**拒绝**：

- 硬阻断：会让框架无法演示/调试；
- 无标记放行：违反项目反伪造原则。

### 5.4 测试

| ID | 期望 |
|----|------|
| SIM-03 | simulated + default → Stage 20 阻断 |
| SIM-04 | simulated + allow=True → 放行 + 水印 |
| SIM-04b | LaTeX 含 simulated 声明 |
| SIM-04c | deliverables 不含未标记 simulated 论文 |

---

## 6. D5 · 成本价格来源

### 6.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 只依赖 provider `usage.cost` | 精确、零维护 | 只有部分 provider 返回；OpenAI 不返回 |
| B | 内置厂商价格表 | 开箱即用 | 价格过时快；维护成本高 |
| C | provider cost + 配置单价 + 无价格时 warning | 平衡 | 用户需配置 |
| D | 只统计 token，不做美元 | 简单 | README 宣传的 Cost Guardrails 失效 |

### 6.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [OpenAI API 用量/费用说明](https://help.openai.com/zh-hans-cn/articles/10478918-reviewing-api-usage-and-costs) | API 响应提供 token 用量；费用在用量页面查看，不是每响应 cost |
| [OpenRouter Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting) | `usage.cost` 直接返回本次请求费用 |
| [LiteLLM Token Usage & Cost](https://docs.litellm.ai/docs/completion/token_usage) | `completion_cost` 用 token + 单价计算成本 |
| 本仓库 `CostGuard` | 已按 `cost_log.jsonl` 的 `cost_usd` 读取 |

### 6.3 裁定

**采纳方案 C：provider cost 优先，配置单价兜底，不内置价格表。**

- `CostTracker.record()`：
  1. `usage.cost` 数字 → 直接用，`source=provider_usage`；
  2. 否则 `config.llm.input_cost_per_1m` / `output_cost_per_1m`（新增，默认 0）→ 计算，`source=pricing_table`；
  3. 都缺失 → `cost_usd=0`，`source=unknown`，每个 model 一次性 warning；
- `CostStatus` 增加 `tracking_complete: bool`；存在 unknown model 时为 False；
- `CostGuard` 在 `tracking_complete=False` 时仍显示 token 与估算成本，但明确 warning「预算可能不准确」；
- 不内置任何厂商价格；文档给出配置示例。

**拒绝**：

- 只依赖 provider cost（OpenAI 不返回）；
- 内置价格表（维护负担 + 过时风险）；
- 只统计 token 不实现美元（与 README 承诺不符）。

### 6.4 测试

| ID | 期望 |
|----|------|
| COST-03a | provider cost → source=provider_usage |
| COST-03b | 配置单价 → source=pricing_table，金额正确 |
| COST-03c | 无价格 → cost=0、warning、tracking_complete=False |
| COST-05 | CostGuard 读取同一日志，阈值正确 |

---

## 7. D6 · `event_log` / `pitfall_detector`

### 7.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 删除两者 | 减少死代码；无维护成本 | 放弃潜在审计/静态检查 |
| B | 实现 event_log | 可审计 | 无 UI 消费者；重复 Dashboard 事件 |
| C | 实现 pitfall_detector | 可能提前发现坏实验 | 当前只传 code，results/config 为空，信号弱 |
| D | 两者都实现 | 完整 | 范围膨胀，偏离本轮修复目标 |

### 7.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [PostHog Stale Feature Flags](https://posthog.com/docs/feature-flags/cleaning-up-stale-flags) | 清理顺序：先移除代码引用，再禁用 flag；死分支应删除 |
| [Unleash + Copilot 清理](https://www.getunleash.io/blog/automating-feature-flag-cleanup-github-copilot) | 自动化清理 stale flag 的流程：只保留实际使用的路径 |
| [OpenTelemetry Python Logs](https://opentelemetry.io/blog/2023/logs-collection/) | 若未来做事件日志，应按结构化 JSON/OTel 字段设计，而不是临时 JSONL |
| 本仓库 | `event_log`/`pitfall_detector` 无测试、无文档、调用参数不完整；Dashboard 已有 WS 事件 |

### 7.3 裁定

**采纳方案 A：删除 `event_log` 与 `pitfall_detector` 的 hook 和缺失模块引用；保留 `cost_tracker`。**

具体：

- 删除 `runner.py` 中 `event_log` 初始化/append 代码块（约 461–470、498–505、539–549）；
- 删除 `pitfall_detector` 代码块（约 581–599）；
- 不创建 `researchclaw/pipeline/event_log.py`、`pitfall_detector.py`；
- 删除/更新任何引用它们的文档/测试；
- `cost_tracker` 按 D5 实现，因为 README 明确宣传 Cost Guardrails。

**未来条件**：

- 若需要审计，新增独立 ADR，采用 JSONL + OpenTelemetry 字段（`timestamp`、`severity`、`run_id`、`stage`、`event`），并接入日志系统；
- 若需要 pitfall 检测，接入 Stage 14 诊断/Stage 20 硬门，而不是在 runner 里做空参调用。

---

## 8. D7 · OpenClaw 真实适配器

### 8.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | 本轮不实现；Recording + 宿主注入 | 诚实、低风险 | OpenClaw 集成仍需手工 |
| B | 实现真实 HTTP/CLI 适配器 | 自动集成 | 无稳定 endpoint；易假成功 |
| C | 保留 MCP stub 适配器 | 表面可用 | 返回假结果，必须禁止 |

### 8.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [OpenClaw Docs](https://docs.openclaw.ai/) | OpenClaw 是 gateway/plugin 架构，能力通过插件/通道提供 |
| [OpenClaw computer-use plan](https://docs.openclaw.ai/plan/computer-use) | 能力由 app-owned worker + provider 适配层提供，不是稳定公共 API |
| [OpenClaw adapter npm 示例](https://www.npmjs.com/package/@runtypelabs/openclaw-adapter) | 第三方适配器以插件形式观察 hooks，说明接口仍在生态层 |
| 本仓库 `adapters.py` | 默认 Recording；`from_config` 只返回 MCP stub；无 endpoint 配置 |

### 8.3 裁定

**采纳方案 A：本轮不实现真实 OpenClaw 适配器。**

- `AdapterBundle` 默认 Recording；
- CLI/Server 不强制调用 `from_config`（或调用后仍返回 Recording + warning）；
- 删除 `MCPMessageAdapter`/`MCPWebFetchAdapter` 的假结果，改为显式 `NotImplementedError` 或移除；
- 文档改为：「OpenClaw 为宿主注入扩展点；默认只记录，不自动消费能力」；
- 等 MCP server 稳定后，可通过 MCP client 实现 message/web_fetch 的真实适配（作为后续 ADR）。

**拒绝**：

- 保留假 MCP adapter；
- 在没有稳定 OpenClaw endpoint 的情况下实现 HTTP 适配（会制造不可维护的耦合）。

### 8.4 测试

| ID | 期望 |
|----|------|
| ADP-01 | 默认 bundle 全是 Recording |
| ADP-02 | `from_config` 不返回假 MCP 成功；无 endpoint 时 warning |
| ADP-03 | adapter 异常不中断流水线 |

---

## 9. D8 · Python 上界

### 9.1 选项

| 方案 | 内容 | 优点 | 缺点 |
|------|------|------|------|
| A | `requires-python = ">=3.11"`，不设上界 | 用户可在新 Python 安装；符合 PyPA 建议 | 新 Python 可能依赖不兼容 |
| B | `>=3.11,<3.14` | 控制兼容范围 | 阻止 3.14 用户；上界常被证明过严 |
| C | CI 只测 3.11，不声明 | 简单 | 其他版本无保证 |

### 9.2 外部证据锚点

| 来源 | 关键事实 |
|------|----------|
| [PyPA Writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) | 「Think twice before applying an upper bound」 |
| [PyPA Dropping older Python versions](https://packaging.python.org/en/latest/guides/dropping-older-python-versions/) | `requires-python` 用于声明兼容范围，不是测试矩阵 |
| [Requires-Python 核心元数据](https://packaging.python.org/en/latest/specifications/core-metadata/) | 安装工具据此选择版本 |

### 9.3 裁定

**采纳方案 A：不设上界。**

- `requires-python = ">=3.11"` 保持不变；
- CI：
  - 3.11 / 3.12 / 3.13：**阻断**；
  - 3.14：**非阻断（allow failure）**，直到依赖与测试通过；
- `classifiers` 只添加已测试版本；
- 若 3.14 因 numpy/scipy 不兼容，文档给出「推荐 3.11–3.13」，但不阻止安装。

**拒绝**：

- `<3.14` 上界：会阻止用户在新版本安装，且 PyPA 不推荐；
- 只测 3.11：无法发现 3.12/3.13 回归。

---

## 10. 决策间一致性检查

| 关系 | 结论 |
|------|------|
| D1 ↔ D2 | MCP SDK 确定后，`review_paper` 用 SDK tool + `asyncio.to_thread`；不手写协议 |
| D1 ↔ D7 | OpenClaw 延后；未来可通过 MCP client 接入，不另造协议 |
| D3 ↔ D4 | `sandbox` 默认 + `simulated` 显式 + Stage 20 阻断 + 水印，形成完整链路 |
| D5 ↔ D6 | 保留 `cost_tracker`，删除 event/pitfall；预算能力不再被死代码拖累 |
| D8 ↔ D1 | MCP SDK v2 要求 Python 3.11+，与项目 `>=3.11` 一致；CI 3.11–3.13 覆盖 |
| D2 ↔ 12 号验收 | MCP-09 改为「有内容或 `CONFIG_REQUIRED`」，不再接受假成功 |
| D1 ↔ 13 号契约 | `mcp>=1.0,<2.0` 改为 `mcp>=2.1,<3`；MCP-01 改用 SDK client |

---

## 11. 实施顺序（按裁定调整）

| PR | 内容 | 对应决策 | 状态 |
|----|------|----------|------|
| PR-1 | 打包修复 + `server`/`mcp`/`voice` extras + CI wheel smoke | D1 版本、D8 CI | 已完成（2026-10-29） |
| PR-2 | `RunState` + Dashboard/Projects + frontend 路径 | 13 §3/§8 | 已完成（2026-10-29） |
| PR-3 | MCP SDK v2 `MCPServer` + 6 工具 + `review_paper` MVP | D1、D2 | 已完成（2026-10-29） |
| PR-4 | 默认 `sandbox` + simulated 阻断/水印 + agent 模式分派 | D3、D4、G6/G7 | 已完成（2026-10-29） |
| PR-5 | `cost_tracker` + 删除 event/pitfall | D5、D6 | 已完成（2026-10-29） |
| PR-6 | OpenClaw 文档诚实化 + README/API + 测试契约 | D7、D8、G10/G11 | 已完成（2026-10-29） |

> CI 已在 GitHub Actions 实跑通过：run `40898741444`（commit `bce0082`），packaging / extras / tests(3.11–3.14) 共 6 个 job 全部 success。

---

## 12. 验收映射

| 决策 | 12 号验收 |
|------|-----------|
| D1 | Gate 2（MCP 全项）、PKG-04/05 |
| D2 | MCP-09a~e |
| D3 | SIM-01a~c、Gate 3 默认模式 |
| D4 | SIM-03/04/04b/04c、Gate 3 模拟阻断 |
| D5 | COST-03a~c、COST-05 |
| D6 | Gate 4 死代码清理、REG-01 |
| D7 | ADP-01~03 |
| D8 | Gate 5 CI 矩阵、PKG-01~06 |

---

## 13. 证据锚点清单

### MCP / Agent

- [MCP Python SDK v2 安装](https://py.sdk.modelcontextprotocol.io/get-started/installation/)
- [MCP Python SDK v2 What's New](https://py.sdk.modelcontextprotocol.io/whats-new/)
- [MCP Python SDK 错误处理](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/)
- [PyPI mcp 2.1.0](https://pypi.org/project/mcp/2.1.0/)
- [MCP issue #3659](https://github.com/modelcontextprotocol/python-sdk/issues/3659)
- [MCP PR #3697](https://github.com/modelcontextprotocol/python-sdk/pull/3697)
- [FastMCP 3 Updates](https://gofastmcp.com/updates)
- [FastMCP Tasks](https://gofastmcp.com/servers/tasks)

### 评审 / 合成数据

- [Q1-Reviewer-MCP](https://lobehub.com/mcp/zaeyasa-q1-reviewer-mcp)
- [openreview-mcp](https://www.opencodice.org/papers/oc-tr-2026-007-openreview-mcp.pdf)
- [paper-distill-mcp](https://pypi.org/project/paper-distill-mcp/)
- [ALSPAC 合成数据指南](https://pmc.ncbi.nlm.nih.gov/articles/PMC11809151/)
- [JPE Data Policy](https://www.journals.uchicago.edu/journals/jpe/datapolicy)
- [Nature/Science 合成数据标注（社区总结）](https://theneuralbase.com/ai-for-research/learn/beginner/ai-generated-fake-data-concerns/)

### 配置 / 成本 / 清理 / Python

- [Pydantic Settings](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/)
- [OpenAI API 用量与费用](https://help.openai.com/zh-hans-cn/articles/10478918-reviewing-api-usage-and-costs)
- [OpenRouter Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [LiteLLM Token Usage & Cost](https://docs.litellm.ai/docs/completion/token_usage)
- [PostHog Stale Feature Flags](https://posthog.com/docs/feature-flags/cleaning-up-stale-flags)
- [Unleash + Copilot 清理](https://www.getunleash.io/blog/automating-feature-flag-cleanup-github-copilot)
- [OpenTelemetry Python Logs](https://opentelemetry.io/blog/2023/logs-collection/)
- [PyPA Writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [PyPA Dropping older Python versions](https://packaging.python.org/en/latest/guides/dropping-older-python-versions/)

### OpenClaw

- [OpenClaw Docs](https://docs.openclaw.ai/)
- [OpenClaw computer-use plan](https://docs.openclaw.ai/plan/computer-use)
- [OpenClaw adapter npm 示例](https://www.npmjs.com/package/@runtypelabs/openclaw-adapter)

---

## 14. 结论

- 8 项决策全部裁定，无「悬而未决」项；
- 最大变更：MCP 改用官方 SDK v2（D1）、默认实验模式改为 `sandbox`（D3）、删除 event/pitfall 死代码（D6）；
- 最大保留：`simulated` 逃生门（D4）与 `review_paper` MVP（D2）；
- 最大延后：OpenClaw 真实适配器（D7）；
- 下一步：按 §11 的 PR-1 开始，先改 `pyproject.toml` + CI wheel smoke，随后按 D1 更新 13 号契约。
