---
id: arc-g3-m2-stage-events-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-12
depends: [arc-g3-m2-stage-events-IMPLEMENTATION, arc-g3-m2-stage-events-DESIGN]
upstream: arc-g3-m2-stage-events-IMPLEMENTATION
---

# 验收清单：G3 M2 stage_events 与 summary 事件链（P-078）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的结论在 DESIGN 中被使用（S-2→D-1、S-4→D-2/D-3、S-7→D-4） | ✅ | DESIGN §7 决策表逐条挂来源 |
| DC-2 | DESIGN 的模块在 IMPLEMENTATION 中有对应实施 | ✅ | DESIGN §2 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 的功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-10 / E-1..E-4 |
| DC-4 | 无文档间矛盾（错误码、字段名、阈值） | ✅ | grep `E_LOOP_DETECTED`/`row_ids_digest`/`window=3` 四文档一致 |
| DC-5 | 术语一致（`plan_sig` / `row_ids_digest` / 锚点 / 执行段） | ✅ | 四文档互查 |
| DC-6 | 派生需求 DR-1..DR-4 已登记且单独验收 | ✅ | DESIGN §8 + F-5/F-7/API-2 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | FC-1：3 轮同签名同结果集 → PAUSED | `test_loop_pauses_after_three_identical_rounds` | action=pause 且 code=E_LOOP_DETECTED | ✅ | 30 passed 套件内 |
| F-2 | FC-2：第二轮新增 5 行 → 放行 | `test_loop_does_not_pause_when_rows_change` | action≠pause | ✅ | 同上 |
| F-3 | FC-3：网络错误轮整轮豁免 | `test_network_error_round_is_exempt` | action≠pause 且 consecutive=0 | ✅ | 同上 |
| F-4 | 2 轮同签名同结果 → WARN 不暂停 | `test_loop_warns_at_two_rounds` | action=warn | ✅ | 同上 |
| F-5 | `plan_sig` 确定且与查询顺序无关 | `test_plan_signature_is_order_independent` | 两次不同顺序同摘要 | ✅ | 同上 |
| F-6 | Stage 4 取数闭环 | `test_collect_stage4_progress` | 签名非空、行数 2、网络标志 False | ✅ | 同上 |
| F-7 | Stage 5 取数闭环 | `test_collect_stage5_progress` | 签名含 0.8 阈值、行数取 shortlist | ✅ | 同上 |
| F-8 | 事件追加 seq 单调、attempt 递增 | `test_append_stage_event_monotonic` | seq 1→2，attempt 1→2 | ✅ | 同上 |
| F-9 | 末行损坏容忍（torn tail） | `test_load_tolerates_torn_tail` | 返回前序事件 | ✅ | 同上 |
| F-10 | 中间坏行 fail-closed | `test_load_rejects_middle_corruption` | 抛 `StageEventError` | ✅ | 同上 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `plan_signature(payload) -> str` | 与 DESIGN §3.2 一致；纯函数 | ✅ |
| API-2 | `collect_progress(run_dir, stage, **kw) -> dict` | 键为 `plan_sig/new_rows/row_ids_digest/network_error` | ✅ |
| API-3 | `append_stage_event(...) -> StageEvent` | 返回写入事件；字段齐全 | ✅ |
| API-4 | `load_stage_events(run_dir) -> list[StageEvent]` | 顺序 = 文件顺序 | ✅ |
| API-5 | `evaluate_loop(events, *, stage, window) -> dict` | 键为 `action/consecutive/code` | ✅ |
| API-6 | `verify_summary(run_dir, *, require_event) -> dict` | 返回 `{ok,digest,errors}`，坏输入不抛 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §9） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 事件文件只追加、seq 单调 | 读码 `append_stage_event`（mode="a"）+ F-8 | ✅ |
| INV-2 | I-2 判定是纯函数 | `test_evaluate_loop_is_pure` + 读码无 IO | ✅ |
| INV-3 | I-3 护栏失败不影响 run | runner `try/except` warning（读码 `runner.py` 循环护栏块） | ✅ |
| INV-4 | I-4 不新增错误码、不改字段集 | 错误码仅 `E_SUMMARY_TAMPERED`/`E_SUMMARY_EVENT_MISSING`/`E_LOOP_DETECTED` | ✅ |
| INV-5 | I-5 不承诺抗一致重写 | DESIGN §4.2 明示 + 本清单 §6 边界 | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 同执行段重复锚（D-2/X-5） | 追加第二条锚 | `E_SUMMARY_TAMPERED`（field=duplicate_anchor） | ✅ |
| E-2 | 锚 payload 被改 | 改 payload 不改 `payload_sha256` | `E_SUMMARY_TAMPERED` | ✅ |
| E-3 | 无锚点 | 无 events 文件 | `E_SUMMARY_EVENT_MISSING` | ✅ |
| E-4 | 循环暂停不写 checkpoint | runner 集成测试 | checkpoint 停在 stage 5 | ✅ |

## 6. 性能验收

| # | 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|---|
| P-1 | 事件追加复杂度 | O(1)，不重写历史 | 单行 append + fsync（读码） | ✅ |
| P-2 | 循环判定复杂度 | O(窗口)，200 事件 < 10 ms | 0.032 ms（E2 探针） | ✅ |

## 7. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | M2 套件 30 passed |
| C-2 | Python 3.11.15 | ✅ | M2 套件 30 passed |
| C-3 | Windows（CRLF/路径） | ✅ | 本机双环境复跑 |
| C-4 | `ARC_EVENTS_DISABLED=1` | ✅ | `test_events_disabled_skips_anchor` |

## 8. ADD 审计（Step 10）

### 8.1 四阶段

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §2 六个接口、§3.2 两组取数、§4.1/§4.2 锚点写读、§5 四个接线点全部有实现 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 无静默简化；一处文字偏移（Stage 5 签名不用 `screen_meta.json`）已登记 DR-2/U-2 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 新增行为均有依据：`row_ids_digest`=DR-1、`prefilter`/阈值=DR-2、坏行语义=DR-3、2/3 阈值=DR-4 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | 护栏真实停机（PAUSED + final_status=paused + checkpoint 不动）；D-2 真实判红（X-5 回归） | 意图一致 | ✅ |

### 8.2 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | 账本中间行损坏时 `load_stage_events` 抛错，runner 仅 warning → 护栏静默失效但 run 继续 | 读码 `record_stage_progress` + runner 兜底 | M3 增只读校验/告警事件 |
| P3 | `_row_id` 在 id/paper_id/doi/title 全缺失时返回空串并被过滤，两个「全无 id」结果集判为相同 | 读码 `_row_id`/`row_ids_digest` | 上游补稳定 id（U-2），或把空 id 计入计数 |
| P3 | 锚点 `payload_sha256` 严格化，使无该字段的旧锚判红 | 读码 `_collect_anchors` | 当前无存量锚；M3 迁移说明保留 |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式：FC-1 断言 `action=pause` 且 `code` 精确匹配；FC-2 断言「不等于 pause」而非恒真
- [x] 单文件检查盲区：既有单测又有 runner 集成测试（跨文件）
- [x] 设计文档独有约束无测试：I-2 纯度、I-5 边界、DR-2 偏移均有对应断言或说明
- [x] 修正阻断性项无测试：D-2 三个回归用例

### 8.4 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境输出（E1） | F-1..F-10、E-1..E-3、C-1/C-2 | ✅ 30 passed（3.13.5 与 3.11.15 各一次） |
| pytest 回归输出（E1） | 相关回归 99 passed；`test_rc_executor` 207 passed | ✅ 零失败 |
| 运行时探针（E2，含退化场景：空账本 / 200 事件 / 中间坏行） | P-2、F-9/F-10、API-5 | ✅ 0.032 ms；坏行按设计分流 |
| git status/diff（E1） | 改动边界：8 个代码/配置 + 4 份 spec + 1 session + 2 派生视图 | ✅ 无越界写入 |
| 静态读码（E3，`@a6f3da2` 基线 + 工作树未提交片段） | INV-1/I-3、API-1..6、ADD-1..4 | ✅ 逐条核对 |
| 盲区扫描（E4，扫描范围：41 项验收 + 3 类 P3 假设） | 全部 | **发现 3 项 P3**（见 §8.2） |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用（无框架级决策） | — |
| 开发日志 | PROGRESS P-078 行 | ✅ |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 10 | 10 | 0 | 0 |
| 接口 | 6 | 6 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 2 | 2 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 41 | 41 | 0 | 0 |

> 统计口径（RULE-2）：来自上表逐项勾选，非事后推算。

### 10.2 验收决定

- [x] **验收通过**（P1/P2 零缺陷；3 项 P3 已登记，不阻塞）
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 机械核验；独立异构 pass 待后续批次 | 2026-11-12 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| 外部锚点（U-1） | G7 | G7 开工 | pending |
| Stage 5 DONE 分支 `screen_meta.json`（U-2） | M3 | M3 开工 | pending |
| `stage_events` 并发写（U-3） | P-079 | 与 D-1 同批 | pending |
| 账本损坏告警（P3-1） | M3 | M3 开工 | pending |
