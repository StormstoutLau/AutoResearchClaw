# P-056 设计修复独立复审报告（2026-11-11）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。纪律同 P-053/P-055——不采信修复文档结论，全部以探针、读码、机检一手重验。
> **对象**：P-056 对 [P-055 复审](arc-g2-m3-impl-review-20261111.md) D-A/D-B/D-C 与 O-1..O-5 的落实（[设计包 v1.1](../spec/arc-g2-m3-implementation/)）。

## 1. 修正落实复验（T 表，全部一手）

| # | 修正 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | **D-A**：9 组判定矩阵——编译失败→`FAILED`、sorry→`tree_partial`、axiom failed/skipped→`partially`、legality fail→`legality_failed`、全清→`formally_verified` | 3.12 探针逐组实跑 | ✅ 全部与 A2-7 一致 |
| T-2 | **D-A** sorry+axiom 并存优先级 | 同上 | ✅ `tree_partial`（policy 中 sorry 先于 compile 检查） |
| T-3 | **D-B**：`failed`/`falsified` → `stage2` | DESIGN §3.3 表 | ✅ |
| T-4 | **D-C**：`wait_for` 不可抢占（F-14） | 读码 `proving_runtime.py:148,170`——`compile_report` 为 `async def` 但**同步**调用 `_run_build`（无 `await`） | ✅ 设计改为 `timed_out` 字段 + 客户端兜底，口径正确 |
| T-5 | **D-C**：超时信号丢失（F-13） | 读码 `proving_runtime.py:287-289`——`TimeoutExpired` 只写 `message`；`compile_report` 只取 `diagnostics` | ✅ |
| T-6 | **O-1**：`CompileReport` 指针 | `datatypes/config.py:194` | ✅ RESEARCH F-5 已订正 |
| T-7 | **O-2**：样例 `inputs_digest` | jsonschema 机检 | ✅ request.claim C4 PASS、response.run C1 PASS、response.claim_record C4 PASS |
| T-8 | **O-3/O-4/O-5** | 读 §5.1/§7/§5.1 尾注 | ✅ 三处均已写入 |
| T-9 | 计数一致（单元 8 / live L-A..L-H） | 三文档比对 | ✅ |
| T-10 | P-056 session 五步链 + 锚点 | 真 ANCHOR_RE | ✅ bad=0 |
| T-11 | `evidence_complete` 残留面 | 读码 `proving_runtime.py:165,195` | ⚠️ 见 O-A |

## 2. 复审发现

### 缺陷：无

D-A/D-B/D-C 三项修正全部正确落地；9 组矩阵探针证明修正后的映射与 A2-7 及退出码契约完全一致；O-1..O-5 全部落实。

### 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-A | DESIGN §3.1 条件 2（`evidence_complete is True`）与「success 即建树」原则**冗余且矛盾**：若未来出现 `success=True, evidence_complete=False`，无树 + `latex_ok=True` 会复发 D-A 的 `latex_verified` 误标。实测 `LeanSimRuntime.compile_report` 在两处构造点**恒写** `evidence_complete=True`（`proving_runtime.py:165,195`），当前不可触发。建议 P-058 删除条件 2（policy 已有 `evidence_incomplete` 出口） | 文档 |
| O-B | §7 矩阵未写**优先级**：sorry 与 axiom 不干净并存时 policy 先判 `tree_partial`（T-2）。建议加一行注 | 文档 |
| O-C | `rejected_dangerous_construct` 的**检测机制**未指明：AP 拒绝路径把 `message` 写进 `diagnostics/errors`，前缀 `rejected: `（`proving_runtime.py` 拒绝分支）是稳定信号；arb_verify 应以 `diagnostics.startswith("rejected:")` 判定，勿再增 AP 字段 | 实现注意 |
| O-D | AP 侧两处改动（`timed_out` 字段、超时分支写 `diagnostics`）可能影响既有断言：P-058 施工时必须跑 AP 相关测试（`tests/test_b27_compile_check.py`、`test_d2_d10_lean4_runtime.py` 等）并回填读数 | 验证项 |

## 3. 结论

- **无幻觉、无缺陷**：P-056 的三项 P1 修正与五个 O 项全部正确落地，判定矩阵 9 组探针 + 读码 + schema 机检全部通过。
- O-A..O-D 均为文档/实现注意级，随 **P-058**（执行批，编号由 P-057 让位）落实：其中 O-A/O-B 为一行订正，O-C/O-D 为施工注意事项。
- 设计包 v1.1 自此**可施工**；CHECKLIST 保持 pending。
