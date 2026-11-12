---
id: arc-spec-gate-strict-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [SPEC-PROCESS, arc-spec-gate-hardening-DESIGN]
upstream: arc-spec-gate-hardening-DESIGN
---

# 调研文档：Spec 门禁严格模式（P-082）

> **Feature**：落实 P-080 审计的 G-4（档位词强制）与 G-3（阈值提前），裁决来源 = 用户 2026-11-12 指令。
> **Spec 步骤**：Step 1-2。

## 1. 调研目标

1. **G-4 的机械面**：`SPEC_PROCESS §批次档位` 自述「可机械化的仅『路径集是否落 Layer-0』与『PROGRESS 行是否含档位词』」，但 P-081 只对「本次变更 feature 的所属 P」检查档位；纯 PROGRESS 声明（batch-registration）不检查。
2. **G-3 的阈值**：`BATCH_BINDING_MIN_P=129`、`EVIDENCE_MIN_P=137` 是渐进棘轮；当前 P-081，两条均不生效。下调到本批意味着 P-082 起「feature 绑定 + 四文档 digest 绑定」立即强制。
3. **自我适用**：下调后本批 session 的 finalize 必须携带四文档 sha256 文件表，否则本批自红。

## 2. 调研方法

| 通道 | 用途 | 结果 |
|---|---|---|
| 读码 `step_enforce.resolve` | 三模式分支 | ✅ batch / session / batch-registration 各有独立路径 |
| 读码 `verify_digests` / `doc_digest` | digest 绑定语义 | ✅ `feats = row.features`；`_read_doc_bytes` 在 base 为空时读 INDEX |
| 读码 `_digest_scope` | digest 文件集 | ✅ 只含 feature 目录下的四文档 |
| P-080 审计报告 | G-3/G-4 定义 | ✅ 本仓 E2 结论 |
| `SPEC_PROCESS` v1.7.1 | 档位与诚实边界 | ✅ 「可机械化的仅……档位词」原文 |

> 本批为**规范内裁决执行**，不引入新的外部技术事实；未新增外部检索（无方法学断言）。

## 3. 调研发现

### 3.1 F-1：档位检查覆盖不全

P-081 的检查在 `_resolve_declared` 内，只遍历 `docs_features`（本次变更的四文档）。因此：

- 只改 PROGRESS（batch-registration）→ 不检查档位；
- 只改 session（session 模式）→ 不检查档位；
- 改了 spec 文档但 feature 无 owner（已由覆盖检查报错）→ 档位检查不触发。

G-4 要求的「PROGRESS 行强制含 T1|T3」应覆盖**本次声明的所有 P 行**，与变更形态无关。

### 3.2 F-2：阈值下调的自我适用链

`EVIDENCE_MIN_P=82` 后，P-082 的 finalize 必须带 `metadata.evidence_digest`：

1. `feats = row.features`（本批只链接 `arc-spec-gate-strict/`）；
2. `doc_digest(feats)` 计算四文档 `{algorithm, files}`；
3. 本地 pre-commit 无 `--base` → `_read_doc_bytes` 读 **INDEX**（staged）；
4. CI `--base` 模式读 **工作树**（= commit 内容）。

→ 操作顺序必须是「四文档定稿 → stage → 生成 digest → 写 session」，此后不得再改四文档。

### 3.3 F-3：阈值常量语义

三个边界语义不同，不能合并为一个常量（P-137 注释已明确 digest 边界独立）：

- feature 绑定（`BATCH_BINDING_MIN_P`）；
- 四文档齐全（`DOC_COMPLETENESS_MIN_P`，P-081 已设 81）；
- digest 绑定（`EVIDENCE_MIN_P`）。

本批把前两者与新增的档位检查统一到 **82**，`DOC_COMPLETENESS_MIN_P` 保持 81（已生效，无需下调）。

## 4. 综合分析

1. 新增 `GATE_STRICT_MIN_P = 82`；`BATCH_BINDING_MIN_P` 与 `EVIDENCE_MIN_P` 同步设为 82。
2. 新增 `_require_tiers(d, rows)`：对 `d.pids` 中 P ≥ 82 的行要求 `row_tier` 非空；在 batch、session、batch-registration 三处调用（maintenance 不调用）。
3. `_resolve_declared` 内原有的按 feature 档位检查保留 T1 四文档判定，删除重复的「缺档位」分支（统一由 `_require_tiers` 报）。
4. 本批 session finalize 写 digest，自证阈值生效。

## 5. 幻觉抑制审查（Step 2 Review）

| 断言 | 来源 | 状态 |
|---|---|---|
| batch-registration 不检查档位 | 读码 `resolve` L474-L483 | ✅ E1 |
| digest 读 INDEX / 工作树 | 读码 `_read_doc_bytes` / `verify_digests` | ✅ E1 |
| 三个阈值语义独立 | `step_enforce` 常量注释（P-137） | ✅ E1 |

- 无外部引用新增；无未验证断言。

## 6. 对设计的输入

### 6.1 方案

- `GATE_STRICT_MIN_P = 82`；档位检查覆盖三模式。
- `BATCH_BINDING_MIN_P = 82`、`EVIDENCE_MIN_P = 82`。
- digest 生成与写入 session 的顺序纳入 CHECKLIST。

### 6.2 约束

- 历史 P 行不回溯（只检查 `d.pids`）。
- 不改变 T3 合法性。
- digest 绑定只在声明 P ≥ 82 时校验。

### 6.3 未决项登记（四元块）

- **U-1 digest 与后续改动**
  - **判据**：文档定稿后任何改动都触发 digest 失配
  - **触发条件**：每次 finalize 后再改四文档
  - **当前倾向**：按「定稿→digest→session」顺序；改动则重新生成并在 session 追加 finalize（带 rebind_reason）
  - **证据等级**：E1 读码（`verify_digests`）

## 7. 参考文献

- spec/SPEC_PROCESS.md v1.7.1 §批次档位与裁剪理由。
- docs/PROGRESS.md P-080 行（G-3/G-4 登记）。

---

**Review 签字**: 自查（单视角）+ 读码 日期: 2026-11-12
