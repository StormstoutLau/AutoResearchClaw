---
id: arc-g2-m4-wiring-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-RESEARCH]
upstream: arc-g2-m4-wiring-RESEARCH
---

# 设计：G2 M4 Stage 9/20/23 接线与双平面

> 基于 [RESEARCH.md](RESEARCH.md)。判定逻辑收敛到 `claim_policy.py` 的纯函数；`stage_hooks.py` 只做 IO；三个 Stage 只做调用与失败映射。
>
> **v1.1（P-063 修订）**：吸收 [P-062 独立复审](../../docs/arc-g2-m4-wiring-review-20261111.md) D-1..D-3——`load_claims` 改为非版本目录优先（R14-2）；坏行/损坏 gate JSON 改为 `ClaimStreamError`；claim/gate 落盘改 `tmp + os.replace`；`evaluate_claim` 入口增加 C4 最小结构校验（`invalid_claim_record`）。详见 [修复设计包](../arc-g2-m4-wiring-fixes/DESIGN.md)。

## 1. 模块与 API

| 文件 | 职责 |
|---|---|
| `researchclaw/evidence/claim_policy.py` | 发布谓词、降级、封顶、`evaluate_claim`/`audit_claim`、Stage 9 claim 抽取 |
| `researchclaw/evidence/stage_hooks.py` | Stage 9 写 claims、Stage 20 gate、Stage 23 双平面比对 |
| `researchclaw/pipeline/stage_impls/_experiment_design.py` | Stage 9 调用 `write_stage9_claims` 并登记 artifacts |
| `researchclaw/pipeline/stage_impls/_review_publish.py` | Stage 20/23 调用钩子并映射 `E20_*`/`E23_*` |
| `tests/test_claim_policy.py` | 谓词、降级、封顶、双平面纯函数测试 |
| `tests/test_stage_claim_hooks.py` | Stage 9/20/23 接线、阻断、漂移、跳过 |

```python
@dataclass(frozen=True)
class ClaimDecision:
    claim: dict
    findings: tuple[Finding, ...] = ()
    deliverable: bool = True
    blocked_reasons: tuple[str, ...] = ()
    downgraded: bool = False
    capped: bool = False
    def as_dict(self) -> dict: ...

def evaluate_claim(claim: Mapping[str, Any], annotation: str | None = None) -> ClaimDecision
def audit_claim(claim: Mapping[str, Any], annotation: str | None = None) -> ClaimDecision
def can_enter_deliverables(claim, findings=()) -> bool
def requires_annotation(claim) -> bool
def downgrade_missing_citation(claim) -> tuple[dict, bool]
def build_claim_records(text: str, plan: Mapping | None = None) -> list[dict]

def write_stage9_claims(stage_dir, hypotheses_text, plan=None) -> tuple[str, ...]
def load_claims(run_dir, stage_prefix="stage-09") -> list[dict]
def run_stage20_gate(stage_dir, run_dir) -> dict
def run_stage23_consistency(stage_dir, run_dir) -> dict
```

## 2. 判定链

`evaluate_claim` 的顺序固定，生产与审计共用：

```text
claim
  → validate_claim_shape          # D-3：id 模式 + 14 必填键 + status 词表
  → downgrade_missing_citation   # A: evidence 三要素；B: 每步 source_refs；C: 不处理
  → check_claim (AR-01..08)      # 纯函数，返回 deterministic findings
  → apply finding.cap            # 仅 AR-05/06，且终态不封顶
  → can_enter_deliverables       # failed/falsified 或 fail finding → False
  → requires_annotation          # numerically_verified 且无 annotation → False
```

不变式：

- 降级只复制映射，不改原 claim；重复评估不会重复追加 `assumptions`。
- `_cap_status` 不把终态（`failed`/`falsified`）改写为任何上限；终态只能阻断。
- `blocked_reasons` 只有三个值：`claim_not_deliverable`、`missing_annotation`、`invalid_claim_record`。
- 结构不合法时短路：不跑降级/AR，直接 `invalid_claim_record` + `problems`。
- `findings` 顺序由 `check_claim` 保证确定性，双平面可直接按值比较。

## 3. Stage 9：claim 抽取

- 输入：`hypotheses.md`（上游 Stage 8），可选 `plan.objectives` 兜底。
- 规则：逐行去列表符号/编号；长度 < 12 或标题行跳过；按首次出现去重；上限 50 条。
- 产物：`stage-09/claims.jsonl`，每行一条 C4 ClaimRecord：
  `claim_class=C`、`claim_type=exploratory`、`status=speculation`、`verification_depth=stage1`、`policy_version=2`、`falsifier={condition:"",test_ref:""}`。
- `claim_id = "c-" + sha256(statement)[:8]`，满足 C4 的 `^c-[0-9a-f]{8}$`。
- 失败处理：hook 异常只记 warning，`exp_plan.yaml` 仍写出；`artifacts` 仅在成功时追加 `claims.jsonl`。

## 4. Stage 20：发布门禁

顺序：`_write_claim_verification` → `run_stage20_gate` → 模拟数据检查 → 评分门禁。

`run_stage20_gate`：

1. 读取最新的 `stage-09*/claims.jsonl`：**非版本目录优先**，无活目录时取版本号最大者（P-063 / R14-2）；坏行抛 `ClaimStreamError`。
2. 读取 run 级 `annotations.json`；存在但损坏同样抛错。
3. 对每条 claim 调 `evaluate_claim`，收集 `updated`、`decisions`、`blocked`、`missing_annotation`。
4. 写回 `stage-20/claims.jsonl`（已降级/封顶后的 claim），原子写 `stage-20/claim_gate.json`。

`claim_gate.json` 契约：

```json
{
  "decision": "pass | downgraded | block",
  "total": 3,
  "blocked": [{"claim_id": "c-...", "status": "falsified", "reasons": ["claim_not_deliverable"], "problems": []}],
  "missing_annotation": ["c-..."],
  "decisions": {"c-...": {"claim_id": "c-...", "status": "speculation", "deliverable": true, "blocked_reasons": [], "downgraded": false, "capped": false, "problems": [], "findings": []}}
}
```

失败映射：

| 条件 | 结果 |
|---|---|
| 钩子抛异常 | `StageStatus.FAILED`，`E20_CLAIM_CONTRACT_INTERNAL: ...`，artifacts 仅含已有产物 |
| `decision == block` | `StageStatus.FAILED`，`E20_CLAIM_CONTRACT: claim cannot enter deliverables (blocked=N)`，artifacts 含 `claim_gate.json`/`claims.jsonl` |
| 通过 | 原有评分/SIM 检查继续；所有后续 return 的 artifacts 追加 `claim_gate.json`、`claims.jsonl` |

## 5. Stage 23：双平面一致性

1. 读取 `stage-20/claims.jsonl`；不存在则回退 `stage-09`；两者都按非版本优先（P-063）。
2. 读取 `stage-20/claim_gate.json` 的 `decisions` 作为生产决定；文件存在但损坏 → `ClaimStreamError`（不再误判为 `skipped`）。
3. 对每条 claim 调 `audit_claim`（与 Stage 20 同一 `evaluate_claim`）。
4. 比对 `status` 与 `deliverable`；写 `stage-23/claim_consistency.json`（原子写）。

```json
{
  "consistent": true,
  "checked": 3,
  "diffs": [{"claim_id": "c-...", "reason": "status_mismatch", "production": "numerically_verified", "audit": "formally_verified"}],
  "production": {"c-...": {"status": "...", "deliverable": true}},
  "audit": {"c-...": {"status": "...", "deliverable": true}},
  "skipped": "no_production_gate"
}
```

- `reason` 三值：`missing_production_decision`、`status_mismatch`、`deliverable_mismatch`。
- 有 claim 但完全没有生产决定（续跑场景）→ `skipped=no_production_gate`、`consistent=true`。
- `consistent=false` → Stage 23 FAILED，`E23_CLAIM_DRIFT`；钩子异常 → `E23_CLAIM_DRIFT_INTERNAL`。
- 一致性检查先于引文核验；即使没有 `references.bib` 也会执行并写出产物。

## 6. 双平面测试设计

| 用例 | 输入 | 期望 |
|---|---|---|
| 生产=审计 | Stage 20 通过后立即 Stage 23 | `consistent=true`，`checked=1` |
| 状态漂移 | 篡改 `stage-20/claims.jsonl` 的 `status` | `status_mismatch`，Stage 23 FAILED |
| 可发布性漂移 | 篡改 statement 为 AR-03 禁用表述 | `deliverable_mismatch` |
| 续跑无门禁 | 只有 `stage-09/claims.jsonl` | `skipped=no_production_gate`，Stage 23 DONE |
| 数值缺标注 | `numerically_verified` 且无 `annotations.json` | Stage 20 阻断，`missing_annotation` |

## 7. 边界与不变量

- **不改 M0 契约**：claim 只写 C4 允许的字段；annotation 走 run 级文件。
- **不改 AR 判据**：`downgrade_missing_citation` 复制 AR-01 的引文口径（A=三要素，B=每步 refs），不新增规则。
- **确定性**：同一 claim + annotation 在任意进程、任意平面输出相同 `ClaimDecision`。
- **fail-closed**：Stage 20/23 的钩子异常与阻断都映射为 FAILED；Stage 9 例外（附加产物）。
- **原子落盘**：claims/gate/consistency 全部 `tmp + os.replace`，崩溃不留半截文件（P-063）。
- **幂等**：重复 Stage 20 不会重复追加 assumptions；重复 Stage 23 覆盖写同一 JSON。
- **无新依赖**：只用标准库 + 既有 `ar_checks`。
