---
id: arc-node-equivalence-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-node-equivalence-DESIGN]
upstream: null
---

# 实施：产物节点等价性与 summary digest（P-150）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：1 个既有模块扩展 + 1 个测试文件扩展；CLI 零改动。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/evidence/run_equivalence.py` | 修改 | 产物回退 `artifacts/nodes.jsonl`、`run_summary` 检查、`checks` 8→9 |
| `tests/test_run_equivalence.py` | 修改 | 夹具扩展 + 7 条新用例（共 23 条） |
| `spec/arc-node-equivalence/` | 新增 | 四文档 |

## 2. 读数

```text
$ python -m pytest tests/test_run_equivalence.py -q
.......................                                                  [100%]
23 passed in 0.89s

$ python -m pytest tests/test_reuse_plan.py tests/test_reuse_verify.py \
    tests/test_pipeline_skill.py tests/test_action_ledger.py tests/test_event_log.py -q
57 passed in 1.73s
```

真实实验数据复判（P-149 遗留的两份 run）：

```text
$ python -m researchclaw runs compare --left artifacts/p149-llm-a \
    --right artifacts/p149-llm-b --json
equivalent=false, checks=9
differences=artifacts(changed=5), run_summary
artifacts_source=node_index（两侧各 6 个产物）
exit=1
```

P-149 时同一对 run 返回 `equivalent=true`；本批修正后能识别 `stage-01/goal.md`、`stage-02/problem_tree.md`、`stage-03/{queries,search_plan,sources}` 五处内容差异与 summary 差异。

诚实记录：严格 TDD。先改测试，红 8 条（`checks 8 != 9`、`KeyError: artifacts_source`、两处「未抛错」、两处「未识别差异」）；实现后 23 全绿。红的原因是契约变更未实现，不是测试缺陷；本批未修改测试来迁就实现。

## 3. 实现要点

### 3.1 产物来源

- `actions.jsonl` 有动作 → `artifacts_source="ledger"`，沿用 P-149 的路径相对化逻辑。
- 无动作且 `artifacts/nodes.jsonl` 存在 → `"node_index"`，投影 `locator → content_hash`，同 locator 后写覆盖。
- 两者皆无 → `"none"`。

### 3.2 summary

读取 `pipeline_summary.json`，按 `summary_check.summary_digest` 计算 canonical digest；两侧不同（含一侧 `null`）记 `run_summary` 差异。

### 3.3 fail-closed

`load_nodes` 解析失败或 summary 非对象 → `ValueError`；CLI 捕获后 exit 2。判定器仍然只读。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-150 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 待推送后核对 |

## 5. 未做与边界

- 未真实重跑 LLM；用 P-149 的两份真实 run 做复判。
- 不回退「账本非空但 outputs 为空」的情况（DESIGN D-7）。
- 不扫描 run 目录全部文件，不比较节点树结构（`verify_tree` 职责）。
- summary digest 只给整体差异，不定位内容。
