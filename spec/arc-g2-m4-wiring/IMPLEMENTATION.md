---
id: arc-g2-m4-wiring-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-DESIGN]
upstream: arc-g2-m4-wiring-DESIGN
---

# 实施记录：G2 M4 Stage 9/20/23 接线与双平面

> **状态**：P-061 已施工完成，本文件记录实际改动与读数；CHECKLIST 已 accepted。
> **依据**：[DESIGN.md](DESIGN.md) §2（判定链）、§3（Stage 9）、§4（Stage 20）、§5（Stage 23）、§6（双平面测试）。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_policy.py` | 新增 | A2-4/5/6 谓词、降级、封顶、`evaluate_claim`/`audit_claim`、Stage 9 claim 抽取 |
| 2 | `researchclaw/evidence/stage_hooks.py` | 新增 | Stage 9 写 claims、Stage 20 gate、Stage 23 双平面比对 |
| 3 | `researchclaw/pipeline/stage_impls/_experiment_design.py` | 修改 | Stage 9 末尾调用 `write_stage9_claims`，artifacts/evidence_refs 追加 |
| 4 | `researchclaw/pipeline/stage_impls/_review_publish.py` | 修改 | Stage 20 gate（`E20_CLAIM_CONTRACT`）、Stage 23 一致性（`E23_CLAIM_DRIFT`）、artifacts 补充 |
| 5 | `tests/test_claim_policy.py` | 新增 | 33 项谓词/降级/封顶/双平面/抽取测试 |
| 6 | `tests/test_stage_claim_hooks.py` | 新增 | 13 项 Stage 9/20/23 接线与漂移测试 |
| 7 | `arc-master-roadmap.md` | 修改 | v1.3i：M4 交付、G2 可进入 M5 |
| 8 | `docs/PROGRESS.md` | 修改 | P-061 执行行 |
| 9 | `.github/workflows/ci.yml` | 修改 | 固定清单加入 `test_claim_policy.py`、`test_stage_claim_hooks.py` |

**不改**：C4 schema、AR-01..08 判据、M3 sidecar、Stage 14/17。

## 2. `claim_policy.py`

### 2.1 顺序

```python
def evaluate_claim(claim, annotation=None):
    working, downgraded = downgrade_missing_citation(claim)
    findings = tuple(check_claim(working))
    capped = False
    for finding in findings:
        if finding.cap:
            working, did_cap = _cap_status(working, finding.cap)
            capped = capped or did_cap
    blocked = []
    if not can_enter_deliverables(working, findings):
        blocked.append("claim_not_deliverable")
    if requires_annotation(working) and not (annotation or "").strip():
        blocked.append("missing_annotation")
    return ClaimDecision(...)
```

### 2.2 引文口径

- A 类：`evidence[]` 至少一条同时具备 `source_id`、`locator`、`quote`。
- B 类：`reasoning_chain` 非空，且每一步 `source_refs` 非空（与 AR-01 的 B 口径一致）。
- C 类：不参与缺引文降级。
- 缺引文 → 复制 claim、把 `statement` 追加进 `assumptions`（`why="缺引文/证据（AR-01）"`）、`status="speculation"`；返回 `(working, True)`，**不产生 fail**。

### 2.3 封顶

- 仅消费 `Finding.cap`（AR-05/AR-06 产出 `latex_verified`）。
- `_cap_status` 对 `failed`/`falsified` 不生效；只降不升。
- 已低于上限的状态不再改写，避免无意义变更。

### 2.4 状态常量

`STATUS_ORDER` 固定为
`formally_verified=7 > partially_formalized=6 > numerically_verified=5 > latex_verified=4 > speculation=3 > failed=2 > falsified=1`。
`TERMINAL={failed,falsified}`。

### 2.5 Stage 9 抽取

- 行清洗：去 `-`/`*`、去编号、去空行、跳过 `#` 标题与长度 < 12 的行。
- 去重后最多 50 条；空文本回退 `plan.objectives`。
- 每条写满 C4 14 项必填字段；`claim_id` 为 `c-` + sha256(statement) 前 8 位。

## 3. `stage_hooks.py`

### 3.1 Stage 9

```python
def write_stage9_claims(stage_dir, hypotheses_text, plan=None) -> tuple[str, ...]:
    claims = build_claim_records(hypotheses_text, plan)
    _write_claims(Path(stage_dir) / "claims.jsonl", claims)
    return ("claims.jsonl",)
```

### 3.2 Stage 20

- `load_claims(run_dir)` 取 `stage-09*/claims.jsonl` 中最新的文件；空行/坏行跳过。
- `_annotations(run_dir)` 读 `annotations.json`，只保留标量值。
- 每条 claim 调 `evaluate_claim(claim, annotations.get(claim_id))`。
- 写回 `stage-20/claims.jsonl`（更新后的 claim）与 `stage-20/claim_gate.json`。
- 返回值 `{"blocked": bool, "verdict": "pass|downgraded|block", "payload": {...}}`。

### 3.3 Stage 23

- 优先读 `stage-20/claims.jsonl`；缺失时回退 `stage-09`。
- `production = claim_gate.json.decisions`。
- 无 claim → `checked=0, consistent=True`；有 claim 但无 production → `skipped=no_production_gate, consistent=True`。
- 逐条 `audit_claim`，比对 `status`，再比对 `deliverable`。
- 写 `stage-23/claim_consistency.json`；`diffs` 非空即 `consistent=False`。

## 4. Stage 接线

| Stage | 调用点 | 失败映射 | artifacts |
|---|---|---|---|
| 9 | `_execute_experiment_design` 末尾，写 `exp_plan.yaml` 前 | 异常仅 warning | `exp_plan.yaml` + `claims.jsonl` |
| 20 | `_write_claim_verification` 后、SIM 检查前 | `E20_CLAIM_CONTRACT_INTERNAL` / `E20_CLAIM_CONTRACT` | 各分支追加 `claim_gate.json`、`claims.jsonl` |
| 23 | `_write_claim_verification` 后、bib 检查前 | `E23_CLAIM_DRIFT_INTERNAL` / `E23_CLAIM_DRIFT` | 成功分支追加 `claim_consistency.json` |

## 5. 测试

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_claim_policy.py` | 33 | A2-4 终态/fail finding、A2-5 数值标注、A2-6 A/B/C 降级、AR-05/06 封顶、双平面同值、Stage 9 抽取与 C4 schema |
| `tests/test_stage_claim_hooks.py` | 13 | Stage 9 hook + executor、Stage 20 pass/block/downgrade/executor、Stage 23 一致/状态漂移/可发布性漂移/续跑跳过/executor 阻断/无 bib 成功 |

机检读数：

- M4 测试：**46 passed**（Python 3.13.5，1.07s）。
- M4 测试：**46 passed**（Python 3.11.15 临时 venv，1.51s）。
- 相关回归（simulated guard / fabrication guards / claim verifier / AR checks / sidecar / contracts）：**105 passed**。
- `tests/test_rc_executor.py`：**207 passed**（234.37s）。
- 全量（排除 `tests/test_mcp.py`、`tests/test_mcp_protocol.py`：本机 Anaconda `mcp` 无 `MCPServer`，需 `[mcp]` extra）：**3328 passed / 7 failed / 108 skipped**（248.25s）。7 项失败均为既有环境性：shell hook `WinError 193`（1）、Keras 3 × Transformers（4）、bash 路径解析（1）、web server 默认 `0.0.0.0`（1），与 P-037 记录的「7 项环境性」一致，M4 改动不触及这些模块。

## 6. 施工注意

1. **C4 闭合**：不要给 claim 加 `annotation` 字段；标注只走 run 级 `annotations.json`。
2. **Stage 9 非阻断**：claim 抽取失败不得影响 `exp_plan.yaml`；异常必须吞掉并 warning。
3. **Stage 20 先于 SIM**：claim 契约优先于模拟数据检查；改顺序会让 `E20_CLAIM_CONTRACT` 被 `E20_SIMULATED_DATA` 掩盖。
4. **Stage 23 先于 bib**：一致性检查不依赖引文库；无 bib 的 run 也必须产出 `claim_consistency.json`。
5. **续跑容忍**：完全没有 Stage 20 生产决定时记 `skipped`，不得误判为漂移。
6. **不要重复降级**：`assumptions` 追加前按 `statement` 去重，保证 Stage 20 重跑幂等。

## 7. P-063 补记（2026-11-11）

P-062 复审 D-1..D-3 已由 [修复设计包](../arc-g2-m4-wiring-fixes/DESIGN.md) 关闭：`load_claims` 改为非版本目录优先；坏行/损坏 gate JSON 改 `ClaimStreamError`；claims/gate/consistency 改原子写；`evaluate_claim` 入口增加 C4 最小结构校验。M4 测试由 46 增至 **59 passed**（+13），原 46 项全部保留通过。
