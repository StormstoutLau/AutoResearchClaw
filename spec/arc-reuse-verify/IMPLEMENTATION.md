---
id: arc-reuse-verify-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-reuse-verify-DESIGN]
upstream: null
---

# 实施：账本查询 CLI 与复现性校验（P-147）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：1 个新模块、1 个测试文件、2 个既有文件最小接入。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/skills/reproducibility.py` | 新增 | `verify_reproducibility` |
| `researchclaw/runtime/action_ledger.py` | 修改 | 追加纯函数 `query_actions`（类零改动） |
| `researchclaw/cli.py` | 修改 | `actions` / `pipeline-skill verify` 两个子命令 + 分发分支 |
| `tests/test_reuse_verify.py` | 新增 | 12 条用例 |

## 2. TDD 读数

```text
# 红（实现前）
$ python -m pytest tests/test_reuse_verify.py -q
ImportError: cannot import name 'query_actions' from
'researchclaw.runtime.action_ledger'
1 error in 0.17s

# 绿（实现后）
$ python -m pytest tests/test_reuse_verify.py -q
............                                                       [100%]
12 passed
```

严格先红后绿：红 = 收集期 ImportError（模块/函数不存在），绿 = 12/12。

## 3. 实现要点

### 3.1 query_actions

纯函数：`EventLog` 式的容错读取（撕裂尾停止），按 `tool`/`status` 过滤，`limit` 截断；账本不存在返回空表。

### 3.2 verify_reproducibility

四组检查（DESIGN §4）：

1. **产物**：`stages[].outputs` 逐文件 `hash_path` 比对 → `missing_outputs` / `hash_mismatches`。
2. **动作**：账本 `action_id` 集合比对 → `unresolved_actions`。
3. **事件链**：`EventLog.verify_chain()` → `chain_ok`。
4. **readpoint**：逐项哈希比对 → `readpoint_failures`。

空 manifest（无 stages）显式 `reproducible=false`，防「零检查假绿」。

### 3.3 CLI

- `actions --run-dir [--tool/--status/--limit/--json]`：exit 0；账本不可读 exit 2。
- `pipeline-skill verify --skill-dir --run-dir [--json]`：`load_pipeline_skill` 失败或目录缺失 exit 2；`reproducible=false` exit 1；全过 exit 0。
- 两个分发分支接入 `cli.py` 既有 `elif` 链。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-147 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 8/8 success |

## 5. 未做与边界

- 未实现重执行（U-1 / P-148 候选）。
- 未做聚合统计、跨 run 查询、表格美化。
- `actions` 查询不做分页游标；`--limit` 即全部能力。
