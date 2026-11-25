---
id: arc-g7-concurrency-dual-plane-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-RESEARCH, arc-g7-field-run-decision-20261125, arc-g7-soak-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：G7 并发段修复（P-173）

> **范围**：① registry 损坏从「静默清空」改为「备份恢复 / 双损坏 fail-closed」；② A7-4 正式验收（轮转 + 压缩 + 缺口判红）；③ A7-1 72h field run 的接入方案与配置模板（执行待端点确认）。
> **不在本批**：真正 72h 运行；A7-5 独立新人盲测（U-172-1）；裸 `run` 准入（U-172-2）。

## 1. 本仓现状（T1）

| 事实 | 证据 |
|---|---|
| P-172 的 registry 写在 `tmp + os.replace`，但损坏时 `_load` 返回空状态并设 `last_error="corrupt_registry"` | [admission.py L176-L212](../../researchclaw/runtime/admission.py#L176-L212)（P-172 版本） |
| 空状态会丢 `fencing` 与在册槽；下一次 acquire 从 fencing=1 重新开始 | [admission.py L296-L320](../../researchclaw/runtime/admission.py#L296-L320) |
| supervisor 在 `_admit` 只处理 `AdmissionTimeout`，无损坏分支 | [supervisor.py L122-L152](../../researchclaw/runtime/supervisor.py#L122-L152) |
| P-160 已有轮转/压缩/偏移链测试；A7-4 的「按 run_id+seq 回放」尚无用例固化 | [tests/test_event_log.py](../../tests/test_event_log.py)、[tests/test_event_log_roll_recovery.py](../../tests/test_event_log_roll_recovery.py) |
| `verify_run` 对 `first_seq>1` 且无 `events.1-*` 段判 `retention_limited`，默认红 | [verifier.py L263-L268](../../researchclaw/soak/verifier.py#L263-L268) |
| P-160 CHECKLIST 的 S-8（72h 现场）仍为 pending（U-1） | [CHECKLIST.md L49](../arc-g7-soak/CHECKLIST.md#L49) |
| 现场已确认：裸 API + 同一模型 + 小规模真实实验；模板见 `config.g7-field.example.yaml` | [field decision §1/§7](../../docs/arc-g7-field-run-decision-20261125.md) |

**关键约束**：
1. 不能静默清空 registry：fencing 回退会破坏「写者拒旧 token」的语义（P-172 E6）。
2. 双损坏必须 fail-closed：宁可拒绝启动，不可超容/超发。
3. A7-4 的负向面必须判红：归档缺口不能因 `allow_retention_gap` 默认值而静默通过。
4. A7-1 的 72h 墙钟不能压缩、不能虚拟时钟；执行前必须有真实 endpoint。

## 2. 外部证据

| # | 来源 | 关键结论 | 本批借用 |
|---|---|---|---|
| E1 | [SQLite — Atomic Commit](https://www.sqlite.org/atomiccommit.html) | 原子提交依赖「先写日志/备份、再改主文件、最后清理」；hot journal 用于崩溃后恢复；仅靠文件锁不能防掉电 | 备份先于主文件写入 + revision 选新；不把 `os.replace` 当唯一保障 |
| E2 | [Kubernetes — Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) | 配额在准入阶段拒绝；系统不因内部状态不可读而放行超额请求 | 双损坏 fail-closed，不 spawn |
| E3 | [SQLite — WAL](https://www.sqlite.org/wal.html) | 单写者 + checkpoint 回收；分段/归档后仍可按序重放 | A7-4 轮转 + gzip 后按 seq 回放 |

## 3. 综合分析

1. **备份 + revision 比单文件更稳**（E1）：主文件损坏时读备份；两份都坏则拒绝，而不是丢掉 fencing。[★★★★☆]
2. **fail-closed 是唯一的诚实选择**（E2）：registry 损坏时无法证明容量与 fencing，放行等于赌运气。[★★★★★]
3. **A7-4 的重点是负向面**（E3）：正向回放已有测试；必须证明「删掉最旧归档段 → 默认判红」，否则验收是纸面的。[★★★★☆]
4. **A7-1 的阻塞是现场，不是代码**：工具链、方案、模板已齐；72h 需要 endpoint 与独占主机。[★★★★☆]

## 4. 未决项

- **U-1 集群端点细节**
  - 判据：`/v1/models` 可列出目标模型；8k 上下文与 JSON mode 冒烟通过
  - 触发条件：启动 72h 前
  - 当前倾向：裸 API + SSH 转发 127.0.0.1
  - 证据等级：E3（field plan）

- **U-2 A7-4 的归档保留参数**
  - 判据：`retention_days/archive_days` 用 Q9 默认（30/365）；缺口默认红
  - 触发条件：正式验收
  - 当前倾向：不改默认，只在显式 `allow_retention_gap=True` 时放行
  - 证据等级：E3
