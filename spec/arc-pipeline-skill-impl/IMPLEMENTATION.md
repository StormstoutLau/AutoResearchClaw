---
id: arc-pipeline-skill-impl-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-pipeline-skill-impl-DESIGN]
upstream: null
---

# 实施：pipeline-as-skill（P-146）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：2 个新增文件；零 workflow、零既有模块改动。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/skills/pipeline_manifest.py` | 新增 | 导出、校验、发现三个入口 |
| `tests/test_pipeline_skill.py` | 新增 | 10 条用例 |

既有 `skills/loader.py`、`skills/schema.py`、`runtime/action_ledger.py` 零改动。

## 2. 读数

```text
$ python -m pytest tests/test_pipeline_skill.py -q
..........                                                               [100%]
10 passed in 0.59s

$ python -m pytest tests/test_tool_events.py tests/test_tool_registry.py tests/test_action_ledger.py -q
56 passed in 2.87s
```

覆盖：导出成功路径、四项成功判据、重试折叠、完整性篡改、阶段映射漂移、未知工具与版本漂移、绝对路径拒绝、发现入口。

## 3. 实现要点

### 3.1 导出

- `EventLog.verify_chain()` 先校验，再读事件。
- 阶段节点取 `stage.completed` 的 stage；`attempts` = `stage.started` + `stage.retried` 次数。
- 动作归属：`event_seq_call` 落在最近 `stage.started` 之后即归该阶段。
- `outputs`：账本记录的文件路径转 run 相对路径，越界丢弃。
- `env_keys`：账本 `env` 的键名并集。
- `readpoints`：`pipeline_summary.json` 存在则记录哈希。

### 3.2 校验

- `manifest_version` 必须为 1；`kind` 必须为 `pipeline-skill`。
- `integrity` 重算，覆盖除自身外全部字段。
- `arc.stage_map` 与当前 `STAGE_NAME_TO_NUMBER` 全量比对。
- 阶段升序、唯一、1..23；产物路径相对且无 `..`/盘符。
- 工具名缺失 → error；版本不一致 → warning。

### 3.3 发现

`load_pipeline_skill` 复用 `load_skill_from_skillmd`，只认 `metadata.kind=pipeline`；manifest 路径必须留在技能目录内。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-146 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 8/8 success |

## 5. 未做与边界

- 未实现重放、部分复用、多 run 合并。
- 未接入任何执行路径；发现即止。
- 阶段归属是 seq 启发式，不是显式标注（RESEARCH §5）。
- 未修改 `SKILL.md` 解析器；`metadata` 键的读取复用既有实现。
