---
id: arc-run-equivalence-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-run-equivalence-DESIGN]
upstream: null
---

# 实施：重跑等价性对照实验（P-149）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：1 新模块 + 1 既有文件扩展 + 1 测试文件。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/evidence/run_equivalence.py` | 新增 | `compare_runs`、8 类判据、差异分类 |
| `researchclaw/cli.py` | 修改 | `runs compare` 子命令与 `cmd_runs_compare` |
| `tests/test_run_equivalence.py` | 新增 | 16 条用例（13 判定 + 3 CLI） |

## 2. 读数

```text
$ python -m pytest tests/test_run_equivalence.py -q
................                                                         [100%]
16 passed in 0.58s

$ python -m pytest tests/test_reuse_plan.py tests/test_reuse_verify.py \
    tests/test_pipeline_skill.py tests/test_action_ledger.py tests/test_event_log.py -q
57 passed in 1.69s
```

诚实记录：本批先写 15 条用例，首轮红为 `ModuleNotFoundError`（模块未实现），符合 TDD 预期；实现后 14 passed / 1 failed，失败原因是测试夹具 `mkdir()` 未建父目录（测试自身缺陷）；修正为 `parents=True` 后全绿，后续补 1 条只读用例，最终 16 passed。实现未迁就测试。

## 3. 实现要点

### 3.1 事实提取

- `EventLog.read_all()` 取 `stage.completed` / `stage.failed` 序列；`verify_chain()` 取链完整性。
- `ActionLedger.read_all()` 取 `tool` / `params_sha256` / `status` / `outputs`；`verify_chain()` 取链完整性。
- 产物键先尝试相对化到 run 目录，失败则退化为 basename，从而剥离绝对路径前缀。

### 3.2 判定

8 类判据逐一比较；空 run 额外记 `activity` 差异；链损坏额外记 `event_chain` / `action_chain`。差异存在即 `equivalent=False`。

### 3.3 CLI

`runs compare` 只读：目录预检 → 判定 → 文本或 JSON 输出。退出码 0/1/2 与 `pipeline-skill verify` 对齐。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-149 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 待合并后核对 |

## 5. 未做与边界

- 未执行真实 LLM 重跑；对照实验为确定性夹具双 run。
- 未比较重试次数、耗时、成本与跨机器环境。
- 只比较账本记录的 `outputs`；未入账产物不在判定范围。
- 同一路径重复写入按最后一次记录的哈希比较。
