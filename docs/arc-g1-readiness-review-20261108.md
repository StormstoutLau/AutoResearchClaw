---
id: arc-g1-readiness-review-20261108
type: design
version: 0.1
status: draft
date: 2026-11-08
depends: [arc-g1-readiness-research-20261108]
upstream: arc-g1-readiness-research-20261108
---

# G-1 就绪调研 · 独立复核报告

> **审查对象**：[arc-g1-readiness-research-20261108.md](arc-g1-readiness-research-20261108.md) 及其驱动的 P-006 实现（`0f31428`）。
> **审查性质**：独立 pass。机检全部重放；**修复前代码事实以 `git show a7427ec` 逐条核验**（不复用调研会话内的读码结果）；**12 项锚点全部重新搜索**；并实际执行了实现文档承诺的 2 项变异抽查。本轮不改任何被审文档。
> **结论标注**：`成立 / 成立但需限定 / 需修正`。

---

## 0. 取证矩阵

| 手段 | 覆盖项 | 结果 |
|---|---|---|
| 机检重放（E1） | 28 个 H 测试、覆盖率门禁、dc-validator、step-gate | ✅ 全部复现 |
| `git show a7427ec`（E2） | H-1/H-7/H-8 的修复前代码事实 | ✅ 4/4 成立 |
| 符号定位（E2） | 8 项修复的落点与调用点 | ✅ 8/8 在位 |
| 变异抽查（E2） | `safe_join` 守卫移除、env 透传 | ✅ 分别 4 红 / 2 红，恢复后复绿 |
| 锚点重验（E4） | 12 项锚点独立搜索 | ✅ 12/12 命中（SSDF PS.3.2 编号确认） |
| 回归重放（E1） | 11 个既有测试文件 | ✅ 346 passed / 5 skipped 逐字复现 |

## 1. 逐项复核

| 调研主张 | 判定 | 复核证据 |
|---|---|---|
| H-1：主路径 payload 无 `returncode`，agent 路径有 | **成立** | `a7427ec` 版 `_execution.py`：agent payload L172 有 `returncode`，主路径内联 dict（L577 起）无 |
| H-2：`max_retries` 无 stage 级消费点 | **成立** | `a7427ec` 的 `executor.py`/`runner.py` 零命中 |
| H-3：`ClaimVerifier` 仅测试引用 | **成立** | 全仓唯一生产引用在 `hitl/claim_verifier.py:68`（定义处） |
| H-4：`retrieval_degraded` 零命中；L203 静默跳过；L352 仅模型计划回退 | **成立** | 三处均在 `a7427ec` 复现 |
| H-5：真缺口在聚合层 | **成立** | `_collect_experiment_results` 修复前不读 `status`/`returncode` |
| H-6：三处透传 `os.environ` | **成立** | `sandbox.py:324/425`、`mcp/client.py:69`（修复前行号） |
| H-7：`safe_join` 不存在；L1141-1144 裸拼接 | **成立** | `git grep safe_join a7427ec` 零命中 |
| H-8：默认 `*` + `allow_credentials=True` | **成立** | `a7427ec` 版 config.py / app.py 逐字复现 |
| Q20 两字段不同作用域，合并会删 CLI 上限 | **成立** | `code_agent.py:579-580` 传 `--max-budget-usd`；`runner.py:482` 把同一字段当整线预算；`runner.py:513` 阶段级检查 |
| 8 个测试文件、28 用例 | **成立** | 重放 28 passed |
| 回归子集 346 passed / 5 skipped | **成立** | 重放逐字一致（144s） |
| 变异抽查 2 项 | **成立** | 本复核实际执行（见 §2 F-0） |
| 12 项锚点 | **成立** | 全部独立命中；SSDF PS.3 编号正确（PS.3.2 = provenance 收集维护共享） |

## 2. 发现清单

| # | 严重度 | 发现 | 处置建议 |
|---|---|---|---|
| **F-0** | ——（验证性发现） | 实现文档承诺的"人工抽查 2 项"此前未实际执行；本复核补做：`safe_join` 守卫移除 → 4 用例变红；env 透传 → 2 用例变红（密钥泄漏复现）；恢复后 9 用例复绿。负向用例"能变红"的声明由此从承诺变为已验证 | 已闭环，无需动作 |
| **F-1** | P3 | H-2 的重试循环只覆盖 executor 返回 FAILED 或抛异常；**契约产物校验发生在重试循环之外**——产物缺失不触发重试。总纲断言未定义重试范围 | 在 G-1 的 `RESEARCH.md` 冻结重试语义时写明（当前行为合理：产物校验失败多为确定性缺陷） |
| **F-2** | P3 | `retrieval_status.json` 已产出并进入 `StageResult.artifacts`，但 **Stage 4 契约 `output_files` 未声明**。契约是最小要求故不致失败，但 A3-4/A3-5 接线时应补 | G3 的 RESEARCH 登记契约更新 |
| **F-3** | P3 | 默认 CORS origins（`localhost:3000`）为占位值：实际前端是 FastAPI 同源挂载的 vanilla JS（`frontend-legacy`，无构建步骤、无独立 dev server），**打包 UI 不需要 CORS** | origins 保留现状；出现真实跨源部署时再改，建议在 G-1 RESEARCH 记一句 |
| **F-4** | P3 | H-4 的降级语义：仅学术 API 失败置 `degraded=true`；web-search 增强失败不置。总纲未定义"降级"边界，实现取了合理解释 | 同 F-1，随 G-1 RESEARCH 冻结 |
| **F-5** | P3 | `test_claim_verifier_wiring` 开发过程中 fixture 曾被修正（`achieves 95% accuracy` → `achieves accuracy 95%`）——`ClaimVerifier` 的数值断言正则对词序敏感。当前用例正确，但该正则敏感性值得在 H-3 的实现里留意 | 可选：给 ClaimVerifier 的 regex 加词序宽容；不阻塞 |

**未发现 P1/P2 级问题**：调研的全部事实主张、裁决逻辑与实现均复核成立。

## 3. 对后续批次的影响

- **G-1 开工**：F-1/F-4 的语义冻结应写进 G-1 的 `RESEARCH.md`（一条段落即可），避免实现者误判重试与降级的边界。
- **G3**：F-2 的契约补声明随 A3-4/A3-5 接线一并做。
- **G6**：Q20 的分层账本实现时，注意 `runner.py:482` 现在把 CLI 字段当整线预算——迁移时需同时改读数点，否则分层不成立。
- **Q19 发布说明**：`host`/`cors_origins` 默认值变更属于行为变更，应在发布说明标注。

## 4. 总结论

调研文档的全部事实主张（8 项修复前状态、6 项 Q20 代码锚点、12 项外部锚点）经独立手段**无一被推翻**；实现与调研的测试矩阵逐项对应；"负向用例能变红"经真实变异验证。仅 5 条 P3 级观察，均不改变 G-1 已达成的状态：**"不产出假结果"所需的最小可信集（H-1..H-8 + Q19）已在代码层闭合**。

> 本报告未修改任何被审文档；F-1..F-5 应在对应阶段（G-1/G3/G6）的 RESEARCH 中登记，不单独开批。
