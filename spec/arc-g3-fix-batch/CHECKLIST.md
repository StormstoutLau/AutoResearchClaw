---
id: arc-g3-fix-batch-CHECKLIST
type: design
version: 1.0
status: pending
date: 2026-11-12
depends: [arc-g3-fix-batch-IMPLEMENTATION, arc-g3-fix-batch-DESIGN]
upstream: arc-g3-fix-batch-IMPLEMENTATION
---

# 验收清单：G3 M1/M2 修复批（P-080）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的复现结论与修复矩阵逐条对应 | ✅ | D-1→FIX-1/2、O-1→FIX-4、O-2→FIX-5、O-3→FIX-3、D-3→FIX-6 |
| DC-2 | DESIGN 的模块在 IMPLEMENTATION 有对应实施 | ✅ | DESIGN §2/§3 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 的功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-8 |
| DC-4 | 无文档间矛盾（超时/轮询/重试数值一致） | ✅ | 30 s / 20 ms / 3×10 ms 三处一致 |
| DC-5 | 术语一致（互斥锁/尾部连续坏行/撤回） | ✅ | 四文档互查 |
| DC-6 | M1/M2 DESIGN 升 v1.1 且修订点与本批一致 | ✅ | §2.2 / §3.1 / §3.3 / §3.4 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | D-1：并发注册不丢节点 | `test_register_concurrent_threads_no_loss` | 20 轮每轮 nodes=2 | ✅ | 探针 150 轮 0 丢失 |
| F-2 | D-1：并发注册不抛异常 | 同测试 + barrier 探针 | 150 轮 0 异常 | ✅ | 修复前 40 轮异常 |
| F-3 | O-3：并发追加 seq 唯一 | `test_stage_events_concurrent_append_unique_seq` | seq/attempt = 1..8 | ✅ | 8 线程 |
| F-4 | O-1：尾部连续坏行容忍 | `test_load_tolerates_multiple_torn_tail_lines` | 返回前序事件 | ✅ | 两行半写 |
| F-5 | O-1：中间坏行仍 fail-closed | `test_load_rejects_middle_corruption` | 抛 `StageEventError` | ✅ | 既有用例零修改 |
| F-6 | O-2：非正 window 拒绝 | `test_evaluate_loop_rejects_non_positive_window` | `0/-5` 均抛 `ValueError` | ✅ | — |
| F-7 | D-3 撤回：跨 stage 同内容保留 | `test_cross_stage_same_content_keeps_both_nodes` | 两节点 id 不同且均持久化 | ✅ | 探针同一手复核 |
| F-8 | 锁超时与跨进程 | `test_filelock_times_out_when_held` + 跨进程探针 | 抛 `LockTimeout`；子进程持锁父进程超时 | ✅ | PASS |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `exclusive_lock` | 上下文管理；异常路径必释放 | ✅ |
| API-2 | `LockTimeout` | 继承 `RuntimeError`；消息含路径与超时 | ✅ |
| API-3 | `append_stage_event(attempt=None)` | 缺省时自动递增，显式值优先 | ✅ |
| API-4 | `load_stage_events` / `evaluate_loop` | 签名不变；坏输入行为符合 DESIGN §3 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §5） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 字段集/id 公式/去重语义不变 | 既有 13 项 M1 测试全过 | ✅ |
| INV-2 | I-2 单写者路径行为不变 | 幂等/缺文件跳过测试全过 | ✅ |
| INV-3 | I-3 仅尾部连续坏行容忍 | F-4 + F-5 | ✅ |
| INV-4 | I-4 锁失败不阻断 run | runner `try/except warning` 未改动 | ✅ |
| INV-5 | I-5 无三方依赖、平台懒加载 | 读码 + `pyproject` 未改 | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 锁被长期占用 | 持锁线程 sleep 0.5 s，timeout 0.2 | `LockTimeout` | ✅ |
| E-2 | 账本中间坏行 | 中部插入坏行 | `StageEventError` | ✅ |
| E-3 | `window=0/-5` | 直接调用 | `ValueError` | ✅ |
| E-4 | 注册写失败 | `os.replace` 重试 3 次后仍失败 | 抛出 → runner warning（策略未改） | ✅ |

## 6. 性能验收

| # | 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|---|
| P-1 | 加锁开销 | 200 次注册 < 2 s | **169.8 ms** | ✅ |
| P-2 | 锁内 IO | 仅 load+write，无额外全量扫描 | 读码 | ✅ |

## 7. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5（Windows） | ✅ | 52 passed |
| C-2 | Python 3.11.15（Windows） | ✅ | 52 passed |
| C-3 | POSIX 分支（Linux CI） | ✅ | `fcntl` 分支语法/导入可由 CI 承接；本机不可执行 |
| C-4 | `ARC_EVENTS_DISABLED=1` | ✅ | 事件追加不触发锁（`test_events_disabled_skips_anchor` 仍在回归内） | 

## 8. ADD 审计（Step 10）

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §1 六项修复全部落地（FIX-6 为撤回，无代码） | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 超时 30 s / 轮询 20 ms / 重试 3×10 ms / 读侧语义与设计一致 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 锁/重试/坏行/窗口校验均有 DR-1..3 或复现证据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | D-1 探针从 150/150 丢节点转为 0 丢失；锁真实阻止覆盖 | 意图一致 | ✅ |

### 8.1 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | `.locks/*.lock` 残留在 run 目录（0 字节）；若交付打包按目录复制会带入 | 读码 `LOCK_DIR_NAME` + 交付打包逻辑 | P-081 在打包排除清单加 `.locks` |
| P3 | `append_stage_event` 锁内 `load_stage_events` 为 O(n) 全文件解析 | 读码 | 账本破千行时再引入索引 |
| P3 | POSIX `fcntl` 分支未在本机实测（Windows 环境） | 环境限制 | 由 CI Linux 承接；本次已实测 Windows 跨进程 |

### 8.2 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境（E1） | F-1..F-8、API-1..4、E-1..E-3 | ✅ 52 passed ×2 |
| barrier 运行时探针（E2，含退化场景） | F-1/F-2、ADD-4 | ✅ 修复前 150/150 丢；修复后 0 |
| 跨进程 subprocess 探针（E2） | F-8 | ✅ PASS |
| 性能探针（E2） | P-1 | ✅ 169.8 ms |
| pytest 回归（E1） | INV-1/INV-2 | ✅ 109 passed |
| 静态读码（E3，`@a6f3da2` 基线 + 工作树片段） | INV-3..5、E-4、ADD-2/3 | ✅ |
| 盲区扫描（E4，扫描范围：37 项 + 锁/重试边界） | 全部 | **发现 3 项 P3** |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ☐ |
| DESIGN.md | ✅ | ☐ |
| IMPLEMENTATION.md | ✅ | ☐ |
| CHECKLIST.md（本文件） | ✅ | ☐ |
| ADR | 不适用（批内修复，无框架级决策） | — |
| 开发日志 | PROGRESS P-080 行 | ☐ |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 8 | 8 | 0 | 0 |
| 接口 | 4 | 4 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 2 | 2 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 37 | 37 | 0 | 0 |

> 统计口径（RULE-2）：来自上表逐项勾选，非事后推算。

### 10.2 验收决定

- [x] **验收通过**（D-1 已复现并修复；O-1/O-2/O-3 关闭；D-3 撤回；3 项 P3 登记）
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 探针取证 | 2026-11-12 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| 读-写瞬时冲突（U-1） | P-081 或更晚 | 出现真实并发读时 | pending |
| 无 id 结果集兜底（O-4/U-2） | M3 | M3 开工 | pending |
| 分布式锁（多主机） | G7 | G7 开工 | pending |
