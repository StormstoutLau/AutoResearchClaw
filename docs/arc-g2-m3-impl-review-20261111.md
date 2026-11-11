# P-054 M3 实施设计包独立复审报告（2026-11-11）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。纪律同 P-039/P-041/P-053——不采信设计文档结论，全部以机检、探针、读码一手重验。
> **对象**：[P-054 设计包](../spec/arc-g2-m3-implementation/)（RESEARCH/DESIGN/IMPLEMENTATION/CHECKLIST）及其对 P-053 D-1/D-2 的关闭方案。

## 1. 复审方法

| 手段 | 内容 |
|---|---|
| 探针 | 判定矩阵 5 组（编译失败/latex 门/sorry/axiom dirty/skipped）；P-054 原探针复跑 |
| 读码 | `verdict/policy.py:30-86`、`sandbox/lean_filter.py` 全文、`stages/proving_runtime.py` 超时路径、`datatypes/config.py:194` |
| 机检 | DESIGN JSON 样例 × C1/C4 schema；session/锚点/PROGRESS 行 |

## 2. 主张复验（T 表，全部一手）

| # | 主张 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | 仅最小树 → `partially_formalized/legality_not_checked`（F-1） | 复跑 P-054 探针 | ✅ |
| T-2 | 最小树 + 真实 7 层合法性：合法→`formally_verified`；axiom 注入→第 2 层失败（F-2） | 复跑双探针 | ✅ |
| T-3 | C4 必填 14 项（F-9） | schema diff | ✅ |
| T-4 | 退出码 0/65/75/77/78/85，77=REVOKED（F-8） | `exit_codes.py:10-15` | ✅ |
| T-5 | 无 console script（F-12） | `pyproject.toml` | ✅ |
| T-6 | DESIGN 请求/响应样例通过 C4 | jsonschema 机检 | ✅ 两处 `claim_record` PASS |
| T-7 | DESIGN 响应样例通过 C1 | jsonschema 机检 | ⚠️ `inputs_digest` 占位符不匹配 pattern（O-2） |
| T-8 | `#print axioms` 标准公理 → `axiom_check=passed`（F-5 内容） | 读 `config.py:194` docstring | ✅ 内容正确，**引用文件错**（O-1） |
| T-9 | 超时路径不抛异常（F-14 前提） | 读 `_run_build` 287 行 | ✅ 捕获 TimeoutExpired → 返回 failed（**引出 D-C**） |
| T-10 | P-054 session 五步链 + 锚点 | 真 ANCHOR_RE + 逐行解析 | ✅ bad=0 |
| T-11 | PROGRESS P-054 行 T1 档位 + in-progress | 读行 | ✅ |
| T-12 | **过滤器不含 `axiom`/`sorry`**（L-D/L-F 可达性前提） | 读 `DANGEROUS_LEAN_TOKENS` 全文 | ✅ 仅 `#eval/#exec/run_cmd/implemented_by/@[extern/unsafe /IO.` |

## 3. 复审发现

### D-A（P1）：§3.1 五条件门 + `latex_ok` 常量 → 三个路径误标 `latex_verified`

DESIGN §3.1 要求「`status=="success"`（无 sorry）且 `axiom_check=="passed"`」才造树，且 `VerdictEvidence(latex_ok=True, ...)` 为常量。探针证实后果：

| 场景 | 设计下的实际 label | A2-7 要求 |
|---|---|---|
| 编译失败（无树，latex_ok=True） | **`latex_verified`**（探针 A） | 失败不得提升 |
| 含 sorry（条件 2 不满足 → 无树） | **`latex_verified`** | 上限 `partially_formalized`、depth stage2 |
| axiom_check failed/skipped（条件 4 不满足 → 无树） | **`latex_verified`**（探针 D/E 反向） | 上限 `partially_formalized` |

即设计**自己的 §7 降级矩阵有三行不可达**，且违反 A2-7。

**修正（探针 C/D/E 已验证）**：
- `latex_ok := compile_report.success`（编译失败 → `FAILED/stage1_not_success`，诚实）；
- `tree := 最小树(sorry=len(sorry_warnings))` **当且仅当** `compile_report.success`（含 sorry 也造树）；
- axiom/legality 交由 policy 判：sorry → `tree_partial`、axiom dirty → `axioms_not_clean`、skipped → `axiom_check_skipped`、合法性失败 → `legality_failed`、全清 → `formally_verified`。

最小树语义不变：`compile_report.success` 即「kernel 已接受全部声明（sorry 除外）」的编译见证。

### D-B（P1）：§3.3 深度映射 `failed → stage1` 违反 A2-7

A2-7 明文「编译失败 → 深度 stage2」。修正：lean_check 模式下 `FAILED → stage2`；`falsified/speculation` 的映射留 M4（lean_check 不产出）。

### D-C（P1）：L-G 的 exit 75 无实现通路

`_run_build` 捕获 `TimeoutExpired` 后返回 `_BuildOutcome(ok=False, message=...)`，而 `compile_report` 只取 `outcome.diagnostics`——**超时信号不进入 CompileReport**，与普通编译失败不可区分。按 §2.3 第 5 步实现的 arb_verify 永远无法产出 75/`lean_timeout`。

**修正**：arb_verify 层用 `asyncio.wait_for(compile_report(...), timeout=timeout_s)` 包裹，捕获后写响应 exit 75；这同时覆盖 LeanSimRuntime 内部超时与整跑挂死。副效应：AP 内部超时先到时 lean.exe 子进程可能残留——ARC 层 `taskkill /T` 仅在 ARC 超时触发，建议响应仍写 `lean_timeout` 并在 finally 清理工程（清理失败的孤儿登记 U-1）。

### O 表

| # | 内容 | 定级 |
|---|---|---|
| O-1 | RESEARCH F-5 引用「`datatypes/numerical.py` 类定义」有误——`CompileReport` 定义在 `datatypes/config.py:194`（内容主张正确，指针订正） | 引用订正 |
| O-2 | §5.2 响应样例 `inputs_digest: "sha256:..."` 不匹配 C1 pattern（T-7 机检）；实施必须为真实 64 hex，建议样例加注释 | 示例 |
| O-3 | `request_id` 直接作 per-run `run_id` 会被 AP `_sanitize_run_id` 改写；响应 `lean.project` 以实际路径为准，ARC 不得假设同名 | 实现注意 |
| O-4 | §7 矩阵缺「危险构造被拒」行：命中 `DANGEROUS_LEAN_TOKENS` → success=False → 修正后 `FAILED/stage2`，建议 `degraded_reason=rejected_dangerous_construct` | 矩阵补行 |
| O-5 | `SidecarConfig.timeout_s`（330）= 请求 `timeout_s`（300）+30 缓冲的关系应写入契约，避免两侧各自配 | 契约 |

## 4. 结论

- **无幻觉**：12 项主张中 11 项复现/读码一致；唯一偏差是 O-1 的引用指针（内容正确）。P-054 的两个核心定案——最小树 + 真实合法性（D-1 解法）、77 保留/78 必需/0 可选（D-2 解法）——**方向正确且经探针背书**。
- **三处 P1 修正（D-A/D-B/D-C）必须在施工前落入 DESIGN**：均为映射规则修正，改动面小（§3.1/§3.3/§2.3 第 5 步 + §7 补行），不需要独立修复批——由执行批（重编号为 **P-056**）开工时先修订 DESIGN 再写码。
- 原「执行批 P-055」编号让位给本复审，P-054 文档中的两处引用已同步订正。
- CHECKLIST 保持 pending；O-1..O-5 与 D-A..D-C 一并作为 P-056 输入。
