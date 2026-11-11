# P-050..P-052 M3 调研独立复审报告（2026-11-11）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。复审基座与调研批次基座不同；纪律同 P-039/P-041——不采信调研文档结论，全部以机检、探针、读码一手重验。
> **对象**：[P-050 RESEARCH v1.2](../spec/arc-g2-m3-sidecar/RESEARCH.md)（含 P-051 锚点增补、P-052 U-1..U-5 裁定）的 F-1..F-22、S-1..S-24、C-1..C-7 与五项结论。

## 1. 复审方法

| 手段 | 内容 |
|---|---|
| 机检 | elan/toolchain/olean/repl 清点；session JSONL 与 ANCHOR_RE（真实现）校验；PROGRESS 行档位声明检查 |
| 探针 | T-1..T-15 共 15 项：Lean 双探针（单文件 + per-run 工程）、leanchecker、scipy、无 lake、判定降级矩阵 |
| 读码 | AP `verdict/policy.py`、`lean4_project.py`、`config.py`、`pyproject.toml`；ARC `runtime/exit_codes.py`；M0 C4 schema |

## 2. 事实与结论复验（T 表，全部一手）

| # | 主张 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | 6 个工具链、默认 4.20.0（F-1/F-2） | `elan show` + 目录清点 | ✅ 6 目录，default v4.20.0 |
| T-2 | lean_src pin 4.20.0（F-4） | 读 `lean-toolchain` | ✅ |
| T-3 | Mathlib 6443 olean + repl.exe（F-5） | 清点 | ✅ 6443 / True |
| T-4 | `import Mathlib` 定理编译 rc=0、axioms `[propext]`（F-6） | `lake env lean` 临时文件 | ✅ rc=0，输出一致 |
| T-5 | per-run 工程 `lake build Main` 成功（F-7） | 新建 rev1 工程 + build | ✅ rc=0、`Main.olean` 产出；**warm 重放 8.4s**（原文 53.3s 为冷读数，结论不变） |
| T-6 | 4.20 无 `leanchecker`（U-5 本机复查） | `leanchecker --version` | ✅ 同一报错（binary 缺失） |
| T-7 | 3.12 venv scipy 可用（U-4） | import + `stats.norm.mean(1,2)` | ✅ scipy 1.18.1 / numpy 2.5.4 / 1.0 |
| T-8 | 无 lake 不抛异常（F-13） | `LeanSimRuntime("definitely-missing-lake")` | ✅ `_lake_available=False`、错误串返回 |
| T-9 | 判定降级链（F-14） | 4 组 `VerdictEvidence` | ✅ latex/numerical/falsified；**见 D-1：`synthesis_verified=True` 且 tree=None 仍降级 `latex_verified`** |
| T-10 | AP 无 console script（F-15） | `pyproject.toml` | ✅ 无 `[project.scripts]` |
| T-11 | e2e 总超时 1800s（F-15） | grep | ✅ `_TOTAL_TIMEOUT_SECONDS = 1800.0` |
| T-12 | session 五步链 + 锚点合法（P-050/051/052） | 逐行解析 + **真 ANCHOR_RE**（spec_runner.py:218） | ✅ seq 连续、5 步有序、step_seq=idx、bad_anchors=0 |
| T-13 | PROGRESS 行档位声明（P-050/051/052） | 读行 | ✅ 均含「T3：Layer-0 …」 |
| T-14 | §7.2 响应示例 vs C4 必填 | diff required 字段 | ⚠️ 缺 8 个必填（见 O-1） |
| T-15 | 外部锚点可解析 | 本会话逐条抓取 S-6..S-24 与 S-1..S-5 | ✅ 无失效 URL；引用内容与读数一致 |

**排除幻觉结论**：22 条 F 事实全部复现或与读码一致；24 条外部锚点全部回源且关键读数（leanchecker 自 4.28、Lean4Lean 慢 20–50%、MCP stdio/Streamable HTTP、Mathlib 同 toolchain 要求）与原文相符；未发现虚构来源或数字。

## 3. 复审发现

### D-1（P1，设计缺口）：§9 场景 A 在 AP 现行 policy 下不可达

调研 §9 预期「可证明定理 + lean_check ⇒ `formally_verified`、depth=stage3」。但 T-9 证实：AP `decide_citation_label` 在 `proof_tree is None` 时**先短路**进 `_fallback`（`verdict/policy.py`），**即使 `synthesis_verified=True`** 也只给出 `latex_verified`/`numerically_verified`；`formally_verified` 需要**根 PROVEN 的 ProofTree** 或「非 None 树 + synthesis_verified」。`lean_check` 模式只有 `CompileReport`，无树。

**修法（M3 实施批先决）**：二选一并在设计文档冻结——
1. sidecar 在 `compile_report.success && axiom_check=="passed" && 无 sorry` 时构造**根 PROVEN 的最小 ProofTree**（叶子 = 该定理），再交给 `decide_citation_label`；语义上等价于「kernel 已接受该定理」，符合 §6.1 信任边界；
2. AP 上游为 policy 增加 compile-only 路径（改动面更大，需 AP 侧测试）。

同时 §7.2 示例的 `verification_depth: "stage3"` 依赖该映射成立。

### D-2（P1，契约冲突）：退出码 77 与 G1b 冻结契约冲突

调研 §7.3 定义「77 = 能力不可用（Lean 不可用降级路径）」。但 ARC 契约（`runtime/exit_codes.py:13`、[P-028 R-1](../spec/arc-g1b-supervisor-protocol/RESEARCH.md)）冻结 **77 = REVOKED / NOPERM**（凭据撤销），且「只有 75 可重试」。按调研实现会让 supervisor 把「Lean 不可用」归入 revoked 语义，破坏 A1-7 的分类不变量。

**修法**：Lean 不可用改判 **78（CONFIG：环境/工具链缺失）**，或在 sidecar 契约内新增 79..84 区间的新码（85 已被 PAUSED 占用）并同步 `exit_codes.py`；**不得占用 77**。建议 M3 实施批在 DESIGN 中定案并补 ADR。

### O 表

| # | 内容 | 定级 |
|---|---|---|
| O-1 | §7.2 响应示例的 `claim_record` 仅含 6 字段，缺 C4 必填 8 项（statement/formality/assumptions/evidence/reasoning_chain/stats_protocol/falsifier/formal_statement）。示例是投影可接受，但实施须返回**完整 C4**或在接口文档显式声明投影口径并声明它**不用于** C4 校验面 | 接口文档 |
| O-2 | 总纲停在 v1.3g（P-049）；M3 调研三批（P-050..P-052）未写修订行。调研批不强制同步，但建议 M3 实施批交付时补 v1.3h（挂 M3 调研 + 实施依据） | 流程 |
| O-3 | §8 降级矩阵「编译失败 → ≤ partially_formalized」与 AP 实际降级链（`_fallback`：numerical > latex > FAILED）措辞易误读——编译失败本身不会给 partially_formalized（那需要树）。建议改为「按 `_fallback` 降级，无树时上限 `latex_verified`」 | 文档 |
| O-4 | F-7 的 53.3s 为冷读数；warm 重放 8.4s（T-5）。`prewarm_timeout=300s` 仍充足，验收 A 的计时断言应允许 8–60s 区间而非固定值 | 验收口径 |
| O-5 | `lake env lean` 会打印依赖仓库 "has local changes" 警告（F-8 已登记）；sidecar 解析 stdout 时须把 lake 警告行与 Lean 诊断区分（AP `_format_build_error` 已按 `trace:` 过滤，可复用） | 实现提示 |

## 4. 结论

- **无幻觉**：F/S/C 三张表的全部主张经受住机检、探针与回源复验；U-1..U-5 的五项结论证据充分（其中 U-4/U-5 有本机正反两向探针）。
- **两处设计缺口（D-1/D-2）须在 M3 实施批先决解决**：D-1 决定场景 A 能否成立，D-2 决定退出码契约不被破坏；两者都有明确修法，不影响调研结论本身。
- O-1..O-5 登记为实施批输入；无需修复批。
- M3 可进入实施批，开工前置 = D-1/D-2 的 DESIGN 定案。
