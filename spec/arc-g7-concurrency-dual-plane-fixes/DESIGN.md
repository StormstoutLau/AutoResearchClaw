---
id: arc-g7-concurrency-dual-plane-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-fixes-RESEARCH, arc-g7-concurrency-dual-plane-DESIGN, arc-g7-field-run-decision-20261125]
upstream: arc-master-roadmap
---

# 设计：G7 并发段修复（P-173）

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | registry 采用 **主 + 备份 + revision**：每次保存先写主 tmp，再复制到备份并替换，最后替换主；加载取 revision 更高的有效副本 | 只写主文件；损坏即清空 | E1 的日志/备份先写；revision 解决「备份更新、主较旧」的崩溃窗口 |
| D-2 | 主损坏 → 读备份并回写主（`last_error=recovered_from_backup`）；主/备都损坏 → `RegistryCorrupt` | 静默返回空状态 | 空状态会回退 fencing 并超容；fail-closed 才是诚实边界 |
| D-3 | supervisor 捕获 `RegistryCorrupt` → 记 `admission_corrupt` 日志、返回 CONFIG(78)、**不 spawn** | 继续 spawn 或重试 | E2 的准入拒绝；非 retryable 避免自旋 |
| D-4 | A7-4 用「小段强制滚动 → run_id+seq 全回放 → gzip 后复验 → 删最旧段默认判红」四段式 | 只测正向回放 | 负向面是验收的承重墙；P-160 S-8 仍是 72h 现场 |
| D-5 | A7-1 接入方式锁定：**裸 API + SSH 转发 + local_only + 同一模型 + sandbox 小规模真实实验** | ACP / 第三方 agent / simulated | P-172 的 budget/local_only/inflight 只覆盖 `LLMClient`；simulated 会污染 Stage 20 |
| D-6 | 提供 `config.g7-field.example.yaml` 作为唯一现场模板；真实端点/凭据不入库 | 在文档里散落配置片段 | 可复制、可校验、可脱敏 |
| D-7 | registry 备份文件 `registry.bak.json` 与主文件同目录、同锁保护 | 单独目录/数据库 | 复用 `exclusive_lock`；备份与主原子替换在同一临界区 |

## 2. registry 状态机

```
load:
  primary = read(registry.json)      # 失败 → None
  backup  = read(registry.bak.json)  # 失败 → None
  if both None and at least one file exists: raise RegistryCorrupt
  if both None and no file: return empty(revision=0)
  if backup None: return primary
  if primary None or backup.revision > primary.revision:
      restore(primary ← backup); return backup
  return primary

save(state):
  state.revision += 1
  write tmp; fsync
  copy tmp → backup.tmp; replace backup
  replace tmp → primary
```

- `revision` 只在 `_save` 递增；加载不修改。
- 备份先于主替换：崩溃窗口内备份更新，下一次加载选备份并回写主。
- `_restore` 用 `copyfile + os.replace`，不经过备份，避免递归。

## 3. 容量与 fencing（不变）

- 容量规则沿用 P-172：`normal_cap = max_attempts - hitl_priority_slots`，总在册 ≤ `max_attempts`。
- `fencing` 只增不减；恢复后从备份的 fencing 继续，不回退。
- 同 run 幂等、`slot_id+fencing` 双条件释放不变。

## 4. A7-4 验收矩阵

| 场景 | 构造 | 期望 |
|---|---|---|
| 轮转后回放 | `max_segment_events=3`，追加 10 条 | 段 `1-3/4-6/7-9`；`read_all` seq=1..10；chain ok |
| gzip 后回放 | 段 mtime 置旧，`apply_retention(30,365)` | 三个 `.gz`；seq=1..10；chain ok；`verify_run.ok` |
| 归档缺口 | 删除 `events.1-3.jsonl.gz` | `retention_limited=True`、`ok=False`、`converged=False`、`first_seq=4` |
| run_id 过滤 | 所有事件 `run_id == run_dir.name` | 无跨 run 混入 |

## 5. A7-1 执行方案（已确认）

- 接入：`llm.provider=openai-compatible`、`base_url=http://127.0.0.1:18000/v1`、`local_only=true`。
- Stage 10/13：同一裸 API 模型（`cli_agent.provider=llm`）。
- 实验：`experiment.mode=sandbox`、`time_budget_sec=600`、固定小数据集；不用 simulated。
- 验收：`soak_report.json.field_run.satisfied == true`（wall ≥ 259200s、restarts ≥ 3）、`verify_run.ok/converged`、`ops` 读数一致。
- 详见 [field decision](../../docs/arc-g7-field-run-decision-20261125.md)。

## 6. 不变式

| ID | 不变式 |
|---|---|
| J-1 | 主损坏、备有效 → 恢复且 fencing 不回退 |
| J-2 | 主备都损坏 → `RegistryCorrupt`，不 spawn |
| J-3 | 备份始终是「最近一次成功保存」的状态（revision 单调） |
| J-4 | 恢复后容量规则不变，不超 `max_attempts` |
| J-5 | A7-4 正向：轮转/gzip 后 seq 完整、链可验 |
| J-6 | A7-4 负向：归档缺口默认判红 |
| J-7 | A7-1 配置模板不含真实凭据，`local_only` 可加载 |
| J-8 | 既有默认行为不变（无 registry 时从空状态开始） |

## 7. 错误语义

| 场景 | 行为 |
|---|---|
| 主缺失、备存在 | 从备份恢复并回写主 |
| 主损坏、备有效 | 从备份恢复；`last_error=recovered_from_backup` |
| 主备都损坏 | `RegistryCorrupt`；supervisor 返回 CONFIG，日志 `admission_corrupt` |
| 备份 revision 更高 | 选备份并回写主 |
| 两份 revision 相同 | 选主 |
| A7-4 删段 | `retention_limited` 计入 problems |

## 8. 回退点

- 还原 `admission.py` 的 `_load/_save` 与 supervisor 的 `except RegistryCorrupt` 即可回到 P-172 行为。
- A7-1 模板/方案是纯文档，删除不影响运行时。
