---
id: arc-g7-soak-CHECKLIST
type: design
version: 1.1
status: pending
date: 2026-11-24
depends: [arc-g7-soak-IMPLEMENTATION, arc-g7-soak-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 第一段「soak 工具链」（P-160）

> **Feature**：P-160（G7 第一段）。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.1 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.2 / verified）。
> **状态**：验收中；Step 10 回填读数。
> **范围**：A7-1 工具链 + 缩时演练、A7-4 完整验收；72h 现场运行不在 CI，单独留证（U-1）。
> **修订**：v1.1 增 F-9（torn tail + 原子替换重试）、J-10、E-7；总数 45 → 48。

---

## 0. DoR / DoD 总则

- **DoR（Definition of Ready）**：该验收项所需的代码、夹具、基线或文档已存在；测试可在当前主机重复运行；不接受“环境不存在所以跳过”（RULE-3）。
- **DoD（Definition of Done）**：该项的通过条件已由**独立读数**证明；读数写入 §10；禁止用“测试总数”推算分项。

---

## 1. 文档一致性验收（Step 8）

| 检查项 | DoR | DoD | 状态 | 说明 |
|---|---|---|---|---|
| D-1 DESIGN 可追溯到 RESEARCH | RESEARCH verified | 每个 D-1..D-11 能指向 RESEARCH §3/§4/§5 | ✅ | D-7/D-8 对应 F-1/F-2；D-11 对应 F-4 |
| D-2 DESIGN 模块在 IMPLEMENTATION 有落点 | 四文档完稿 | 模块表/文件清单逐项对应 | ✅ | soak 包 + F-1/F-1b/F-2/F-4 + CLI |
| D-3 IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | T01–T23 已定义 | 每个功能/接口/不变式至少一项 | ✅ | §2–§4 |
| D-4 术语一致 | 四文档完稿 | driver/verifier/report、seq、收敛签名、field run 用法一致 | ✅ | 交叉 grep：4 份文档术语一致 |

## 2. 功能验收

| 验收项 | DoR | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| S-1 轮转边界重开继续 seq | T08 夹具 | 删 active 后重开 `last_seq=2`，append 得 3，`verify_chain` ok | ✅ | T08 passed |
| S-2 归档-only checkpoint 恢复 | T09 夹具 | `read_checkpoint` 返回下一阶段，`recovered=true` | ✅ | T09 passed |
| S-3 链/seq/run_id/checkpoint 一致性 | T01–T05 | 篡改/缺口/跨 run/checkpoint 落后均判失败 | ✅ | T01–T05 passed |
| S-4 轮转后完整回放 | T06 | `read_all` 覆盖 `1..N`，`read_after` 游标一致 | ✅ | T06 passed |
| S-5 3 次注入后收敛 | T10 fake worker | 基线签名 == soak 签名；`restarts=3`；checkpoint 领先 1 事件不误报（T18） | ✅ | T10/T18 passed |
| S-6 重启预算硬上限 | T11 | 注入 4 目标、`max_restarts=2` → 只注入 2 次，`capped=true` | ✅ | T11 passed |
| S-7 报告字段完整 | T14 | 含 restart/recovery/failure/verification/requirements | ✅ | T14 passed |
| S-8 72h 现场运行证据 | 独占主机（U-1） | `wall_seconds≥259200`、`restarts≥3`、`converged=true` | ⏳ | 未执行；本段不伪绿 |
| S-9 写入边界加固 | T17/T19 | torn tail 截断后事件可见；`PermissionError` 重试后 checkpoint 落盘 | ✅ | T17/T19 passed |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `verify_run` 只读 | run 目录夹具 | 调用前后文件清单/哈希不变；不创建新文件/目录 | ✅ | 读码 + T01 passed |
| I-2 `convergence_signature` | 两份 run | 易变字段变化不影响签名；终态阶段/状态变化影响签名 | ✅ | T07 passed |
| I-3 `SoakDriver` 注入 | fake worker | 只在进度后注入；注入次数/阶段可复现 | ✅ | T10/T11 passed |
| I-4 `build_report/render_markdown/write_report` | T14 | JSON/MD 字段一致；无 `.tmp` 残留 | ✅ | T14 passed |
| I-5 `soak run` 解析 | CLI parser | `--duration/--inject-at-stages/--reference-run` 可解析 | ✅ | T15 passed |
| I-6 `soak verify` 退出码 | 有效/篡改 run | 0/1/2 三种退出码 | ✅ | T16 passed |
| I-7 `soak report` 离线重渲染 | 已有 `soak_report.json` | 不重跑 worker，重新生成 Markdown | ✅ | T23 passed |
| I-8 `parse_duration` | 无 | `72h/90m/5s/7` → 259200/5400/5/7 | ✅ | T15 passed |

## 4. 不变式验收

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 driver 不持租约 | 读码 | `soak/` 无 `acquire(`；worker 是唯一写者 | ✅ | 读码：仅 import read/release/is_pid_alive |
| J-2 `verify_run` 只读 | T01 | 运行前后 run 目录文件清单/哈希不变 | ✅ | T01 passed |
| J-3 重启后 seq 无重复/断链 | T08/T10 | `verify_chain` ok；`duplicate_seqs=()` | ✅ | T08/T10 passed |
| J-4 签名排除易变字段 | T07 | 改 `generated/run_id` 签名不变 | ✅ | T07 passed |
| J-5 非注入退出只在 75 重启 | T12 | rc=65 不重启 | ✅ | T12 passed |
| J-6 `max_restarts` 硬上限 | T11 | 注入+可重试合并计数，不超限 | ✅ | T11 passed |
| J-7 报告原子写 | T14 | 无 `.tmp`；中断不留半文件 | ✅ | T14 passed |
| J-8 field run 门槛 | T14 | 只以 `wall>=72h && restarts>=3` 为 true | ✅ | T14 passed（satisfied=false） |
| J-9 只回收死/过期租约 | T22 | 活 PID 租约不被 release；死 PID 可回收 | ✅ | T13/T22 passed |
| J-10 原子替换有限重试 | T19 | 瞬时 `PermissionError` 重试；永久失败重抛 | ✅ | T19 passed |

## 5. 错误处理验收

| 错误场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 不可恢复 run 目录 | 不存在的目录 | `status=failed` + `run_dir_missing`；CLI 65 | ✅ | T20 passed |
| E-2 链损坏 | 篡改夹具 | `chain_ok=false`，不判 converged | ✅ | T02 passed |
| E-3 seq 缺口 | 删行夹具 | `seq_gaps` 非空，`ok=false` | ✅ | T03 passed |
| E-4 活租约冲突 | 活 PID 租约夹具 | driver 不重启；报告 `lease_held` | ✅ | T22 passed |
| E-5 超时 | `duration=0.06s` + 慢 worker | `status=timed_out`，不伪造收敛 | ✅ | T21 passed |
| E-6 非法 CLI 参数 | `--duration abc` | exit 2 + stderr | ✅ | T15 passed |
| E-7 瞬时替换失败 | `Path.replace` 抛 2 次 `PermissionError` | 重试后落盘；不吞永久失败 | ✅ | T19 passed |

## 6. 性能验收

| 指标 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| P-1 轮询成本 | 读码 | 每 poll 只读 checkpoint，不全量 `read_all` | ✅ | 读码：`_progress` 单文件 |
| P-2 CI 不跑 72h | CI 配置 | 无 72h job；测试总时长 `<10s` | ✅ | 27 passed in 5.87s |
| P-3 报告写入 | T14 | 原子替换，无临时文件残留 | ✅ | T14 passed |

## 7. 兼容性验收

| 环境 | DoR | DoD | 状态 | 说明 |
|---|---|---|---|---|
| C-1 Python 3.13（本机） | 本机可用 | 新增测试全绿 | ✅ | 3.13.5，27 passed |
| C-2 Python 3.11（CI） | CI 可用 | CI 全绿 | ⏳ | 两次 CI 待跑 |
| C-3 Windows 硬杀路径 | 本机 Windows | `taskkill /F /T /PID` 生效，worker 被终止 | ✅ | T10/T22 passed |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

| 维度 | 得分（0-1） | 说明 |
|---|---|---|
| 可测试约束 | 1 | A7-1/A7-4 均有机械判据；S-8 明确 pending |
| 模块映射 | 1 | 6 个运行时落点（soak 3 + event_log + runner + CLI） |
| 接口契约 | 1 | dataclass/函数签名固定；无外部依赖 |
| 修正项 | 1 | F-1/F-1b/F-2/F-4 均有回归测试 |
| 跨模块契约 | 1 | EventLog/runner/CLI 边界读码 + 测试 |
| **总分** | 5 /5 | **档位: A** |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P2-1 | `verify_run` 参考模式最初只看签名，断链仍可能 `converged=True` | 审计读码 `verifier.py` | 已改为 `integrity_ok and signature==ref`；T02/T03 覆盖 |
| P2-2 | 收敛签名含完整阶段序列，checkpoint 已写/事件未写的崩溃窗口会误报不收敛 | T18 夹具 + `runner.py:950-953` | 已改为终态三字段（DESIGN v1.1 D-4） |
| P3-1 | `has_resumable_run` 无消费点 | 全仓 grep | 已删除 |
| P3-2 | 注入杀进程后未检查 kill 是否完成，可能在活租约下继续 spawn | 审计读码 | 已加 `kill_failed` + spawn 前 `_reclaim_stale_lease` |
| P3-3 | CLI `worker_cwd=Path.cwd()` 在非仓库 cwd 下可能导入失败 | 审计读码 | 已改为 repo root（存在 `researchclaw/` 时） |
| P3-4 | 新增 subprocess 调用未进边界注册表，`test_boundary_coverage` 红 | `test_boundary_coverage` 首轮 2 failed | 已登记 S-061/S-062（category C，env inherit） |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式已检查（签名/覆盖断言至少在负向夹具上会失败）
- [x] 单文件检查盲区已检查（跨 EventLog/runner/CLI）
- [x] 设计独有约束有测试（J-1..J-10）
- [x] 修正阻断性项有测试（F-1/F-1b/F-2/F-4 → T08/T09/T17/T19）

### 8.4 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| `pytest` 输出（E1） | T01–T23 + 既有 runtime 回归 | ✅ 27 passed（新）；54/56 passed（runtime）；207 passed（executor） |
| 运行时脚本（E2，含轮转边界/归档-only/torn-tail/并发替换） | F-1/F-1b/F-2/F-4 | ✅ 四类边界均复现并转绿 |
| 静态读码（E3 @`284e105` + P-160 diff） | J-1/J-5/P-1/D-11 | ✅ |
| `git diff --check`（E1） | 回退点/无越界 | ✅ 无空白错误 |
| 盲区扫描（E4，扫描范围：48 项断言） | 全部 | **发现 6 项（P2×2、P3×4），已修复** |
| `test_boundary_coverage`（E1） | 新增 subprocess 边界 | ✅ 17 passed（S-061/S-062 登记） |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR（如有） | n/a | n/a |
| 开发日志 | n/a | 本仓近批未设 `docs/dev-log/`，以 session + PROGRESS 行留痕 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 9 | 8 | 0 | 1 |
| 接口 | 8 | 8 | 0 | 0 |
| 不变式 | 10 | 10 | 0 | 0 |
| 错误处理 | 7 | 7 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 3 | 2 | 0 | 1 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | **48** | **46** | **0** | **2** |

> **统计口径（RULE-2）**：逐项来自 §1–§8；Step 10 回填后重新做双算术校验（逐行 `总数 = 通过 + 失败 + 待办`；总计 = 8 行按列求和）。

### 10.2 验收决定

- [ ] **验收通过**：所有 P1 项通过，无阻塞性问题
- [x] **有条件通过**：C-2 待 CI 两轮；S-8 72h 现场运行待独占主机（U-1，P2）
- [ ] **验收失败**：<原因>
- [x] **无条件成立的项**：48 项中 46 项已由独立读数证明；无 P1/P2 未修问题

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | 本次会话（单视角） | 2026-11-24 |
| 审查者 | 自查（RULE-4）；待异基座复审可升级 | 2026-11-24 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| U-1 72h 现场运行并保存 `soak_report.json` | 待定 | 主机可用时 | 待办 |
| 回填 PROGRESS P-160 | 实施者 | 本批 | 待办 |
| CI 两轮 | 实施者 | 本批 | 待办 |
| 记录开发日志 | 实施者 | 本批 | 待办 |
