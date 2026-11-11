---
id: arc-g3-m1-artifacts-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-m1-artifacts-DESIGN]
upstream: arc-g3-m1-artifacts-DESIGN
---

# 实施记录：G3 M1 ArtifactNode 与 summary 校验（P-075）

> **状态**：内核、runner 接线与 21 项测试完成；CHECKLIST accepted。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/artifact_node.py` | 新增 | `ArtifactNode`、`build_node`、`register_stage_artifacts`、`load_nodes`、`verify_tree`、`project_to_evidence` |
| 2 | `researchclaw/evidence/summary_check.py` | 新增 | canonical summary、SHA-256 侧车、`verify_summary`、M2 事件锚定 helper |
| 3 | `researchclaw/pipeline/runner.py` | 修改 | DONE 阶段注册节点；`_write_pipeline_summary` 改原子写 + 侧车 |
| 4 | `tests/test_artifact_node.py` | 新增 | 13 项节点/血缘/投影/注册测试 |
| 5 | `tests/test_pipeline_summary_check.py` | 新增 | 8 项 summary 侧车/事件/runner 测试 |
| 6 | `.github/workflows/ci.yml` | 修改 | 固定清单加入两个测试文件 |

**不改**：C4 schema、判定内核、`pipeline_summary` 字段集、`events.jsonl`（M2 才写）。

## 2. 关键行为

- `build_node`：内容哈希、`node_id`、`inputs_digest`；小文本入 `artifacts/blobs/`，敏感/大文件/二进制只存指针。
- `register_stage_artifacts`：线性父边（上一 stage 全部节点）、幂等、缺文件跳过、整体原子重写 `artifacts/nodes.jsonl`。
- `verify_tree`：哈希/父节点/环/inputs_digest/敏感 materialized 五类检查，返回错误 dict。
- `write_summary`：canonical compact JSON + `.sha256` 侧车，均原子写。
- `verify_summary`：summary/侧车双向；`require_event=True` 时叠加 `events.jsonl` 锚定（M2 使用）。

## 3. 读数

| 项 | 读数 |
|---|---|
| 新增 M1 测试 | **21 passed**（3.13.5） |
| M1 + runner 回归 | **67 passed** |
| runner/checkpoint/kb/report 回归 | **92 passed** |
| Python 3.11.15 | 21 passed |
| DC / 门禁 | 见 CHECKLIST |

## 4. 验收边界（诚实口径）

- **AN-1/AN-2/AN-3**：节点注册、父边/环、inputs_digest 全链测试通过。
- **AN-4**：`project_to_evidence` API 与 digest 覆盖已测；旧 AR-01 fixture 的逐字段全量回归留 M3（claim 脊柱）。
- **AN-5/AN-6**：节点侧指针/敏感规则已测；导出/预览过滤与 inline_copy 上限留 M3/M5。
- **A3-2**：侧车双向已测；事件链三向留 M2。

## 5. 风险

- 线性父边在 PIVOT 后形成多分支 DAG；M1 只保证可解析/无环。
- 节点注册为非致命路径；IO 失败只 warning，需由 `verify_tree` 事后判红。
- `canonical_summary` 为 JCS 兼容子集（sorted keys/compact），完整 RFC 8785 数值规范化未实现；当前字段均为字符串/整数，风险可控。
