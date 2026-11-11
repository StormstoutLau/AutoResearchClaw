---
id: arc-g2-m3-sidecar-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-decisions, arc-g2-py311-env, arc-g2-m2-vendor]
upstream: arc-g2-m2-vendor
---

# 调研：G2 M3 sidecar + Lean 可选（主控站多版本 Lean）

> **Feature**：P-050，G2 里程碑 M3 的开工调研。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行；零生产代码/零门禁）。
> **结论先行**：主控站已有 **6 个 elan 工具链**（4.18.0 / 4.20.0 默认 / 4.30.0 / 4.31.0 / 4.31.0-rc1 / 4.32.0-rc1），本地 mathlib 工程 `D:\Textbook\lean_src` 固定 **4.20.0** 且依赖全部为 path、Mathlib 已有 **6443 个 olean** 预热；实测 per-run 工程 `lake build Main` **53.3s 成功**。M3 建议：**Lean 版本以工程 `lean-toolchain` 为唯一真值源**（elan 自动选择），sidecar 用 **3.12.11 + numpy** 即可 import 完整 AP 管线；传输用**文件型 JSON**，`arb verify` 采用「预置 Lean 语句的确定性检查」作为 M3 验收面，完整 NL→Lean 管线留 M4。

## 1. 问题与 M3 DoD

R-03 §5.2 的 M3 为「完整 AP 子进程 + JSON 契约 + Lean 可选」，DoD：

1. `arb verify` 在 **3.12 venv** 跑通；
2. 无 Lean 时**正确降级**；
3. 强制输入 I-4：sidecar JSON 含 `schema_version` / `policy_version` / `exit_code` / `degraded_reason`；
4. 强制输入 I-5：Lean 未启用时导出 `verification_depth=stage2` 与 `lean_unavailable_reason`。

本调研回答：多版本 Lean 如何选、sidecar 环境怎么建、传输与契约怎么定、降级矩阵与验收怎么落。

## 2. 主控站 Lean 资产（一手，2026-11-11）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | elan **4.2.0**；默认工具链 `leanprover/lean4:v4.20.0`；`settings.toml` 的 `[overrides]` 为空 | `elan --version`、`elan show`、`~/.elan/settings.toml` |
| F-2 | 已安装 **6 个**工具链：`v4.18.0` / `v4.20.0`（默认）/ `v4.30.0` / `v4.31.0` / `v4.31.0-rc1` / `v4.32.0-rc1` | `elan toolchain list`、`~/.elan/toolchains/` |
| F-3 | 每个工具链自带 Lake 5.0.0（commit 与 Lean 对应）；`lean +v4.18.0 --version` 可显式切换 | 逐工具链实跑；`lean +v4.18.0 --version` |
| F-4 | 本地 mathlib 工程 `D:\Textbook\lean_src` 的 `lean-toolchain` = `leanprover/lean4:v4.20.0`；`elan show` 报 `overridden by '...\lean_src\lean-toolchain'` | `elan show`（cwd=lean_src） |
| F-5 | 该工程 `lake-manifest.json` 的 mathlib/repl 均为 **path** 依赖；Mathlib 已有 **6443** 个 `.olean`，`repl.exe` 已构建 | 清点 `.lake/packages/mathlib/.lake/build/lib/lean` 与 `repl/.lake/build/bin` |
| F-6 | `lake env lean` 编译一个 `import Mathlib` 的定理：**rc=0，1.45s**，`#print axioms` 输出 `[propext]` | 本批临时文件探针 |
| F-7 | 用 AP `create_per_run_project` 生成 per-run 工程后 `lake build Main`：**rc=0，53.3s**，产出 `Main.olean`（40,304 B） | 本批实跑（3.12 venv + `PYTHONPATH=F:\Auto_Prover`） |
| F-8 | `lake env lean` 会打印依赖仓库 “has local changes” 警告（importGraph/proofwidgets/aesop/batteries），**非致命** | 探针 stderr |
| F-9 | `~/.elan/toolchains/leanprover--lean4---v4.14.lock` 是锁文件（内容 `13692`），**不是**工具链 | 目录清点 |
| F-10 | 4.20.0 **低于** AP `lean_meta` 的 `>= 4.30.0` 门槛；核心 Stage3 的 `LeanSimRuntime` **不校验版本** | `lean_meta/extract.py`、`proving_runtime.py` |

## 3. AP 侧集成事实

| # | 事实 | 证据 |
|---|---|---|
| F-11 | AP 通过 `AUTO_PROVER_LEAN_PROJECT` 指定源工程；`lean4_project_enabled` 时在 `run_root` 派生 per-run 工程，复制 `lean-toolchain` 与 path manifest | `proof_pipeline/config.py`、`lean4_project.py` |
| F-12 | `LeanSimRuntime` 以**显式目标** `lake build Main` 编译并校验构建物存在；默认 `prewarm_timeout=300s` | `stages/proving_runtime.py`、`config.py` |
| F-13 | lake 不可用**不抛异常**：`_lake_available=False`，`compile_check` 返回 `(False, "lake not available at ...")` | 本批 3.12 探针 |
| F-14 | 无证明树时判定按证据降级：`latex_ok ⇒ LATEX_VERIFIED`；`numerical_passed ⇒ NUMERICALLY_VERIFIED`；`numerical_failed ⇒ FALSIFIED` | 本批探针 + `verdict/policy.py` |
| F-15 | AP 无 console script；`scripts/e2e_stage3.py` 是诊断入口（1800s 总超时），不是 JSON 契约 | `pyproject.toml`、`scripts/e2e_stage3.py` |
| F-16 | `proof_pipeline.Pipeline` 的导入面只需 **stdlib + numpy**；scipy/sklearn 为延迟导入（缺失 ⇒ `OracleInvalid`），`mcp` 只在 `mcp_servers/` | 逐文件 import 扫描 + 3.12 实跑 |
| F-17 | `ModelGateway` 的 `base_url=""` 即 Mock 模式；设置 `AUTO_PROVER_LLM_BASE_URL` 才走 HTTP | `model_gateway.py` |
| F-18 | AP 已有真实 Lean 测试范式：`AUTO_PROVER_LAKE_PROJECT` + `shutil.which("lake")` 决定 skip/实跑 | `tests/test_b27_compile_check.py` |

## 4. Sidecar Python 环境

| # | 事实 | 证据 |
|---|---|---|
| F-19 | 本机可用 **3.12.10**（python.org）与 **3.12.11**（uv 托管） | `uv python list --only-installed`、`py -0p` |
| F-20 | 3.12.11 venv 仅装 **numpy 2.5.4** 即可 `import proof_pipeline` 与 `ProofPipeline` | 本批实跑 |
| F-21 | AP 声明 `requires-python >=3.12`，依赖 `numpy/scipy/scikit-learn/aiohttp/mcp>=1,<2`；M3 检查路径不需要 mcp | `F:\Auto_Prover\pyproject.toml` |
| F-22 | 3.11 内核已在 ARC 进程内（P-049）；sidecar 必须是独立的 3.12 进程，二者不共享解释器 | P-049 |

**建议**：sidecar venv = `uv venv --python 3.12` + `numpy`；以 `PYTHONPATH=F:\Auto_Prover` 或 `pip install -e F:\Auto_Prover --no-deps` 引入 AP。`scipy` 作为可选增强（数值 oracle），缺失时按 AP 既有语义降级。

## 5. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [elan README](https://github.com/leanprover/elan) | `lean`/`lake` 代理按工程 `lean-toolchain` **自动选择**版本；`elan show` 显示 override 来源 | T1 官方文档 |
| S-2 | [Lean 4 Setup](https://lean-lang.org/lean4/doc/setup.html) | 工程结构含 `lean-toolchain`；`lake build` 编译包与依赖 | T1 官方文档 |
| S-3 | [Lean Reference · Build Tools](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/) | 工具链由 elan 管理；`lake` 增量调用 `lean`；`leanchecker` 可重放 kernel 检查 | T1 官方文档 |
| S-4 | [Python subprocess](https://docs.python.org/3/library/subprocess.html) | 超时、进程树与 `CREATE_NEW_PROCESS_GROUP` 语义（Windows 需额外终止子树） | T1 官方文档 |
| S-5 | [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) | M0 契约的方言；sidecar 响应复用 C1/C4 | T1 标准 |

## 6. 决策矩阵

判据：

- **D-1**：多版本 Lean 下**可复现**（同一工程永远同一版本）；
- **D-2**：无 Lean / 编译失败 / sorry / 超时都能**显式降级**，不冒充 `FORMALLY_VERIFIED`；
- **D-3**：sidecar 与 ARC 3.11 进程隔离，契约可离线校验；
- **D-4**：M3 验收**不依赖 LLM**（确定性、可重跑）。

| 决策点 | 方案 | D-1 | D-2 | D-3 | D-4 | 结论 |
|---|---|---|---|---|---|---|
| Lean 选择 | **工程 `lean-toolchain`（elan 自动）** | ✅ | ✅ | ✅ | ✅ | **采纳**（S-1） |
| Lean 选择 | 固定 4.20 路径 | ✅ | ✅ | ✅ | ✅ | 淘汰：换工程即失效 |
| Lean 选择 | 自动选最高版本（4.32-rc1） | ❌ | ⚠️ | ✅ | ✅ | 淘汰：与 mathlib pin 冲突 |
| 传输 | **文件型 JSON（atomic rename）** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| 传输 | stdio JSONL | ✅ | ✅ | ⚠️ 长驻生命周期 | ✅ | 备选（M4 长驻时） |
| 传输 | 本地 HTTP | ✅ | ✅ | ❌ 端口/权限 | ✅ | 淘汰（P-042 U-3 倾向） |
| 入口 | **AP 上游新增 `scripts/arb_verify.py`（JSON CLI）** | ✅ | ✅ | ✅ | ✅ | **采纳**（同作者、可复用 AP 测试） |
| 入口 | ARC 侧直接 import AP | ❌ 3.11 不能 import 3.12 包 | ✅ | ❌ | ✅ | 淘汰 |
| 入口 | 复用 `e2e_stage3.py` | ⚠️ | ⚠️ | ✅ | ❌ 需 LLM | 淘汰 |
| 验证范围 | **预置 Lean 语句的 `lean_check`（M3 验收）** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| 验证范围 | 完整 NL→Lean 管线 | ⚠️ | ✅ | ✅ | ❌ 需 LLM | 留 M4 |
| sidecar 依赖 | **3.12 + numpy（+ scipy 可选）** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| sidecar 依赖 | 完整 AP 安装（含 mcp） | ✅ | ✅ | ✅ | ✅ | 过重；仅 CI 全量时用 |

## 7. 接口草案

### 7.1 请求（ARC → sidecar）

```json
{
  "schema_version": "1.0",
  "request_id": "req-20261111-0001",
  "mode": "lean_check",
  "claim": {
    "claim_id": "c-1a2b3c4d",
    "statement": "For every natural number n, n + 0 = n.",
    "lean_statement": "theorem probe_nat_add_zero (n : Nat) : n + 0 = n := by simp",
    "theorem_name": "probe_nat_add_zero"
  },
  "lean": {
    "source_project": "D:\\Textbook\\lean_src",
    "toolchain": null,
    "timeout_s": 300
  }
}
```

- `toolchain=null` ⇒ 跟随工程 `lean-toolchain`；显式值仅用于诊断（`lean +<toolchain>`）。
- `mode=lean_check` 不调用 LLM；`mode=verify` 留 M4。

### 7.2 响应（sidecar → ARC）

```json
{
  "schema_version": "1.0",
  "run": {
    "run_id": "req-20261111-0001",
    "attempt": 1,
    "inputs_digest": "sha256:...",
    "exit_code": 0,
    "status": "succeeded",
    "usage": {}
  },
  "claim_record": {
    "claim_id": "c-1a2b3c4d",
    "claim_class": "C",
    "claim_type": "exploratory",
    "status": "formally_verified",
    "policy_version": 2,
    "verification_depth": "stage3"
  },
  "lean_available": true,
  "lean_version": "4.20.0",
  "lean_unavailable_reason": null,
  "degraded_reason": null
}
```

- `run` 直接满足 C1 `RunEnvelope` 的必填字段，且**不含 `verdict`**（产出方不自评）。
- 判定只在 `claim_record.status`，由 AP `decide_citation_label` 产生。
- 失败也必须写响应文件，并带 `degraded_reason`。

### 7.3 退出码

沿用 G1b 的退出码语义（见 [P-028](../arc-g1b-supervisor-protocol/RESEARCH.md)）：

| 码 | 含义 | sidecar 场景 |
|---|---|---|
| 0 | 正常完成（含业务失败状态） | 编译/验证完成，`claim_record.status` 可为 `failed`/`falsified` |
| 65 | 数据错误 | 请求 JSON 非法、字段缺失 |
| 75 | 暂时性失败 | 编译/验证超时（可重试） |
| 77 | 能力不可用 | Lean 不可用（降级路径） |
| 78 | 配置错误 | `source_project` 不存在 / `lean-toolchain` 缺失 |

## 8. 降级矩阵

| 条件 | 检测 | 状态上限 | 深度 | `degraded_reason` |
|---|---|---|---|---|
| Lean/lake 不可用 | `LeanSimRuntime._lake_available=False` | AP 证据链决定（≤ `latex_verified`/`numerically_verified`） | `stage2` | `lean_unavailable` |
| 源工程缺失/无 `lean-toolchain` | 创建 per-run 前校验 | 不产出正式标签 | `stage2` | `lean_project_missing` |
| 编译失败 | `compile_report.status=failed` | ≤ `partially_formalized`（实际按证据降级） | `stage2` | `lean_compile_failed` |
| 含 sorry | `sorry_warnings` 非空 | `partially_formalized` | `stage2` | `lean_sorry_present` |
| 超时 | 进程超时 | 不提升 | `stage2` | `lean_timeout` |
| 工程 < 4.30 且请求 meta 提取 | `lean_meta.read_toolchain` | meta 功能不可用（不影响核心证明） | 原深度 | `lean_meta_requires_4_30` |

**不冒充**：任何降级路径都不得产出 `formally_verified`；`verification_depth` 与 `lean_unavailable_reason` 必须同时出现（I-5）。

## 9. M3 验收设计（确定性）

| # | 场景 | 预期 |
|---|---|---|
| A | 3.12.11 venv + `lean_check` 一条可证明定理（4.20 工程） | exit 0；`status=formally_verified`；`depth=stage3`；`lean_version=4.20.0` |
| B | `source_project` 指向不存在目录 | exit 78；`degraded_reason=lean_project_missing`；不产出正式标签 |
| C | `lake` 指向不存在可执行文件 | exit 77；`depth=stage2`；`lean_unavailable_reason` 非空 |
| D | 注入 `sorry` 的定理 | `status=partially_formalized`；`depth=stage2`；`degraded_reason=lean_sorry_present` |
| E | 编译错误（语法/未定义） | 不提升状态；`degraded_reason=lean_compile_failed` |
| F | 超过 `timeout_s` | exit 75；可重试；不产生 `formally_verified` |

A/D 用本地 4.20 工程；B/C/E/F 不需要真实 Lean 或只需极短运行。全部不调用 LLM。

## 10. 未决（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | sidecar 传输是否长期保持文件型 | M4 需要长驻/并发调用时 | 先文件；并发 >5 或延迟敏感时评 stdio/HTTP | E2（本批） |
| U-2 | `arb verify` 是否必须支持完整 NL→Lean（LLM） | M4 接线 Stage 9/20 时 | M3 只做 `lean_check`；完整模式 M4 用 ARC 既有 provider | E3（设计判断） |
| U-3 | 4.30+ 工程是否作为 meta 提取的默认 | 出现需要 `lean_meta` 的 claim | 按工程 pin；meta 功能显式请求，<4.30 直接降级 | E2（F-10） |
| U-4 | sidecar 是否安装 scipy | 数值 oracle 在真实 claim 上被使用 | 先不装；缺失按 AP 既有 `OracleInvalid` 降级，M4 再评估 | E2（F-16） |

## 11. 引用

1. 仓内：[R-03 §2.3/§5.2](../../arb-v2-decisions-research-design.md)、[总纲 G2](../../arc-master-roadmap.md)、[P-042 §8](../arc-g2-decisions/RESEARCH.md)、[P-045](../arc-g2-py311-env/RESEARCH.md)、[P-049](../arc-g2-m2-vendor/IMPLEMENTATION.md)、`F:\Auto_Prover\proof_pipeline\{config,lean4_project,model_gateway}.py`、`stages/proving_runtime.py`、`lean_meta/extract.py`。
2. 外部：S-1..S-5（§5 表，URL 已解析）。
