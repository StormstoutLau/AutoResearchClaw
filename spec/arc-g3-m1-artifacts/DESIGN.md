---
id: arc-g3-m1-artifacts-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-m1-artifacts-RESEARCH]
upstream: arc-g3-m1-artifacts-RESEARCH
---

# 设计：G3 M1 ArtifactNode 与 summary 校验

> 基于 [RESEARCH.md](RESEARCH.md)。接口沿用 [M0 DESIGN](../arc-g3-m0-design/DESIGN.md) §3/§4。

## 1. 模块

| 文件 | 职责 |
|---|---|
| `researchclaw/evidence/artifact_node.py` | `ArtifactNode`、`build_node`、`register_stage_artifacts`、`load_nodes`、`verify_tree`、`project_to_evidence` |
| `researchclaw/evidence/summary_check.py` | `canonical_summary`、`summary_digest`、`write_summary`、`verify_summary` |
| `researchclaw/pipeline/runner.py` | DONE 阶段注册节点；summary 改原子写 + 侧车 |

## 2. ArtifactNode

### 2.1 节点生成

```python
build_node(run_dir, locator, *,
           node_type="stage_artifact", parent_nodes=(),
           producer=None, sensitive=False, evidence=None,
           materialize_limit=1 MiB, created_at=None) -> ArtifactNode
```

- `content_hash = sha256(file bytes)`。
- `node_id = "an-" + sha256(canonical({type, locator, content_hash}))[:16]`。
- `inputs_digest = sha256(canonical({"parents": sorted(parent hashes), "params": producer}))`。
- `materialized = not sensitive and size <= limit and is_utf8_text`；为 true 时写 `artifacts/blobs/<hex>`（原子写、内容寻址）。
- 只存指针时仍计算 `content_hash`；`verify_tree` 从原路径复算。

### 2.2 阶段注册

`register_stage_artifacts(run_dir, stage, stage_name, artifacts, attempt=1)`：

- 跳过不存在的文件（mock/可选产物）。
- 父节点 = 已注册节点中 `producer.stage < stage` 的最大 stage 全部节点；无则为空。
- 按 `node_id` 幂等；新增后整体原子重写 `artifacts/nodes.jsonl`。
- 注册异常由 runner 捕获并 warning（不阻断 run）。

### 2.3 校验

`verify_tree(run_dir, nodes=None) -> list[error]`：

| 检查 | 错误 |
|---|---|
| `node_id` 与 type/locator/hash 重算一致 | `E_ARTIFACT_ID` |
| 父节点存在且无环 | `E_ARTIFACT_PARENT` / `E_ARTIFACT_CYCLE` |
| blob 或原文件哈希一致 | `E_ARTIFACT_HASH` |
| `sensitive=true` 不得 materialized | `E_ARTIFACT_HASH` |
| `inputs_digest` 重算一致 | `E_ARTIFACT_INPUTS` |

`project_to_evidence(node)`：存在 `evidence` facet 时复制并以 `content_hash` 覆盖 `digest`；否则返回 `None`（AN-4 API）。

## 3. pipeline_summary

- `canonical_summary`：`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`（JCS 兼容子集）。
- `write_summary`：原子写 `pipeline_summary.json` + `pipeline_summary.sha256`（`sha256:<64>\n`）。
- `verify_summary(run_dir, require_event=False)`：
  - summary 缺失 → `E_SUMMARY_MISSING`；
  - 侧车缺失/不符 → `E_SUMMARY_TAMPERED`；
  - `require_event=True` 时读 `events.jsonl` 最后 `pipeline.summary.payload.digest`，缺失 → `E_SUMMARY_EVENT_MISSING`，不符 → `E_SUMMARY_TAMPERED`。
- M1 只启用侧车双向；M2 启用事件链三向。

## 4. 接线

`runner._write_pipeline_summary` → `summary_check.write_summary`。
DONE 阶段：`register_stage_artifacts(run_dir, int(stage), stage.name, result.artifacts)`，随后写 checkpoint。

## 5. 边界

- 不改 `pipeline_summary` 字段集；仅改序列化与侧车。
- 不改 C4/判定内核；不写 `events.jsonl`（M2）。
- `verify_tree` 只读，不修复。
