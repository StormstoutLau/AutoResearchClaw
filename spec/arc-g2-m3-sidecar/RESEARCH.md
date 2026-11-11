---
id: arc-g2-m3-sidecar-RESEARCH
type: design
version: 1.2
status: verified
date: 2026-11-11
depends: [arc-g2-decisions, arc-g2-py311-env, arc-g2-m2-vendor]
upstream: arc-g2-m2-vendor
---

# 调研：G2 M3 sidecar + Lean 可选（主控站多版本 Lean）

> **Feature**：P-050，G2 里程碑 M3 的开工调研。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行；零生产代码/零门禁）。
> **结论先行**：主控站已有 **6 个 elan 工具链**（4.18.0 / 4.20.0 默认 / 4.30.0 / 4.31.0 / 4.31.0-rc1 / 4.32.0-rc1），本地 mathlib 工程 `D:\Textbook\lean_src` 固定 **4.20.0** 且依赖全部为 path、Mathlib 已有 **6443 个 olean** 预热；实测 per-run 工程 `lake build Main` **53.3s 成功**。M3 建议：**Lean 版本以工程 `lean-toolchain` 为唯一真值源**（elan 自动选择），sidecar 用 **3.12.11 + numpy + scipy** 即可 import 完整 AP 管线并保留解析矩 oracle；传输用**文件型 JSON**，`arb verify` 采用「预置 Lean 语句的确定性检查」作为 M3 验收面，完整 NL→Lean 管线留 M4。
> **修订**：v1.1（2026-11-11，P-051）**补充外部社区案例与学术锚点**——新增 Mathlib4 依赖工程实践、lean-action CI、Azure/Kubernetes sidecar 模式、Lean 4 与 Mathlib 论文、`lean4checker` 验证指南、`os.replace` 原子替换等 9 条来源（S-6..S-14）与 7 个工程先例（C-1..C-7）；据此新增 U-5（是否把 `lean4checker` 作为独立深度）与 §6.1 信任边界。决策与 F 事实不变。
> **修订**：v1.2（2026-11-11，P-052）**U-1..U-5 全部关闭**——补充 MCP/LSP 传输实践、LeanDojo/miniCTX/autoformalization 学术资料、Lean meta 版本敏感性与 oracle 问题综述；新增 S-15..S-24 与 §11 逐项方案对比。结论：文件型 + 每请求独立进程（U-1）、M3 仅 `lean_check`（U-2）、工程 pin + meta 显式 ≥4.30（U-3）、sidecar 安装 scipy（U-4）、M3 不做独立 kernel 深度（U-5，4.20 无 `leanchecker`）。

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

**建议**：sidecar venv = `uv venv --python 3.12` + `numpy + scipy`；以 `PYTHONPATH=F:\Auto_Prover` 或 `pip install -e F:\Auto_Prover --no-deps` 引入 AP。scipy 缺失时仍按 AP 既有语义降级，但 M3 默认安装（§11.4）。

## 5. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [elan README](https://github.com/leanprover/elan) | `lean`/`lake` 代理按工程 `lean-toolchain` **自动选择**版本；`elan show` 显示 override 来源 | T1 官方文档 |
| S-2 | [Lean 4 Setup](https://lean-lang.org/lean4/doc/setup.html) | 工程结构含 `lean-toolchain`；`lake build` 编译包与依赖 | T1 官方文档 |
| S-3 | [Lean Reference · Build Tools](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/) | 工具链由 elan 管理；`lake` 增量调用 `lean`；`leanchecker` 可重放 kernel 检查 | T1 官方文档 |
| S-4 | [Python subprocess](https://docs.python.org/3/library/subprocess.html) | 超时、进程树与 `CREATE_NEW_PROCESS_GROUP` 语义（Windows 需额外终止子树） | T1 官方文档 |
| S-5 | [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) | M0 契约的方言；sidecar 响应复用 C1/C4 | T1 标准 |
| S-6 | [Mathlib4 README](https://github.com/leanprover-community/mathlib4) | 下游用 `lake exe cache get` 取预编译 olean；`lake build` / 单文件构建；依赖版本由 `lean-toolchain` 与 `lake-manifest.json` 固定 | T1 官方仓库 |
| S-7 | [Mathlib4 wiki · Using as a dependency](https://github.com/leanprover-community/mathlib4/wiki/Using-mathlib4-as-a-dependency) | **工程必须与 mathlib4 使用同一 Lean 工具链**；升级按 Lean stable/rc 对应的 Mathlib tagged release 逐步进行 | T1 社区官方文档 |
| S-8 | [lean-action](https://github.com/leanprover/lean-action) | CI 直接消费工程 `lean-toolchain`；缓存 `.lake` 与 mathlib cache endpoint；Ubuntu/macOS/Windows 均测 | T1 官方 Action |
| S-9 | [Azure Architecture Center · Sidecar pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar) | 组件放独立进程/容器，与主应用**共享生命周期**；隔离故障、语言与技术可不同 | T1 行业架构文档 |
| S-10 | [Kubernetes · Sidecar Containers](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/) | sidecar 与主容器同 Pod，生命周期绑定（v1.33 stable）；启动/退出顺序可声明 | T1 官方文档 |
| S-11 | [Lean 4 论文（CADE-28, 2021）](https://doi.org/10.1007/978-3-030-79876-5_37) | Lean 4 用 Lean 自身重写；可扩展 elaborator/tactic，但**证明由 kernel 检查** | T1 学术论文 |
| S-12 | [The Lean Mathematical Library（CPP 2020）](https://arxiv.org/abs/1910.09336) | 社区大型数学库；依赖类型基础 + 大规模自动化；库与工具链强耦合 | T1 学术论文 |
| S-13 | [Python `os.replace`](https://docs.python.org/3/library/os.html#os.replace) | 同文件系统内替换为原子操作（POSIX 要求）；Windows 上目标为文件时静默替换 | T1 官方文档 |
| S-14 | [Lean Reference · Validating a Lean Proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) | 用 `#print axioms` 查公理；可用 `lean4checker` 重放 kernel；`comparator`/外部检查器为金标准 | T1 官方文档 |
| S-15 | [MCP · Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) | 两种标准传输：**stdio（本地子进程）**与 **Streamable HTTP（远程独立进程）** | T1 官方规范 |
| S-16 | [LSP 3.17 规范 · Base Protocol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#baseProtocol-inline) | 传输可为 stdio / socket / named pipe / node ipc；stdio 是默认 | T1 官方规范 |
| S-17 | [LeanDojo（NeurIPS 2023）](https://arxiv.org/abs/2306.15626) | 开源 Lean 交互环境；支持 whole-proof 生成与 proof search；98,734 条定理基准；需与证明环境交互 | T1 学术论文 |
| S-18 | [miniCTX（2024）](https://arxiv.org/abs/2408.03350) | 真实 Lean 项目/教材定理依赖数万 token 上下文；上下文能力是独立维度 | T1 学术论文 |
| S-19 | [Autoformalization in the Era of LLMs: A Survey](https://arxiv.org/abs/2505.23486) | NL→形式化的端到端流程（预处理/模型/评估）；可验证性是核心价值 | T1 学术综述 |
| S-20 | [lean4checker（已并入 Lean）](https://github.com/leanprover/lean4checker) | 仓库已弃用；`leanchecker` 自 **4.28.0** 随工具链分发；用 Lean **同一 kernel** 重放，检测 environment hacking，非外部验证器 | T1 官方仓库 |
| S-21 | [Lean4Lean（CPP 2026 投稿）](https://arxiv.org/abs/2403.14064) | 独立类型检查器；比参考实现慢 **20%–50%**，可验证全部 mathlib；研究级 | T1 学术论文 |
| S-22 | [The Oracle Problem in Software Testing: A Survey](http://www0.cs.ucl.ac.uk/staff/mharman/tse-oracle.pdf) | 测试 oracle 问题综述；独立 oracle 是自动化验证的关键瓶颈 | T1 学术综述 |
| S-23 | [SciPy · `scipy.stats`](https://docs.scipy.org/doc/scipy/reference/stats.html) | 提供分布、矩与统计检验；AP 的解析矩 oracle 依赖该模块 | T1 官方文档 |
| S-24 | [Lean 4 Metaprogramming Book](https://leanprover-community.github.io/lean4-metaprogramming-book/main/04_metam.html) | `MetaM`/环境 API 与版本强相关；声明图提取依赖具体 toolchain 的元编程接口 | T1 社区官方教材 |

### 5.1 社区案例与工程先例

| # | 案例 | 做法/读数 | 对 M3 的采用 |
|---|---|---|---|
| C-1 | Mathlib4 下游工程（S-6/S-7） | 下游必须与 mathlib4 同一 `lean-toolchain`；升级按 tagged release 逐步；先 `lake exe cache get` 再构建 | **工程 pin 是唯一版本真值源**；4.20 工程不得混用 4.30 工具链；预热 olean 可复用（本机 6443 个） |
| C-2 | lean-action CI（S-8） | CI 从工程 `lean-toolchain` 取版本，缓存 `.lake`，Windows runner 同样支持 | M3 验收脚本沿用「工程 pin + 缓存」模式；sidecar 不做自己的版本选择器 |
| C-3 | Azure sidecar 模式（S-9） | 独立进程/容器、与主应用同生命周期、隔离故障、可跨语言 | sidecar 用 3.12 独立进程承载 AP；ARC 3.11 只经 JSON 交互，不 import |
| C-4 | Kubernetes sidecar（S-10） | 同 Pod 生命周期绑定；启动/终止顺序可声明 | ARC 负责 sidecar 的启动、超时与清理；异常退出不得留孤儿进程/临时工程 |
| C-5 | Lean 4 论文（S-11） | 证明由 kernel 检查，elaborator/tactic 可扩展 | 信任锚是 `lake build` + olean，不是 LLM 自报「已证明」；状态只能由 `decide_citation_label` 产生 |
| C-6 | Mathlib 论文（S-12） | 大型社区库与工具链强耦合，升级成本高 | 不追最新 RC；本地 4.20 + 预编译 mathlib 是现实基线；`lean_meta` 的 4.30 门槛单独降级 |
| C-7 | Lean 证明验证指南（S-14） | `#print axioms` / `lean4checker` / `comparator` 分层验证 | M3 至少输出 axioms 与 sorry 证据；`lean4checker` 作为可选深度（U-5） |

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
| sidecar 依赖 | **3.12 + numpy + scipy** | ✅ | ✅ | ✅ | ✅ | **采纳**（P-052 定案） |
| sidecar 依赖 | 完整 AP 安装（含 mcp） | ✅ | ✅ | ✅ | ✅ | 过重；仅 CI 全量时用 |

### 6.1 信任边界（S-11/S-14）

- **可信锚**：`lake build` 返回 0 且产出 `Main.olean`，再由 `#print axioms` 给出公理集；证明由 Lean kernel 检查，不由 LLM 自报。
- **不采信**：模型输出中的「已证明」「无 sorry」文本；状态只来自 `decide_citation_label`。
- **可选加强**：`leanchecker`（4.28+）重放 kernel、`comparator` 外部检查（U-5，P-052 结论：M3 不做；4.20 无 `leanchecker`）。

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

## 10. 未决（四元块，P-052 已全部关闭）

> v1.1 的四元块见 git 历史；§11 给出补充调研与裁定。

| # | 判据 | 结论（P-052） | 证据等级 |
|---|---|---|---|
| U-1 | sidecar 传输是否长期保持文件型 | **文件型 + 每请求独立进程**；仅当需要单进程长驻会话时改 stdio JSON-RPC；本机不采用 HTTP | E1/E2（S-15/S-16） |
| U-2 | `arb verify` 是否必须支持完整 NL→Lean | **M3 仅 `lean_check`**；完整 `verify` 留 M4（需 LLM + 环境交互） | E1（S-17..S-19） |
| U-3 | 4.30+ 工程是否作为 meta 默认 | **始终工程 pin**；`lean_meta` 显式请求且仅 ≥4.30；4.20 降级 | E1/E2（S-7/S-24） |
| U-4 | sidecar 是否安装 scipy | **安装**（AP 声明依赖；3.12 venv 实测 1.2s）；ARC 3.11 环境不装 | E1（S-22/S-23 + 本机） |
| U-5 | 是否把 `lean4checker` 作为独立深度 | **M3 不做**；4.20 工具链无 `leanchecker`；4.28+ 项目可选，Lean4Lean 暂不引入 | E1（S-20/S-21 + 本机） |

## 11. 未决项补充调研与裁定（P-052）

### 11.1 U-1：传输形态

**外部证据**

- MCP 的两种标准传输：stdio（客户端拉起本地子进程）与 Streamable HTTP（独立进程、多客户端、远程）——本地工具默认 stdio（S-15）。
- LSP 的传输可为 stdio / socket / named pipe / node ipc，stdio 为默认；语言服务器本身是独立进程（S-16）。
- Azure/Kubernetes 的 sidecar 模式强调「独立进程 + 与主应用同生命周期 + 故障隔离」，不规定具体 IPC（S-9/S-10）。

**方案对比**

| 方案 | 并发模型 | 审计/可重放 | Windows 实现 | 失败隔离 | 结论 |
|---|---|---|---|---|---|
| **文件型 per request** | 进程池：每请求一个 sidecar 进程 | 请求/响应文件天然留档 | 临时文件 + `os.replace`（S-13） | 进程级 | **采纳** |
| stdio JSON-RPC | 单进程多路复用 | 需额外日志/分帧 | pipe | 进程级（协议层需自担） | 备选：单会话长驻 |
| 本地 HTTP | 多客户端 | 需额外访问日志 | 端口/防火墙 | 服务级 | 淘汰 |

**结论**：M3/M4 默认**文件型 + 每请求独立进程**。它同时满足审计、失败隔离与并发（进程池），且不需要自定义多路复用协议；只有出现「单进程长驻会话 + 低延迟」需求时才升级为 stdio JSON-RPC。M3 落地：`runs/<id>/sidecar/{request,response}.json`，`os.replace` 原子写，超时后终止进程树并清理临时 Lean 工程。

### 11.2 U-2：`lean_check` 与完整 `arb verify`

**外部证据**

- LeanDojo：开源 Lean 交互环境，whole-proof 生成与 proof search 都依赖与证明环境交互；基准含 98,734 条定理（S-17）。
- miniCTX：真实 Lean 项目的定理依赖数万 token 的上下文，上下文能力是独立维度（S-18）。
- Autoformalization 综述：NL→形式化是端到端流程（数据、模型、评估），可验证性是其核心价值（S-19）。

**方案对比**

| 方案 | 确定性 | 依赖 | M3 范围 | 结论 |
|---|---|---|---|---|
| **仅 `lean_check`（预置 Lean 语句）** | 完全确定 | 仅 Lean 工程 | 可验收 | **M3 采纳** |
| 完整 `verify`（NL→LaTeX→Lean→证明） | 依赖模型与上下文 | LLM + 检索 + Lean | 超出 M3 | M4 |
| 两者同时做 | 部分不确定 | 全量 | 范围膨胀 | 淘汰 |

**结论**：M3 的 `arb verify` 只承诺 `lean_check`；完整 NL→Lean 是 M4 的 `verify` 模式，复用同一 JSON 契约，但需要 ARC 既有 provider 与上下文检索。M3 验收全程零 LLM。

### 11.3 U-3：`lean_meta` 与 4.30 门槛

**外部证据**

- Mathlib4 下游工程必须与 mathlib4 使用**同一** `lean-toolchain`；升级按 tagged release 逐步进行（S-7）。
- Lean 的 `MetaM`/环境 API 与具体 toolchain 强相关，声明图提取依赖这些接口（S-24）。
- 本机 `lean_src` 固定 4.20.0，而 AP `lean_meta.read_toolchain` 要求 ≥4.30（F-10）。

**方案对比**

| 方案 | 可复现 | meta 可用 | mathlib 兼容 | 复杂度 | 结论 |
|---|---|---|---|---|---|
| **工程 pin + meta 显式请求** | ✅ | 仅 ≥4.30 | ✅ | 低 | **采纳** |
| 默认 4.30 工程 | ✅ | ✅ | ❌ 需 4.30 mathlib | 中 | 淘汰 |
| 独立 meta 服务 | ✅ | ✅ | ✅ | 高 | 暂不需要 |

**结论**：始终以工程 `lean-toolchain` 为准；`lean_meta` 是**显式可选能力**，只在工程 ≥4.30 时启用；4.20 工程请求 meta 时直接降级并给出 `lean_meta_requires_4_30`，绝不混用 4.30 工具链与 4.20 mathlib。M3 不调用 `lean_meta`。

### 11.4 U-4：sidecar 是否安装 scipy

**外部证据**

- 测试 oracle 综述：独立 oracle 是自动化验证的关键瓶颈，缺失会显著降低验证覆盖（S-22）。
- `scipy.stats` 提供分布、矩与统计检验；AP 的解析矩 oracle 依赖它（S-23）。
- 本机 3.12.11 venv 实测：`scipy==1.18.1` 安装 **1.2s**，与 `numpy 2.5.4` 共存，`stats.norm.mean(loc=1.0, scale=2.0)` 返回 `1.0`。

**方案对比**

| 方案 | oracle 覆盖 | 依赖成本 | 与 AP 语义 | 维护 | 结论 |
|---|---|---|---|---|---|
| **安装 scipy** | 完整解析矩 | 1 个 wheel（1.2s） | 一致 | 低 | **采纳** |
| 不装 scipy | 降为 `OracleInvalid` / `unrecognized` | 0 | 一致但覆盖下降 | 低 | 仅最小镜像 |
| 自实现统计矩 | 有限 | 0 | 分叉风险 | 高 | 淘汰 |

**结论**：sidecar venv 安装 `numpy + scipy`；ARC 3.11 进程内不装。scipy 缺失时仍按 AP 既有语义 fail-safe 降级，不改变判定。

### 11.5 U-5：`lean4checker` 是否作为独立深度

**外部证据**

- `lean4checker` 仓库已弃用：`leanchecker` 自 **4.28.0** 随工具链分发；它用 Lean **同一 kernel** 重放环境，用于检测 environment hacking，**不是外部验证器**（S-20）。
- Lean4Lean 是独立类型检查器，比参考实现慢 **20%–50%**，可验证全部 mathlib，属研究级外部检查（S-21）。
- Lean 官方验证指南把 `#print axioms`、`leanchecker`、`comparator` 分为不同强度层次（S-14）。

**本机复查**

- `leanchecker --version` → `toolchain 'leanprover/lean4:v4.20.0' does not have the binary ...\bin\leanchecker.exe`。
- `lake env leanchecker --help` 在 `lean_src`（4.20）同样不可用。

**方案对比**

| 方案 | 4.20 可用 | 保证强度 | 成本 | 适用 | 结论 |
|---|---|---|---|---|---|
| **仅 axioms + sorry 证据** | ✅ | kernel 已检查 + 公理可见 | 0 | M3 | **采纳** |
| 内置 `leanchecker` | ❌（需 ≥4.28） | 同 kernel 重放，查环境攻击 | 低 | M4+ 高保障 | 备选 |
| Lean4Lean 外部检查 | ❌（需匹配构建） | 独立类型检查器 | 高（慢 20–50%） | 研究级 | 暂不引入 |

**结论**：M3 只输出 `#print axioms` 与 sorry 证据，不新增深度；若 M4 出现高保障需求且工程升级到 ≥4.28，可把 `lake env leanchecker` 作为可选 `stage3_5`；Lean4Lean 不作为产品依赖。

### 11.6 汇总

| U | 结论 | M3 动作 | M4 触发 |
|---|---|---|---|
| U-1 | 文件型 + 每请求进程 | request/response 文件、原子写、超时清理 | 单会话长驻 → stdio |
| U-2 | 仅 `lean_check` | 零 LLM 验收 A..F | 完整 `verify` 接线 |
| U-3 | 工程 pin；meta 显式 ≥4.30 | 不调用 `lean_meta` | 需要声明图时 |
| U-4 | 安装 scipy | venv = numpy + scipy | 真实数值 claim |
| U-5 | 不做独立深度 | 输出 axioms/sorry | 工程 ≥4.28 且需高保障 |

## 12. 引用

1. 仓内：[R-03 §2.3/§5.2](../../arb-v2-decisions-research-design.md)、[总纲 G2](../../arc-master-roadmap.md)、[P-042 §8](../arc-g2-decisions/RESEARCH.md)、[P-045](../arc-g2-py311-env/RESEARCH.md)、[P-049](../arc-g2-m2-vendor/IMPLEMENTATION.md)、`F:\Auto_Prover\proof_pipeline\{config,lean4_project,model_gateway}.py`、`stages/proving_runtime.py`、`lean_meta/extract.py`。
2. 外部：S-1..S-24（§5 表，URL 已逐条解析）；工程先例 C-1..C-7（§5.1）。
