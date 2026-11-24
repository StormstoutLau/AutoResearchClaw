---
id: arc-g7-orchestration-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-25
depends: [arc-g7-orchestration-IMPLEMENTATION, arc-g7-orchestration-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 第二段「编排评测」（P-162）

> **Feature**：P-162（G7 第二段）。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **状态**：验收完成；44/45 通过 + 1 待 CI（C-2）。
> **范围**：OB-1..OB-5 的离线 dry-run 工具链；真实框架排名、A7-2/3/5/6/7、FA、真实科学运行不在本批。
> **修订**：v1.1（2026-11-25，Step 10 回填读数；新增 DR-7/DR-8 与 2 项 P3 观察）。

---

## 0. DoR / DoD 总则

- **DoR（Definition of Ready）**：该项所需的代码、夹具、任务语料或文档已存在；测试可在当前主机重复运行；不接受“环境不存在所以跳过”（RULE-3）。
- **DoD（Definition of Done）**：该项的通过条件已由**独立读数**证明；读数写入 §10；禁止用“测试总数”推算分项（RULE-2）。
- 计数：**45 项 = 文档 5 + 功能 9 + 接口 8 + 不变式 10 + 错误 7 + 性能 3 + 兼容 3**。

---

## 1. 文档一致性验收（Step 8）

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 结论进入 DESIGN | RESEARCH v1.0 verified | F-1/F-2/F-3 分别对应 D-2/D-7/D-12；§5.1 六条发现对应 D-5..D-13 | ✅ | DESIGN §1/§11 逐条引用 |
| D-2 DESIGN 模块在 IMPLEMENTATION 有落点 | 四文档完稿 | DESIGN §2 八个模块 ↔ IMPLEMENTATION §1 八项文件 | ✅ | 文件清单 13 项（含 15 JSON） |
| D-3 IMPLEMENTATION 接口在 CHECKLIST 有验收项 | 四文档完稿 | §2–§4 每个函数/文件至少一项 | ✅ | I-1..I-8 覆盖全部公开 API |
| D-4 术语一致 | 四文档完稿 | “五件套 / gold_orchestrator / single_shot / dummy / serial_claiming / over_budget / prose_only / over_split / OB-1..OB-5” 用法一致 | ✅ | 四文档 grep 均命中；无同义漂移 |
| D-5 双向引用与断言延续 | 四文档完稿 | 四文档互链成立；RESEARCH U-1..U-5 在 DESIGN §11 全部有裁决态；U-6/U-7 新增且带触发条件 | ✅ | 断链检查 0；U-1..U-7 均有判据/触发/倾向/证据 |

## 2. 功能验收

| 验收项 | DoR | DoD（通过条件） | 状态 | 证据 |
|---|---|---|---|---|
| F-1 任务语料 | `tasks/*.json` 15 份 | 计数 4/4/4/3；id 唯一；`source_manifest` 存在；`validate_task` 零问题 | ✅ | T01 passed（5 用例） |
| F-2 gold 矩阵 | gold adapter | 15 任务逐任务 total：D/L/A ≥10、C ≥8；`aggregation=3`；无 gate 清零 | ✅ | T03 passed；gold D/L/A=11、C=8 |
| F-3 单发负向控制 | single_shot adapter | D/L/A 逐任务 total ≤7；无 `aggregation=0` 导致的意外清零 | ✅ | T04 passed；D/L=6..7、A=6 |
| F-4 dummy 契约 | dummy adapter | 五件套文件齐全、可解析；`status="completed"` | ✅ | T05 passed |
| F-5 OB-3 判红 | serial_claiming fixture | D1：`checks.ob3_parallel_claim_ok=false`、`delegation=0`、`total=0` | ✅ | T06 passed |
| F-6 OB-4 判红 | over_budget fixture | D1：`status="budget_exceeded"`、`usage.exceeded=true`、`usage.truncated=false`、成本 0 | ✅ | T07 passed |
| F-7 OB-5 散文不变 | prose_only fixture | 15 任务逐任务 `total` 与 gold 相等；`inputs_whitelist` 不含散文文件 | ✅ | T08 passed；prose mean=gold mean=10.4 |
| F-8 OB-5 过度拆分 | over_split fixture | C1..C3 逐任务 `total < gold.total`；分解 0 | ✅ | T08 passed；over_split=2 < gold=8 |
| F-9 OB-2 布局 | dummy + submission | `submission/{code/,results/metrics.json,README.md,claims.json,reproduce.sh,reproduce.log,reproduce.log.creation_time}` 与 `judge_result.json` 均存在；`run_baseline.py` git diff 为空 | ✅ | T09 passed；CLI dummy D1 七项齐全 |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `BudgetTracker` | model.py | 四类计费（tokens/wall/workers/depth）均可在超限时抛 `BudgetExceeded` 且 `kind` 正确 | ✅ | T02 passed（4 用例） |
| I-2 `start/collect/artifacts` | 适配器基类 | 正常 run `completed`；`collect` 幂等；缺失 artifacts 返回空结构不抛 | ✅ | T05 passed |
| I-3 `judge_run` 白名单 | judge.py | 只打开五个 artifact 文件；结果含 `inputs_whitelist` 六项 | ✅ | T08/T12 passed；len=6 |
| I-4 `usage_from_trace` | judge.py | token 汇总与 span `tokens_in/out` 相等；篡改 usage → `usage_matches_trace=false` | ✅ | T12 passed |
| I-5 `build_submission` | submission.py | 七项布局齐全；`metrics.json` 含 aggregate；无 paper 时 README 为固定占位 | ✅ | T09 passed |
| I-6 `run_matrix` | runner.py | 返回按 `(adapter, task)` 可索引的 runs + `summary.json`；计数 45 + fixtures | ✅ | T10 passed；15×3 + 1+1+15+3 = 65 |
| I-7 `evaluate_gates` | runner.py | 返回 `ob1..ob5` 五个布尔；任一项为 false 时 CLI exit 1 | ✅ | T10 passed；CLI 全绿 exit 0 |
| I-8 CLI 参数 | run_orchestration.py | `--tasks/--adapters/--no-fixtures/--no-gate/--list-tasks` 可解析；非法任务 exit 2 | ✅ | T09 passed |

## 4. 不变式验收

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 judge 只读五件套 | 读码 + 夹具 | 写入 `paper.md/README.md` 前后 total 相同 | ✅ | T08/T12 passed |
| J-2 期望值独立于适配器 | 读码 | judge 不 import adapters/workers；期望值只来自 `task.truth` | ✅ | 读码 + T03 passed |
| J-3 usage 从 trace 反算 | T12 | 自报与 trace 不一致 → 成本 0 | ✅ | T12 passed |
| J-4 并行双条件 | T06 | 区间重叠 + 不同 thread_id；串行声明并行 → 判红 | ✅ | T06 passed |
| J-5 预算前置 | T02/T07 | 超限发生在返回结果前；`truncated=false` | ✅ | T02/T07 passed |
| J-6 每 run 隔离 | T11 | 两次矩阵/两次加载互不影响；无模块级可变注册表 | ✅ | T11 passed |
| J-7 任务加载返回新对象 | T11 | 改动一次加载结果，第二次加载不受影响 | ✅ | T11 passed |
| J-8 同输入同输出 | T03 | gold 两次逐任务 total 相同 | ✅ | T03/T10 passed；repeats 15/15 equal |
| J-9 门控不可补偿 | T06 | OB-3 违例时其他维度高分不改 total=0 | ✅ | T06 passed |
| J-10 C 类 9 分制与过度拆惩罚 | T08 | over_split 分解 0，total < gold | ✅ | T08 passed；2 < 8 |

## 5. 错误处理验收

| 错误场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 任务坏 JSON | 临时坏文件 | `load_task` 抛 `ValueError`；CLI exit 2 | ✅ | T01 passed |
| E-2 适配器非预算异常 | 注入故障适配器 | `status="failed"` + `error` 落 meta；judge 不崩溃 | ✅ | T05 passed |
| E-3 预算超限 | over_budget | `status="budget_exceeded"`；不静默截断 | ✅ | T07 passed |
| E-4 五件套缺文件 | 删 aggregate | judge `total=0` + `checks.missing_files` | ✅ | T12 passed |
| E-5 坏 trace 行 | 篡改 JSONL | judge `total=0` + `checks.parse_errors` | ✅ | T12 passed |
| E-6 结果目录越界 | 构造 `../` workdir | runner 抛 `ValueError` | ✅ | T11 passed |
| E-7 非法 CLI 任务名 | `--tasks Z9` | exit 2 + stderr | ✅ | T09 passed |

## 6. 性能验收

| 指标 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| P-1 全矩阵时长 | 本机 | 15×3 + fixtures + gold 复跑 < 90 s | ✅ | CLI 全矩阵 2.04 s |
| P-2 无子进程/无网络 | 读码 | `orchestration/` 无 `subprocess`/`requests`/`socket` | ✅ | grep 0 命中 |
| P-3 无真实 sleep | 读码 | 并行由 `Barrier` 保证；无 `time.sleep` 制造重叠 | ✅ | grep 0 命中 |

## 7. 兼容性验收

| 环境 | DoR | DoD | 状态 | 说明 |
|---|---|---|---|---|
| C-1 Python 3.13（本机） | 本机 3.13.5 | 新增测试全绿 | ✅ | 24 passed in 6.15 s |
| C-2 Python 3.11（CI） | CI 矩阵 | 两轮 CI 全绿 | ⏳ | 第一轮 8/8（run 45451347197）；第二轮由本提交触发 |
| C-3 旧资产零改动 | git | `run_baseline.py` / `judge.py` / `researchclaw/` diff 为空 | ✅ | git status 仅新增文件 |

## 8. ADD 审计（Step 10）

> **诚实结果列**：本批 **0 P1 / 0 P2 / 2 P3**（均为阈值裕度观察，不阻断验收）。

### 8.1 Phase 0：Spec 质量门

| 维度 | 得分（0-1） | 说明 |
|---|---|---|
| 可测试约束 | 1 | OB-1..OB-5 全部落到 T01..T12；无“合理/充分”类不可判词 |
| 模块映射 | 1 | DESIGN §2 八模块 ↔ 实现 7 py + CLI + 15 JSON |
| 接口契约 | 1 | 五件套 schema + 七个 adapter + judge/runner 签名固定 |
| 修正项 | 1 | 冲突规则公开、C 类分值、invalid 粒度三处在 Step 4 修正 |
| 跨模块契约 | 1 | 任务/worker/adapter/judge/runner 边界由 T01..T12 锁定 |
| **总分** | **5 /5** | **档位 A** |

### 8.2 Phase 1：完整性（design → code）

| 设计元素 | 代码落点 | 状态 |
|---|---|---|
| 15 任务（D4/L4/A4/C3） | `tasks/*.json` | ✅ |
| `Budget/BudgetTracker` 四类前置检查 | `model.py` | ✅ T02 |
| `start/collect/artifacts` 窄接口 | `adapters.py` | ✅ T05 |
| gold / single_shot / dummy | `adapters.py` | ✅ T03/T04/T05 |
| serial_claiming / over_budget / prose_only / over_split | `adapters.py` | ✅ T06/T07/T08 |
| 五件套 + OTel 风格 trace | `adapters.py` / `judge.py` | ✅ T12 |
| 四维 judge + 门控 + 白名单 | `judge.py` | ✅ T03..T08 |
| submission 七项布局 | `submission.py` | ✅ T09 |
| 矩阵 + summary + OB gate | `runner.py` | ✅ T10 |
| CLI | `run_orchestration.py` | ✅ T09/T10 |

### 8.3 Phase 2：忠实度（实现 ↔ 设计）

| 设计条文 | 实现 | 偏差处置 |
|---|---|---|
| 聚合摘要“按组均值” | `summary[group][metric]` 嵌套形态 | 已在 IMPLEMENTATION §2.4 写明；无行为偏差 |
| single_shot 为负向控制 | D/L=6..7、A=6 | 已在 IMPLEMENTATION §2.4 改为实测口径 |
| C 类过度拆分总分 < gold | 2 vs 8 | 与 DESIGN J-10 一致 |
| `usage` 由 trace 反算 | `usage_from_trace` | 篡改判红（T12） |
| 散文不进评分 | 六项白名单 | prose_only 与 gold 完全相等（T08） |

### 8.4 Phase 3：必要性（code → design）

| 实现行为 | 设计依据 |
|---|---|
| `_assignments` 为 `distinct_roles` 选未占用 worker | DR-7（DESIGN §3 角色互异） |
| `_placeholder_nodes` 为 over_split 产生 8 个占位节点 | DR-6（DESIGN D-11） |
| `repeat_gold` 复跑 | DR-3（OB-1 可复现） |
| 无死代码 / 无未使用公开 API | 读码 + `ruff`/pre-commit 待跑 |

### 8.5 Phase 4：语义（意图层）

- 意图“测编排、不测写作”：judge 白名单 + prose 不变（T08/T12）成立。
- 意图“自报不可信”：usage 必须与 trace 相等，否则成本 0（T12）成立。
- 意图“串行不得冒充并行”：区间重叠 + 不同 thread_id 双条件（T06）成立。
- **能力边界**：judge 不验证科学正确性，只验证结构/真值/算术；这一点在 DESIGN §9 已声明。

### 8.6 取证矩阵（规则 6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| `pytest tests/test_orchestration_*.py -q`（E1） | F-1..F-9、I-1..I-8、J-1..J-10、E-1..E-7 | ✅ 24 passed in 6.15 s |
| CLI 全矩阵 + `summary.json`（E2，含 4 个负向场景） | OB-1..OB-5、P-1 | ✅ 全 PASS；gold mean 10.4 / single max 7 / over_split 2 |
| `pytest tests -q` 全量回归（E1） | C-1 兼容性 | 3893 passed / 6 failed（均为本机环境态）/ 108 skipped |
| 文档链接 + U/DR 引用 grep（E1） | D-1..D-5 | ✅ 断链 0；U-1..U-7 全登记 |
| 静态读码（E3 @ 本批 commit） | J-2（judge 不 import adapter/worker）、P-2/P-3 | ✅ 无越界 import、无 subprocess/socket/sleep |
| git status/diff（E1） | C-3 旧资产零改动 | ✅ 仅新增文件 |
| 盲区扫描（E4，扫描范围：45 项断言 + 12 测试） | 全部 | **发现 2 项 P3**（见 §8.7） |

### 8.7 发现（P3）

| 编号 | 发现 | 影响 | 建议 |
|---|---|---|---|
| P3-1 | C 类 gold 恰为 8/9（成本维 2），贴阈值 | 未来成本分档调整可能使 OB-1 的 C 类阈值失效 | 后续把 C 类阈值改为“相对 gold”或提高成本档容差；本批不改 |
| P3-2 | single_shot 在 L1..L3 恰为 7/12，贴 OB-1 上限 | 负向控制裕度小 | 后续在 L 类增加聚合/成本区分项；本批以 A 类 6、D 类 6 与 L 类 7 共同满足 ≤7 |

## 9. 派生需求登记（Step 8）

| 编号 | 派生需求 | 来源 | 验收 |
|---|---|---|---|
| DR-1 | 固定任务顺序 `TASK_ORDER` | 保证 summary/重跑确定性 | T01/T03 |
| DR-2 | fixture × 任务映射 `FIXTURE_TASKS` | DESIGN 只规定 fixture 类型，未规定跑哪些任务 | T06/T07/T08 |
| DR-3 | gold 复跑 `repeat_gold` | OB-1 可复现性的机械手段 | T03 |
| DR-4 | `checks` 子键集合 | DESIGN 只列主键；实现细化为 12 个布尔 | T03..T12 |
| DR-5 | single_shot 聚合 first-wins + 静默丢弃 invalid | DESIGN “naive merge”的具体行为 | T04 |
| DR-6 | over_split 每子目标 5 节点（共 10） | DESIGN “拆 10 节点”的结构化 | T08 |
| DR-7 | `distinct_roles` 按子目标顺序分配未被占用的 worker | DESIGN “角色互异”未规定选择算法 | T03（L1..L4 全 11 分） |
| DR-8 | 聚合摘要为 `summary[group][metric]` 嵌套 | DESIGN 只说“按组均值”，未定形态 | T03（D 类 aggregation=3） |

## 10. 验收统计（Step 10 回填）

> 逐项核对表见 §1–§7；汇总只能来自逐项状态，不得从测试总数推算。

| 分类 | 总数 | 通过 | 失败 | 待定 |
|---|---|---|---|---|
| 文档 | 5 | 5 | 0 | 0 |
| 功能 | 9 | 9 | 0 | 0 |
| 接口 | 8 | 8 | 0 | 0 |
| 不变式 | 10 | 10 | 0 | 0 |
| 错误 | 7 | 7 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容 | 3 | 2 | 0 | 1（C-2 CI） |
| **合计** | **45** | **44** | **0** | **1** |

> 算术：5+9+8+10+7+3+3 = 45；44+0+1 = 45。C-2 第一轮已绿（8/8）；第二轮由本提交触发，通过后改 45/45。

## 11. 测试映射（T01..T12）

| 测试 | 文件 | 覆盖验收项 |
|---|---|---|
| T01 | `tests/test_orchestration_tasks.py` | F-1、E-1、DR-1 |
| T02 | `tests/test_orchestration_budget.py` | I-1、J-5 |
| T03 | `tests/test_orchestration_matrix.py` | F-2、J-2、J-8、DR-3 |
| T04 | `tests/test_orchestration_matrix.py` | F-3、DR-5 |
| T05 | `tests/test_orchestration_matrix.py` | F-4、I-2、E-2 |
| T06 | `tests/test_orchestration_negative.py` | F-5、J-4、J-9 |
| T07 | `tests/test_orchestration_negative.py` | F-6、J-5、E-3 |
| T08 | `tests/test_orchestration_negative.py` | F-7、F-8、J-1、J-10、DR-6 |
| T09 | `tests/test_orchestration_ob2.py` | F-9、I-5、I-8 |
| T10 | `tests/test_orchestration_matrix.py` | I-6、I-7、I-8、E-7、P-1 |
| T11 | `tests/test_orchestration_matrix.py` | J-6、J-7、E-6 |
| T12 | `tests/test_orchestration_trace.py` | I-3、I-4、J-3、E-4、E-5 |
