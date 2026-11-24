---
id: arc-pipeline-skill-impl-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-pipeline-skill-impl-RESEARCH, arc-pipeline-skill-DESIGN]
upstream: null
---

# 设计：pipeline-as-skill 实施（P-146）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **继承**：[P-145 DESIGN](../arc-pipeline-skill/DESIGN.md) 的 D-1..D-9 与 J-1..J-6，本批不重新裁决。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 新模块 `researchclaw/skills/pipeline_manifest.py`；不改 loader 解析器 |
| D-2 | `export_manifest(run_dir, skill_dir, *, name, description, repo_commit, tool_versions)` 写 `pipeline.json` + `SKILL.md` |
| D-3 | 成功判据五项（见 RESEARCH §4），任一失败抛 `ManifestExportError` 且不落盘 |
| D-4 | 阶段归属：动作 `event_seq_call` 落在最近的 `stage.started` 之后即归该阶段 |
| D-5 | 产物路径转 run 相对路径；越界丢弃，校验再拒绝对路径/`..` |
| D-6 | 校验返回 `(errors, warnings)`；版本漂移只进 warnings |
| D-7 | 发现走 `load_pipeline_skill`：`SKILL.md` → `metadata.manifest` → 校验 |
| D-8 | 不执行、不推荐、不修改执行路径 |

## 2. API

```python
export_manifest(run_dir, skill_dir, *, name, description="",
                repo_commit="", tool_versions=None) -> dict
validate_manifest(manifest, *, stage_map=None,
                  tool_versions=None) -> tuple[list[str], list[str]]
load_pipeline_skill(skill_dir) -> tuple[dict | None, list[str]]
```

- `export_manifest`：读事件链与账本，写两个文件，返回 manifest。
- `validate_manifest`：完整性、阶段映射、阶段顺序与范围、产物路径、工具名/版本。
- `load_pipeline_skill`：`SKILL.md` 校验 `metadata.kind=pipeline`，路径必须留在技能目录内。

## 3. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 失败 run 不产生任何文件 | `test_export_requires_run_completed` 等 |
| J-2 | `manifest_sha256` 覆盖除 `integrity` 外全部字段 | `test_validate_integrity_detects_tamper` |
| J-3 | 阶段映射快照不匹配即拒绝 | `test_validate_rejects_stage_map_drift` |
| J-4 | 产物路径必须相对且不含 `..`/盘符 | `test_validate_rejects_absolute_output_path` |
| J-5 | 工具名缺失拒绝、版本漂移仅警告 | `test_validate_unknown_tool_and_version_drift` |
| J-6 | 发现不触发执行 | `test_loader_discovers_and_accepts`（只返回 manifest） |

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| 事件链坏 | `ManifestExportError("event chain invalid: ...")` |
| 缺 `run.completed` | `ManifestExportError("run.completed missing")` |
| 有 `stage.failed` | `ManifestExportError("stage.failed present")` |
| 缺 Stage 23 | `ManifestExportError("stage 23 did not complete")` |
| 技能名无前缀 | `ManifestExportError("pipeline skill name must start with 'pipeline-'")` |
| manifest 不可读 | `load_pipeline_skill` 返回 `(None, [...])` |
| 注册表不可用 | 跳过工具校验，不误伤纯发现 |

## 5. 兼容性

- `skills/loader.py`、`skills/schema.py` 零改动。
- 现有 20 个 `SKILL.md` 不受影响：`metadata.kind` 缺省不是 `pipeline`。
- 无新增依赖；`yaml` 已是既有依赖。
- 无执行路径接入，运行时行为不变。

## 6. 非目标

- 重放、部分复用、多 run 合并、技能推荐、CLI。
