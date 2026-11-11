---
id: arc-g2-m5-offline-audit-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-RESEARCH]
upstream: arc-g2-m5-offline-audit-RESEARCH
---

# 设计：G2 M5 离线审查模式

> 基于 [RESEARCH.md](RESEARCH.md)。判定与比对全部复用 M4 内核，本批只新增只读入口、版本核验与 CLI。
>
> **v1.1（P-068 修订）**：吸收 P-065..P-067 复核——`compare_claims` 增**双向集合检查**（`duplicate_claim_id`、`orphan_production_decision`，见 [修复设计包](../arc-g2-m5-offline-audit-fixes/DESIGN.md)）；`run_stage20_gate` 对重复 id 直接 block；`--policy-version < 1` 与 `--output` 失败 → exit 2；所有诊断改 stderr；`no_claims` 仅在无 claims 且无 production 时成立。P-067 D-5 约束：集合检查无条件执行，逐条循环保留跳过守卫。

## 1. 模块与 API

| 文件 | 职责 |
|---|---|
| `researchclaw/evidence/claim_policy.py` | `CURRENT_POLICY_VERSION = 2`（唯一真值源，`build_claim_records` 引用） |
| `researchclaw/evidence/stage_hooks.py` | 新增共享 `compare_claims` 与 `_load_production_gate`；`run_stage23_consistency` 改为调用前者（行为零变化） |
| `researchclaw/evidence/offline_audit.py` | 新增：`run_offline_audit`、`write_audit_report` |
| `researchclaw/cli.py` | 新增 `audit` 子命令与 `cmd_audit` |
| `tests/test_offline_audit.py` | 29 项：核心 17 + CLI 7 + 7 状态矩阵 |

```python
def compare_claims(claims, production, annotations) -> dict
    # -> {"diffs": [...], "audit": {...}, "skipped": "" | "no_production_gate"}

def run_offline_audit(run_dir: Path,
                      expected_policy_version: int = CURRENT_POLICY_VERSION) -> dict
def write_audit_report(report: dict, output: Path) -> Path
```

## 2. 共享比对（防双实现漂移）

`compare_claims` 吸收 Stage 23 原比对循环，含跳过语义与双向集合检查：

```text
keys/counts = 逐条 claim_key 计数
重复 key（count>1）           -> duplicate_claim_id        # 无条件
claims 非空 且 production 为空  ->  skipped="no_production_gate"（逐条循环跳过）
否则逐条：
  claim_key = claim_id（非法则 <invalid-N>）
  audit   = audit_claim(claim, annotations[claim_key])   # 生产内核同源
  prod 缺失                    -> missing_production_decision
  prod.status  != audit.status    -> status_mismatch
  prod.deliverable != audit.deliverable -> deliverable_mismatch
production 有而 claims 无        -> orphan_production_decision   # 无条件
```

**P-067 D-5**：duplicate/orphan 两个集合检查必须在 skip 守卫之外；逐条循环保持在守卫内，否则续跑会被误判漂移。

`run_stage23_consistency` 的 payload/返回值结构不变；`skipped` 键由 `result["skipped"]` 驱动。既有 Stage 23 用例（含 `test_stage23_skips_without_production_gate`）不改一字通过。

## 3. 离线审计

读取顺序（与 Stage 23 相同）：

1. claims：`stage-20*/claims.jsonl` → 回退 `stage-09`（`_claims_candidates` 保证活目录优先）。
2. production：`stage-20/claim_gate.json` 的 `decisions`（`_load_production_gate`，缺失→`{}`，损坏→`ClaimStreamError`）。
3. annotations：run 级 `annotations.json`（损坏→抛错）。

版本核验（D-2）：逐条比对 `claim.policy_version == expected_policy_version`，不符产生
`{"claim_id", "reason": "policy_version_mismatch", "expected", "found"}`。
跳过场景下版本核验仍执行（版本不符是独立事实）。

报告契约：

```json
{
  "consistent": true,
  "checked": 3,
  "diffs": [],
  "production": {"c-...": {"status": "...", "deliverable": true}},
  "audit": {"c-...": {"status": "...", "deliverable": true}},
  "expected_policy_version": 2,
  "skipped": "no_production_gate"
}
```

`skipped` 两值：`no_production_gate`（共享比对给出）、`no_claims`（**无 claims 且无 production**，离线专属）。「有 production 无 claims」不是 skip，是孤儿漂移。只读：除 `--output` 外不落任何文件。

## 4. CLI

```text
researchclaw audit --run-dir <path> [--json] [--policy-version N] [--output <path>]
```

- 退出码：`0` 一致（含 skipped）/ `1` diffs 非空 / `2` 输入不可用（目录缺失、claim/gate 损坏、`--policy-version < 1`、`--output` 写失败）。
- 人类可读输出：`audit: CONSISTENT|DRIFT  checked=N  diffs=M  expected_policy_version=V`，逐条 diff（前 10 条），`skipped` 单独行。
- `--json` 打印完整报告；`--output` 经 `write_audit_report` 落盘（可与 `--json` 并用）。
- **流分离**：stdout 只放数据（JSON/verdict），所有诊断（report written / 版本错误 / 写失败）走 stderr。
- 派发接入 `main()` 的 `elif command == "audit"`。

## 5. 测试设计（36 项）

| 组 | 用例 |
|---|---|
| 核心-正常 | 一致复现、**7 状态矩阵**（每状态 gate→audit 同 status）、确定性（两次 JSON 相等）、只读（全树字节快照不变）、stage-20 优先、版本化目录不触达 |
| 核心-漂移 | status_mismatch、deliverable_mismatch、missing_production_decision、policy_version_mismatch、`orphan_production_decision` |
| 核心-跳过 | 无 gate→`no_production_gate`、空 run→`no_claims`、整删 claims→孤儿非 skip |
| 核心-封闭 | 目录缺失→`FileNotFoundError`、claims 坏行→`ClaimStreamError`、gate 损坏→`ClaimStreamError`、重复 id→`duplicate_claim_id`/gate block |
| CLI | exit 0/1/2、`--json` 可解析、`--policy-version` 触发 exit 1、`--policy-version 0`→exit 2、`--output` 落盘、`--json --output` stdout 纯净 |

## 6. 不变量

- 判定唯一入口：审计平面不复制任何规则，只调用 `audit_claim`/`compare_claims`。
- 只读：审计前后 run 目录字节级不变（快照断言）。
- 与 Stage 23 同构：同一 run 上 `run_stage23_consistency` 与 `run_offline_audit` 的 diffs/audit 必须一致（同一函数保证）。
- 双向完整性：claim↔decision 必须 1:1；任一方向缺失或 id 重复均判漂移。
- 续跑容忍：有 claims 无 gate → `no_production_gate` 放行；有 gate 无 claims → 孤儿漂移。
- 无新依赖：标准库 + 既有 evidence 内核。
