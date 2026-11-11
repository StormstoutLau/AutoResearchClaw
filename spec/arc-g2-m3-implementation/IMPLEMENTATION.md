---
id: arc-g2-m3-implementation-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-m3-implementation-DESIGN]
upstream: arc-g2-m3-implementation-DESIGN
---

# 实施记录：G2 M3 sidecar

> **状态**：P-060 已施工完成（AP + ARC + 测试 + vendor 同步），本文件记录**实际改动与读数**；CHECKLIST 已 accepted。O-2..O-7 全部落实。
> **依据**：[DESIGN.md](DESIGN.md) §3（D-1）、§4（D-2）、§5（契约）、§6（生命周期）。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `F:\Auto_Prover\scripts\arb_verify.py` | 新增（AP） | JSON CLI：请求校验、工程/lake 解析、编译、判定、响应落盘 |
| 2 | `F:\Auto_Prover\proof_pipeline\datatypes\config.py` | 修改（AP） | `CompileReport` 增 `timed_out: bool = False`（D-C） |
| 3 | `F:\Auto_Prover\proof_pipeline\stages\proving_runtime.py` | 修改（AP） | `_BuildOutcome` 增 `timed_out`；超时分支写 `diagnostics`（D-C） |
| 4 | `researchclaw/evidence/sidecar.py` | 新增（ARC） | 客户端：请求写、进程启动、超时终止、响应校验、退出码映射 |
| 5 | `researchclaw/evidence/__init__.py` | 修改 | 导出 `SidecarConfig`、`SidecarResult`、`run_lean_check` 与错误类型 |
| 6 | `tests/test_evidence_sidecar.py` | 新增 | 8 项单元测试（mock，无 Lean） |
| 7 | `tests/test_evidence_sidecar_live.py` | 新增 | 8 项 live（`ARB_LEAN_PROJECT` 门控） |
| 8 | `.github/workflows/ci.yml` | 修改 | 单元测试加入固定清单；live 测试在 CI skip |
| 9 | `docs/PROGRESS.md` | 修改 | P-060 执行行与读数 |
| 10 | `researchclaw/vendor/auto_prover/datatypes/config.py` | 修改 | re-vendor：`timed_out` + 修改声明；`SOURCE.json` 重算 sha256（O-5） |
| 11 | `F:\Auto_Prover\tests\test_arc_m3_timeout_evidence.py` | 新增（AP） | 超时证据单测 |

**不改**：M0 契约 schema；ARC 3.11 内核；AP 其余 `proof_pipeline/` 模块。

## 2. AP 侧 `arb_verify.py`（新增）

### 2.1 CLI

```text
python scripts/arb_verify.py --request <request.json> --response <response.json>
```

- 退出码按 DESIGN §4；任何异常都必须落一份响应，再返回码。
- 不读 stdin，不写 stdout 业务数据（stdout 仅诊断；ARC 不解析）。

### 2.2 函数分解

```python
def load_request(path: Path) -> dict
def validate_request(req: dict) -> None            # 失败抛 RequestError -> 65
def resolve_project(req: dict) -> tuple[Path, str] # (project, toolchain)；缺失抛 CapabilityError
def resolve_lake() -> str | None                   # ARB_LEAN_LAKE 或 shutil.which("lake")
def build_tree(theorem_name: str) -> ProofTree     # 根 PROVEN，total=1/proven=1
def run_legality(code: str, tree: ProofTree) -> LegalityReport
def decide(req: dict, report: CompileReport) -> tuple[str, str, str | None]
def build_response(req: dict, exit_code: int, ...) -> dict
def main() -> int
```

### 2.3 执行顺序

1. 读请求；`schema_version == "1.0"`、`mode == "lean_check"`、C4 14 必填、`theorem_name` 正则、`lean_statement` 长度、`timeout_s` 钳制。
2. 解析工程：`lean.source_project` → `ARB_LEAN_PROJECT`；检查目录与 `lean-toolchain`。
3. 解析 lake；`require_lean=true` 且缺失 → 写降级响应 + **78**；`false` → 写降级响应 + **0**。
4. `use_per_run_project=true` → `create_per_run_project(source, run_root=ARB_LEAN_RUN_ROOT or temp, run_id=request_id)`；失败 → 78。
5. `LeanSimRuntime(lake_path=lake, project_dir=project).compile_report(code, theorem_name, timeout_s)`。
6. **超时**：`report.timed_out` 为真 → 写响应 `exit 75` + `lean_timeout`，跳过判定（不提升状态）。
7. 按 DESIGN §3：`report.success` → 最小树（`tree.sorry=len(report.sorry_warnings)`）+ `LegalityChecker` + `legality_checked=True`；否则 `tree=None`、`latex_ok=False`。若 `report.diagnostics.startswith("rejected:")` → `rejected_dangerous_construct`（P-059 O-7）。
8. `decide_citation_label` → `status`；映射 `verification_depth`；更新 C4 的 `status`/`verification_depth`/`policy_version`。
9. `finally`：写响应（原子）、`remove_per_run_project`；保留 request/response。

### 2.4 响应构造要点

- `run.inputs_digest = "sha256:" + sha256(request_bytes)`。
- `run.status`：0→`succeeded`；75→`timeout`；65/78→`failed`。
- `claim_record` 必须是**完整 C4**（不得只回投影）。
- `lean.tree_origin = "compile_only"` 仅在造树时出现；`legality` 只回 `overall_pass`/`failed_layers`。
- `degraded_reason`/`lean_unavailable_reason` 按 DESIGN §7。

## 3. ARC 侧 `sidecar.py`（新增）

### 3.1 公开 API

```python
@dataclass(frozen=True)
class SidecarConfig:
    python_exe: str
    ap_root: Path
    timeout_s: float = 330.0
    require_lean: bool = True
    env_extra: Mapping[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class SidecarResult:
    exit_code: int
    response: dict
    request_path: Path
    response_path: Path

class SidecarError(RuntimeError): ...
class SidecarRequestError(SidecarError): ...   # 65
class SidecarTimeout(SidecarError): ...        # 75
class SidecarConfigError(SidecarError): ...    # 78

def run_lean_check(
    claim: Mapping[str, Any],
    lean_statement: str,
    theorem_name: str,
    *,
    config: SidecarConfig,
    run_dir: Path,
    source_project: str | None = None,
    use_per_run_project: bool = True,
) -> SidecarResult
```

### 3.2 内部函数

```python
def _build_env(config: SidecarConfig) -> dict[str, str]   # 白名单
def _write_json_atomic(path: Path, payload: dict) -> None  # tmp + os.replace
def _kill_tree(pid: int) -> None                            # taskkill /pid /t /f
def _validate_response(payload: dict) -> None               # 窄校验
def _map_exit(code: int, payload: dict) -> None             # 抛对应异常
```

- `_build_env` 只保留 `PATH/SYSTEMROOT/TEMP/TMP/PYTHONPATH/ARB_LEAN_PROJECT/ARB_LEAN_RUN_ROOT/ARB_LEAN_LAKE`。
- `_write_json_atomic` 的临时文件必须与目标同目录（`os.replace` 同文件系统，S-9）。
- 超时等待 `timeout_s + 30`，留出进程启动与响应落盘时间。
- `_validate_response` 检查：`schema_version`、`request_id` 一致、`run.exit_code` 为整数、`claim_record` 必含 C4 14 键、`claim_record.status` 属于 7 值枚举、`verification_depth` 属于 4 值枚举。

### 3.3 并发与审计

- 每请求独立 `run_dir`；`request_id` 作为子目录名（仅 `[A-Za-z0-9._-]`）。
- request/response 永久保留（审计）；临时 Lean 工程由 sidecar 清理。

## 4. 测试清单（执行批落地）

### 4.1 单元（`tests/test_evidence_sidecar.py`，无 Lean）

| # | 用例 | 关键断言 |
|---|---|---|
| U-1 | 原子写 | 无 `.tmp` 残留 |
| U-2 | 响应缺失 | `SidecarError` |
| U-3 | 65/75/78 | 对应异常类型 |
| U-4 | 超时 | mock `Popen`/`taskkill` 调用参数 |
| U-5 | 窄校验 | 缺键/非法枚举拒绝 |
| U-6 | 完整 C4 | 14 必填通过（jsonschema 测试态） |
| U-7 | 环境白名单 | 不含 API key/endpoint |
| U-8 | 非法 theorem_name | 请求侧拒绝（65） |

### 4.2 Live（`tests/test_evidence_sidecar_live.py`，门控）

| # | 场景 | 预期 |
|---|---|---|
| L-A | 可证定理 | 0 / `formally_verified` / stage3 |
| L-B | 工程缺失 + true | 78 / `lean_project_missing` |
| L-C | lake 缺失 true/false | 78 / 0；stage2 |
| L-D | sorry | `partially_formalized` / stage2 |
| L-E | 语法错误 | 不提升 / `lean_compile_failed` |
| L-F | axiom 注入 | `partially_formalized` / `legality_failed` |
| L-G | 极小 timeout | 75 / `lean_timeout`（`timed_out`） |
| L-H | 危险构造（`IO.`） | `failed` / `rejected_dangerous_construct`；exit 0 |

门控：`ARB_LEAN_PROJECT` + `shutil.which("lake")`；否则 `pytest.skip`（S-11）。

## 5. 实施顺序（P-060）

1. **AP 超时证据**：`CompileReport.timed_out` + `_run_build` 超时分支写 `diagnostics`，补 AP 单测。
2. AP `arb_verify.py` 纯函数骨架（请求校验、响应构造）→ 本地以假数据跑通 65/78/75。
3. ARC `sidecar.py` + 8 项单元测试（mock）→ 3.11/3.13 全绿。
4. AP 接真实 Lean（`LeanSimRuntime` + `LegalityChecker`）→ live L-A/L-D/L-F。
5. 补 L-B/L-C/L-E/L-G/L-H；记录 warm/cold 计时。
6. CI 固定清单加入单元测试；live 文件保留 skip。
7. 回填 §6 读数、CHECKLIST 勾选、PROGRESS P-060。
8. 施工后重跑 AP 相关测试并与 **P-058 基线**对比（无 Lean 环境：`29 passed, 2 skipped`；`AUTO_PROVER_LAKE_PROJECT` 指向 **per-run 项目**而非 `lean_src`，否则 b27 真实用例因无 `Main` 目标失败）。
9. **P-059 O-5**：`datatypes/config.py` 改动涉及 vendor 清单——随批 re-vendor 该文件（Modified 头 + `SOURCE.json` 重算 sha256）或登记 pending-divergence。
10. **P-059 O-1**：本文件与 DESIGN 版本号随施工批递增（1.1）。

## 6. 验证命令与预期读数（待执行）

```powershell
# 单元（3.13 与 3.11 venv）
python -m pytest tests/test_evidence_sidecar.py -q
# 预期：8 passed

# live（本机 Lean 4.20 工程）
$env:ARB_LEAN_PROJECT="D:\Textbook\lean_src"
python -m pytest tests/test_evidence_sidecar_live.py -q
# 预期：8 passed（L-A..L-H）

# 直接 CLI 冒烟
python F:\Auto_Prover\scripts\arb_verify.py --request <req> --response <resp>
# 预期：exit 0；claim_record.status=formally_verified；depth=stage3

# 门禁
pre-commit run --all-files
python scripts/spec/roadmap_coverage_check.py
```

| 项 | 预期 | 实测（P-060） |
|---|---|---|
| 单元 | 8 passed | **10 passed**（8 项 + 退出码参数化 3） |
| live | 8 passed | **8 passed**（11.65s，本机 Lean 4.20） |
| L-A 构建 | rc=0，warm 8–60s | **`formally_verified` / stage3 / legality pass** |
| L-D sorry | `partially_formalized` | **`partially_formalized` / `lean_sorry_present`** |
| L-F axiom | `legality_failed` | **`axioms_not_clean`**（policy 先于 legality；L-F 用例允许两者） |
| L-G 超时 | 75 / `timed_out=True` | **75 / `lean_timeout`** |
| L-H 危险构造 | `rejected_dangerous_construct` | **`failed` / `rejected_dangerous_construct`** |
| AP 测试 | 基线 29 passed/2 skipped | **30 passed / 2 skipped**（新增超时单测） |
| vendor | 99 passed | **99 passed**（config.py re-vendor 后） |
| wheel/包 | 无新增依赖 | **无新增 ARC 运行时依赖** |

## 7. 回退点

- 删除 `arb_verify.py`、`sidecar.py`、两个测试文件与 CI 行即可回到当前状态。
- 不改 schema/AP 内核，无数据迁移；已产生的 request/response 仅是审计文件。
- 若 D-1 的最小树在真实工程上触发 `legality_failed`，按 fail-safe 接受 `partially_formalized`，不回退代码。

## 8. 工程注意

1. **不伪造证据**：`tree_origin=compile_only` 必须出现在响应；无树时不得声称形式化。
2. **不占用 77**：`_map_exit` 显式拒绝 77；遇到 77 抛 `SidecarError`（契约违规）。
3. **不传凭据**：`_build_env` 白名单；测试 U-7 机械断言。
4. **不吞超时**：AP 内部超时置 `timed_out=True` → 响应 75；ARC 硬超时先 `taskkill /t /f` 再合成 75，不得仅 `Popen.kill()`。
5. **不让 lake 警告污染诊断**：sidecar 只信 `compile_report` 结构化字段，不从 stdout 解析。
6. **Windows 路径**：全部 `Path`；JSON 中统一 `str()`；不拼接 `\\`。
7. **超时字段兼容**：`CompileReport.timed_out` 默认 `False`，AP 既有构造点零变化；vendor（P-049）不含 `proving_runtime`，无需同步。
