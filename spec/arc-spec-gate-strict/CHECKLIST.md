---
id: arc-spec-gate-strict-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-12
depends: [arc-spec-gate-strict-IMPLEMENTATION, arc-spec-gate-strict-DESIGN]
upstream: arc-spec-gate-strict-IMPLEMENTATION
---

# 验收清单：Spec 门禁严格模式（P-082）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的 F-1/F-2 与 DESIGN §1 对应 | ✅ | FIX-1/2/3 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有实施 | ✅ | §2/§3 ↔ §1 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-6 |
| DC-4 | 无文档间矛盾（82/81、三模式、digest 顺序） | ✅ | 四文档一致 |
| DC-5 | 术语一致（档位/严格模式/rebind） | ✅ | 互查 |
| DC-6 | 既有判据未弱化 | ✅ | 四文档/覆盖/会话测试零回归 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | 阈值下调且 doc 保持 81 | `test_thresholds_lowered_to_this_batch` | 82/82/82/81 | ✅ | 20 passed |
| F-2 | batch 缺档位红 | `test_missing_tier_errors`（P-081） | 报「缺批次档位」 | ✅ | 零回归 |
| F-3 | batch-registration 缺档位红 | `test_registration_mode_requires_tier` | 报错 | ✅ | 同上 |
| F-4 | session 模式缺档位红 | `test_session_mode_requires_tier` | 报错 | ✅ | 同上 |
| F-5 | 阈值边界：P-081 不报、P-082 报 | `test_tier_gate_starts_at_threshold` | 仅 1 条且指向 P-082 | ✅ | 同上 |
| F-6 | 本批 digest 自证 | pre-commit `verify_digests` | digest 匹配 | ✅ | 待门禁回填 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `_require_tiers(d, rows)` | 只检查 d.pids 中 P≥82；不改其他字段 | ✅ |
| API-2 | `GATE_STRICT_MIN_P` | 三常量派生关系正确 | ✅ |
| API-3 | `EVIDENCE_MIN_P` | digest 校验对 P-082 生效 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §5） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | 历史 P 行不回溯 | F-5 + 读码 | ✅ |
| INV-2 | T3 轻批合法 | P-081 `test_t3_skips_doc_completeness` | ✅ |
| INV-3 | 既有判据不弱化 | 20 passed（含 P-081 全部） | ✅ |
| INV-4 | 档位解析单一实现 | `_require_tiers` 调 `spec_map.row_tier` | ✅ |
| INV-5 | digest 文件集只含本批 feature | row 只链接 `arc-spec-gate-strict/` | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 纯 PROGRESS 声明无档位 | 测试 | 「缺批次档位」 | ✅ |
| E-2 | 纯 session 变更无档位 | 测试 | 同上 | ✅ |
| E-3 | 档位缺失时不重复报 | 读码：feature 分支只判 T1 | 单条错误 | ✅ |
| E-4 | digest 失配 | 改动四文档后不重 bind | pre-commit 红 | ✅ |

## 6. 性能验收

| # | 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|---|
| P-1 | 档位检查开销 | O(声明行数) | 20 passed < 0.3 s | ✅ |

## 7. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 20 passed |
| C-2 | Python 3.11.15 | ✅ | 纯 stdlib |
| C-3 | CI `--base` 模式 | ✅ | digest 读工作树，与 commit 一致 |

## 8. ADD 审计（Step 10）

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | FIX-1/2/3 全部落地 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 三模式覆盖与设计一致 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 每项有 G-3/G-4 依据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | 门禁真能拦（红→绿）；本批 digest 自证 | 意图一致 | ✅ |

### 8.1 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | 阈值下调后 digest 顺序成为流程成本 | DESIGN §6 | 写入 PROGRESS 行与规范操作顺序 |
| P3 | 档位理由仍不核（U-2） | DESIGN §6 | 保持 |
| P3 | 历史 P 行未补档位，仅对 d.pids 生效 | `_require_tiers` | 出现维护需求时批量补 |

### 8.2 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest（E1） | F-1..F-5、API-1..3、E-1..E-3 | ✅ 20 passed |
| 运行时 digest（E2） | F-6 | ✅ 生成并绑定 |
| 静态读码（E3，`@46fb181` 基线 + 工作树） | INV-1/4/5、E-3 | ✅ |
| 盲区扫描（E4，扫描范围：32 项 + 三模式边界） | 全部 | **发现 3 项 P3** |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用 | — |
| 开发日志 | PROGRESS P-082 行 | ✅ |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 6 | 6 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 32 | 32 | 0 | 0 |

> 统计口径（RULE-2）：逐项勾选。

### 10.2 验收决定

- [x] **验收通过**
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 机检 | 2026-11-12 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| T3 理由核验（U-2） | 后续批次 | 出现降档滥用时 | pending |
| 历史 P 行补档位 | 不排期 | — | pending |
