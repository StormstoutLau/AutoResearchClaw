---
id: arc-g3-closure-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g3-closure-fixes-IMPLEMENTATION, arc-g3-closure-fixes-DESIGN]
upstream: arc-g3-closure-fixes-IMPLEMENTATION
---

# 验收清单：G3 收口缺口修复（P-089）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 中被使用（R-2→D-1、R-4→D-2、R-5→D-3、R-6→D-4、R-7→D-5） | ✅ | DESIGN §3 逐条挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有实施 | ✅ | DESIGN §2 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-8 / API-1..API-5 |
| DC-4 | 无文档矛盾（A3-7=prompt_version、A3-8=StageHandback） | ✅ | 四文档与总纲一致 |
| DC-5 | 术语一致（ContextVar / 侧车 / handback / guard） | ✅ | 四文档互查 |
| DC-6 | 未决边界已声明 | ✅ | IMPL §6 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | 渲染后请求上下文携带版本 | `test_for_stage_sets_request_context_version` | `get_prompt_version() == sp.version` | ✅ | 31 passed 关键集 |
| F-2 | 每次 `LLMClient.chat` 记录版本 | 读码 `client.chat` 入口 + 既有 LLM 回归 | 日志行含 `prompt_version` | ✅ | E3 读码 + 357 回归 |
| F-3 | claim 导出携带生成版本 | `test_export_includes_stage17_prompt_version` | 条目 `prompt_version=sha256:abc` | ✅ | 同上 |
| F-4 | Stage 17 阻断产 handback | `blocked_no_metrics` / `blocked_simulated_data` 断言 | `handback.json` 的 reason/scope | ✅ | `test_rc_executor` 2 项 |
| F-5 | runner 越界 handback 转 FAILED | `test_runner_guard_rejects_out_of_scope_handback` | `E_HANDBACK_SCOPE` + FAILED | ✅ | 31 passed |
| F-6 | 配置变更不重写 mandate | `test_mandate_survives_config_change` | 两次 mandate 相等 | ✅ | 同上 |
| F-7 | 编号映射统一 | grep 总纲/P-087 四文档 | A3-7=prompt_version、A3-8=StageHandback | ✅ | E1 grep |
| F-8 | 无侧车时 export 原样 | `test_export_maps_...` 断言无 `prompt_version` | 旧行为不变 | ✅ | 同上 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `set/get/log_prompt_version` | 上下文读写与日志 | ✅ |
| API-2 | `write_handback_file` | 原子写、不校验 | ✅ |
| API-3 | `_apply_handback_guard` | 越界 FAILED、范围内原样 | ✅ |
| API-4 | `_write_paper_sections` | 返回 `(draft, version)`；调用点已更新 | ✅ |
| API-5 | `export_claim_labels` | 侧车缺失不加键 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §4） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 不改 C4/AR/错误码 | 357 回归 + diff | ✅ |
| INV-2 | I-2 无侧车 export 逐字段不变 | F-8 | ✅ |
| INV-3 | I-3 handback 写失败不改变暂停 | 读码 best-effort | ✅ |
| INV-4 | I-4 范围内 handback 不改变 runner 结果 | F-4 + guard 读码 | ✅ |
| INV-5 | I-5 日志只增、不改请求内容 | 读码 `log_prompt_version` | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 越界 handback | `tool:shell` | `E_HANDBACK_SCOPE`，FAILED | ✅ |
| E-2 | 侧车缺失/损坏 | 删除或写坏 JSON | export 不加版本、不抛 | ✅ |
| E-3 | 阻断分支写 handback 失败 | 目录不可写 | 仅 warning，暂停结果不变 | ✅ 读码 |

## 6. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 关键集 31 passed；回归 357 passed |
| C-2 | Python 3.11.15 | ✅ | 关键集 30 passed |
| C-3 | 既有 Stage 17 写段测试 | ✅ | 元组解包已更新，行为不变 |

## 7. ADD 审计

### 7.1 四阶段

| # | 阶段 | 结果 | 状态 |
|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN 四项修复全部有实现 | ✅ |
| ADD-2 | Phase 2 忠实度 | 无静默偏离；API 变更仅 `_write_paper_sections` 返回元组，调用点已更新 | ✅ |
| ADD-3 | Phase 3 必要性 | 新增行为均有 R-1..R-7 依据 | ✅ |
| ADD-4 | Phase 4 语义 | A3-7 真实覆盖请求侧；A3-8 真实产生并阻断越界 | ✅ |

### 7.2 审计发现

| 严重性 | 发现 | 证据 | 建议 |
|---|---|---|---|
| P3 | 请求记录是日志行，非独立 JSONL | IMPL §6 | 需要逐请求审计时再落文件 |
| P3 | handback 生产者仅 Stage 17 两分支 | IMPL §6 | 其他暂停场景按需扩展 |
| P3 | 非 LLM 模板路径无版本侧车 | IMPL §7 | 非 LLM 论文不产生 claim 版本 |

### 7.3 取证矩阵

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境（E1） | F-1..F-8、C-1/C-2 | ✅ 31/30 passed |
| pytest 回归（E1） | INV-1、C-3 | ✅ 357 passed |
| 运行时探针（E2） | F-4/F-5 | ✅ handback 落盘、越界 FAILED |
| 静态读码（E3） | F-2/F-7、INV-3/5 | ✅ |
| 盲区扫描（E4，扫描范围：34 项 + 3 边界） | 全部 | **发现 3 项 P3**（§7.2） |

## 8. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用 | — |
| 开发日志 | PROGRESS P-089 行 | ✅ |

## 9. 验收结论

### 9.1 统计

| 类别 | 总数 | 通过 | 失败 |
|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 |
| 功能 | 8 | 8 | 0 |
| 接口 | 5 | 5 | 0 |
| 不变式 | 5 | 5 | 0 |
| 错误处理 | 3 | 3 | 0 |
| 兼容性 | 3 | 3 | 0 |
| ADD 审计 | 4 | 4 | 0 |
| **总计** | 34 | 34 | 0 |

> 统计口径（RULE-2）：逐项勾选，非事后推算。

### 9.2 决定

- [x] **验收通过**（P1/P2 零缺陷；3 项 P3 登记）
- [ ] 有条件通过
- [ ] 验收失败

### 9.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-13 |
| 审查者 | 自查（单视角）+ 机械核验；P-090 复评待后续 | 2026-11-13 |

## 10. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| P-090 复评 2 P2 + 1 P3 | 后续批次 | 收口前 | pending |
| P-083 O-3 计数订正 | 后续批次 | — | pending |
| P-084 D-3..D-6 / P-086 O-2..O-3 | 后续裁决 | — | pending |
