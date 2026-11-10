# Q3 Grandfather 策略独立复核（P-019 复核）

> **日期**：2026-11-10
> **复核对象**：[spec/arc-q3-grandfather-policy/](../spec/arc-q3-grandfather-policy/)（P-019，提交 `9728ec6`）
> **复核方法**：①在已提交基线上独立重跑机检；②锚点回源抽查（本轮独立检索，不复用 P-019 执行路径）；③对照 `dc_validator` / `step_enforce` 源码做设计可行性审查。
> **复核人声明**：本报告为独立会话产出；机检结果为本机对 `9728ec6` 的独立重跑；锚点引用来自本轮独立 WebSearch 结果。

---

## 1. 总体结论

P-019 的核心主张**基本成立**：当前基线为空、"B 基线+棘轮"方向正确、外部锚点总体真实可回源。但发现 **1 个实施前必须解决的设计缺口（F-1）**、**2 项需要修正/明确的表述（F-2、F-3）**、**2 项低风险澄清（F-4、F-5）**，以及 **3 项 P-019 未引用的补充佐证（S-1..S-3）**。

**裁决建议维持 B**；实施批（G0b 内）必须吸收 F-1..F-5 后方可开工。

---

## 2. 机检独立重跑（对 `9728ec6`）

| 检查 | P-019 主张 | 复核结果 |
|---|---|---|
| `pre-commit run --all-files` | exit 0，六钩子全绿 | ✅ 独立重跑 exit 0（六钩子全 Passed） |
| `dc_validator` 对全部 spec 文档 | 0 违规（pre-commit 语义） | ✅（含于全量钩子通过） |
| `spec/grandfather.yaml` | 不存在 | ✅ `Test-Path` = False |
| `step_enforce` finalize digest 绑定 | 已实现（`EVIDENCE_MIN_P=137`） | ✅ [step_enforce.py:52-59](../scripts/step_enforce.py#L52-L59) |
| grandfather 清单可为空 | 是（无存量违规） | ✅ 由前两项直接推出 |

**结论**：P-019 RESEARCH §2 的事实表（F-1..F-7）全部成立。

---

## 3. 锚点回源抽查

| 锚点 | P-019 标注 | 复核 | 结论 |
|---|---|---|---|
| X-1 Android Lint baseline | ✅ | 官方文档确认：baseline 记录现有问题集，后续只报新问题 | 成立 |
| X-2 PHPStan baseline | ✅ | 官方确认；且官方明示 baseline "不是万能工具"、严重错误不可忽略 | 成立（附官方警告，见 S-3） |
| X-3 ESLint bulk suppressions | ✅ | v9.24.0（2025-04）官方博客确认；**同文件同规则出现新违规时该文件全部重新上报** | 成立（细节见 S-1） |
| X-4 detekt baseline | ✅ | 官方迁移指南确认 `detektBaseline*` 任务族 | 成立 |
| X-5 SonarQube Clean as You Code | ✅ | 官方文档确认"新代码定义 + 质量门禁" | 成立 |
| X-6 K8s deprecation policy | ✅ | GA API 弃用后至少一年/按稳定性分级才移除 | 成立；但注意与"90 天"参数的差异（→ F-3） |
| X-7 Kruchten/Nord/Ozkaya 2012 | ✅元数据 | 仅元数据命中，未回原文 | **标注降级**：应记 T2/E2。P-019 将其作论证性引用（非 A 类事实断言）可接受，但标注需改 |
| X-8 增量静态分析（ACM CSUR 2025） | ✅摘要 | 检索命中，"from-scratch vs incremental"二分与摘要一致 | 成立（E2，摘要级） |
| X-9 pylint-grandfather | ✅ | PyPI 页面确认："grandfather old code, while still enforcing that all **new or changed** code is compliant" | 成立（细节见 S-2） |

---

## 4. 发现

### F-1（实施前必须解决）：与 `dc_validator` 自身不变式冲突

[dc_validator.py:9-10](../scripts/dc_validator.py#L9-L10) 声明不变式 **I-3 零新规则 / I-4 单一真值源**，其权威源为 `spec/doc-contract/PLAN.md §1` + `ADR-0007` + `ASSERTION_EVIDENCE_FRAMEWORK R7`。P-019 DESIGN §5 要求 `dc_validator` 读取 `spec/grandfather.yaml` 并跳过 DC1-DC3 错误，这同时：

1. 引入**第二个真值源**（豁免清单）；
2. **改变校验行为**（新增豁免规则）。

直接实施会破坏 I-3/I-4。**实施批必须二选一并落档**：

- (a) 先修订权威源（新增 ADR 或扩 PLAN §1）把 grandfather 语义纳入契约，再改 `dc_validator`；
- (b) 将豁免实现为**独立策略层**（如 `--grandfather` 显式参数或包装脚本），`dc_validator` 本体不变式不动。

P-019 DESIGN 未处理此冲突——这是本复核最重要的发现。

### F-2（可行性已验证，但机制需写明）：按 DC 豁免在数据模型上可行

复核抽查确认 [dc_validator.py:52-58](../scripts/dc_validator.py#L52-L58) 的 `CheckResult.check_id` 按 DC 打标（`"dc1" | "dc2" | "dc3" | "dc4" | "r7" | dc5`）。因此"只豁免 DC1/DC2/DC3"**可实现**：按 `check_id ∈ {dc1, dc2, dc3}` 过滤即可，`dc4/dc5/r7` 照常执行。

但 P-019 DESIGN §5 未写明该机制。实施批 DESIGN 应补充：豁免 = 过滤 `CheckResult.check_id`；并显式声明 `dc4`（id 全仓唯一）、`dc5`（版本引用）、`r7` **不参与豁免**——注意 dc4/dc5 是全仓扫描语义（I-6），按文件豁免本身就不适用，这一点 P-019 未意识到但结论碰巧正确，应写明理由。

### F-3（参数依据）：「90 天」无外部锚点

唯一时间类锚点 X-6（K8s）是 ≥1 年。90 天是合理的内部政策参数，但 P-019 未标注其证据等级。应改为：**内部政策参数（E3，可调）**，与 U-1（豁免数量趋势复审）绑定，不得表述为外部推导结论。

### F-4（边界澄清）：DC 范围外文档与 grandfather 无交互

`docs/*.md`（除 PROGRESS/CONSOLE）本就不在 dc-validator 作用域，T3 轻批、调研报告无需 grandfather。边界成立，但建议实施批 CHECKLIST 增加一条负向用例固化"scope 外文件不消耗豁免条目"。

### F-5（schema 细节）：续期基准未定义

DESIGN §3 说"单条 `expires` 不得晚于 `cutoff + 2*expires_days`"，但未定义续期时 `expires` 如何计算。建议明确：**续期 = 以原 `expires` 为基准 +90 天，总寿命 ≤ `cutoff + 180 天`**；续期行须保留原 `expires` 历史（append-only），避免静默改日期。

---

## 5. 补充佐证（P-019 未引用，均强化 B 方案）

- **S-1**：ESLint bulk suppressions 官方语义包含"同文件该规则出现新违规时，**该文件全部违规重新上报**"。这为"语义触碰 → grandfathered 文件全部错误重新可见 → 自然强制迁移"提供了直接外部先例，比 P-019 的抽象"touch = migrate"表述更强。
- **S-2**：`pylint-grandfather` 官方描述即"grandfather old code, enforce all **new or changed** code"——"changed"就是 touch=migrate 的社区同义词，与 S-1 同构。
- **S-3**：PHPStan 官方警告 baseline 非万能 + 社区实践（WordPress 官方 agent-skills）明确"generate once, reduce over time; **do not baseline newly introduced errors**"——直接支撑 P-019 不变量 1（新文档零豁免）与"棘轮只减不增"。

---

## 6. 复核后裁决建议

**维持 P-019 的 B（基线 + 棘轮）**，附 4 项实施前提：

| # | 前提 | 来源 |
|---|---|---|
| 1 | 解决 F-1：修订权威源或独立策略层，二选一落档 | F-1 |
| 2 | DESIGN 补写豁免机制 = `check_id` 过滤，并说明 dc4/dc5/r7 不豁免的全仓扫描理由 | F-2 |
| 3 | 90 天改标"内部政策参数（E3）"，绑定 U-1 复审 | F-3 |
| 4 | 明确续期基准与 append-only 要求 | F-5 |

---

## 7. 复核清单

- [x] 机检独立重跑（对已提交基线）
- [x] P-019 事实表 F-1..F-7 逐项核对
- [x] 锚点 X-1..X-9 回源抽查
- [x] `dc_validator` 不变式与错误结构源码审查
- [x] `step_enforce` digest 边界核对
- [x] 裁决建议逻辑复核（A/C/D 拒绝理由成立）
- [x] 未修改 P-019 归档文档（本报告为追加证据）
