---
id: arc-stage10-blueprint-integrity-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-symbol-recheck, arc-stage10-blueprint-yaml-robust]
upstream: arc-master-roadmap
---

# 调研：蓝图落盘完整性（P-230）

> **档位**：S1 缺陷型（§2.3）。根因由运行 N 的产物与代码路径直接给出。

## 1. 问题

运行 N 的 Stage 10 报 `done (4130.5s, attempt 1)`，但产物中的蓝图无法被任何下游门禁读取：

```
artifacts/runs/g7-baseline/stage-10/architecture_spec.yaml#L156
signature: (config: Config, rng: np.random.Generator) -> dict
```

YAML 把 `(config:` 读成映射键，随后 `rng:` 触发 `mapping values are not allowed here`，整份文件解析失败。写盘的是**模型原文**，而模型在内存里的 dict 是解析成功的——同一份蓝图存在两个版本：内存可用、磁盘不可用。

后果链（全部来自现场读数）：

1. `load_blueprint` 返回 `None`，文件集合 / 指标 / 数据源三道证据门全部跳过；
2. `codegen_evidence.json` 写 `ok=true`，本次 DONE **未经证据门验证**；
3. P-229 的 `_ensure_symbol_contract` 同样构不出蓝图，静默空转；
4. `codegen_decision.json` 未生成——P-227/P-232 告警文案引用的文件在现场不存在。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 解析成功后没有把结构重新序列化落盘，写盘发生在解析之前 | [code_agent.py#L498](../../researchclaw/pipeline/code_agent.py#L498) |
| L-2 | `load_blueprint` 只读 YAML，无第二格式兜底 | [codegen_evidence.py#L85](../../researchclaw/pipeline/codegen_evidence.py#L85) |
| L-3 | 蓝图缺失时证据门只记 warning，仍可判 DONE | [codegen_evidence.py#L592](../../researchclaw/pipeline/codegen_evidence.py#L592) |
| L-4 | 解析失败后的修复重试不带解析器错误，同错重发 | [code_agent.py#L531](../../researchclaw/pipeline/code_agent.py#L531) |
| L-5 | 决策记录只有 fallback/reason，无法区分蓝图来自模型、规范化还是修复 | [code_agent.py#L600](../../researchclaw/pipeline/code_agent.py#L600) |
| L-6 | 阶段层在蓝图可解析时会用 raw spec 覆盖 canonical 文件 | [\_code_generation.py#L1460](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1460) |

（锚点为本批改动后的代码位置；L-1/L-4/L-5 描述的是改动前的行为，改动点见 IMPLEMENTATION。）

## 2.3 档位与最小来源

- **档位**：S1。
- **来源**：E1 ≥2 —— 运行 N 的 `stage-10/architecture_spec.yaml#L156` 与 `codegen_evidence.json` 现场读数；代码路径 L-1..L-6。
- **豁免**：根因在本机可复现（解析失败 → 门禁空转），不需外部检索即可定档。P-230 立项前的社区解法比对（canonical 重序列化、OutputFixingParser 的 `max_retries=1`、schema 校验失败即 fail-closed、错误回传 delta 重试）作为设计参照写进 DESIGN，不引用无法解析的 ID。

## 2.4 降级链

MCP 学术检索（S1 豁免，未调用）→ 运行 N 现场产物 → 仓内代码与既有测试 → P-202/P-232 的 YAML 结论。

## 3. 结论

蓝图必须以**解析后的结构**重新序列化后落盘，并提供 JSON 孪生兜底；出口前若仍无可用蓝图，必须 fail-closed，不得让证据门空转放行。

## 4. 来源

- 运行 N 现场：B 站 `~/arc-runs/g7-baseline/stage-10/`（`architecture_spec.yaml` L156、`codegen_evidence.json`、日志 `done (4130.5s)`）
- [P-232 调研](../arc-stage10-blueprint-yaml-robust/RESEARCH.md)（YAML 折行与一次修复重试）
- [codegen_evidence.py#L85](../../researchclaw/pipeline/codegen_evidence.py#L85)
