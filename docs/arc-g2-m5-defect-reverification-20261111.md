# P-066 M5 缺陷发现与复核报告（2026-11-11）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。在 [P-065 异构复审](arc-g2-m5-offline-audit-review-20261111.md) D-1..D-3 基础上，用**独立探针**重新验证缺陷是否成立、是否影响 Stage 23，并补充复核中新发现的同族缺陷。
> **对象**：[P-064 G2 M5 离线审查模式](../spec/arc-g2-m5-offline-audit/IMPLEMENTATION.md)。工作树状态：P-064/P-065 已暂存未提交。
> **编号说明**：本报告占用 **P-066**（T3 文档批）；修复批先顺延 **P-067**、再由 [P-067 报告复核](arc-g2-m5-p066-review-20261111.md) 占用后**顺延 P-068**（沿 P-054 让位先例）。
> **探针**：`%TEMP%\p066_reverify_probe.py`（C0、D-1a、D-1b、D-1c、D-2、D-3）+ 内联 Stage 23 复核；全部临时目录，零仓库变异。

## 1. 复核结论

| 探针 | 场景 | 实测输出 | 判定 |
|---|---|---|---|
| C0 | 2 claims + 2 decisions（对照） | gate `pass`；offline `consistent=True, checked=2`；Stage 23 `True` | 基线正常 |
| D-1a | 删除 1 条 claim 行，保留 2 条 decision | `production keys=['c-11111111','c-22222222']`；`checked=1`；offline `consistent=True`；Stage 23 `True`；`diffs=[]` | **D-1 成立** |
| D-1b | 删除全部 claims（stage-20 + stage-09），保留 decision | `checked=0`；`skipped=no_claims`；`consistent=True`；Stage 23 `True, checked=0` | **D-1 成立（整份删除）** |
| D-1c | 两条 claim 使用同一 `claim_id` | gate `decisions=1`；`checked=2`；offline `consistent=True`；Stage 23 `True, checked=2` | **D-4 成立（新发现）** |
| D-2 | `--policy-version 0` | `rc=0`；`expected_policy_version=2` | **D-2 成立** |
| D-3 | `--json --output` | `rc=0`；stdout 首行 `audit: report written to ...`；`json.loads` 失败 | **D-3 成立** |

**结论**：P-065 的 D-1/D-2/D-3 全部复现；D-1 同时影响 Stage 23（同一 `compare_claims`），非仅离线审计；复核新增 **D-4 重复 `claim_id` 导致生产决定被覆盖**。

## 2. 根因

| # | 级 | 根因 | 代码位置 |
|---|---|---|---|
| **D-1** | P2 | `compare_claims` 只做 `claim → decision` 单向比对，缺 `set(production) − set(claim_keys)` 的孤儿检查；claims 为空时循环空转 | [stage_hooks.py](../researchclaw/evidence/stage_hooks.py) `compare_claims` |
| **D-2** | P3 | `args.policy_version or CURRENT_POLICY_VERSION`：`0` 为 falsy，静默回退默认版本 | [cli.py](../researchclaw/cli.py) `cmd_audit` |
| **D-3** | P3 | 「report written」提示打印到 stdout，先于 JSON 输出 | [cli.py](../researchclaw/cli.py) `cmd_audit` |
| **D-4** | P3 | gate 以 `claim_id` 为 dict 键，重复 id 后写覆盖前写；C4 与 P-063 结构校验均不检查集合内唯一性 | [stage_hooks.py](../researchclaw/evidence/stage_hooks.py) `run_stage20_gate` |

**连带语义**：`offline_audit` 在 claims 为空时无条件写 `skipped=no_claims`，与 D-1 修复后的孤儿 diff 冲突；修复需同时收紧为「无 claims **且**无 production 才跳过」。

## 3. 修复方案（P-067）

### F-1 对称孤儿检查（D-1）

`compare_claims` 逐条比对后追加：

```python
keys = [_claim_key(claim, i) for i, claim in enumerate(claims)]

duplicates = sorted(k for k, n in Counter(keys).items() if n > 1)
for key in duplicates:
    diffs.append({"claim_id": key, "reason": "duplicate_claim_id"})

orphans = sorted(set(production) - set(keys))
for key in orphans:
    prod = production[key]
    diffs.append({
        "claim_id": key,
        "reason": "orphan_production_decision",
        "production": prod.get("status") if isinstance(prod, dict) else None,
    })
```

- 同时覆盖 D-1a（删一行）与 D-1b（删全部）。
- Stage 23 自动继承：孤儿 → `consistent=False` → `E23_CLAIM_DRIFT`。

### F-2 重复 `claim_id` 阻断（D-4）

- `run_stage20_gate` 预扫描 `Counter(_claim_key(...))`；重复键加入 `blocked`（reason `duplicate_claim_id`），payload 增 `duplicate_claim_ids`，verdict 直接 `block`。
- `compare_claims` 同步做重复检查，防止 gate 之后被篡改。
- 正常 Stage 9 路径已按 statement 去重，不产生重复 id；该规则面向外部导入/篡改。

### F-3 版本参数显式判空（D-2）

```python
expected = args.policy_version
if expected is None:
    expected = CURRENT_POLICY_VERSION
elif expected < 1:
    print("audit: --policy-version must be >= 1", file=sys.stderr)
    return 2
```

### F-4 诊断信息走 stderr（D-3）

```python
print(f"audit: report written to {out}", file=sys.stderr)
```

数据留 stdout、诊断留 stderr。

### F-5 跳过语义收紧

```python
elif not claims and not production:
    payload["skipped"] = "no_claims"
```

有 production 无 claims → 不写 `skipped`，只报孤儿 diff，避免「skipped 且 inconsistent」的矛盾报告。

## 4. 契约变更

| 位置 | 变更 |
|---|---|
| `compare_claims` diff reasons | 新增 `orphan_production_decision`、`duplicate_claim_id` |
| `claim_gate.json` | `blocked[].reasons` 可含 `duplicate_claim_id`；payload 增 `duplicate_claim_ids` |
| offline report | 无新增必填字段；`diffs` 可出现上述两种 reason |
| CLI | `--policy-version < 1` → exit 2；`--output` 提示改 stderr |
| Stage 23 | 孤儿/重复 → `consistent=False` → `E23_CLAIM_DRIFT`（预期收紧） |

## 5. 测试计划

| 用例 | 断言 |
|---|---|
| `test_offline_audit_detects_orphan_production_decision` | 删一行 → `orphan_production_decision`，`consistent=False` |
| `test_stage23_detects_orphan_production_decision` | 同一 run → Stage 23 `consistent=False` |
| `test_offline_audit_all_claims_deleted_is_drift` | 删全部 claims、保留 gate → 孤儿 diff，无 `skipped` |
| `test_stage20_gate_blocks_duplicate_claim_id` | verdict `block`，payload 含 `duplicate_claim_ids` |
| `test_offline_audit_detects_duplicate_claim_id` | 篡改后重复 id → `duplicate_claim_id` diff |
| `test_cli_audit_rejects_policy_version_zero` | `rc=2`，stderr 有提示 |
| `test_cli_audit_json_output_keeps_stdout_clean` | `--json --output` 时 stdout 可解析，提示在 stderr |

预期：M5 29 → **36**；M4+M5 88 → **95**；既有 29 项零回归。

## 6. 影响面与风险

- **正常管线**：Stage 20/23 的 claim 与 decision 始终 1:1，孤儿检查不触发。
- **续跑**：`no_production_gate` 不受影响；仅「有 gate 无 claims」判漂移。
- **PIVOT**：stage-20 claims 缺失时回退 stage-09；若两代 claim id 不同，孤儿 diff 如实报告「旧 gate 配新 claims」，属期望的 fail-closed。
- **误报风险**：外部导入 claim 若 id 重复，Stage 20 将阻断——这是有意的完整性要求，G3 导入侧需保证唯一 id。
- **兼容性**：不新增依赖、不改 C4 schema；`claim_gate.json` 仅增字段。

## 7. 社区先例映射

| 修复 | 先例 | 映射 |
|---|---|---|
| F-1 孤儿检查 | **Argo CD Orphaned Resources Monitoring**（argo-cd.readthedocs.io） | 双平面比对必须检测「不属于任何 Application 的孤儿资源」；对应「有 decision 无 claim」 |
| F-1 记录/重算 | **OPA Decision Logs**（openpolicyagent.org） | 生产记录决策、审计平面用同一评估器重放 |
| F-2 重复/不一致拒绝 | **Flyway Validate**（Redgate 文档） | 检测事后增删改，不一致即报错拒绝，不给默认值 |
| F-3 版本锚点 | **OPA bundle revision / Flyway version** | 版本不符必须可判定 |
| F-4 退出码/流分离 | **pytest exit codes** 与 **Terraform `-detailed-exitcode`** | 1=可判定失败、2=输入/错误；数据走 stdout、诊断走 stderr |
| F-1 只读审计 | **git fsck** / **pt-table-checksum** | 只读校验，不修改被审计对象 |

> 锚点完整回源与 URL 见 [P-065 §3](arc-g2-m5-offline-audit-review-20261111.md)。

## 8. 结论与批次安排

- **D-1/D-2/D-3 复核成立，D-4 新登记**；四项均有机械修法，无需改判定内核或 C4 契约。
- **P-068 修复批**（T1）：F-1..F-5 + 7 项测试 + M5 四文档升版 + session + PROGRESS；完成后 M5 复审缺陷收口。**F-1 集成方式按 [P-067 复审](arc-g2-m5-p066-review-20261111.md) D-5 执行**：守卫保留于逐条循环，duplicate/orphan 集合检查无条件执行。
- **可选顺带**（建议同批）：O-1 报告透传 gate verdict、O-2 claims 来源溯源、O-3 报告原子写、O-5 状态矩阵绑定 `STATUS_ORDER`、O-6 退出码语义注明；另 P-067 O-B（`--output` 写失败捕获）。
- **不纳入**：O-4 私有名公开化（代码卫生，后续）、O-7 session 时间戳（数据卫生，存档）。

## 9. 附录：探针复现

```powershell
python "$env:TEMP\p066_reverify_probe.py"
```

探针使用临时目录构造 claim/gate，依次执行 C0、D-1a、D-1b、D-1c、D-2、D-3；Stage 23 复核用内联脚本对同一 run 调用 `run_stage23_consistency`。全部只读仓库代码，不写工作树。
