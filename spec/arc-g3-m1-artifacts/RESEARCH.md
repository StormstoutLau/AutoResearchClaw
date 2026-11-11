---
id: arc-g3-m1-artifacts-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-m0-design-DESIGN]
upstream: arc-g3-m0-design-DESIGN
---

# 调研：G3 M1 ArtifactNode 与 summary 校验

> **Feature**：P-075，G3 M1（ArtifactNode v1 + pipeline_summary 侧车校验）。
> **Spec 步骤**：T1（内核新增 + runner 接线 + 21 项测试）。
> **结论先行**：按 M0 冻结接口落地 ArtifactNode v1 与 summary 侧车。**M1 完成 AN-1/AN-2/AN-3 全链、A3-2 侧车双向、AN-4 投影 API、AN-5/AN-6 节点侧规则**；事件链三向（A3-2 后半）留 M2，claim/export 侧 AN-4/5/6 全量回归留 M3。

## 1. 输入与范围

- 冻结接口：[G3 M0 DESIGN](../arc-g3-m0-design/DESIGN.md) §3（ArtifactNode）、§4（summary）。
- 现状：`pipeline_summary.json` 由 `runner._build_pipeline_summary` 程序生成，但无侧车/校验；无 ArtifactNode 存储。
- 本批：新增 `evidence/artifact_node.py`、`evidence/summary_check.py`；runner 在 DONE 阶段注册产物、summary 改原子写 + 侧车；新增 21 测试。

## 2. 一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `StageResult.artifacts` 为阶段内相对文件名；阶段目录为 `run_dir/stage-NN/` | `_helpers.py` StageResult；各 stage return |
| F-2 | runner 在每个 stage 后统一 append results 并写 checkpoint | `runner.py` `results.append`/`_write_checkpoint` |
| F-3 | summary 写入是普通 `write_text(indent=2)`，无摘要 | `runner._write_pipeline_summary`（修改前） |
| F-4 | 现有测试只解析 summary JSON，不依赖缩进格式 | `tests/test_rc_runner.py` |
| F-5 | G1a `events.jsonl` 有哈希链与 `canonical_json`，M2 可直接锚定 | `runtime/event_log.py` |

## 3. 决策

| # | 决策 | 理由 |
|---|---|---|
| D-1 | 父节点取「上一 DONE 阶段的全部节点」（线性前驱） | M1 先保证 AN-2/AN-3 可验证；精细语义父边留 M3 |
| D-2 | 节点注册失败不阻断 run（warning） | 避免非核心产物缺失打断长管线；AN-1 由 `verify_tree` 事后判红 |
| D-3 | summary 以 canonical compact JSON 落盘 + `.sha256` 侧车 | 手改 summary 不更新侧车即失败（A3-2） |
| D-4 | `verify_summary` 不自动修复；M2 再叠加事件链 | 校验只读；M1/M2 两阶段与 O-5 一致 |
| D-5 | 二进制/大文件/敏感节点只存指针，仍计算 content_hash | 满足 AN-5/AN-6 节点侧；blobs 只收小文本 |

## 4. 风险

- 线性父边会在 PIVOT 后形成多分支 DAG；M1 只要求无环/可解析，完整血缘语义留 M3。
- 节点注册是非致命路径，若 IO 失败只 warning；`verify_tree` 会把缺失/篡改判红。
- M1 不覆盖导出侧敏感过滤与旧 evidence 全字段回归；不得据此宣称 AN-4/5/6 全绿。
