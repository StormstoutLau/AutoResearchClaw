---
id: arc-g3-m4-m5-governance-k5-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g3-m4-m5-governance-k5-IMPLEMENTATION, arc-g3-m4-m5-governance-k5-DESIGN]
upstream: arc-g3-m4-m5-governance-k5-IMPLEMENTATION
---

# 验收清单：G3 M4+M5 合并批（P-087）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 中被使用（R-1→D-1、R-3→D-2、R-4→D-3、R-5→D-4） | ✅ | DESIGN §4 逐条挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有实施 | ✅ | DESIGN §2 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-12 / API-1..API-7 |
| DC-4 | 无文档矛盾（错误码、字段名、严格口径） | ✅ | 四文档 grep `E_HANDBACK_SCOPE`/`E_K5_UNRESOLVED_REF`/`retrieval_degraded` 一致 |
| DC-5 | 术语一致（mandate / handback / K5 / retrieval） | ✅ | 四文档互查 |
| DC-6 | 未决项 U-1..U-3 已登记 | ✅ | RESEARCH §6.2 + CHECKLIST §10 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | mandate 写一次且不可变 | `test_mandate_is_written_once_and_immutable` | 两次返回相等、`created_at` 不变 | ✅ | 17 passed 套件内 |
| F-2 | 其他 run_id 复用被拒 | `test_mandate_rejects_other_run_id` | 抛 `MandateError` | ✅ | 同上 |
| F-3 | 范围内 handback 可写可读 | `test_handback_in_scope_roundtrips` | 文件存在且 roundtrip 相等 | ✅ | 同上 |
| F-4 | 越界/空理由 handback 被拒 | `test_handback_out_of_scope_is_rejected`、`test_handback_requires_reason` | 抛 `HandbackScopeError`，不落盘 | ✅ | 同上 |
| F-5 | prompt_version 确定且对模板敏感 | `test_prompt_version_is_deterministic_and_sensitive` | 同输入同值、改 system 变值 | ✅ | 同上 |
| F-6 | 渲染结果携带版本 | `test_rendered_prompt_carries_version` | `sha256:` 前缀、同模板稳定 | ✅ | 同上 |
| F-7 | K5 解析含 kind/key/line，非法不捕获 | `test_parse_refs_reports_kind_key_and_line`、`test_parse_refs_ignores_malformed_tokens` | 精确列表 | ✅ | 同套件 |
| F-8 | `paper:` 按 BibTeX key 解析 | `test_resolve_paper_against_bib_keys` | 仅缺 key 未解析 | ✅ | 同上 |
| F-9 | `tb:` 按 KB 文件名解析 | `test_resolve_tb_against_nested_kb` | 嵌套目录命中 | ✅ | 同上 |
| F-10 | Stage 22 未解析 K5 阻断 | `test_stage22_blocks_unresolved_k5_ref` | FAILED + `E_K5_UNRESOLVED_REF` + 报告 | ✅ | wiring 3 passed |
| F-11 | Stage 23 未解析 K5 阻断 | `test_stage23_blocks_unresolved_k5_ref` | FAILED + 报告 | ✅ | 同上 |
| F-12 | retrieval 降级显式 | `test_stage22_adds_retrieval_notice` + summary 字段 | 论文注记、报告、summary 布尔 | ✅ | 同上 + 读码 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `ensure_run_mandate` | 幂等、不可变、run_id 校验 | ✅ |
| API-2 | `write_handback` / `read_handback` | 先校验后写；缺失返回 None | ✅ |
| API-3 | `validate_handback` | 子集校验；错误消息含 `E_HANDBACK_SCOPE` | ✅ |
| API-4 | `prompt_version` | 确定性 JCS sha256 | ✅ |
| API-5 | `parse_refs` / `resolve_refs` | 纯函数、只读 | ✅ |
| API-6 | `check_k5_refs` | 返回 `{file,line,ref}` | ✅ |
| API-7 | `bib_keys_from_text` | 惰性导入，返回 key 集合 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §5） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 不改 C4/AR/claim 判定 | 401 项回归全绿 | ✅ |
| INV-2 | I-2 mandate/handback 原子写、mandate 不可变 | 读码 + F-1/F-3 | ✅ |
| INV-3 | I-3 DONE 路径零影响 | runner 仅在 PAUSED/BLOCKED 校验 | ✅ |
| INV-4 | I-4 K5 只读 | 读码 `check_k5_refs` 无写操作 | ✅ |
| INV-5 | I-5 retrieval 缺失/坏文件 → false | 读码 `_retrieval_degraded` + runner 测试 | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | handback 请求 `tool:shell` | 越界 scope | `E_HANDBACK_SCOPE`，runner FAILED | ✅ |
| E-2 | handback 空理由 | `reason="  "` | 拒绝 | ✅ |
| E-3 | K5 非法 token | `tb:-x` / `tb:` | 不解析，不误报 | ✅ |
| E-4 | Stage 22/23 未解析 K5 | `tb:missing` / `paper:missing` | FAILED + `k5_refs.json` | ✅ |
| E-5 | K5 检查内部异常 | 异常路径 | FAILED `check_failed`（fail-closed） | ✅ 读码 |

## 6. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 新增 17 passed；回归 401 passed |
| C-2 | Python 3.11.15 | ✅ | 新增 17 passed |
| C-3 | 既有 Stage 22 早退分支 | ✅ | `test_rc_executor` 全绿 |

## 7. ADD 审计（Step 10）

### 7.1 四阶段

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §2 五组接口、§3 四形态、§1 接线全部有实现 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 一处文法细化（键末字符收紧，DR-1）已登记；其余逐条一致 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 新增行为均有 R-1..R-8 依据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | K5 真实阻断、retrieval 真实显式、mandate 真实不可变 | 意图一致 | ✅ |

### 7.2 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | handback 当前无生产者，校验面只在「文件存在时」生效 | R-3；U-1 | 首个 handback 场景出现时补阶段侧写入 |
| P3 | prompt 版本只写 `logger.info`，无独立逐请求日志 | R-4；U-2 | 需要逐请求审计时再引入 request log |
| P3 | `tb:` 用 `rglob` 全树扫描，无 KB 索引 | R-5；U-3 | KB 规模 > 10k 时建索引 |

### 7.3 Iron Law 检查

- [x] 断言恒真式：F-1 断言对象相等而非「无异常」；F-10/11 断言精确错误码
- [x] 单文件检查盲区：单元 + Stage 22/23 接线 + 401 回归
- [x] 设计独有约束无测试：I-4 只读由读码证据覆盖
- [x] 阻断性项无测试：F-4/E-1/E-4 均有可失败用例

### 7.4 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境（E1） | F-1..F-9、C-1/C-2 | ✅ 17 passed ×2 |
| pytest 回归（E1） | INV-1、C-3 | ✅ 401 passed |
| 运行时探针（E2，含越界/未解析/降级三场景） | F-4/F-10/F-11/F-12、E-1/E-4 | ✅ 判红与注记均生效 |
| 静态读码（E3） | API-1..7、INV-3/4/5 | ✅ |
| 盲区扫描（E4，扫描范围：42 项验收 + 3 类 U 项） | 全部 | **发现 3 项 P3**（§7.2） |

## 8. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用 | — |
| 开发日志 | PROGRESS P-087 行 | ✅ |

## 9. 验收结论

### 9.1 统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 12 | 12 | 0 | 0 |
| 接口 | 7 | 7 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 5 | 5 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 42 | 42 | 0 | 0 |

> 统计口径（RULE-2）：逐项勾选，非事后推算。

### 9.2 决定

- [x] **验收通过**（P1/P2 零缺陷；3 项 P3 登记）
- [ ] 有条件通过
- [ ] 验收失败

### 9.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-13 |
| 审查者 | 自查（单视角）+ 机械核验；独立异构 pass 待后续批次 | 2026-11-13 |

## 10. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| U-1 handback 生产者 | G3 后续 | 首个 handback 场景 | pending |
| U-2 逐请求 prompt 日志 | G3 后续 | 需要审计时 | pending |
| U-3 KB 索引 | G3 后续 | KB > 10k | pending |
| P-086 O-2/O-3 加固候选 | 后续裁决 | — | pending |
