---
id: arc-g7-concurrency-dual-plane-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-fixes-IMPLEMENTATION, arc-g7-concurrency-dual-plane-fixes-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 并发段修复（P-173）

> **状态**：**26/28 通过 + 2 待办**（C-2 CI 待回填；C-3 A7-1 72h 待现场，未执行不伪绿）。
> **计数**：**28 项 = 文档 4 + 功能 8 + 接口 4 + 不变式 6 + 错误 3 + 兼容 3**。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 回原文 | RESEARCH v1.0 | E1-E3 含 URL/要点 | ✅ | §2 三条 |
| D-2 DESIGN 覆盖实现 | 四文档 | D-1..D-7 有落点 | ✅ | D-1..D-7 ↔ IMPLEMENTATION §1 |
| D-3 IMPLEMENTATION 源码锚点 | 四文档 | ≥10 锚点 | ✅ | §1 表 12 行 |
| D-4 术语一致 | 四文档 | revision/backup/fail-closed 同义 | ✅ | 四文档一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 主损坏恢复 | T-A1 | fencing 不回退、主被回写 | ✅ | `test_corrupt_primary_recovers_from_backup` |
| F-2 主缺失恢复 | T-A2 | 从备份恢复并回写 | ✅ | `test_missing_primary_recovers_from_backup` |
| F-3 双损坏 fail-closed | T-A3 | 抛 `RegistryCorrupt` | ✅ | `test_both_copies_corrupt_fail_closed` |
| F-4 supervisor 不 spawn | T-S1 | 退出 CONFIG、日志 `admission_corrupt` | ✅ | `test_corrupt_registry_fails_closed_without_spawning` |
| F-5 revision/fencing 单调 | T-A1/T-A4 | 恢复后 fencing=f+1 | ✅ | F-1/F-2 + `test_registry_file_is_readable...` |
| F-6 轮转后回放 | T-R1 | seq=1..10、chain ok | ✅ | `test_rotation_keeps_every_seq_readable_by_run_id` |
| F-7 gzip 后回放 | T-R2 | 三个 `.gz`、seq 完整、verify ok | ✅ | `test_compressed_segments_still_replay` |
| F-8 归档缺口判红 | T-R3 | `retention_limited`、ok/converged False | ✅ | `test_archived_gap_is_reported_as_failure` |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `RegistryCorrupt` 可导入 | DESIGN §1 | 异常类型公有 | ✅ | [admission.py L37](../../researchclaw/runtime/admission.py#L37) |
| I-2 备份路径/同锁 | DESIGN §1 | `registry.bak.json` + `registry.lock` | ✅ | [L27](../../researchclaw/runtime/admission.py#L27)、[L146](../../researchclaw/runtime/admission.py#L146) |
| I-3 `last_error` 语义 | DESIGN §7 | `recovered_from_backup` | ✅ | F-1/F-2 |
| I-4 现场模板 | DESIGN §5 | 可加载、无真实凭据、loopback | ✅ | `config.g7-field.example.yaml` |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 主坏备好 → 恢复且 fencing 不回退 | DESIGN §6 | fencing=f+1 | ✅ | F-1 |
| J-2 双坏 → 不 spawn | DESIGN §6 | spawn 未调用 | ✅ | F-4 |
| J-3 备份是最近成功保存 | DESIGN §6 | revision 单调 | ✅ | `_save` [L220](../../researchclaw/runtime/admission.py#L220) + F-5 |
| J-4 恢复后容量不变 | DESIGN §6 | active ≤ max | ✅ | F-3/F-4 + P-172 容量用例 |
| J-5 轮转/gzip 后 seq 完整 | DESIGN §6 | 1..10 | ✅ | F-6/F-7 |
| J-6 缺口默认判红 | DESIGN §6 | `retention_limited` | ✅ | F-8 |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 主缺失备在 | DESIGN §7 | 恢复 | ✅ | F-2 |
| E-2 主坏备好 | DESIGN §7 | 恢复 | ✅ | F-1 |
| E-3 双坏 | DESIGN §7 | `RegistryCorrupt` | ✅ | F-3 |

## 6. 兼容性与现场

| 环境/项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| C-1 本机 3.13 | 3.13.5 | 修复面全绿 | ✅ | 33 passed |
| C-2 CI 3.11–3.14 | CI 矩阵 | 两轮 8/8 | ⏳ | 待推送后回填 |
| C-3 A7-1 72h 现场 | 端点 + 独占主机 | wall≥259200、restarts≥3、converged | ⏳ 待现场 | 方案/模板已就绪；未执行，不伪绿 |

## 7. 诚实边界

1. **A7-1 未执行**：本批只落方案/模板/判据；72h 必须真实墙钟，不能用虚拟时钟或人为重启补数。
2. **A7-4** 机械验收通过；field run 完成后需在真实 run 目录复跑 `soak verify` 留证。
3. **A7-5** 仍为部分（U-172-1），本批不改变。
4. **registry 恢复**只保证「最近一次成功保存」的状态；如果主备在同一磁盘同时损坏（如坏道），仍会 fail-closed。

## 8. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | 备份与主同目录，单盘故障无法恢复 | DESIGN §8 声明；跨盘备份留后续 |
| P3-2 | low | `last_error` 是进程内状态，不落盘 | 仅用于日志/测试；不改契约 |
| P3-3 | medium | A7-1 仍未执行，G7 不能收口 | C-3 显式 pending |

## 9. 门禁读数

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / 0 结果 / **0 违规** |
| `step-gate` | **5/5 pass** |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-173 digest_bound=1` |
| `pre-commit` | **10/10 Passed** |
| 两轮 CI | 待推送后回填 |
