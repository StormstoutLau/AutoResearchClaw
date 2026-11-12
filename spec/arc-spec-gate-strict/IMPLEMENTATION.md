---
id: arc-spec-gate-strict-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-spec-gate-strict-DESIGN]
upstream: arc-spec-gate-strict-DESIGN
---

# 实施记录：Spec 门禁严格模式（P-082）

> **状态**：两项加固完成；本批 session 自带 digest 自证。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `scripts/spec/step_enforce.py` | 修改 | `GATE_STRICT_MIN_P=82`；`BATCH_BINDING_MIN_P` / `EVIDENCE_MIN_P` 下调至 82；新增 `_require_tiers()` 并在 batch / session / batch-registration 三处调用；`_resolve_declared` 的 feature 级档位分支简化为只判 T1 |
| 2 | `tests/test_step_enforce_branches.py` | 修改 | 新增 T-7 四项（常量、registration 档位、session 档位、阈值边界） |
| 3 | `tools/spec_runner/sessions/specwf-p082-arc-spec-gate-strict.jsonl` | 新增 | 五步决策流 + finalize `evidence_digest` |

**不改**：`spec_map`（档位解析复用）、`DOC_COMPLETENESS_MIN_P=81`、既有四文档判据、`dc_validator`。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `_require_tiers` | `(d: Decision, rows: dict) -> None` | 只对 `d.pids` 中 P≥82 的行；历史不回溯 |
| `GATE_STRICT_MIN_P` | 常量 82 | 回退 = 调回 129/137（两常量独立定义） |
| `EVIDENCE_MIN_P` | 常量 82 | 回退 = 置哨兵值 9999，digest 校验降为观察 |

## 3. 关键行为

- 纯 PROGRESS 声明（batch-registration）与纯 session 变更（session 模式）现在也要求档位词。
- P ≥ 82 的批次：feature 绑定 + 四文档（T1）+ digest 绑定同时生效。
- 本批按「四文档定稿 → stage → 生成 digest → 写 session」顺序自证。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限 | 状态 |
|---|---|---|---|
| `spec_map.row_tier` | 档位读取 | P-081 已引入 | ✅ |
| `hashlib` / `json` | digest 生成 | 3.11 | ✅ |
| 3.12+ API | 无 | — | ✅ |

## 5. 读数

| 项 | 读数 |
|---|---|
| 新增测试 | **+4**；两文件合计 **20 passed** |
| 红→绿 | 红：4 项（常量仍 129/137、两模式不报档位、阈值边界）。绿：**20 passed** |
| 回归 | P-081 既有 5 项四文档测试零回归 |
| 本批 digest | `--doc-digest arc-spec-gate-strict` 生成，finalize 绑定；回填读数后按 rebind 追加（带 `rebind_reason`） |
| 门禁 | DC 4 文件 0 违规；step-gate 5/5；console/repo_stats 一致；rework PASS；pre-commit **9/9 Passed**；`verify_digests` 对 P-082 生效并通过 |

## 6. 验收边界

- 档位只校验词存在，不核「T3 是否真 Layer-0」（U-2，沿用 P-081）。
- 阈值下调后，P≥82 批次必须按 digest 顺序操作；改文档需重新 finalize（`rebind_reason`）。
- 历史 P 行不补标、不追溯。
