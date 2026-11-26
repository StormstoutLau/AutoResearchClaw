# arc-stage10-intra-stage-checkpoint 实施异构复审报告（2026-11-26）

> **性质**：Layer-0 独立异构复审（T3，零代码/零门禁变更）。纪律同 P-020/P-023/P-030/P-062/P-160/P-161——**不采信**原文结论，全部以探针、读码、机检一手重验。
> **异构声明（RULE-5）**：本复审由 **GLM-5.3-Flash** 独立会话执行，实施文档由 DeepSeek-V4.1-Flash 产出——模型家族异构；reviewer 只标记问题、不改写实现（单向权限）。
> **对象**：B-33 M1 实施（P-193），含四份 spec 文档、三个测试文件、三处代码改动。工作树状态：干净（main @ `56b3dde` + P-192/P-193 未提交改动）。
> **探针**：`%TEMP%\p195_review_probe.py`、`%TEMP%\p195_review_probe2.py`（全部临时目录，零仓库变异）。

---

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | `_write_stage_start` 保留 `last_completed_stage` 并写 `in_progress_stage/name/at` | 读码 `runner.py` L224-252 | ✅ |
| T-2 | `read_checkpoint` 优先返回 `in_progress_stage`，类型检查 `isinstance(int) and not bool` | 读码 `runner.py` L396-434 | ✅ |
| T-3 | 阶段循环在 `stage.started` 后调用 `_write_stage_start`（异常不中断主流程） | 读码 `runner.py` L835-841 | ✅ |
| T-4 | `_write_checkpoint` 全量重写隐式清除 `in_progress_stage` | 读码 `runner.py` L192-221 | ✅ |
| T-5 | `CodeAgent._phase1_blueprint` 标记 `variant=first/retry` 并立即原子落盘 `architecture_spec.yaml` | 读码 `code_agent.py` L295-317 | ✅ |
| T-6 | `_persist_blueprint` 调用 `append_step` 记录 `blueprint:first/retry`，YAML 解析失败也落盘 | 读码 `code_agent.py` L329-365 | ✅ |
| T-7 | 重建 `RenderedPrompt` 时补 `version=`（复审 D-4 指出的丢失） | 读码 `code_agent.py` L316 | ✅ |
| T-8 | `_blueprint_inputs_digest` 仅含 `topic/metric/exp_plan`（无蓝图自身） | 读码 `code_agent.py` L46-56 | ✅ |
| T-9 | `step_journal.py` 新增：`hash_text/code_version/step_key/load_steps/append_step/last_done/should_skip` | 读码 `step_journal.py` 全文 | ✅ |
| T-10 | `append_step` 使用 `exclusive_lock` + `flush` + `fsync`，末尾坏行容忍、中间抛错 | 读码 `step_journal.py` L105-146 | ✅ |
| T-11 | `should_skip` 纯函数：逐项比对 inputs_digest/code_version/prompt_version/outputs sha256 | 读码 `step_journal.py` L163-198 | ✅ |
| T-12 | `code_version` 算法：包版本 + 双文件 sha256 前 8 位（D-8 单一算法） | 读码 `step_journal.py` L46-64 | ✅ |
| T-13 | 新增 33 例单测全部通过（step_journal 20 + checkpoint_in_progress 7 + blueprint_persistence 6） | 机检 `pytest -q` | ✅ |
| T-14 | 回归测试全绿：code_agent/entrypoint/truncation 63、runner/checkpoint 72 | 机检 `pytest -q` | ✅ |
| T-15 | `step-gate` 5/5、`verify-anchor` 12/12、`step_enforce` digest_bound=2、grandfather 0 违规、pre-commit 10/10 | 门禁实跑 | ✅ |
| T-16 | `rebuild_checkpoint` 从事件重建时**不**恢复 `in_progress_stage` | 读码 `event_log.py` L538-558 | ✅（符合 DESIGN §5 边界声明） |
| T-17 | `in_progress_stage` 类型检查 `isinstance(int) and not isinstance(bool)` 防 bool-as-int | 读码 `runner.py` L419 | ✅ |

---

## 2. 缺陷（D 表）

### D-1（P3）文档口径不一致：`step_id` 三段式表述与实现不符

- **现状**：DESIGN §1 D-4 与 §2 接口表述 `step_id` 为三段式 `<phase>:<subject>:<variant>`；实现中 `step_id="blueprint"`、`variant="first/retry"` 两字段分离，`step_key` 拼接为 `blueprint:first`。
- **影响**：仅为文档口径差异，实现逻辑自洽（`step_id` + `variant` 复合键），无行为错误。
- **建议**：统一文档口径，改为「复合键 `(step_id, variant)`」或在接口表中说明分离设计。

### D-2（P3）IMPLEMENTATION 表述笔误：`RenderedPrompt` 补 `version=` 归因错误

- **现状**：IMPLEMENTATION §1 第 3 行「补 `version=`（D-4）」，但 DESIGN D-4 是关于 `step_id` 三段式，与 prompt version 无关。
- **影响**：仅文档归因错误，实现正确（`getattr(sp, "version", "")` 传给 `prompt_version`）。
- **建议**：改为「补 `version=`（prompt_version 字段）」或引用正确决策编号。

### D-3（P3）测试注释误导：`test_in_progress_survives_later_completion`

- **现状**：测试名与注释称「较新完成阶段不清除较旧 in-progress」，但测试实际写的是「较旧完成 + 较新 in_progress」，未写较新完成。
- **影响**：测试逻辑正确（验证 in_progress 优先），但注释可能误导阅读者。
- **建议**：改名为 `test_in_progress_wins_over_older_completed`，注释改为「in_progress 优先于更早的完成阶段」。

### D-4（P2）`rebuild_checkpoint` 恢复路径丢失 `in_progress_stage` 导致 `--resume` 可能跳过中断阶段

- **现状**：`event_log.py:rebuild_checkpoint` 仅从 `stage.completed` 事件重建，不包含 `stage.started`，因此恢复的 checkpoint 不含 `in_progress_stage`。若 checkpoint 损坏且恰好处于 Stage 10 进行中，`--resume` 会退回阶段级语义，落在 Stage 12 而非 Stage 10。
- **影响**：checkpoint 损坏这一低概率场景下，B-33 L0 失效；但 DESIGN §5 已声明「语义退回阶段级（可接受）」。
- **建议**：在 `rebuild_checkpoint` 中补充扫描 `stage.started` 且无对应 `stage.completed` 的事件，回填 `in_progress_stage`。或在边界声明中明确标注为已知局限。

### D-5（P3）`step_journal.py` 中 `code_version` 读取路径依赖文件相对位置，打包/安装后可能失效

- **现状**：`code_version()` 用 `Path(__file__).resolve().parent` 定位 `code_agent.py` 与 `_code_generation.py`。若作为 wheel 安装或文件结构变动，相对路径可能失效。
- **影响**：开发环境正常，分发场景潜在风险。
- **建议**：改用 `importlib.resources` 读取包内文件，或在 setup.py 构建时注入版本哈希。

---

## 3. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | `should_skip` 暂无主线调用点（L2 留 M2），但已具备 8 条完备单测 | 实施注记 |
| O-2 | `append_step` 的 `model` 字段默认为空串，未在实现中填充（可选增强） | 实施注记 |
| O-3 | `prompt_version` 取自 `RenderedPrompt.version`（sha256），含 system+user_template+model_role+bank_version，覆盖完整 | 确认 |
| O-4 | `_blueprint_inputs_digest` 不含蓝图自身摘要（蓝图是输出而非输入），设计合理 | 确认 |
| O-5 | `STEP_LOCK_NAME = ".steps.lock"` 为 stage 级锁，与 run 级 `stage_events.lock` 分离，避免争用 | 确认 |
| O-6 | `in_progress_stage` 写入在 `stage.started` 后，若阶段极快完成可能与 `_write_checkpoint` 竞争（极低概率，原子写兜底） | 确认 |

---

## 4. 结论与待办

### 通过项（✅）

1. **核心功能完备**：L0（`--resume` 语义修正）、N-1（蓝图提早落盘）、L1（步骤账本 + `should_skip`）三大件全部落地，且通过 33 例新增单测 + 135 例回归测试。
2. **设计落地一致**：spec 四文档（RESEARCH/DESIGN/IMPLEMENTATION/CHECKLIST）与代码实现一致，验收清单 20/21 项本地通过，仅 C-21 待现场部署。
3. **边界诚实声明**：L2/L3 留 M2/M3、checkpoint 损坏退回阶段级、账本不接入主线等均在文档中明确登记。
4. **门禁全绿**：step-gate/verify-anchor/step_enforce/grandfather/pre-commit 全部通过。

### 待办（需原作者或后续立项处理）

| # | 项 | 责任 | 备注 |
|---|---|---|---|
| 1 | 修正 DESIGN 与 IMPLEMENTATION 中的 `step_id` 口径与归因笔误 | 文档定稿前 | D-1、D-2 |
| 2 | 修正 `test_in_progress_survives_later_completion` 注释与命名 | 文档定稿前 | D-3 |
| 3 | `rebuild_checkpoint` 补充 `stage.started` 扫描回填 `in_progress_stage` | M1 后续或 M2 | D-4（已知局限，DESIGN §5 已声明） |
| 4 | `code_version` 改用 `importlib.resources` 兼容打包分发 | M2 或独立任务 | D-5 |
| 5 | B 站部署验证 C-21（`--resume` 落在 Stage 10） | 部署窗口 | C-21 |

---

## 5. 复审纪律确认

- ✅ 全程**不改写**原文档/代码（零变异）
- ✅ 所有「✅」结论均来自探针/读码/机检，非采信原文
- ✅ 缺陷定级遵循 P1=阻塞、P2=需修、P3=可观
- ✅ 异构模型：GLM-5.3-Flash（本会话） vs DeepSeek-V4.1-Flash（原文产出会话）

---

**复审结果**：实施**通过**，可作为 B-33 M1 交付基线。上述 4 缺陷中 D-1/D-2/D-3 属文档口径，建议合并提交前修正；D-4 局限已在 DESIGN 声明，建议后续迭代改进；D-5 为分发兼容性，建议列入技术债清单。核心结论（L0/L1/N-1 三件套落地、测试全绿、门禁全过、边界诚实）经一手复验全部成立。

---

## 6. 核实与修正结果（2026-11-26，实施方回填）

> 逐条核实 §2–§3，核实方式为读码 + 机检，不采信本报告原文。修正已写入 spec 四文档 v1.1 与代码。

| 意见 | 核实 | 处理 |
|---|---|---|
| **D-1** `step_id` 三段式口径不一致 | **成立（文档）**：DESIGN D-4 写「三段式 `<phase>:<subject>:<variant>`」，实现是 `step_id` + `variant` 两字段、由 `last_done(step_id, variant)` 检索 | DESIGN D-4 改为「复合键 `(step_id, variant)`」，并在接口表注明 `step_key()` 仅用于日志展示 |
| **D-2** IMPLEMENTATION 归因笔误 | **成立**：`version=` 属 `prompt_version` 字段，与 D-4 无关 | IMPLEMENTATION 改为「补 `version=`（即 `prompt_version` 字段）」 |
| **D-3** 测试命名/注释误导 | **成立** | 改名 `test_in_progress_wins_over_older_completed`；新增 `test_in_progress_cleared_for_later_stage` |
| **D-4** 事件重建丢 `in_progress_stage` | **成立且已修**（原为 P2 局限）：新增 `_last_unfinished_stage`，`rebuild_checkpoint` 回填 `in_progress_stage/name/at`；新增 5 例（含「checkpoint 损坏 + 在飞阶段 → 该阶段」端到端） | DESIGN 增 D-9；DESIGN §5 边界改为「仅剩无任何 `stage.completed` 时不可恢复」；CHECKLIST C-19/C-20 |
| **D-5** `code_version` 相对路径依赖 | **成立且已修**：新增 `_read_package_bytes`，优先 `importlib.resources`、`Path(__file__)` 兜底；新增 3 例（包读取、字节变化、文件缺失兜底） | DESIGN D-8 补充「经 importlib.resources 读取」；CHECKLIST C-21 |
| **O-1..O-6** | 均为实施注记/确认项，无需改动 | 不改 |

### 6.1 修正后状态

| 原待办 | 状态 |
|---|---|
| 1 DESIGN/IMPLEMENTATION 口径与归因 | **已闭合** |
| 2 测试注释与命名 | **已闭合** |
| 3 `rebuild_checkpoint` 回填 `in_progress` | **已闭合**（代码 + 5 例） |
| 4 `code_version` 打包兼容 | **已闭合**（importlib.resources + 3 例） |
| 5 B 站部署验证 C-25 | **仍待现场**（未部署） |

### 6.2 修正后测试读数

| 组 | 结果 |
|---|---|
| `test_event_log + test_step_journal + test_checkpoint_in_progress + test_blueprint_persistence` | **55 passed**（18 + 22 + 9 + 6） |
| `test_code_agent + test_entrypoint_contract + test_codegen_truncation` | 63 passed |
| `test_rc_runner + test_runner_events + test_checkpoint_atomic + test_rc_checkpoint` | 72 passed |