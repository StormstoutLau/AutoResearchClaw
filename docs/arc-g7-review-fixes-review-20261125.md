# P-164（G7 复审修复批）异构独立复审报告

---
id: arc-g7-review-fixes-review-20261125
type: review
version: 1.0
status: final
date: 2026-11-25
reviewer: GLM-5.3-Flash
implementer: DeepSeek-V4.1-Flash
target: PR #45（spec/p164-g7-review-fixes，squash merge `992d6c1`）
---

> **复审性质**：异构基座独立复审（SPEC_PROCESS RULE-5：GLM-5.3-Flash × DeepSeek-V4.1-Flash）+ RULE-6 单向权限（只标记，不修复）+ RULE-1 独立 pass（不采信 P-164 四文档自报，全部一手重验）。
> **取证纪律**：探针落 `%TEMP%\arc-rv164\`（两轮），**零仓库变异**；结论绑定 E1-E4。复审者首轮探针自身错误一处（PR-7 用单层任务 D1 测 depth 溢出，depth 永不触顶），已在第二轮以 L3（3 层 DAG）修正复测——按 P-161 T-3 先例披露，不计为产品缺陷。

## 1. 结论（诚实结果列）

**P-164 四条修复全部一手成立且经对抗探针无缺陷：0 P1 / 0 P2 / 0 P3，登记 6 项观察（O-1..O-6）。零发现已按 RULE-6(c) 降级重扫一轮（换 depth/wall/摘要尾三个新角度），仍为零，扫描范围见 §4.3。**

| 主张 | 复审判定 | 证据 |
|---|---|---|
| 偏移链：删前缀后 `verify_chain(start_seq=first)` 可验 | ✅ PR-2 chain=True（first_seq=3） | E2 |
| 默认严格仍红（`retention_limited`） | ✅ PR-2 strict ok=False | E2 |
| 逃生舱 `allow_retention_gap=True` → ok/converged/chain_ok 全 True | ✅ PR-2 relaxed 三 True | E2 |
| 首条 payload 篡改仍判红 | ✅ PR-3 payload_sha256 mismatch at seq 3 | E2 |
| 零 prev 伪造判红 | ✅ PR-1 "offset chain starts with zero prev_sha256" | E2 |
| 摘要尾绑定在偏移模式仍生效 | ✅ PR-12 错误 chain_tail → chain False | E2 |
| POSIX 进程组守卫（组长 killpg / 非组长与 OSError 回退） | ✅ T04 5 用例 + PR-8 spawn kwargs | E1 |
| 死代码清零 | ✅ PR-9 grep：`killed =`/`_mtime` 0 命中，is_dir 1 处 | E1 |
| 真实 token 溢出五件套可读且自洽 | ✅ PR-6 usage 424/424=trace_sum，judge total=0、ob4=True、match=True | E2 |
| depth/wall 溢出同样落工件 | ✅ PR-10/PR-11（budget_exceeded、五件套齐、ob4=True、total=0） | E2 |
| fixture 不被覆盖 | ✅ T08（charged=budget+1 保持） | E1 |
| 正常路径零变化 | ✅ 76 passed 复跑 + 矩阵 OB-1..OB-5 全 PASS 均值不变 | E1/E2 |

## 2. T 表：一手复验

| # | 复验项 | 读数 | 等级 |
|---|---|---|---|
| T-1 | 触及面测试复跑（13 文件） | `76 passed in 17.41s`（声称 19.07s，同数） | E1 |
| T-2 | 编排全矩阵复跑 | ob1..ob5 全 PASS；均值逐项一致（gold 10.4 / single 5.8 / over_split 2.0） | E2 |
| T-3 | digest 绑定 | session finalize sha256 == 终稿四文档（CHECKLIST 382b0d67…、DESIGN f97a5232…、IMPLEMENTATION 45745b04…、RESEARCH 3ede5299…）4/4 OK；session 5 步链完整 | E1 |
| T-4 | CHECKLIST 算术 | 6 行 4+7+4+5+3+3=26，通过列和 26，`26=26+0+0` 成立（RULE-2 逐项核对） | E1 |
| T-5 | diff 面 vs 意图 | `992d6c1` = 15 files / +911 / -44，恰为 4 实现 + 3 测试 + 4 文档 + session + 3 派生视图，无越界文件 | E1 |
| T-6 | 三轮 CI + 合并 | 45459190463 / 45459697236 / 45460304395 全 success；PR45 `state=MERGED merge=992d6c1` | E1 |
| T-7 | pre-commit 10 钩子 | 登记 pass（见 §6 本批复跑读数） | E1 |
| T-8 | 改动引入面 | adapters 新增 98 行无 subprocess/socket；driver 变更仅 kill/spawn 路径；新增禁用面 0 | E1/E3 |
| T-9 | 既有消费者零破坏 | `verify_chain()` 无参调用（run_equivalence/pipeline_manifest/reproducibility 等）走默认分支，全量 3905 passed（CI 3.11–3.14 佐证） | E1 |
| T-10 | 外部依据回原文 | Python `subprocess.Popen(start_new_session=)` 官方文档（T1）；POSIX `killpg`/进程组语义（T1 标准） | E1 |

## 3. 探针明细（E2，两轮 15 项）

| # | 场景 | 结果 |
|---|---|---|
| PR-1 | 偏移起点伪造零 prev | 拒绝（zero prev_sha256） |
| PR-2 | 真实轮转 + 删前缀两段 | strict 红 / relaxed 绿（first_seq=3） |
| PR-3 | 偏移首条 payload 篡改 | 判红（payload_sha256 mismatch） |
| PR-4 | 新鲜 run 无 events_summary.json | 尾绑定跳过（与既有 event_log 测试的存在-用例互补） |
| PR-5 | `start_seq=0` / `-3` | 钳位为 1，offset 关闭，正常链 True |
| PR-6 | 真实 token 溢出（D1×300） | 五件套齐；usage 424=trace_sum=charged；judge total=0、gate=aggregation_zero、ob4/match True |
| PR-7 | ~~depth 溢出~~（D1 单层，探针自身无效） | 撤销，第二轮修正 |
| PR-8 | spawn kwargs 平台分支 | nt={} / posix={start_new_session:True} |
| PR-9 | 死代码 grep | 0 命中；is_dir 1 处 |
| PR-10 | depth 溢出（L3×3 层×max_depth=1） | budget_exceeded、五件套齐、judge ob4=True、total=0 |
| PR-11 | wall 溢出（wall_seconds=0） | budget_exceeded、五件套齐、ob4=True、total=0 |
| PR-12 | 偏移链 × 错误 chain_tail 摘要 | chain False（chain_tail mismatch） |

## 4. O 表：观察项（不构成缺陷）

| # | 观察 | 证据 | 建议 |
|---|---|---|---|
| O-1 | 偏移链对**首条可读事件**的 `prev_sha256` 本质不可验（任何非零值都被接受）——真值已随被删段消失；零 prev 检查只拦截懒惰伪造 | E2 PR-1 + E3 读码 | 与 P-040 O-1「归档级验证超范围」口径一致；无需改动，文档已声明 |
| O-2 | 失败工件 token 语义双轨：trace 已存在时取已成功计费之和；trace 缺失时合成 trace 记录的是 `exc.observed`（尝试值）。两种状态各自自洽，但混写场景（部分工件存在）尚未被测试触碰 | E3 读码 | 后续如接入真实计费，补一个混合态测试 |
| O-3 | **覆盖缺口**：CHECKLIST E-3 宣称「workers/wall/depth 也落 budget_exceeded 工件」，但提交的 T07 只测 workers；wall/depth 由本复审探针（PR-10/PR-11）补证成立，未固化为回归测试 | E1/E2 | 后续批把 PR-10/PR-11 落成 2 个测试用例 |
| O-4 | 摘要尾绑定只在 `events_summary.json` 存在时生效；soak verifier 不产摘要，偏移链在无摘要 run 上无尾闭包 | E2 PR-4 | 与 P-160 设计一致；无需改动 |
| O-5 | POSIX 真路径（真实子进程 + 真实 killpg）无提交测试：单测全部走注入助手；CI Linux 的 soak 注入测试隐式经过真路径但 fake worker 无孙进程 | E3 | A7-2 段（多 run 并发）落地时补一个真实进程组测试 |
| O-6 | `validate_task` 校验 `max_workers ≥ 最宽层` 但**未校验** `max_depth ≥ 层数`；当前 15 任务全部满足（L3 恰为 3/3），若未来任务配错，gold 将永久 `budget_exceeded` → OB-1 红 | E3 | 下次触碰任务语料时补一条校验 |

### 4.3 盲区扫描范围声明（RULE-6c/E4）

- 扫描面：26 项 CHECKLIST 断言、12 个新测试、4 个改动文件的分支覆盖（verify_chain 偏移/零 prev/摘要尾、_posix_kill_tree 四分支、_write_budget_failure 全缺/部分缺/全齐三态、_spawn_kwargs 平台）、gate 谓词、派生视图一致性。
- 零发现处置：首轮 9 探针零缺陷 → 换角度（depth/wall/摘要尾/钳位）重扫 6 项 → 仍零 → 记合规并声明范围。1 项探针自身错误（PR-7）已披露并修正。
- 未覆盖：真实 LLM 计费（本仓无）、Windows taskkill 真杀（P-160 已测）、POSIX 真实孙进程（O-5）。

## 5. 与 P-161/P-163 复审的口径对照

| 项 | P-161 | P-163 | 本复审（P-165） |
|---|---|---|---|
| 异构对 | GLM × DeepSeek | 同 | 同（互换角色） |
| 缺陷 | D-1/D-2 P2 + D-3 P3 | D-1 P2 + D-2 P3 | **0 缺陷** |
| 观察 | O-1..O-5 | O-1..O-6 | O-1..O-6（含 1 项覆盖缺口 O-3） |
| 探针自身错误披露 | T-3 注记 | PR-7 撤销注记 | PR-7 撤销注记 |
| 单向权限 | 未改实现 | 未改实现 | 未改实现 |

## 6. 复审登记门禁（本批执行读数）

- dc（grandfather_gate）：`grandfathered=0 expired=0 violations=0`
- step-gate：`specwf-p165-g7-review-fixes-review` 5/5
- verify-anchor：见登记后输出
- step-enforce：`mode=session-progress pid=P-165`
- pre-commit：10/10 Passed

## 7. 处置建议

1. **四条缺陷正式关闭**：P-161 D-1/D-2/D-3、P-163 D-1 → 状态从「登记待修」改为「已修复并回归」。
2. **O-3（覆盖缺口）优先**：PR-10/PR-11 场景落成 2 个测试用例，随下一次触碰 orchestration 的批次执行。
3. **O-1..O-6 其余**：登记在案，不强制承接；O-6 涉及任务语料校验，承接时须先过 DESIGN。
4. **边界维持**：本复审零代码变更；P-163 的 O-1..O-6 中与 soak 无关者继续留档。
