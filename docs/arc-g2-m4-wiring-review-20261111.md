# P-061 M4 独立复审报告（2026-11-11）

> **性质**：Layer-0 独立复审（T3，零代码/零门禁）。纪律同 P-053/P-055/P-057——不采信 [IMPLEMENTATION](../spec/arc-g2-m4-wiring/IMPLEMENTATION.md)/[CHECKLIST](../spec/arc-g2-m4-wiring/CHECKLIST.md) 结论，全部以探针、读码、机检一手重验。
> **对象**：P-061 G2 M4（Stage 9/20/23 接线与双平面，[spec/arc-g2-m4-wiring/](../spec/arc-g2-m4-wiring/)）。工作树状态：已暂存未提交。
> **探针**：`%TEMP%\m4_review_probe.py`（9 组，全部临时目录，零仓库变异）。

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | A2-4：`falsified`/`failed` → 不可发布；`fail` finding 阻断；`warn`/`downgrade` 不阻断 | 测试复跑（参数化 2+3+2 例） | ✅ |
| T-2 | A2-5：`numerically_verified` 无 annotation 阻断；补 `annotations.json` 后通过；非数值状态免检 | 测试复跑 | ✅ |
| T-3 | A2-6：A 缺引文 → assumptions+speculation **不阻断**、原 claim 不被改写；B 链完整不降级、缺链降级；C 免降级 | 测试复跑 | ✅ |
| T-4 | 封顶：AR-05/06 → `latex_verified`；终态不被抬升 | 测试复跑 | ✅ |
| T-5 | Stage 9 抽取产物 C4 合规（14 必填 / `c-[0-9a-f]{8}`） | 探针 P-H：2 条 schema 全 PASS | ✅ |
| T-6 | Stage 20 接线：FALSIFIED → `E20_CLAIM_CONTRACT`；gate 先于 SIM 检查；各 return 追加 artifacts | 读码 `_review_publish.py:419-448,465,677,710,721,734` + 测试复跑 | ✅ |
| T-7 | Stage 23 接线：status/deliverable 漂移可判红；续跑无生产决定 → `skipped` 放行；无 bib 仍写 `claim_consistency.json` | 测试复跑 | ✅ |
| T-8 | 门禁重跑幂等（不重复追加 assumptions） | 探针 P-E：两次运行逐字节相等 | ✅ |
| T-9 | Stage 23 fallback（stage-20 claims 缺失但 gate 存在）不误报 | 探针 P-F：consistent=True, checked=1 | ✅ |
| T-10 | 测试读数：M4 46 passed（3.13.5 本轮 1.04s；3.11.15 venv 本轮 0.61s）；相关回归 105 passed（3.14s） | 本轮全部实跑 | ✅ 与 P-061 记载一致 |
| T-11 | 机检：pre-commit 9/9；`step_enforce` mode=batch pid=P-061；coverage missing=0 | 本批复跑 | ✅ |
| T-12 | 全量读数 3328 passed / 7 环境性失败 / 108 skipped | P-061 施工日志（`%TEMP%\arc-m4-full.log`）复核 | ✅ 与记载一致 |

**文档计数零幻觉**：IMPLEMENTATION 改动表 9 项与 `git status` 一致；测试计数 33+13=46 与 `--collect-only` 一致；总纲 v1.3i、PROGRESS P-061 行、CI 固定清单插入位置均属实。

## 2. 缺陷（D 表）

### D-1（P1）PIVOT 后门禁/审计读到版本化旧 claim

- **证据**：`runner.py:1459-1477`（`_version_rollback_stages` 对 PIVOT 把 **stage-08..15** 全部 rename 为 `stage-NN_v{attempt}`，stage-09 在列）；[stage_hooks.py](../researchclaw/evidence/stage_hooks.py) `load_claims` 用 `sorted(glob("stage-09*/claims.jsonl"))[-1]` 取**字典序最大**；探针 **P-A** 实测同时存在 `stage-09`（NEW）与 `stage-09_v1/_v2`（OLD）时 picked=`OLD-v2`。
- **影响**：PIVOT 是受支持流程（`MAX_DECISION_PIVOTS=2`）。回滚重跑后 Stage 20 评估的是**前一轮**的 claim——新假设永远进不了 claim 系统，门禁空转在旧数据上。与 R14-2 约定（`_helpers.py:399-410`：非版本目录优先）和 DESIGN §4 自述「取最新前缀」均矛盾。
- **修法**：`load_claims` 排序语义与 `_read_prior_artifact` 对齐（非版本优先、版本按号降序），或精确匹配 `stage-09`/`stage-20` 不用通配。

### D-2（P1）坏行静默跳过 + 非原子写 → 阻断类 claim 可被静默绕过

- **证据**：探针 **P-C**——`claims.jsonl` 中 FALSIFIED 行损坏（其余合法）→ gate `verdict=pass, total=1`，而文件中 "falsified" 字样仍在；`load_claims` 对 `json.JSONDecodeError` 静默 `continue`；`_write_claims` 用 `write_text` **非原子**覆盖写。
- **影响**：崩溃截断尾行（部分写）或篡改单行即可让 FALSIFIED/FAILED claim 从门禁视野消失；Stage 23 读的 `stage-20/claims.jsonl` 由 gate 从同一污染源写出，**双平面同盲**，无法检出。与 DESIGN §7「fail-closed」姿态直接矛盾。M3 为 sidecar 响应正是为此采用 `os.replace` 原子替换（M3 RESEARCH F-11/S-24 锚点），claims 落盘未沿用同一纪律。
- **修法**：对**已存在**文件中的坏行 fail-closed（计数并计入 blocked）；`_write_claims` 改 tmp+`os.replace`。

### D-3（P2）gate 无 C4 结构/词表校验 → 畸形 claim 双平面一致放行

- **证据**：探针 **P-B1**——`{"claim_id","statement","status":"excellent"}` → `verdict=pass`，decision 记录 `status:"excellent", deliverable:true`；**P-B2**——仅 `{"claim_id"}` 单字段 → `pass`，`status:null`；**P-I**——同一畸形输入生产/审计输出完全一致（`excellent/True` 两平面相同）。
- **影响**：C4 schema 只在 M0 fixture 测试中运行，运行时 gate 从不校验。只要不触发 AR 规则，篡改/损坏造成的词表违规、字段缺失对两平面同等不可见——双平面只能捕获「影响谓词输出」的漂移，这是其设计内的共同盲区。
- **修法**：`run_stage20_gate` 入口做最小结构校验（`claim_id` 模式、14 必填键存在、`status ∈ STATUS_ORDER`），违规计入 `blocked`；不必在管线内引 jsonschema（可选）。

## 3. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | AR-06 cap 可解除 annotation 要求（探针 P-D：numerically_verified + 完整证据 + 非法 consensus → cap `latex_verified` → 免标注放行）。语义上与 A2-5「谓词消费终态 status」自洽，但 M5/G3 渲染侧须明示 **annotation 跟随封顶后状态** | 语义注记 |
| O-2 | `annotations.json` 在管线内**无生产者**（无任何 stage 写入）。当前 Stage 9 只产 speculation claim 故无实际影响；数值 claim 接线（M5/G3）前必须补供词路径 | 待办 |
| O-3 | 空 claims（无假设 run）→ gate 空转通过（total=0，探针 P-G）。预期行为，DESIGN 未明示 | 文档 |
| O-4 | `ClaimDecision.as_dict` 丢弃 findings 的 `message`/`cap`：`claim_gate.json` 不足以审计封顶原因 | 实现注记 |
| O-5 | session ts 单调性破坏：P-060 session ts（11-12T08:50）晚于 P-061（11-11T19:50），CONSOLE「最近会话」回退显示 P-060。继承自 P-060 的未来时间戳，非 M4 引入 | 数据卫生 |
| O-6 | 3.11 读数环境为临时 venv（`%TEMP%\arc-m4-py311`，本轮仍在、已复跑证实），未持久化；读数有效但引用环境不可复现 | 记录 |

## 4. 结论

- **M4 三条主线成立**：A2-4/A2-5/A2-6 谓词、Stage 9/20/23 接线、双平面漂移检测在 T-1..T-12 全部一手复现，文档计数零幻觉。
- **三项缺陷登记**：D-1（P1，正常流即可触发的陈旧 claim）、D-2（P1，完整性绕过）、D-3（P2，结构校验缺失）。三项均有机械修法、无需改设计。
- **处置建议**：**P-063 修复批**落实 D-1..D-3 与 O-3/O-4（作为 M5 开工前置或并行均可）；O-1/O-2 记为 M5/G3 输入；O-5/O-6 存档。M4 交付状态维持，D-1/D-2 修复前不建议将 PIVOT 场景或不可信 run 目录接入生产门禁。
