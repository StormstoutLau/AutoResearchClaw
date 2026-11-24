---
id: arc-g7-review-fixes-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-25
depends: [arc-g7-review-fixes-IMPLEMENTATION, arc-g7-review-fixes-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 复审修复批（P-164）

> **状态**：验收完成；25/26 通过 + 1 待 CI（C-2）。
> **计数**：**26 项 = 文档 4 + 功能 7 + 接口 4 + 不变式 5 + 错误 3 + 兼容 3**。

## 0. DoR / DoD

- **DoR**：代码锚点、探针或测试夹具已存在；测试可在本机重复运行。
- **DoD**：独立读数写入 §8；禁止用测试总数推算分项（RULE-2）。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 四条缺陷均有代码锚点 | RESEARCH v1.0 | 每条含文件+行号+探针 | ✅ | §1 四行均含锚点 |
| D-2 DESIGN 修法覆盖 D-1..D-4 | 四文档 | 决策表逐条对应 | ✅ | D-1..D-4 与四条缺陷一一对应 |
| D-3 IMPLEMENTATION 接口在 CHECKLIST 有验收项 | 四文档 | §2–§4 每签名至少一项 | ✅ | I-1..I-4 覆盖 verify_chain/助手/失败工件 |
| D-4 术语一致（偏移链/逃生舱/进程组/失败工件） | 四文档 | 四文档用法一致 | ✅ | 四文档 grep 一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 偏移链可验 | T01 夹具 | 删首段后 `verify_chain(start_seq=2)` True，默认 False | ✅ | T01 passed |
| F-2 retention 逃生舱 | T02 夹具 | 默认 `retention_limited` 且不 ok；allow=True 时 ok/converged/chain_ok 全 True | ✅ | T02 passed |
| F-3 偏移模式仍抓篡改 | T03 夹具 | 首条 payload 篡改 + 中段缺口均判红 | ✅ | T03 passed（payload + middle gap 两用例） |
| F-4 POSIX 进程树 | T04 | `start_new_session=True`；组长 killpg；非组长/OSError 回退 | ✅ | T04 passed（5 用例） |
| F-5 死代码清零 | 读码 | 重复 is_dir / killed / mtime 零命中 | ✅ | grep：is_dir 1 处、无 killed/_mtime |
| F-6 真实 token 溢出工件 | T06 | 五件套齐全；ob4 true；usage_matches true；total 0 | ✅ | T06 passed |
| F-7 真实 worker 溢出工件 | T07 | 同上（kind=workers） | ✅ | T07 passed |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `verify_chain(start_seq=1)` 默认兼容 | 既有 event_log 测试 | 不传参行为不变 | ✅ | test_event_log*.py 全过 |
| I-2 verifier 只读 | T02 | 调用前后文件清单/哈希不变 | ✅ | T02 复用 P-160 只读断言 |
| I-3 `_spawn_kwargs` / `_posix_kill_tree` 可注入 | T04 | 假 getpgid/killpg/kill 可驱动 | ✅ | T04 passed |
| I-4 `_write_budget_failure` 不覆盖既有工件 | T08 | over_budget `charged_tokens==budget+1` 保持 | ✅ | T08 passed |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 normal chain 零变化 | T09 | 既有 event_log/soak 测试全过 | ✅ | 76 passed / 0 failed |
| J-2 偏移只跳首条 prev | T01/T03 | 首条 payload 仍验；零 prev 判红 | ✅ | T01/T03 passed |
| J-3 killpg 组长守卫 | T04 | 非组长不 killpg | ✅ | T04 passed |
| J-4 失败工件只补缺 | T08 | 已有工件字节不变 | ✅ | T08 passed |
| J-5 不改 gate/CLI/schema | git diff | 相关文件零改动 | ✅ | git diff 仅 4 个实现文件+3 测试 |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 run 目录缺失 | 既有测试 | 行为不变（failed/no_resumable_run） | ✅ | test_driver_rejects_missing_run_dir passed |
| E-2 归档不可读 | T02 | `archive_unreadable`，不伪装 ok | ✅ | T02 passed |
| E-3 非 token 超限 | T07 | workers/wall/depth 也落 `budget_exceeded` 工件 | ✅ | T07 passed（workers） |

## 6. 兼容性

| 环境 | DoR | DoD | 状态 | 说明 |
|---|---|---|---|---|
| C-1 Python 3.13 本机 | 本机 3.13.5 | 新增测试全绿 | ✅ | 12 passed in 5.35s |
| C-2 Python 3.11–3.14 CI | CI 矩阵 | 两轮 8/8 | ⏳ | 第一轮 8/8（run 45459190463）；第二轮由本提交触发 |
| C-3 Windows/POSIX | 本机 Windows + CI Linux | Windows 全绿；POSIX 分支由单测覆盖 | ✅ | Windows 12 passed；T04 覆盖 POSIX 分支 |

## 7. 测试映射

| 测试 | 文件 | 覆盖 |
|---|---|---|
| T01 | `tests/test_soak_verifier_retention.py` | F-1、J-2 |
| T02 | 同上 | F-2、I-2、E-2 |
| T03 | 同上 | F-3、J-2 |
| T04 | `tests/test_soak_driver_kill.py` | F-4、I-3、J-3 |
| T05 | `tests/test_soak_driver.py`（既有） | F-5、E-1 |
| T06 | `tests/test_orchestration_overflow.py` | F-6 |
| T07 | 同上 | F-7、E-3 |
| T08 | 同上 | I-4、J-4 |
| T09 | 既有 soak + orchestration 套件 | I-1、J-1、C-1 |

## 8. 验收统计（Step 10 回填）

| 分类 | 总数 | 通过 | 失败 | 待定 |
|---|---|---|---|---|
| 文档 | 4 | 4 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 4 | 4 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误 | 3 | 3 | 0 | 0 |
| 兼容 | 3 | 2 | 0 | 1（C-2 CI） |
| **合计** | **26** | **25** | **0** | **1** |

> 算术：4+7+4+5+3+3 = 26；25+0+1 = 26。C-2 两轮 CI 全绿后改 26/26。

## 9. ADD 审计（Step 10）

| 阶段 | 结果 | 证据 |
|---|---|---|
| Phase 0 Spec 质量门 | 4/4 可测试约束 | 26 项均有机械 DoD；无不可判词 |
| Phase 1 完整性 | 四条缺陷均有落点 | F-1..F-7 与 RESEARCH §1 一一对应 |
| Phase 2 忠实度 | 1 处实现偏差已修 | `_write_budget_failure` 初版用 `task.budget` 而非运行时 `budget`，T06 判红后修正 |
| Phase 3 必要性 | 两个助手为可测试性所必需 | `_spawn_kwargs`/`_posix_kill_tree` 在 Windows 上无法直接跑 POSIX 分支 |
| Phase 4 语义 | 意图成立 | 默认失败仍红（retention_limited）、逃生舱绿、篡改仍红；fixture 不被覆盖 |

**取证矩阵**：pytest 新增 12 用例（E1）→ F-1..F-7；76 passed 定向回归（E1）→ J-1；全量 3905 passed（E1）→ C-1；grep 死代码零命中（E1）→ F-5；矩阵 OB-1..OB-5 全 PASS（E2）→ 无回归。
**发现**：0 P1 / 0 P2 / 0 P3（本批只修不新增）。
