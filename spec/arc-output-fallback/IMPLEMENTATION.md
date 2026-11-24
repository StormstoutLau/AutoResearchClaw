---
id: arc-output-fallback-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-output-fallback-DESIGN]
upstream: null
---

# 实施：零产物账本的回退（P-151）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：1 个既有模块的条件判定 + 2 条测试；CLI 零改动。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/evidence/run_equivalence.py` | 修改 | 来源判定由动作数改为账本产物数；docstring 同步 |
| `tests/test_run_equivalence.py` | 修改 | `with_output` 夹具参数 + 2 条新用例（共 25 条） |
| `spec/arc-output-fallback/` | 新增 | 四文档 |

## 2. 读数

```text
$ python -m pytest tests/test_run_equivalence.py -q
.........................                                                [100%]
25 passed in 0.92s

$ python -m pytest tests/test_reuse_plan.py tests/test_reuse_verify.py \
    tests/test_pipeline_skill.py tests/test_action_ledger.py tests/test_event_log.py -q
57 passed in 2.49s
```

严格 TDD：先加 2 条用例，红（`assert 'ledger' == 'node_index'`、`assert 'ledger' == 'none'`）；改条件后 25 全绿。红由契约未实现导致，未修改测试迁就实现。

## 3. 实现要点

- `ledger_artifacts` 汇总所有动作的 `outputs`（路径相对化后）。
- `if ledger_artifacts:` 非空才用 `ledger`；否则看节点索引是否存在；否则 `none`。
- 回退路径复用 `_node_artifacts`，损坏索引仍抛 `ValueError`。
- `actions` 字段仍报告动作数，tool/params/status 序列不变。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-151 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 待推送后核对 |

## 5. 未做与边界

- 不合并账本与节点索引（D-4）。
- 不做动作级产物归属。
- 未观察到该组合的真实 run；夹具覆盖。
- P-150 历史文档不改写，新语义只登记在 P-151。
