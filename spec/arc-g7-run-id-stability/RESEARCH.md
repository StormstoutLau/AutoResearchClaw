---
id: arc-g7-run-id-stability-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-fixes-RESEARCH, arc-g7-field-run-decision-20261125]
upstream: arc-master-roadmap
---

# 调研：run_id 稳定性与 A7-1 现场适配（P-174）

> **范围**：修复 `run --output` 每次重启铸造新 `run_id` 导致 mandate/事件链/`verify_run` 三方不一致；记录 B 站现场部署与两阶段启动。
> **不在本批**：72h field run 本体（C-3，基线 run 运行中）。

## 1. 本仓现状（T1）

| 事实 | 证据 |
|---|---|
| `cmd_run` 每次用时间戳生成 `run_id`，`--output` 只决定目录 | [cli.py L243-L244](../../researchclaw/cli.py#L243-L244) |
| 仅当 `--resume/--from-stage` **且无** `--output` 时才回填 `run_id = run_dir.name` | [cli.py L250-L283](../../researchclaw/cli.py#L250-L283) |
| `ensure_run_mandate` 在 run 目录已有 mandate 且 id 不同时抛 `MandateError` | [mandate.py L112](../../researchclaw/runtime/mandate.py#L112) |
| `verify_run` 以 `run_dir.name` 为期望 `run_id`，事件中的 `run_id` 不一致即 `run_id_mismatch` | [verifier.py L189-L260](../../researchclaw/soak/verifier.py#L189-L260) |
| 现场：B 站 `halogen-qwen3.8-flash-next`、1M ctx、JSON schema；doctor PASS；Stage 1 冒烟 67.9s | `/v1/models`、`researchclaw doctor`（2026-11-25） |
| 现场：本地模型未抽出英文检索式（`model_queries_extracted=false`）；中文 topic 与英文候选无关键词重叠 → Stage 5 拒绝全部 | `stage-03/queries.json`、`stage-05/screen_meta.json` |

**关键约束**：
1. `run_id` 必须与 run 目录名一致，且跨重启稳定；否则 soak `--resume` 无法收敛。
2. 默认 `artifacts/<generated-id>` 行为不变；只有显式 `--output` 才取目录名。
3. 现场干预（seed queries / 英文 domains）必须记录，不得计作注入重启。

## 2. 外部证据

| # | 来源 | 关键结论 | 本批借用 |
|---|---|---|---|
| E1 | [AWS Builders' Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) | 重试必须携带稳定的幂等键；客户端重复请求不得产生新的逻辑实体 | `run_id` 是跨重启的幂等键，不能每次重试换新 |
| E2 | [Kubernetes — Object Names and IDs](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/) | 对象有稳定 Name（同一资源唯一）与 UID（跨历史区分）；版本不是身份的一部分 | 目录名 = Name；重启是同一对象的新执行，不是新对象 |

## 3. 综合分析

1. **run_id 是恢复语义的主键**（E1）：mandate、事件链、session、soak 收敛签名都以它对齐；换 id 等于换实体。[★★★★★]
2. **目录名是最小稳定身份**（E2）：显式 `--output` 已经是用户声明的身份；再生成时间戳 id 是双重身份。[★★★★☆]
3. **默认路径不能改**：`artifacts/<rc-ts-hash>` 的 id 仍可由 topic 生成，避免破坏既有习惯与测试。[★★★★☆]
4. **现场适配是检索质量问题，不是管线缺陷**：本地模型查询抽取失败 + 中文/英文关键词不重叠，用 seed/domains 一次性修正即可。[★★★★☆]

## 4. 未决项

- **U-1 72h field run**
  - 判据：`field_run.satisfied=true`（wall≥259200、restarts≥3）、`verify_run.ok/converged`
  - 触发条件：基线 run 完成并确认收敛签名后
  - 当前倾向：B 站 tmux 启动 `soak run --duration 72h --max-restarts 3 --inject-at-stages 3,7,11`
  - 证据等级：E3
