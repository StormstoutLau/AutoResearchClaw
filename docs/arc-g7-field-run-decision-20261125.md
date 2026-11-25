---
id: arc-g7-field-run-decision-20261125
type: design
version: 1.0
status: decided
date: 2026-11-25
depends: [arc-g7-soak-RESEARCH, arc-g7-concurrency-dual-plane-DESIGN, arc-g7-soak-review-20261125]
upstream: arc-master-roadmap
---

# G7 A7-1 72h field run 方案（待确认）

> **用途**：在已建立 SSH 通道、工作站集群可跑本地模型的前提下，确定 A7-1 的**执行拓扑与模型接入方式**，并给出可复核的验收证据清单。
> **状态**：方案（proposed）；**未启动 72h 运行**，未把任何结果计入验收。
> **不在本文**：registry 损坏修复与 A7-4 正式回放验收的实现细节（见 P-173 四文档）。

## 1. 结论（推荐）

**推荐：裸 API（OpenAI-compatible）+ SSH 端口转发到本地模型 + `local_only=true`。**

> **已确认（2026-11-25）**：模型接入 = 裸 API；Stage 10/13 = 同一裸 API 模型；实验模式 = 小规模真实实验（`experiment.mode=sandbox`，固定小数据集，不跑 simulated）。

理由（按权重）：

1. **A7-1 测的是 researchclaw 自身的长跑/重启/收敛**，不是 agent 框架的能力。裸 API 把变量隔离到最小。
2. **现有守卫只覆盖 `LLMClient`**：`pre_call_budget_check`、`check_local_only`、P-172 的 `_inflight_guard` 都在 `LLMClient.chat` 路径；`ACPClient` 三者都没有（[acp_client.py](../../researchclaw/llm/acp_client.py) 全文无 budget/local_only/成本记录）。用 ACP 跑 72h 会绕过 G6 与 P-172 的预算/限流面，验收口径不一致。
3. **ACP 会引入第二层会话生命周期**：acpx 持久会话在 worker 重启后需 `sessions ensure`（[acp_client.py L208-L241](../../researchclaw/llm/acp_client.py#L208-L241)），重启失败会被误判为 researchclaw 不收敛。
4. **第三方 agent 内运行**把外层 agent 的限流/重试/上下文管理叠加进来，72h 失败无法归因，且外层 agent 可能自带超时上限。

**例外（混合）**：仅当本地模型代码能力不足、Stage 10/13 代码生成反复失败时，把 `experiment.cli_agent.provider` 设为 `claude_code`/`codex`（只影响 Stage 10/13），其余 stage 仍走裸 API。若选此项，需在报告中标注「混合模式」，A7-1 的收敛判定只看 researchclaw 的 checkpoint/事件链，不看代码质量。

## 2. 三选项对比

| 维度 | A. 裸 API（推荐） | B. ACP agent（`llm.provider=acp`） | C. 第三方 agent 内运行框架 |
|---|---|---|---|
| 覆盖 stage | 23/23 | 23/23（经 acpx 会话） | 23/23（经外层 agent） |
| G6 预算前置拒绝 | ✅ | ❌（ACPClient 无此逻辑） | ❌ |
| `local_only` 硬禁网 | ✅（仅 loopback） | ❌ | 由外层决定 |
| P-172 inflight 限流 | ✅ | ❌ | ❌ |
| 重启后上下文 | 无状态，天然重建 | 依赖 acpx 会话恢复 | 依赖外层 |
| 故障归因 | 清晰（模型/网络/管线） | 混淆（acpx/agent/管线） | 最难 |
| 依赖 | vLLM/SGLang + SSH 隧道 | acpx + agent CLI + 鉴权 | 外层 agent + 鉴权 |
| 适合 A7-1 | **是** | 否（口径不一致） | 否（变量过多） |

## 3. 执行拓扑

```
[工作站集群 GPU]
  vLLM/SGLang  ── 127.0.0.1:8000/v1（集群侧 loopback）
        ▲
        │ SSH 端口转发（-N -L 18000:127.0.0.1:8000）
        │
[本机/工作站]
  researchclaw supervisor ── worker: python -m researchclaw run --resume
        │                         │
        │                         └─ LLMClient → http://127.0.0.1:18000/v1
        └─ soak driver（72h、3 次注入、每 5s poll）
              run_dir/events*.jsonl、supervisor.jsonl、soak_session.jsonl
```

- **必须走 loopback**：`local_only=true` 只允许 `localhost/127.0.0.1/::1`（[model_policy.py L168-L176](../../researchclaw/llm/model_policy.py#L168-L176)）；直连集群 LAN IP 会被拒。
- 端口转发需长连：`ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 18000:127.0.0.1:8000 user@cluster`；断线由 `autossh` 或 systemd 拉起。
- 模型服务需支持 `chat/completions`、JSON mode（`response_format`）；不支持时 Stage 5/7/15 的 JSON 解析会重试，可能拖长 72h。

## 4. 72h 运行配置（soak profile）

```yaml
project:
  name: g7-field
  mode: full-auto
research:
  topic: "<固定主题，基线 run 与 field run 必须完全相同>"
  graceful_degradation: true
llm:
  provider: openai-compatible
  base_url: "http://127.0.0.1:18000/v1"
  api_key_env: "LOCAL_MODEL_KEY"   # 本地服务可任意非空值
  primary_model: "<集群模型名>"
  fallback_models: []
  timeout_sec: 600
experiment:
  mode: sandbox          # 小规模真实实验：真实子进程 + 固定小数据集
  time_budget_sec: 600
  cli_agent:
    provider: llm        # 已确认：Stage 10/13 与其余 stage 同一裸 API 模型
model_policy:
  enabled: true
  local_only: true
  run_budget_usd: 0.0    # 本地模型；预算闸门关闭，改用 wall/token 上限
multi_project:
  enabled: true
  max_concurrent_attempts: 2
  hitl_priority_slots: 1
  max_inflight_llm_calls: 2
  queue_timeout_sec: 300
```

> `run_budget_usd=0` 表示不按美元拒绝；A7-1 的资源上限由 `soak --duration 72h` 与 `experiment.time_budget_sec` 承担。

## 5. 执行步骤

1. **预检（≤15 分钟）**
   - `curl http://127.0.0.1:18000/v1/models` 能列出目标模型；
   - `python -m researchclaw validate --config <soak.yaml>`；
   - `python -m researchclaw doctor`；
   - 单 stage 冒烟：`python -m researchclaw run --config <soak.yaml> --to-stage topic_init`（确认 JSON/中文/长上下文不崩）。
2. **基线 run（无注入）**
   - `python -m researchclaw supervisor --output artifacts/g7-baseline --config <soak.yaml>`；
   - 记录 `soak verify --output artifacts/g7-baseline` 的 `convergence_signature`。
3. **72h field run（3 次硬杀）**
   - `python -m researchclaw soak run --output artifacts/g7-field --config <soak.yaml> --duration 72h --max-restarts 3 --inject-at-stages 3,7,11 --reference-run artifacts/g7-baseline`；
   - 断线恢复：soak driver 只在本机；SSH 隧道断线不杀 driver，但模型调用会失败 → 重试/75；需 autossh。
4. **验收读数**
   - `soak_report.json`：`field_run.satisfied == true`（`wall_segments >= 259200`、`restarts >= 3`）；
   - `soak verify`：`ok=true`、`converged=true`、无 `chain:*`/`seq_gaps`/`run_id_mismatch`；
   - `researchclaw ops --runs-root artifacts`：`restarts>=3`、`recovery_seconds` 有读数；
   - `python -m researchclaw audit --run-dir artifacts/g7-field`：exit 0。

## 6. Abort / Kill criteria

- 模型服务 5xx 连续 10 分钟或隧道不可用 → 暂停 driver，修复后 `--resume`，不重置 run 目录。
- `supervisor_exhausted` 且根因是模型/网络 → 允许提高 `--max-restarts` 重跑；根因是管线缺陷 → 停，转修复批。
- 磁盘 < 10GB 或事件日志接近 `max_run_bytes`（256MB）→ 先 `sweep_runs` 归档，再继续。
- 72h 到达但 `restarts < 3` → 判失败；不得用人为重启补数。

## 7. 待确认项

| ID | 待确认 | 建议 |
|---|---|---|
| C-1 | 集群模型名 / 上下文长度 / 是否支持 JSON mode | 提供 `/v1/models` 与一次 8k 上下文冒烟结果 |
| C-2 | 模型接入方式 | **已确认：A 裸 API**；B ACP 仅作对照，不计入 A7-1 |
| C-3 | Stage 10/13 代码生成 | **已确认：裸 API 同模型**；连续失败再评估 cli_agent，报告标注混合 |
| C-4 | `experiment.mode` | **已确认：`sandbox` 小规模真实实验**（600s 预算，固定小数据集）；不用 `simulated` |
| C-5 | 运行主机与磁盘 | 与模型服务同机或低延迟内网；预留 ≥20GB |
| C-6 | 费用/配额 | 本地模型；如需外部 API，先设 `run_budget_usd` 与 `max_inflight_llm_calls` |

## 8. 与 A7-4 / registry 修复的关系

- **A7-4**：P-160 已有轮转/压缩回放测试；P-173 补「正式验收」用例（强制小段滚动 → 按 `run_id+seq` 回放 → gzip 后复验 → 缺口必须判红），并用 field run 的真实 run 目录复跑 `soak verify`。
- **registry 损坏**：P-173 改为「写前备份 + 主损坏读备份 + 双损坏 fail-closed（`RegistryCorrupt`）」，supervisor 捕获后返回 CONFIG 且不 spawn；不再静默清空 registry（避免 fencing 回退与超容）。

## 9. 诚实边界

- 本文是**方案**，未执行 72h；A7-1 仍为待验收。
- 本地模型能力未知；若 JSON/长上下文不达标，需先换模型或降级 stage 预期，不得修改验收判据。
- 72h 期间的本机/集群可用性不由 researchclaw 保证；断线/重启属于现场条件，需在报告中记录。
