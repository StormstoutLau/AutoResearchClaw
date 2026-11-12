---
id: arc-spec-gate-hardening-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-12
depends: [arc-spec-gate-hardening-IMPLEMENTATION, arc-spec-gate-hardening-DESIGN]
upstream: arc-spec-gate-hardening-IMPLEMENTATION
---

# 验收清单：Spec 门禁加固（P-081）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的 F-1/F-2/F-3 与 DESIGN §1 逐条对应 | ✅ | FIX-1/2/3 |
| DC-2 | DESIGN 的模块在 IMPLEMENTATION 有对应实施 | ✅ | §2/§3 ↔ §1/§2 |
| DC-3 | IMPLEMENTATION 的功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-7 |
| DC-4 | 无文档间矛盾（阈值 81、四份清单、跳过语义） | ✅ | 三处一致 |
| DC-5 | 术语一致（档位/四文档/范围兜底） | ✅ | 四文档互查 |
| DC-6 | 既有判据未弱化 | ✅ | 覆盖/会话/digest 顺序与语义读码确认 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | CI range 步骤接入 | 读码 `ci.yml` L162-L202 | `fetch-depth: 0` + `--base` + `--check-merge` 均在位 | ✅ | 静态 |
| F-2 | base 缺失/全 0/不可达 → 跳过 | 读码分支 | 打印后 exit 0，不静默通过 | ✅ | 静态 |
| F-3 | 范围模式不误报 | `--base HEAD~1`（P-078..P-080，29 路径） | exit 0 | ✅ | 实测 |
| F-4 | T1 缺任一文档 → 红 | `test_t1_missing_doc_errors` | 报「四文档不全」 | ✅ | 16 passed |
| F-5 | T1 四份齐全 → 绿 | `test_t1_complete_docs_passes` | 无四文档错误 | ✅ | 同上 |
| F-6 | T3 缺文档 → 绿 | `test_t3_skips_doc_completeness` | 无四文档错误 | ✅ | 同上 |
| F-7 | 缺档位 → 红；低编号不回溯 | `test_missing_tier_errors` / `test_low_pid_is_not_gated` | 前者报错，后者不报 | ✅ | 同上 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `parse_progress_rows` 增 `basis` | 旧键不变；新键为第 3 列原文 | ✅ |
| API-2 | `row_tier` | T1/T3/None 三态；`T10` 不误匹配 | ✅ |
| API-3 | `_missing_docs` | 兼容 `CHECKLIST_FUNC.md`；缺失列表有序 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §5） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | 既有判据不弱化 | 原 8 项分支测试全过 | ✅ |
| INV-2 | T3 轻批合法 | F-6 | ✅ |
| INV-3 | fail-closed（缺档位/缺文档红；base 不可达显式跳过） | F-2/F-4/F-7 | ✅ |
| INV-4 | 档位解析单一实现 | 读码：`step_enforce` 调用 `spec_map.row_tier` | ✅ |
| INV-5 | 无三方依赖 | `pyproject` 未改；CI 仅 bash | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | P 行无 T1/T3 | 测试构造 | 「缺批次档位」 | ✅ |
| E-2 | T1 缺 CHECKLIST | 测试注入 | 「四文档不全」 | ✅ |
| E-3 | base 为全 0 | 读码分支 | 打印跳过 | ✅ |
| E-4 | base 不在克隆内 | 读码 `git cat-file -e` | 打印跳过 | ✅ |

## 6. 性能验收

| # | 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|---|
| P-1 | range 检查耗时 | P-080 范围 29 路径 < 2 s | 实测 < 1 s（本地） | ✅ |

## 7. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5（本地） | ✅ | 16 passed |
| C-2 | Python 3.11.15（CI） | ✅ | 纯 stdlib，语法兼容 |
| C-3 | bash（ubuntu CI） | ✅ | `mapfile` / `set -euo pipefail` | 

## 8. ADD 审计（Step 10）

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | FIX-1/2/3 全部落地 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 阈值/四份/跳过语义与设计一致 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 档位、四文档、range 均有 RESEARCH 依据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | 门禁真能拦（单测红→绿）；范围模拟不误报 | 意图一致 | ✅ |

### 8.1 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | 范围模式看不到中间提交（U-1） | DESIGN D-1 | 出现真实事故再引入 `--commit` |
| P3 | 档位只校验词存在，不核裁剪理由（U-2） | SPEC_PROCESS 自述不可机械拦截 | 保持 |
| P3 | fork PR 的 `base.sha` 可能不在克隆内 | 代码防御 | 已显式跳过并打印 |

### 8.2 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 输出（E1） | F-4..F-7、API-1..3、E-1/E-2 | ✅ 16 passed |
| 本地 range 探针（E2） | F-3、ADD-4 | ✅ exit 0（29 路径 / 3 P / 3 session） |
| 静态读码（E3，`@026ed84` 基线 + 工作树片段） | F-1/F-2、E-3/E-4、INV-1/4/5 | ✅ |
| git 结构检查（E1） | CI 步骤中的命令均可解析 | ✅ |
| 盲区扫描（E4，扫描范围：33 项 + 范围/档位边界） | 全部 | **发现 3 项 P3** |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用（批内门禁加固） | — |
| 开发日志 | PROGRESS P-081 行 | ✅ |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 33 | 33 | 0 | 0 |

> 统计口径（RULE-2）：来自上表逐项勾选，非事后推算。

### 10.2 验收决定

- [x] **验收通过**（3 项 P3 登记，不阻塞）
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 实测 | 2026-11-12 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| 逐提交语义（U-1） | 后续批次 | 出现中间提交事故时 | pending |
| T3 裁剪理由机械核验（U-2） | 后续批次 | 出现降档滥用时 | pending |
| 全仓历史 feature 文档补齐 | 不排期 | — | pending |
