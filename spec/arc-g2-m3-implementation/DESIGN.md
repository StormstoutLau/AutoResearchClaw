---
id: arc-g2-m3-implementation-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-m3-implementation-RESEARCH]
upstream: arc-g2-m3-implementation-RESEARCH
---

# 设计：G2 M3 sidecar 实施

> 基于 [RESEARCH.md](RESEARCH.md)。关闭 P-053 的 D-1/D-2，给出可直接施工的模块、契约与测试设计。

## 1. 范围

- **做**：ARC 侧 sidecar 客户端；AP 侧 `scripts/arb_verify.py`；`mode=lean_check` 的确定性验证；完整 C4 响应；降级与退出码；单元 + live 测试；**AP 侧一处超时证据修复**（D-C）。
- **不做**：NL→Lean 的 `mode=verify`（M4）；`leanchecker` 独立深度（4.20 无）；sidecar 随 wheel 分发。

## 2. 模块与文件

| 位置 | 文件 | 职责 |
|---|---|---|
| ARC | `researchclaw/evidence/sidecar.py` | 请求构造、进程启动、超时终止、响应校验、退出码映射 |
| ARC | `researchclaw/evidence/__init__.py` | 导出 `run_lean_check`、`SidecarResult`、错误类型 |
| ARC | `tests/test_evidence_sidecar.py` | 单元测试（mock 进程，无 Lean） |
| ARC | `tests/test_evidence_sidecar_live.py` | live 测试（环境门控，真实 Lean） |
| AP | `scripts/arb_verify.py` | JSON CLI：读请求、跑 Lean、建判定、写响应 |
| AP | `proof_pipeline/stages/proving_runtime.py` | **修改**：超时分支写 `diagnostics` 并置 `timed_out`（D-C） |
| AP | `proof_pipeline/datatypes/config.py` | **修改**：`CompileReport` 增 `timed_out: bool = False` |
| AP | （其余 `proof_pipeline/` 不改） | 复用 `LeanSimRuntime`、`LegalityChecker`、`decide_citation_label` |

## 3. D-1 判定映射（编译见证 + 真实合法性）

### 3.1 触发条件

构造最小树**当且仅当** `compile_report.success is True`。

`evidence_complete` **不进入建树条件**：它由 policy 的 `evidence_incomplete` 出口处理（P-057 O-A；`LeanSimRuntime` 当前两处构造点恒为 `True`，但删除该条件可避免未来出现 `success=True, evidence_complete=False` 时无树、又被 `latex_ok` 误标 `latex_verified`）。

含 sorry 时**也造树**，并令 `tree.sorry = len(compile_report.sorry_warnings)`；axiom 与合法性的处置交给 policy（`axioms_not_clean` / `axiom_check_skipped` / `legality_failed` / `tree_partial`）。否则 `proof_tree=None`、`legality_checked=False`，走 policy 的 `_fallback`。

> **P-055 D-A 修正**：旧设计把「无 sorry + axioms passed」也放进建树条件，导致含 sorry / axiom dirty / 编译失败时无树，而 `latex_ok=True` 常量又让它们回落成 `latex_verified`——越过 A2-7 上限。现改为「success 即建树，其余交给 policy」，并令 `latex_ok = compile_report.success`（编译失败 → `FAILED`，不再冒充 `latex_verified`）。

### 3.2 构造与判定

```python
if compile_report.success:
    tree = ProofTree(
        root=ProofNode(id="root", goal=theorem_name, status=NodeStatus.PROVEN),
        total_subgoals=1, proven=1,
        sorry=len(compile_report.sorry_warnings), blocked=0,
    )
    verified = VerifiedProof(
        theorem_name=theorem_name, lean_code=code,
        compile_status=compile_report.status, proof_tree=tree,
    )
    legality = LegalityChecker(PipelineConfig()).check(verified)   # 真实 7 层
else:
    tree, legality = None, None

evidence = VerdictEvidence(
    latex_ok=compile_report.success,          # 编译失败 → FAILED
    proof_tree=tree,
    compile_report=compile_report,
    legality_report=legality,
    legality_checked=tree is not None,
)
label, reason = decide_citation_label(evidence)
```

- **语义**：最小树是「kernel 已接受该定理（sorry 已计入 `tree.sorry`）」的**编译见证**（`tree_origin="compile_only"`），不是伪造证明；合法性由真实 `LegalityChecker` 报告背书。
- **反例（P-055 探针）**：合法代码 → `formally_verified / all_gates_passed`；`axiom cheat : False` → 第 2 层失败 → `partially_formalized / legality_failed`；sorry → `tree_partial`；编译失败 → `FAILED / stage1_not_success`。
- **禁止**：不运行合法性却设 `legality_checked=True`（P-053 D-1 的淘汰方案）。

### 3.3 深度映射

| `status` | `verification_depth` |
|---|---|
| `formally_verified` | `stage3` |
| `partially_formalized` / `numerically_verified` / `failed` / `falsified` | `stage2` |
| `latex_verified` / `speculation` | `stage1` |
| （未来 `leanchecker` 通过） | `stage3_5`（M4+，M3 不产出） |

**P-055 D-B 修正**：`failed` 由 `stage1` 改为 `stage2`——A2-7 明文要求「编译失败 → 深度 stage2」；`falsified` 来自 Stage 2 数值反例，同样记 `stage2`（lean_check 不产出，属 M4 语义）。`stage3_5` 保留但 M3 不写。

## 4. D-2 退出码与 `require_lean`

### 4.1 退出码

| 码 | 含义 | sidecar 场景 | 响应 |
|---|---|---|---|
| **0** | 完成（含业务失败） | 编译失败、`falsified`、可选 Lean 降级 | 写完整响应 |
| **65** | 数据错误 | 请求 JSON 非法、缺 C4 必填、`theorem_name` 非法 | 写错误响应 |
| **75** | 暂时性失败 | 编译/验证超时 | 写错误响应；可重试 |
| **78** | 配置/必需能力缺失 | `require_lean=true` 时工程/`lean-toolchain`/lake 缺失 | 写降级响应 |
| 77 | **保留**（REVOKED） | **sidecar 永不发出** | — |
| 85 | 保留（PAUSED） | 不使用 | — |

### 4.2 `require_lean` 语义

| 值 | 缺失 Lean/工程 | 结果 |
|---|---|---|
| `true`（`lean_check` 默认） | 是 | exit **78**；`degraded_reason` + `lean_unavailable_reason`；`depth=stage2`；不产出 `formally_verified` |
| `false`（M4 `verify` 预留） | 是 | exit **0**；同样写降级字段，体现 Lean 可选（Q2） |

**D-2 结论**：77 不被占用；必需 vs 可选由 `require_lean` 显式区分，避免 supervisor 把「Lean 缺失」误判为凭据撤销。

## 5. JSON 契约（v1.0）

### 5.1 请求

```json
{
  "schema_version": "1.0",
  "request_id": "req-20261111-0001",
  "mode": "lean_check",
  "require_lean": true,
  "claim": {
    "claim_id": "c-1a2b3c4d",
    "claim_class": "C",
    "claim_type": "exploratory",
    "statement": "For every natural number n, n + 0 = n.",
    "formal_statement": null,
    "formality": {"status": "formal", "reason": null},
    "assumptions": [],
    "evidence": [],
    "reasoning_chain": [],
    "stats_protocol": null,
    "falsifier": {"condition": "", "test_ref": ""},
    "verification_depth": "stage1",
    "status": "speculation",
    "policy_version": 2
  },
  "lean": {
    "lean_statement": "theorem probe_nat_add_zero (n : Nat) : n + 0 = n := by simp",
    "theorem_name": "probe_nat_add_zero",
    "source_project": "D:\\Textbook\\lean_src",
    "use_per_run_project": true,
    "timeout_s": 300
  }
}
```

- `claim` 必须是**完整 C4**（14 必填）；sidecar 只改 `status`/`verification_depth`/`policy_version`，不动其他字段。
- `lean_statement` ≤ 200,000 字符；`theorem_name` 限 `^[A-Za-z_][A-Za-z0-9_'.]*$`；`timeout_s` 钳制 5..1800。
- **`request_id` 限 `[A-Za-z0-9._-]+`**（P-059 O-4）；用于 sidecar 目录名与 AP per-run `run_id`。
- `source_project` 为空时读 `ARB_LEAN_PROJECT`；仍为空 → 按 §4 处理。
- **P-055 O-3**：`request_id` 会经 AP `_sanitize_run_id` 改写为 per-run `run_id`；响应中的 `lean.project` 是实际路径，ARC 不得假设目录名与 `request_id` 相同。
- **P-055 O-5**：ARC 硬超时 = 请求 `timeout_s` + 30s（进程启动/响应落盘缓冲）；契约两侧只认请求里的 `timeout_s`，客户端不另配业务超时。

### 5.2 响应

```json
{
  "schema_version": "1.0",
  "request_id": "req-20261111-0001",
  "run": {
    "run_id": "req-20261111-0001",
    "attempt": 1,
    "inputs_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "exit_code": 0,
    "status": "succeeded",
    "usage": {"build_ms": 8421.0, "total_ms": 9100.0}
  },
  "claim_record": {
    "claim_id": "c-1a2b3c4d",
    "claim_class": "C",
    "claim_type": "exploratory",
    "statement": "For every natural number n, n + 0 = n.",
    "formal_statement": null,
    "formality": {"status": "formal", "reason": null},
    "assumptions": [],
    "evidence": [],
    "reasoning_chain": [],
    "stats_protocol": null,
    "falsifier": {"condition": "", "test_ref": ""},
    "verification_depth": "stage3",
    "status": "formally_verified",
    "policy_version": 2
  },
  "lean": {
    "available": true,
    "version": "4.20.0",
    "toolchain": "leanprover/lean4:v4.20.0",
    "project": "C:\\Users\\...\\lean_runs\\req-...",
    "tree_origin": "compile_only",
    "legality": {"overall_pass": true, "failed_layers": []},
    "axioms": ["propext"],
    "sorry": 0
  },
  "degraded_reason": null,
  "lean_unavailable_reason": null
}
```

- `run` 满足 C1 必填且**无 `verdict`**；判定只在 `claim_record.status`。
- `claim_record` 为**完整 C4**（O-1）；`policy_version` 取 AP 当前值（2）。
- 失败也写响应：`exit_code` 非 0，`claim_record.status` 不提升，`degraded_reason` 说明原因。

## 6. 进程生命周期与安全

### 6.1 ARC 客户端

1. `run_dir = <artifacts>/<run_id>/sidecar/<request_id>`；`mkdir(parents=True)`。
2. 请求写入 `request.json.tmp` → `os.replace` → `request.json`（S-9）。
3. `Popen([python, script, "--request", ..., "--response", ...], cwd=run_dir, env=allowlist, stdout/stderr 落文件, creationflags=CREATE_NEW_PROCESS_GROUP)`（S-8）。
4. `wait(timeout=timeout_s + 30)`；超时 → `taskkill /pid <pid> /t /f`（S-10）→ `SidecarTimeout`（75）。
5. 读 `response.json`；缺失/非法 → `SidecarError`。
6. 窄校验：`schema_version`、`run.exit_code`、`claim_record` 必填键、`claim_record.status` 枚举；全量 C4 校验只在测试态用 `jsonschema`。
7. 退出码映射：0 结果；65 `SidecarRequestError`；75 `SidecarTimeout`；78 `SidecarConfigError`；其他非 0 `SidecarError`。

### 6.2 环境白名单

只传 `PATH`、`SYSTEMROOT`、`TEMP`、`TMP`、`USERPROFILE`、`PYTHONUTF8`、`PYTHONIOENCODING`、`PYTHONPATH`（AP 根）、`ARB_LEAN_PROJECT`、`ARB_LEAN_RUN_ROOT`、`ARB_LEAN_LAKE`。**不透传** ARC 的 provider key、endpoint、token。

> **P-060 实测**：`PYTHONUTF8` 不可省——缺它时 sidecar 以系统代码页解码 Lean 的 UTF-8 诊断，`#print axioms`/sorry 行丢失，判定退化为 `axiom_check_skipped`（Live L-A 曾因此失败）。`USERPROFILE` 为 P-059 O-6 的保险项（本机 elan 4.2.0 无它也工作）。

### 6.3 AP 脚本

1. `argparse --request --response`；读 JSON；校验 schema/字段（失败 → 65）。
2. 解析工程：`lean.source_project` → `ARB_LEAN_PROJECT`；检查目录与 `lean-toolchain`。
3. 解析 lake：`ARB_LEAN_LAKE` → `shutil.which("lake")`。
4. 必需能力缺失且 `require_lean=true` → 写降级响应 + exit 78；`false` → 写降级响应 + exit 0。
5. `use_per_run_project=true` → `create_per_run_project`（AP）；失败按配置错误 78。
6. `LeanSimRuntime(lake_path, project_dir).compile_report(code, theorem_name, timeout)`；`is_llm_code=True` 走 AP 危险构造过滤。
7. **超时**：AP `compile_report` 在 `_run_build` 超时后置 `report.timed_out=True`（见 §2 的 AP 改动）；arb_verify 见 `timed_out` → 写响应 `exit 75` + `lean_timeout`，不再走普通失败。
8. 按 §3 构造树/合法性/判定；更新 C4；写响应（`finally` 中保证落盘）。
9. `finally`：`remove_per_run_project`（Windows 文件锁重试）；不删除 request/response（审计）。

> **P-055 D-C 修正（实现口径）**：`compile_report` 虽然是 `async def`，内部却同步调用 `_run_build`（阻塞事件循环），**`asyncio.wait_for` 无法抢占**。因此不能只在 arb_verify 外层加 `wait_for`；必须让 AP 把超时信号结构化（`CompileReport.timed_out`），arb_verify 据此返回 75。ARC 的 `timeout_s + 30` 硬超时仅作**兜底**：若 sidecar 整体挂死，客户端 `taskkill /T` 后合成 75 结果（无响应文件）。

## 7. 降级矩阵（实施口径）

| 条件 | `require_lean` | exit | status 上限 | depth | `degraded_reason` |
|---|---|---|---|---|---|
| lake 缺失 | true | 78 | 不提升（封顶 `latex_verified`） | stage2 | `lean_unavailable` |
| lake 缺失 | false | 0 | 不提升（封顶 `latex_verified`） | stage2 | `lean_unavailable` |
| 工程/`lean-toolchain` 缺失 | true | 78 | 不提升 | stage2 | `lean_project_missing` |
| 工程/`lean-toolchain` 缺失 | false | 0 | 不提升 | stage2 | `lean_project_missing` |
| 编译失败 | 任意 | 0 | `FAILED`（`latex_ok=False`） | stage2 | `lean_compile_failed` |
| 含 sorry | 任意 | 0 | `partially_formalized` | stage2 | `lean_sorry_present` |
| axiom 不干净/未检 | 任意 | 0 | `partially_formalized` | stage2 | `axioms_not_clean` |
| 合法性失败 | 任意 | 0 | `partially_formalized` | stage2 | `legality_failed` |
| 危险构造被拒 | 任意 | 0 | `failed` | stage2 | `rejected_dangerous_construct` |
| 超时（`timed_out`） | 任意 | 75 | 不提升 | stage2 | `lean_timeout` |
| sidecar 整体硬超时 | 任意 | 75 | 不提升 | stage2 | `lean_timeout`（客户端合成） |

**判定优先级（P-057 O-B）**：policy 的短路顺序为 `tree_partial`（sorry/blocked）> `file_sorry`（sorry 警告）> `evidence_incomplete` > `axioms_not_clean`/`axiom_check_skipped` > `legality_not_checked`/`legality_failed` > `all_gates_passed`。多条件并存时按此取第一条；矩阵各行为单条件示例。

**危险构造检测（P-057 O-C）**：`rejected_dangerous_construct` 以 `report.diagnostics.startswith("rejected:")` 判定——`proving_runtime.py:161` 的拒绝分支稳定写入该前缀，不新增 AP 字段。

## 8. 测试设计

### 8.1 单元（ARC，无 Lean，进 CI 固定清单）

| # | 用例 | 断言 |
|---|---|---|
| U-1 | 请求原子写 | 目标文件存在且无 `.tmp` 残留 |
| U-2 | 缺失响应 | 抛 `SidecarError` |
| U-3 | exit 65/75/78 | 映射到对应异常 |
| U-4 | 超时终止 | mock `Popen` 断言调用 `taskkill /t /f` |
| U-5 | 响应窄校验 | 缺 `claim_record`/非法 `status` 拒绝 |
| U-6 | 完整 C4 | 14 必填通过（jsonschema 测试态） |
| U-7 | 环境白名单 | 不含 `*_API_KEY`/endpoint |
| U-8 | 参数注入 | 含空格/引号的 theorem_name 被拒（65） |

### 8.2 Live（环境门控，CI skip）

| # | 场景 | 预期 |
|---|---|---|
| L-A | 4.20 工程 + 可证定理 | exit 0；`formally_verified`；`depth=stage3`；`tree_origin=compile_only` |
| L-B | 工程不存在 + `require_lean=true` | exit 78；`lean_project_missing` |
| L-C | lake 缺失 + true/false | 78 / 0；`lean_unavailable`；depth stage2 |
| L-D | 注入 sorry | `partially_formalized`；depth stage2 |
| L-E | 语法错误 | 不提升；`lean_compile_failed`；exit 0 |
| L-F | 注入 axiom | `partially_formalized`；`legality_failed` |
| L-G | 极小 timeout | exit 75；`lean_timeout`（`timed_out=True`） |
| L-H | 危险构造（`#eval`/`axiom` 之外的 `IO.`） | `failed`；`rejected_dangerous_construct`；exit 0 |

门控：`ARB_LEAN_PROJECT` 存在且 `shutil.which("lake")` 非空，否则 `pytest.skip`（S-11，C-3）。

## 9. 兼容与风险

| 风险 | 缓解 |
|---|---|
| AP 上游改动导致 `LegalityChecker` 行为变化 | 记录所需 AP commit（`bd95f02` 起）；live 测试锁定 |
| AP 超时字段（`timed_out`）漂移 | 该字段为 M3 新增契约；AP 测试与 live L-G 双锁定；vendor 升级时复核 |
| 最小树被误读为「伪造证明」 | 响应 `tree_origin=compile_only`；DESIGN/README 写明语义；合法性真实运行 |
| `taskkill` 留孤儿 | U-1；连续 2 次泄漏改 Job Object |
| `theorem_name` 非法/Unicode | 正则白名单；不合法 → 65 |
| 构建时间波动（warm 8.4s / 冷 53.3s） | `timeout_s` 默认 300；验收允许区间 |
| C4 完整记录由调用方提供 | M4 适配器补齐；缺失 → 65 |

## 10. 开放项

- U-1：taskkill → Job Object（触发：孤儿进程）。
- U-2：`mode=verify`（M4）。
- U-3：sidecar 打包（发布审阅）。
