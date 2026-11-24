---
id: arc-pipeline-skill-impl-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-pipeline-skill-DESIGN, arc-action-ledger-IMPLEMENTATION]
upstream: null
---

# 调研：pipeline-as-skill 实施（P-146）

> **Feature**：P-146。按 P-145 冻结的 DESIGN 落地导出器、校验器与发现入口。
> **性质**：T1 实施批；新增 1 个模块、1 个测试文件。
> **结论先行**：① 导出只需要事件流 + 动作账本 + `pipeline_summary.json`，无需触碰 23 阶段；② 阶段归属用「最近一个 `stage.started` 的 seq ≤ 动作的 `event_seq_call`」推导，避免给账本加阶段字段；③ 校验分 errors/warnings 两级，只有 errors 阻断加载。

## 1. 实施边界

| 做 | 不做 |
|---|---|
| 从成功 run 导出 `pipeline.json` + `SKILL.md` | 重放执行 |
| 校验 manifest（完整性/阶段映射/工具/路径） | 自动调用 pipeline 技能 |
| 通过现有 `SKILL.md` loader 发现 | 修改 `SKILL.md` 解析器 |
| 失败即拒绝（fail-closed） | 部分可用降级 |

## 2. 资源清单

| 资源 | 用途 |
|---|---|
| `EventLog.read_all/verify_chain` | 成功判据、阶段序列、seq 区间 |
| `ActionLedger.read_all`（P-143） | 工具、动作 id、产物哈希、env 键名 |
| `pipeline_summary.json` | readpoint 哈希 |
| `skills.loader.load_skill_from_skillmd` | 发现 `metadata.kind=pipeline` |
| `skills.schema.STAGE_NAME_TO_NUMBER` | `arc.stage_map` 快照 |
| `tools.registry.load_registry` | 工具名与版本（可选，加载时用） |

## 3. 风险

| 风险 | 处理 |
|---|---|
| 账本无 stage 字段 | 用事件 seq 推导；无法归属的动作跳过 |
| 账本路径为绝对路径 | 导出时转相对，越界丢弃；校验再拒一次 |
| 注册表不可用 | 加载时跳过工具校验（`tool_versions=None`），不阻断发现 |
| 阶段映射未来变化 | 快照写入 manifest，加载比对，不匹配拒绝 |
| 导出的 run 含 PIVOT | 只记录最终成功的 `stage.completed`，重试折叠 |

## 4. 成功判据的实现口径

- `run.completed` 存在；
- 不存在 `stage.failed`；
- 存在 `stage=23` 的 `stage.completed`；
- 事件链 `verify_chain` 通过；
- 技能名必须以 `pipeline-` 开头（DESIGN Q3）。

任一不满足抛 `ManifestExportError`，不写任何文件。

## 5. 诚实边界

- 阶段归属是启发式（按 seq 区间），不是显式标注；跨阶段并发动作可能归属到较早阶段。
- 导出的 `outputs` 只覆盖账本记录过的产物；未经过工具写出的文件不会出现。
- 本批不验证重放，因此 manifest 的「可复现性」只是字段完备，不是行为等价。
