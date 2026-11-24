---
id: arc-pipeline-skill-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-pipeline-skill-RESEARCH]
upstream: null
---

# 设计：pipeline-as-skill 的 manifest 与加载语义（P-145）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **性质**：决策冻结；零代码。实施批 P-146 按本文件落地。

---

## 1. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | manifest 放技能目录内的 `pipeline.json`；`SKILL.md` front-matter 以 `metadata.manifest` 指向它 | RESEARCH §4 方案 A |
| D-2 | `manifest_version` 为整数，主版本必须为 1；未知主版本拒绝加载 | R3 |
| D-3 | 成功判据 = `run.completed` + 无 `stage.failed` + Stage 23 `stage.completed` | R1；机械可判 |
| D-4 | 阶段子图 = 每阶段一个节点，重试折叠为 `attempts` 计数 | R1；避免图膨胀 |
| D-5 | 每个阶段节点引用 `action_id` 列表、产物哈希与事件 seq 区间 | R1；复用 P-143 |
| D-6 | 版本三元组：`manifest_version` + `arc.stage_map` 快照 + `tools[].version` | R3 |
| D-7 | 安全：只记录 env 键名、参数哈希、相对路径；不含密钥与原始 prompt | R4 |
| D-8 | 加载即可见、不可自动执行；复用需显式调用 | R5 |
| D-9 | 重放只保留字段，不在本批实现 | R6 |

## 2. Manifest 结构

```json
{
  "manifest_version": 1,
  "kind": "pipeline-skill",
  "name": "exp-bootstrap-ci-20261124",
  "description": "成功运行的可复用阶段序列",
  "created_at": "2026-11-24T06:00:00+00:00",
  "integrity": {"algorithm": "sha256", "manifest_sha256": "sha256:..."},
  "arc": {"repo_commit": "6ae4dd4", "stage_map": {"1": "topic_init", "23": "citation_verify"}},
  "success": {
    "run_id": "run-20261124-...",
    "criteria": ["run.completed", "no_stage_failed", "stage23.completed"],
    "completed_at": "2026-11-24T05:40:00+00:00"
  },
  "stages": [
    {
      "stage": 1,
      "name": "topic_init",
      "attempts": 1,
      "event_seq": [1, 4],
      "actions": ["b3c1..."],
      "outputs": {"stage-01/topic.json": "sha256:..."}
    }
  ],
  "tools": [{"name": "echo", "version": "1.0"}],
  "env_keys": ["CUDA_VISIBLE_DEVICES"],
  "readpoints": [
    {"stage": 23, "artifact": "pipeline_summary.json", "digest": "sha256:..."}
  ]
}
```

字段约束：

| 字段 | 约束 |
|---|---|
| `stages[].stage` | 1..23，升序且不重复 |
| `stages[].outputs` 的键 | 相对 run 目录，禁止绝对路径与 `..` |
| `env_keys` | 只有键名，无值 |
| `actions` | 必须能在账本中解析到 `action_id` |
| `integrity.manifest_sha256` | 对去掉该字段后的 canonical JSON 求 sha256 |

## 3. 成功判据

三者同时成立才可导出：

1. 事件流存在 `run.completed`；
2. 全量事件中不存在 `stage.failed`；
3. Stage 23 存在 `stage.completed`。

排除：

- 出现 `E_LOOP_DETECTED` 导致的 `PAUSED`；
- 任一阶段被 `StageHandback` 越界阻断；
- 事件链 `verify_chain` 失败。

## 4. 子图折叠

- 每阶段一个节点；`stage.retried` 只增加 `attempts`，不新增节点。
- PIVOT/回退：只记录最终成功的那次；被替换的版本记入 `attempts` 与 `event_seq` 区间。
- 未执行阶段不写入 `stages`；`arc.stage_map` 仍保留全量 23 项，供兼容性比对。

## 5. 版本与兼容

| 比对 | 不匹配时 |
|---|---|
| `manifest_version` 主版本 | 拒绝加载（fail-closed） |
| `arc.stage_map` 与当前 `STAGE_NAME_TO_NUMBER` | 拒绝加载（阶段语义已变） |
| `tools[].name` 在当前注册表缺失 | 拒绝加载 |
| `tools[].version` 不一致 | 警告，不拒绝（允许小版本漂移） |
| `integrity.manifest_sha256` | 拒绝加载 |

## 6. 安全

- 不含密钥、token、原始 prompt；只存键名与哈希。
- 路径必须相对；`:` 或前导 `/` 一律拒绝。
- pipeline 技能只被列出，不被任何执行路径自动调用；显式调用需带 `--skill <name>`。
- 加载失败一律 fail-closed，不降级为「部分可用」。

## 7. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | manifest 不含密钥、原始 prompt、绝对路径 |
| J-2 | 主版本或阶段映射不匹配即拒绝加载 |
| J-3 | 成功判据三项缺一不可 |
| J-4 | 每阶段一个节点，重试不膨胀子图 |
| J-5 | 加载不触发执行 |
| J-6 | `manifest_sha256` 覆盖除自身外全部字段 |

## 8. 留待实施批裁决

| 编号 | 问题 | 默认倾向 |
|---|---|---|
| Q1 | 重放语义：完全按 manifest 还是允许参数覆盖 | 先只读展示，重放另开批 |
| Q2 | 部分复用（只取某几阶段） | 首版不支持 |
| Q3 | 与 builtin 技能重名 | 前缀 `pipeline-`，冲突拒绝 |
| Q4 | 多 run 合并成一个技能 | 首版不支持 |
