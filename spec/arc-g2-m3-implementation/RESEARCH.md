---
id: arc-g2-m3-implementation-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-m3-sidecar, arc-g2-m0-contracts, arc-g2-m2-vendor]
upstream: arc-g2-m3-sidecar
---

# 调研：G2 M3 sidecar 实施工程细节

> **Feature**：P-054，M3 实施批的工程调研（设计包）。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `researchclaw/evidence/sidecar.py`、AP `scripts/arb_verify.py` 与测试）。
> **结论先行**：P-053 的 **D-1 已可解**——最小 `ProofTree`（根 PROVEN）+ **真实运行 AP 7 层 `LegalityChecker`** 后，`decide_citation_label` 返回 `formally_verified`（本批探针）；仅造树不跑合法性只会得到 `partially_formalized`。**D-2 按「必需 vs 可选」拆分**：77 保留给 REVOKED，必需 Lean 缺失用 78，可选 Lean 缺失走 exit 0 + `degraded_reason`。工程形态：ARC 侧文件型客户端 + AP 侧 JSON CLI，进程每请求、超时 `taskkill /T`、响应返回**完整 C4**。
> **修订**：v1.1（2026-11-11，P-056 设计修复）**D-A/D-B/D-C 修正**——建树条件改为「success 即建树、sorry 计入 `tree.sorry`」；`latex_ok=report.success`；`failed→stage2`；超时改用 AP `CompileReport.timed_out`（`wait_for` 无法抢占同步 `_run_build`）。新增 F-13/F-14。

## 1. 问题与开工前置

P-053 复审确认两项 P1 缺口，必须在实施前定案：

1. **D-1**：`lean_check` 只有 `CompileReport`，而 AP policy 在 `proof_tree=None` 时先短路；即使 `synthesis_verified=True` 也只给 `latex_verified`。§9 场景 A（`formally_verified`）不可达。
2. **D-2**：调研 §7.3 把 77 用作「能力不可用」，与 ARC G1b 的 `77=REVOKED` 冲突。

同时吸收 O-1..O-5：响应须返回完整 C4；总纲待同步；降级措辞按 `_fallback`；计时允许 warm 区间；过滤 lake 警告行。

## 2. 一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | **仅造最小树**（根 PROVEN，sorry/blocked=0）+ `CompileReport(success, evidence_complete, axiom_check=passed)`，policy 返回 `partially_formalized / legality_not_checked` | 本批 3.12 探针 |
| F-2 | **最小树 + 真实 `LegalityChecker.check(VerifiedProof)`**：合法代码 → `formally_verified / all_gates_passed`；注入 `axiom cheat : False` → 第 2 层失败 → `partially_formalized / legality_failed` | 本批双探针 |
| F-3 | `ProofTree` 字段：`root/total_subgoals/proven/sorry/blocked`；`ProofNode(id, goal, status=PROVEN)` 足以构造最小树 | `datatypes/proof.py:28-52` |
| F-4 | `VerifiedProof` 必填 `theorem_name/lean_code`，`proof_tree` 可选；`LegalityChecker(PipelineConfig).check(proof)` 为纯正则检查，无 IO | `datatypes/result.py`、`stage3_5_legality.py:24-50` |
| F-5 | `CompileReport` 默认 `evidence_complete=True`、`axiom_check="not_requested"`；要拿 `formally_verified` 必须显式传 `theorem_name` 并得到 `axiom_check="passed"` | `datatypes/config.py:194` 类定义 |
| F-6 | AP 已有「真实 Lean 测试按环境变量跳过」范式：`AUTO_PROVER_LAKE_PROJECT` + `shutil.which("lake")` 决定 skip/实跑 | `tests/test_b27_compile_check.py` |
| F-7 | 3.12.11 venv（numpy 2.5.4 + scipy 1.18.1）可导入完整 `proof_pipeline` 并调用判定/合法性模块 | P-052 探针 + 本批探针 |
| F-8 | 退出码契约：0 ok / 65 data / 75 retryable / 77 revoked / 78 config / 85 paused；**只有 75 可重试** | `researchclaw/runtime/exit_codes.py:10-15` |
| F-9 | C4 必填 14 项；响应若只给 6 项投影会缺 8 项（P-053 O-1） | `contracts/v1/c4_claim_record.schema.json` |
| F-10 | Windows `taskkill /pid <pid> /t /f` 可终止进程及其子进程 | Microsoft taskkill 文档 |
| F-11 | `os.replace` 在同文件系统内为原子替换（POSIX 要求；Windows 目标为文件时静默替换） | Python 文档 |
| F-12 | AP 无 console script；sidecar 需新增 `scripts/arb_verify.py`，不能复用 `e2e_stage3.py`（1800s、需 LLM） | `pyproject.toml`、`scripts/e2e_stage3.py` |
| F-13 | `_run_build` 的 `TimeoutExpired` 分支只写 `message`，不写 `diagnostics`；`compile_report` 只取 `diagnostics` ⇒ **超时信号丢失**，与普通编译失败不可区分 | `stages/proving_runtime.py:287-289`、`compile_report` 读码 |
| F-14 | `compile_report` 是 `async def`，内部却**同步**调用 `_run_build`（阻塞事件循环）⇒ `asyncio.wait_for` 无法抢占；超时必须由结构化字段或外部进程终止兜底 | `proving_runtime.py` 读码 |

## 3. 外部锚点与工程先例（S/C）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [Azure · Sidecar pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar) | 独立进程、共享生命周期、故障隔离、跨语言 | T1 行业文档 |
| S-2 | [Kubernetes · Sidecar Containers](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/) | 生命周期绑定；启动/终止顺序 | T1 官方文档 |
| S-3 | [MCP · Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) | 本地 stdio、远程 Streamable HTTP；不规定文件 IPC | T1 规范 |
| S-4 | [LSP 3.17 · Base Protocol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#baseProtocol-inline) | stdio/socket/named pipe，stdio 默认 | T1 规范 |
| S-5 | [LeanDojo (NeurIPS 2023)](https://arxiv.org/abs/2306.15626) | 证明生成需与环境交互；M3 不做 NL→Lean | T1 学术 |
| S-6 | [Mathlib4 wiki · Using as dependency](https://github.com/leanprover-community/mathlib4/wiki/Using-mathlib4-as-a-dependency) | 下游必须与 mathlib 同一 `lean-toolchain` | T1 社区官方 |
| S-7 | [Lean Reference · Validating a Lean Proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) | `#print axioms`、`leanchecker`（4.28+）分层验证 | T1 官方 |
| S-8 | [Python subprocess](https://docs.python.org/3/library/subprocess.html) | `timeout`、`CREATE_NEW_PROCESS_GROUP`、参数列表不启 shell | T1 官方 |
| S-9 | [Python os.replace](https://docs.python.org/3/library/os.html#os.replace) | 同文件系统原子替换 | T1 官方 |
| S-10 | [Microsoft taskkill](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/taskkill) | `/t` 终止子树、`/f` 强制 | T1 官方 |
| S-11 | [pytest · Skipping](https://docs.pytest.org/en/stable/how-to/skipping.html) | 环境不满足时 skip 并保持套件绿 | T1 官方 |
| S-12 | [Oracle Problem Survey](http://www0.cs.ucl.ac.uk/staff/mharman/tse-oracle.pdf) | 独立 oracle 是验证覆盖关键 | T1 学术 |

| # | 工程先例 | 采用 |
|---|---|---|
| C-1 | Azure/K8s sidecar 生命周期（S-1/S-2） | ARC 负责启动/超时/清理；sidecar 不自行常驻 |
| C-2 | LSP/MCP 本地传输（S-3/S-4） | 本机不引入 HTTP；文件型 per request，单会话长驻才 stdio |
| C-3 | AP `test_b27` 环境门控（F-6） | live 测试用 `ARB_LEAN_PROJECT` + `which("lake")` 决定 skip |
| C-4 | Lean 验证分层（S-7） | M3 只输出 axioms/sorry；不启 `leanchecker`（4.20 无） |
| C-5 | Mathlib 同 toolchain（S-6） | sidecar 不选版本；只读工程 `lean-toolchain` |
| C-6 | 测试 oracle 独立性（S-12） | sidecar 安装 scipy，保留解析矩 oracle |

## 4. 决策矩阵

判据：**E-1** 判定可复现且不伪造证据；**E-2** 不破坏 G1b 退出码契约；**E-3** 失败可隔离、可清理；**E-4** 契约可离线校验。

### 4.1 D-1 判定映射

| 方案 | E-1 | 说明 | 结论 |
|---|---|---|---|
| **最小树 + 真实 7 层合法性** | ✅ | 编译成功 + 无 sorry + axioms passed 时造根 PROVEN 树，并跑 AP `LegalityChecker` 得真实报告 | **采纳**（F-2） |
| 最小树 + 伪造 `legality_checked=True` | ❌ | 未跑检查却宣称合法，违反信任边界 | 淘汰 |
| 改 AP policy 增 compile-only 路径 | ⚠️ | 改动 AP 语义，需上游测试与版本升级 | 暂缓（M4 评估） |
| 接受 `partially_formalized` | ✅ | 不改代码，但 §9 场景 A 失效 | 淘汰（验收目标不成立） |

**结论**：最小树只是「kernel 已接受该定理」的**编译见证**，不是伪造证明；合法性由真实 `LegalityChecker` 报告背书，响应中标注 `tree_origin="compile_only"`。

### 4.2 D-2 退出码

| 方案 | E-2 | 说明 | 结论 |
|---|---|---|---|
| 77 = Lean 不可用 | ❌ | 与 `77=REVOKED` 冲突，supervisor 会误判凭据撤销 | 淘汰 |
| **78 = 必需能力缺失；0 = 可选降级** | ✅ | `require_lean=true`（lean_check）缺失 → 78；`require_lean=false` → 0 + degraded | **采纳** |
| 新增 79..84 专用码 | ⚠️ | 不冲突，但新增契约面，需同步 `exit_codes.py` 与文档 | 暂缓 |

**结论**：`mode=lean_check` 默认 `require_lean=true`，缺 lake/工程/toolchain → **78**；`require_lean=false` 时返回 **0** + `degraded_reason` + `depth=stage2`，体现 Lean 可选（Q2）。

### 4.3 工程形态

| 决策点 | 方案 | 结论 |
|---|---|---|
| sidecar 入口 | **AP `scripts/arb_verify.py`（JSON CLI）** | 采纳：同作者、可复用 AP 测试、ARC 3.11 不 import 3.12 包 |
| ARC 客户端 | **`researchclaw/evidence/sidecar.py`** | 采纳：文件型请求/响应 + 超时/清理 |
| 响应校验 | **窄校验（必需键/类型/exit_code）+ 测试态全量 C4** | 采纳：不新增运行时 `jsonschema` 依赖 |
| 超时终止 | **`taskkill /T /F`** | 采纳：零依赖；Job Object 留作后续加固 |
| 并发 | **进程每请求** | 采纳：天然隔离，进程池由调用方控制 |

## 5. 未决（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | 是否把 `taskkill` 升级为 Job Object | 出现 taskkill 未清理的孤儿进程 | 先 taskkill；连续 2 次泄漏后改 Job Object | E2（S-10） |
| U-2 | `require_lean=false` 的完整 `verify` 是否在 M4 实现 | M4 接线 Stage 9/20 | 是；复用同一契约，仅增 `mode=verify` | E3（S-5） |
| U-3 | sidecar 是否随 ARC wheel 分发 | 发布审阅要求「开箱即用」 | 暂不；AP 作为外部 3.12 依赖，README 说明 | E3（P-042 Q2） |

## 6. 引用

1. 仓内：[P-050 v1.2](../arc-g2-m3-sidecar/RESEARCH.md)、[P-053 复审](../../docs/arc-g2-m3-survey-review-20261111.md)、[M2 vendor](../arc-g2-m2-vendor/IMPLEMENTATION.md)、[C4 schema](../../contracts/v1/c4_claim_record.schema.json)、`researchclaw/runtime/exit_codes.py`、`F:\Auto_Prover\proof_pipeline\{verdict/policy.py,stages/stage3_5_legality.py,datatypes/proof.py}`。
2. 外部：S-1..S-12（§3 表，URL 已解析）。
