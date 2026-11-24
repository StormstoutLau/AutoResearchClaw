# P-162（G7 编排评测）异构独立复审报告

---
id: arc-g7-orchestration-review-20261125
type: review
version: 1.0
status: final
date: 2026-11-25
reviewer: GLM-5.3-Flash
implementer: DeepSeek-V4.1-Flash
target: PR #44（spec/p162-g7-orchestration，head 48f9ae9）
---

> **复审性质**：异构基座独立复审（SPEC_PROCESS RULE-5：GLM-5.3-Flash × DeepSeek-V4.1-Flash）+ RULE-6 单向权限（只标记，不修复）+ RULE-1 独立 pass（不采信 P-162 四文档自报结论，全部一手重验）。
> **取证纪律**：探针脚本全部落 `%TEMP%\arc-rv162\`，**零仓库变异**；每条结论绑定 E1-E4 证据等级（E1 可重放命令 / E2 运行时探针 / E3 静态读码@48f9ae9 / E4 盲区扫描）。

## 1. 结论（诚实结果列）

**P-162 的三条主线一手成立，计数零幻觉；登记 1 项 P2 忠实度缺陷 + 1 项 P3 登记口径缺陷 + 6 项观察。无 P1。**

| 主张 | 复审判定 | 证据 |
|---|---|---|
| 24 个编排用例全过 | ✅ 成立（两次复跑 6.64s / 6.18s） | E1 |
| 全矩阵 OB-1..OB-5 全 PASS | ✅ 成立（复跑逐 gate 对照） | E2 |
| 两次矩阵确定性（J-8） | ✅ 成立（rvA/rvB 全部 (adapter,task) total 逐字节相等） | E2 |
| digest 绑定（P≥82） | ✅ 成立（session finalize sha256 == 终稿四文档，4/4 OK） | E1 |
| 旧资产零改动（C-3） | ✅ 成立（`git diff fcb7b2b..48f9ae9` 涉 run_baseline/judge/researchclaw = 0 文件） | E1 |
| 三轮 CI 8/8 | ✅ 成立（45451347197 / 45452010362 / 45452615559 全 success；PR #44 OPEN/MERGEABLE） | E1 |
| judge 白名单/期望独立（J-1/J-2） | ✅ 成立（judge.py 零 adapters/workers/runner/submission import；subprocess/socket/requests/time.sleep 全仓 orchestration/ 0 命中） | E1/E3 |
| **真实预算溢出可观测（D-10/§5.4）** | ❌ **不成立** —— 见 D-1 | E2/E3 |
| PROGRESS 行读数与终稿一致 | ❌ 陈旧 —— 见 D-2 | E1 |

**发现 N 项声明（RULE-6c）**：缺陷 2 项（D-1 P2、D-2 P3），观察 6 项（O-1..O-6）。零发现降级重扫不适用（非零发现）；扫描范围见 §4.3。

## 2. T 表：一手复验（12 项全过）

| # | 复验项 | 读数 | 等级 |
|---|---|---|---|
| T-1 | 编排测试复跑 ×2 | `24 passed in 6.64s` / `24 passed in 6.18s`（声称 6.15s，同数） | E1 |
| T-2 | CLI 全矩阵复跑 | ob1..ob5 全 PASS；均值逐项一致（gold 10.4 / single 5.8 / over_split 2.0 / dummy 0.0） | E2 |
| T-3 | 两次全矩阵确定性 | rvA/rvB summary `runs` 全部 (adapter,task) total 相等 | E2 |
| T-4 | digest 绑定 | `declared==actual: True`；四文档 sha256 逐字节一致（CHECKLIST cd96e03…、DESIGN 94dfd8f…、IMPLEMENTATION 88a8ff2…、RESEARCH b7af59a…） | E1 |
| T-5 | 文件清单 vs 提交 | `82f4b77` = 38 files / +5241 / -12；工作树 clean | E1 |
| T-6 | pre-commit 全钩子 | 10/10 Passed（登记时复跑，见 §6） | E1 |
| T-7 | 三轮 CI + PR 态 | 三 run 全 success（2m22s / 2m17s / 2m22s）；PR #44 `state=OPEN mergeable=MERGEABLE head=48f9ae9` | E1 |
| T-8 | 禁用面扫描 | orchestration/*.py 无 `subprocess` / `socket` / `requests` / `urllib` / `time.sleep` / `os.system` | E1 |
| T-9 | 旧资产零改动 | `git diff --name-only fcb7b2b 48f9ae9` 过滤 run_baseline/scripts-judge/researchclaw = **0 文件** | E1 |
| T-10 | 任务语料 | 15 任务 4/4/4/3；manifest 0 缺失；conflict=A1..A4、invalid=D3/L4/A2；`validate_task` 全零问题 | E1 |
| T-11 | J-2 期望独立性 | judge.py 无 `from .adapters/.workers/.runner/.submission` import | E1 |
| T-12 | session 决策链 | 5 步 research→design→implement→verify→finalize；digest 为末次 finalize 携带 | E1 |

### 2.1 引用抽查（T1 回原文，3/3 命中）

| 引用 | 复验方式 | 字段比对 | 状态 |
|---|---|---|---|
| SwarmBench arXiv 2608.30661 | arXiv abs 页全读 | 标题/作者（Gao, Jin, Men, Liu, Zhao）/ EMNLP 2026 Findings 全一致 | 已验证（T1） |
| MAST arXiv 2503.13657 | arXiv abs 页全读 | 1600+ traces / 14 modes / 3 categories / κ=0.88 / v3 全一致（P-162 标注「venue 未回原文」诚实） | 已验证（T1） |
| MT-Bench arXiv 2306.05685 | arXiv abs 页全读 | NeurIPS 2023 D&B / >80% agreement / position-verbosity-self-enhancement biases 全一致 | 已验证（T1） |

### 2.2 F-1 精确复现（RESEARCH 关键承重断言）

- `run_baseline.py --framework ais_v2 --topic ML01 --dry-run` → exit 1，`FileNotFoundError: ...config/topics.yaml`（E2）——RESEARCH F-1 逐字成立。
- 补充：`--framework dummy` → argparse `invalid choice`（exit 2）——从 CLI 面再次证实 F-2（静态 ADAPTERS 三项，无插件入口）。

## 3. D 表：缺陷登记

### D-1（P2）真实预算溢出路径不落任何工件，OB-4 契约对非 fixture 不可达

- **现象**（探针 PR-1，E2）：gold adapter 在 D1 上以 `Budget(tokens=300)`（plan 计费 136 通过、worker 计费触顶 424>300）真实溢出 → `status="budget_exceeded"`，但 **workdir 为空（0 文件）**；judge 只能报 `missing_or_unparseable_artifacts`（缺 5 件），而非 D-10/§5.4 承诺的 `usage.exceeded=true、truncated=false` 读数。探针 PR-2（`max_workers=2 < 层宽 3` 的 worker 超限）同样零工件。
- **根因**（E3 @48f9ae9，`adapters.py` `ThreadedAdapter.start` 内 `target()`）：`except BudgetExceeded` 分支只更新 `handle.status` 与 `handle.error`，**不写任何部分工件**；而 `OverBudgetAdapter._execute`（PR-10 对照）是先 `self._write(...)` 再 `charge_tokens` 抛出——即五件套是 fixture **手工预写**的。
- **影响**：OB-4 gate 的 `usage.exceeded==true` 判据只对 fixture 成立；真实框架接入（field run）时预算溢出将表现为 missing_files，无法机械化判定「未静默截断」。属 ADD Phase 2 忠实度漏网（实现 ≠ DESIGN D-10 条文）。
- **不阻断本批验收的理由**：OB-4 的验收对象是 gate 判红能力本身（fixture 路径已证明），且本批边界明确为 dry-run 构念、无真实 LLM 计费路径。
- **修法建议**（供修复批承接，本复审不改动）：`target()` 的 `BudgetExceeded` 分支写最小工件（`usage.json`：`exceeded=true, truncated=false, status, charged_tokens` + `trace.jsonl`：已记录 span）后再置 status；或 runner 在 `status=="budget_exceeded"` 且工件缺失时合成 usage。附测试：真实溢出（非 fixture）→ judge `checks.ob4_budget_state_ok==true`。

### D-2（P3）PROGRESS P-162 行读数陈旧

- **现象**（E1）：P-162 行依据列写「CHECKLIST v1.1 = **44/45 + C-2 待 CI**」，而终稿（48f9ae9）为 **45/45**（C-2 两轮 CI ✅）。行随 CI 回填后未同步。
- **影响**：登记口径与终稿不一致，纯文档；不影响代码与门禁。
- **处置建议**：随本复审登记批一并订正该单元格为「CHECKLIST v1.1 = 45/45（两轮 CI 8/8）」（属 P-162 行的事实性回填，非重写）。

## 4. O 表：观察项（不构成缺陷，供后续批次参考）

| # | 观察 | 证据 | 建议 |
|---|---|---|---|
| O-1 | `ADAPTERS` 为普通 dict（可变绑定），J-6「无模块级可变注册表」靠约定维持 | E3 @48f9ae9 adapters.py 末段 | 用 `MappingProxyType` 包装或加只读注释 |
| O-2 | `SingleShotAdapter` 全程不调 `check_wall`；gold 仅层级间检查，单层执行中不可中断 → wall 预算为软上限（确定性 worker 秒级完成，当前无实际风险） | E3 | 真实框架接入前在 worker 循环内加硬检查 |
| O-3 | `_score_delegations` 的 ob3 只检查每个 subgoal 的 `items[0]`；重复委派上的虚假 `parallel_with` 不被检查（当前无 fixture 触发） | E3 | ob3 扫描改为全量 delegation |
| O-4 | `keep_with_flag` 聚合策略在 15 任务中零覆盖（全部 `exclude`）→ 该分支零测试 | E1（语料扫描） | 后续补 1 个 keep_with_flag 任务或 fixture |
| O-5 | `usage_from_trace.wall_seconds` 取全 span（含 orchestrator）min/max，成本口径含编排开销；`llm_calls=workers+2` 的 +2 为硬编码，dummy 自报 0 与反算 2 不一致（judge 不校验该字段，无行为影响） | E3 | 文档明示口径；或按 kind 过滤 |
| O-6 | 能力错配（探针 PR-3：worker 改为不存在 id）→ 委派 0 但总分 8（不门控）——与 DESIGN §5.1 一致（总分 0 仅 OB-3/aggregation），负向威慑弱于 OB-3 | E2 | 后续评估是否升级为门控（需 DESIGN 修订） |

### 4.3 盲区扫描范围声明（RULE-6c/E4）

- 扫描面：45 项 CHECKLIST 断言、12 测试×24 用例、7 适配器×15 任务的 gate 映射、judge 四维评分函数的分支覆盖（`_score_plan/_score_delegations/_score_aggregate/_score_cost`）、ThreadedAdapter 异常路径、runner gate 谓词、PROGRESS/CONSOLE/REPO_STATS 派生一致性。
- 结果：**发现 2 项**（D-1/D-2）+ 6 项观察；无凑数项。未覆盖：真实 LLM 计费路径（本批无）、`keep_with_flag` 行为（O-4）、A7 其余段。

## 5. 与 P-161 复审的口径对照

| 项 | P-161（soak 复审） | 本复审（P-162） |
|---|---|---|
| 异构对 | GLM-5.3-Flash × DeepSeek-V4.1-Flash | 同（互换角色） |
| 发现 | D-1/D-2（P2）+ D-3（P3）+ O-1..O-5 | D-1（P2）+ D-2（P3）+ O-1..O-6 |
| D-1..D-3 修复批状态 | **仍未承接**（P-162 未触碰 soak） | 维持未承接；本批新增 D-1 待修复批统一承接 |
| 单向权限 | 未改实现 | 未改实现（探针全部落 %TEMP%） |

## 6. 复审登记门禁（本批执行读数）

- dc（grandfather_gate）：`grandfathered=0 expired=0 violations=0`
- step-gate：`specwf-p163-g7-orchestration-review` 5/5
- verify-anchor：见登记后输出
- step-enforce：`mode=session pid=P-163`
- pre-commit：10/10 Passed

## 7. 处置建议汇总

1. **D-1（P2）** → 与 P-161 的 D-1..D-3 合并为一个「G7 复审修复批」（独立 P 编号），修复后补真实溢出回归测试。
2. **D-2（P3）** → 本登记批直接订正 P-162 行单元格（一行事实回填）。
3. **O-1..O-6** → 登记在案；不强制承接，任一涉及 OB 语义者（O-3/O-6）承接前须先修订 DESIGN。
4. **边界维持**：PR #44 保持 OPEN（用户裁决暂不合并）；本复审不改任何实现代码。
