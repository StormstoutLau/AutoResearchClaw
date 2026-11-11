---
id: arc-g2-m4-wiring-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-IMPLEMENTATION]
upstream: arc-g2-m4-wiring-IMPLEMENTATION
---

# 调研：G2 M4 复审缺陷修复（P-063）

> **Feature**：P-063，M4 复审 D-1..D-3 的修复批。
> **Spec 步骤**：T1 完整管线（Layer-1：修改 `researchclaw/evidence/claim_policy.py`、`stage_hooks.py`，新增 13 个测试）。
> **结论先行**：三项缺陷都出在 **claim 产物的读写边界**，不是判定逻辑。修复策略统一为「边界 fail-closed + 写入原子化 + 结构校验前移」：D-1 对齐 R14-2 的目录优先级；D-2 坏行抛错、`tmp + os.replace`；D-3 在 `evaluate_claim` 入口做 C4 最小结构校验，使生产与审计两平面同时可见。

## 1. 缺陷来源

| # | 级 | 复审证据 | 根因 |
|---|---|---|---|
| D-1 | P1 | P-062 探针 P-A：`stage-09`/`_v1`/`_v2` 并存时 picked=`OLD-v2` | `load_claims` 用 `sorted(glob(...))[-1]`，字典序把版本目录排在活目录之后；而 [runner.py](../../researchclaw/pipeline/runner.py) 的 PIVOT 会把 stage-08..15 rename 为 `_v{attempt}` |
| D-2 | P1 | P-062 探针 P-C：falsified 行损坏后 gate `pass` | `load_claims` 对 `JSONDecodeError` 静默 `continue`；`_write_claims` 用 `write_text` 原地覆盖 |
| D-3 | P2 | P-062 探针 P-B1/P-B2/P-I：非法 status / 单字段 claim 双平面一致放行 | gate 只在 M0 fixture 测试里跑 C4 schema，运行时无结构校验 |

## 2. 一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `_read_prior_artifact` 的约定是**非版本目录优先、版本按号降序**（R14-2） | [`_helpers.py`](../../researchclaw/pipeline/_helpers.py) `_stage_sort_key` |
| F-2 | PIVOT 的 `_version_rollback_stages` 重命名 `stage-08..15`，stage-09 的活目录会重新生成 | [`runner.py`](../../researchclaw/pipeline/runner.py) `_version_rollback_stages` |
| F-3 | `claims.jsonl` 是 Stage 20/23 的唯一 claim 输入；`claim_gate.json` 是唯一生产决定输入 | [`stage_hooks.py`](../../researchclaw/evidence/stage_hooks.py) |
| F-4 | C4 必填 14 项；`claim_id` 模式 `^c-[0-9a-f]{8}$`；status 七值词表 | [`c4_claim_record.schema.json`](../../contracts/v1/c4_claim_record.schema.json) |
| F-5 | M3 sidecar 已确立 `os.replace` 原子落盘先例（同文件系统静默替换） | `researchclaw/evidence/sidecar.py` |
| F-6 | 续跑场景允许没有 Stage 20 生产决定（`skipped=no_production_gate`），因此**缺失文件不能一律视为损坏** | M4 DESIGN §5 |

## 3. 决策

| # | 决策 | 理由 | 备选与否决 |
|---|---|---|---|
| D-1a | `load_claims` 候选排序 = 非版本目录优先，其次版本号降序 | 与 R14-2 及 `_read_prior_artifact` 一致；PIVOT 后活目录代表最新一次尝试 | 继续用字典序 → 版本号 ≥10 时排序也会错 |
| D-2a | 已存在 claim 文件中的坏行 → 抛 `ClaimStreamError`，不跳过 | 跳过等于让被篡改/截断的 FALSIFIED claim 消失 | 计数后告警 → 仍然放行，违背 fail-closed |
| D-2b | `_write_claims`/`_write_json` 改 `mkstemp + os.replace`，失败清理临时文件 | 崩溃不会留下半截文件；gate JSON 同样受保护 | 仅 claims 原子化 → gate 截断仍会让 Stage 23 误判 `skipped` |
| D-2c | `_read_json` 改为「缺失 → 默认值；存在但损坏 → 抛错」 | 区分「续跑无文件」与「文件损坏」 | 全部抛错 → 破坏续跑 |
| D-3a | `evaluate_claim` 入口做最小 C4 校验（id 模式、14 必填键、status 词表），失败返回 `invalid_claim_record` | 生产/审计共用同一入口，两平面同时可见；不引入 jsonschema 运行时依赖 | 只在 gate 校验 → 审计平面仍然放行 |
| D-3b | `claim_gate.json` 的 blocked 条目增加 `problems`，decision 增加 `problems` | 让拒绝原因可审计，避免只看到 `invalid_claim_record` | 不记录原因 → 排障困难 |

## 4. 外锚

- JSON Schema 2020-12：C4 是结构校验的真值源；P-063 只做最小子集，完整校验仍在 M0 契约测试。
- R14-2 / `_read_prior_artifact`：目录优先级唯一约定。
- M3 `os.replace`：同仓原子落盘先例。
