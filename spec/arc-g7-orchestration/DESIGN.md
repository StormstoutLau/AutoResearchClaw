---
id: arc-g7-orchestration-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-orchestration-RESEARCH, orchestration-benchmark-plan]
upstream: arc-master-roadmap
---

# 设计：G7 第二段「编排评测」（P-162）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 `experiments/arc_bench/orchestration/`（任务语料 15 份 + 模型/适配器/judge/runner/submission）与 `scripts/run_orchestration.py`；不修改 `run_baseline.py` / `judge.py` / 现有 topic 注册表。
> **本段定位**：OB-1..OB-5 的**离线 dry-run 工具链**；不包含真实框架排名、A7-2/A7-3/A7-5/A7-6/A7-7、FA、真实科学重跑。
> **与 P-161 的关系**：P-161 登记的 D-1..D-3（soak retention 逃生舱 / POSIX 进程树 / 死代码）不在本批；本批不触碰 `researchclaw/soak/`。
> **OB-2 口径（重要）**：OB-2 字面要求“dummy 经 `run_baseline.py`”，但该脚本当前在 `_load_topics()` 即抛 `FileNotFoundError`（RESEARCH F-1），且 `ADAPTERS`/judge 均静态硬编码（F-2/F-3），**字面路径不可达**。本设计按 U-2 裁决 A 走“baseline-compatible 入口”：新入口产出与旧基线一致的 `submission/` + `judge_result.json`，旧脚本零改动；OB-2 的“不修改现有 runner”负向约束以 `git diff` 证明。**本段不宣称字面 OB-2 已满足**，roadmap 措辞修订登记为 U-6。

---

## 1. 决策

| 编号 | 决策 | 被拒绝的替代方案 | 拒绝理由 / 代价 |
|---|---|---|---|
| D-1 | 本段只做离线 dry-run 评测：15 任务 ×（gold / single_shot / dummy）+ 4 个负向 fixture；不接真实框架 | 接 AIS v2 / AgentLab / AIDE | 三者均不产编排五件套，需改各自的 adapter；真实 LLM 成本与不可复现性会把 OB-1 变成“网络稳定度测试”。代价：本段分数**不代表**真实框架排名 |
| D-2 | OB-2 用 `run_orchestration.py` 新入口；旧 `run_baseline.py` **零改动** | 修 `_load_topics`/`ADAPTERS`/judge 硬编码并在旧入口注册 dummy | 旧 runner 的 topic 加载与 judge 语义是科学 rubric 路径，插入编排分支会把两套评分混在一个脚本；且 OB-2 负向条款明确“需改现有 runner 即失败”。代价：OB-2 字面路径仍未通，须登记 U-6 |
| D-3 | 15 任务冻结为 `orchestration/tasks/*.json`，含题面、子目标、隐藏真值、陷阱、预算；运行时**不读** manifest | 运行时从 5 域 manifest 动态派生 | 动态派生会让任务随 manifest 漂移，读数不可复现；且 ARC manifest 是科学实验定义，不是编排题面。代价：任务与 manifest 的对应关系靠 `source_manifest` 字段留痕 |
| D-4 | 适配器用**进程内线程**实现 `start/collect/artifacts` 窄接口；`start` 起后台线程，`collect` 带超时 join | 每个 adaptor 起子进程 / 直接同步返回 | 子进程在 Windows + pytest 下引入句柄/清理问题，且本段不需要进程隔离；纯同步则无法验证 `timeout` 分支。代价：超时只能中断 join，不能硬杀线程（文档声明） |
| D-5 | `trace.jsonl` 采用 OTel 风格最小字段：`trace_id/span_id/parent_id/kind/start/end/pid/thread_id/attributes`；并行由评测侧按**区间重叠 + 声明对照**判定 | 只看 `delegations.parallel=true` 自报 | 自报可伪造（CrewAI 顺序执行、AutoGen group chat 默认顺序，RESEARCH C-2/C-3）。代价：评测侧需实现区间扫描 |
| D-6 | worker 用**确定性模拟器**：读任务真值行，按 DAG 层级用 `threading.Barrier` 保证同层真实重叠；token 按行数固定计费 | 真实 LLM worker / 纯 `sleep` 制造重叠 | LLM 不可复现且超预算；`sleep` 只造时间不造数据。代价：模拟器不能反映真实工具延迟分布 |
| D-7 | judge **确定性优先**：四维 0–3，聚合正确性=0 或 OB-3 违例 → 总分 0；LLM residual 只留注入钩子，默认关闭 | 默认 LLM judge / 直接复用 `judge.py` | `judge.py` 第二轮读 Writeup/README（RESEARCH F-3），OB-5 必红；LLM 单独承重有 MT-Bench/G-Eval 已知偏差。代价：语义覆盖判断较弱，残留到 U-7 |
| D-8 | 聚合判定用任务内**独立期望值**（`truth.expected_rows` / `truth.expected_conflicts`），不调用适配器的聚合代码复算 | 从 worker 输出现算期望值 | 同源复算会重演 M7「对账抓不住两实现同错」。代价：15 份任务需作者预置期望聚合 |
| D-9 | 成本维度以**同一批次 gold 实测 usage** 为参考，比率 ≤0.8/1.0/1.5 分档；usage 必须与 trace 汇总一致 | 用固定 token 常量 / 采信 `usage.json` 自报 | 固定常量会把任务难度拍平；自报不可信（RESEARCH §6 风险行）。代价：必须先跑 gold 才能给其他适配器评分 |
| D-10 | 预算在**每次计费前**检查；超限抛 `BudgetExceeded`，句柄状态 `budget_exceeded`，`usage.exceeded=true`、`truncated=false` | 事后截断 / 只在结束时比较 | OB-4 明确“静默截断即失败”。代价：适配器必须通过 tracker 计费，不能绕过 |
| D-11 | C 类只计分解/委派/成本（满分 9）；题面含“可拆 10 份”的诱导；节点数 > 2× 必答 → 分解 **0**，`over_split` fixture 总分必须低于 gold | 把 C 类也按 12 分制并与 D/L/A 混排 / 过度拆分只扣 1 分 | 会把“拆得多”变成部分得分；plan §3 明确 C 类只计三维且过度拆分应扣分。代价：C 类分数不可与 D/L/A 直接横比 |
| D-12 | OB-5 用 `prose_only` fixture（gold + 散文）判分必须与 gold **逐任务相等**；judge 只打开 6 个白名单文件 | prompt 里提醒“不要看散文” | 输入白名单是机械约束，prompt 不是。代价：需要额外的 fixture 与白名单断言 |
| D-13 | 无模块级可变注册表；每 run 独立目录；任务加载返回新对象；trace id 用 `uuid5(run_id/adapter/task/span)` 确定性生成 | 全局 ADAPTER 字典 / 复用上次 run 目录 | Inspect #4972 的全局 registry 污染会造成 xdist 随机翻转（RESEARCH C-5）。代价：少量重复构造开销 |
| D-14 | 负向行为一律用**独立 fixture adapter** 表达，不靠 judge 开关 | judge 加 `--assume-serial` 之类模式 | 开关会污染正常路径；fixture 既测 judge 也测接口。代价：适配器数量从 3 增到 7 |

## 2. 模块划分

| 模块 | 职责 | 不负责 |
|---|---|---|
| `orchestration/model.py` | 数据模型、schema 常量、`Budget`/`BudgetTracker`、`BudgetExceeded`、`RunHandle` | 不做 IO、不评分 |
| `orchestration/tasks.py` | 加载/校验 `tasks/*.json`，DAG 拓扑校验，返回 `OrchestrationTask` | 不读 ARC manifest、不派生题面 |
| `orchestration/workers.py` | 确定性 worker 模拟器：真值行 → worker 输出 + token 计量；同层 barrier | 不写 plan/delegations、不评分 |
| `orchestration/adapters.py` | `OrchestrationAdapter` ABC + gold / single_shot / dummy + 4 fixture | 不判分、不写 submission |
| `orchestration/judge.py` | 确定性 judge：白名单读入、四维评分、门控、OB 检查 | 不发 LLM 请求（默认）、不修改 artifacts |
| `orchestration/submission.py` | baseline-compatible `submission/` 布局 + `judge_result.json` 写出 | 不做评分 |
| `orchestration/runner.py` | 15×N 矩阵、gold 参考、汇总 `summary.json`、OB-1..OB-5 gate | 不启动 CLI |
| `scripts/run_orchestration.py` | CLI：任务/适配器选择、结果目录、gate 退出码 | 不承载业务逻辑 |
| `tests/test_orchestration_*.py` | T01..T12 | — |

## 3. 任务语料（U-1 裁决）

**共同 schema**（`tasks/*.json`，`arc-orchestration-task/1`）：

```json
{
  "schema": "arc-orchestration-task/1",
  "id": "D1",
  "class": "D",
  "title": "Dropout × dataset metrics table",
  "source_manifest": "experiments/arc_bench/config/ml/manifests/ML01.yaml",
  "version": 1,
  "prompt": "...",
  "delegation_style": "capability",
  "subgoals": [
    {"id": "breast_cancer", "capability": "ml_metrics", "depends_on": [],
     "inputs": ["task.prompt"], "outputs": ["metrics_rows"],
     "acceptance": "18 rows; schema (dataset,condition,seed,accuracy,ece)"}
  ],
  "worker_pool": [{"id": "ml_runner", "capabilities": ["ml_metrics"]}],
  "aggregate": {
    "columns": ["dataset","condition","seed","accuracy","ece"],
    "key": ["dataset","condition","seed"],
    "invalid_policy": "exclude",
    "conflict_required": false,
    "conflict_rule": null,
    "arithmetic": "mean_by_group",
    "group_by": ["condition"]
  },
  "trap": null,
  "budget": {"tokens": 24000, "wall_seconds": 60, "max_workers": 3, "max_depth": 2},
  "truth": {
    "rows": [{"dataset":"breast_cancer","condition":"no_dropout","seed":1,"accuracy":0.951,"ece":0.041}, "..."],
    "invalid_subgoals": [],
    "expected_conflicts": []
  }
}
```

- `delegation_style`：`capability`（D/A/C，同能力 worker 可复用）或 `distinct_roles`（L，委派对象必须互异，且 `delegation.inputs` 必须等于子目标声明的 `inputs`——用于机械化“verifier 只拿到 raw evidence”的隔离约束）。
- `conflict_rule`（仅 A 类）：`prefer_higher_n` / `dedupe_overlap` / `method_evidence`，是**公开**的聚合规则；gold 按规则合并，judge 只对照 `truth.expected_conflicts` 判定裁决是否正确。规则本身不泄漏冲突出现在哪一片。
- `truth.rows` 是 worker 模拟器的唯一数据源；`valid:false` 行表示陷阱子目标/切片。
- `truth.expected_rows` 仅在冲突任务出现；非冲突任务由 judge 从 `rows` 过滤 `valid` 后派生（**仍不调用适配器代码**）。
- `trap.kind`：`infeasible_subgoal`（D3/L4）、`degenerate_slice`（A2）、`over_split`（C1..C3）。

**15 任务清单**：

| ID | 类 | 来源 manifest | 子目标（≥3，C=2） | 能力/角色 | 陷阱 | 冲突 | 算术 |
|---|---|---|---|---|---|---|---|
| D1 | D | ML01 | 3 数据集 | `ml_metrics` ×1 | — | 否 | condition 均值 |
| D2 | D | ML05 | 3 数据集 | `dimred_metrics` ×1 | — | 否 | method 均值 |
| D3 | D | P01 | 2 通道 + 1 理论基线 + 1 不可行能量点 | `hep_scan` ×1 | 第 4 个子目标不可行（整体 invalid） | 否 | — |
| D4 | D | Q03 | 3 bond length | `quantum_sim` ×1 | — | 否 | bond_length 均值 |
| L1 | L | P01 | producer / verifier / literature | 三角色互异 | — | 否 | — |
| L2 | L | ML02 | bagging / boosting / stacking | 三角色互异 | — | 否 | — |
| L3 | L | S01 | point / CI audit / coverage report | 三角色互异、链式依赖 | — | 否 | — |
| L4 | L | B01 | build / solve / verify / infeasible probe | 四角色互异、链式依赖 | 第 4 个子目标不可行（整体 invalid） | 否 | — |
| A1 | A | ML06 | 3 schedule 切片 | `ml_train` ×3 | — | 种子数优先 | — |
| A2 | A | Q01 | 3 数据切片 | `quantum_eval` ×3 | 1 个退化切片 | 种子数优先 | — |
| A3 | A | P03 | 3 contour 分析 | `hep_contour` ×3 | — | 去重优先 | — |
| A4 | A | S02 | 3 bootstrap 切片 | `stats_ci` ×3 | — | 方法证据优先 | — |
| C1 | C | ML04 | 2 独立目标 | `ml_scaling` ×2 | 题面诱导 10 拆 | 否 | — |
| C2 | C | Q02 | 2 独立目标 | `quantum_ablate` ×2 | 题面诱导 10 拆 | 否 | — |
| C3 | C | P02 | 2 独立目标 | `hep_majorana` ×2 | 题面诱导 10 拆 | 否 | — |

- 来源 manifest 均已实测存在（RESEARCH U-1；本批 T01 再次断言）。
- 题面只写研究目标与产物契约，**不写**切分方式；C 类题面故意写“可考虑拆成 10 份并行”作为诱导。
- 每个任务 `budget.tokens` 按 gold 实测上浮 ≥30% 设定；`max_workers ≥ 同层最大宽度`。

## 4. 数据模型与 API

```python
# model.py
SCHEMA_TASK = "arc-orchestration-task/1"
SCHEMA_PLAN = "arc-orchestration-plan/1"
SCHEMA_DELEGATIONS = "arc-orchestration-delegations/1"
SCHEMA_AGGREGATE = "arc-orchestration-aggregate/1"
SCHEMA_TRACE = "arc-orchestration-trace/1"
SCHEMA_USAGE = "arc-orchestration-usage/1"
SCHEMA_RESULT = "arc-orchestration-result/1"
SCHEMA_SUMMARY = "arc-orchestration-summary/1"

@dataclass(frozen=True)
class Subgoal:
    id: str
    capability: str
    depends_on: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    acceptance: str

@dataclass(frozen=True)
class Worker:
    id: str
    capabilities: tuple[str, ...]

@dataclass(frozen=True)
class Budget:
    tokens: int
    wall_seconds: float
    max_workers: int
    max_depth: int

class BudgetExceeded(RuntimeError):
    def __init__(self, kind: str, limit: float, observed: float): ...

class BudgetTracker:
    def __init__(self, budget: Budget, *, clock=time.monotonic): ...
    def charge_tokens(self, tokens: int, *, reason: str) -> None: ...   # 超限即抛
    def check_wall(self) -> None: ...
    def register_worker(self) -> None: ...                              # 超过 max_workers 即抛
    def enter_depth(self, depth: int) -> None: ...
    @property
    def total_tokens(self) -> int: ...
    @property
    def exceeded(self) -> dict | None: ...

@dataclass
class RunHandle:
    run_id: str
    workdir: Path
    status: str = "running"       # running|completed|failed|timeout|budget_exceeded
    error: str | None = None
    started_at: float = 0.0
    elapsed_sec: float = 0.0
    task_id: str = ""
    adapter_id: str = ""

@dataclass(frozen=True)
class OrchestrationArtifacts:
    plan: dict
    delegations: list[dict]
    aggregate: dict
    trace: list[dict]
    usage: dict
```

```python
# tasks.py
def load_tasks(tasks_dir: Path | None = None) -> list[OrchestrationTask]
def load_task(task_id: str, tasks_dir: Path | None = None) -> OrchestrationTask
def validate_task(task: OrchestrationTask) -> list[str]      # 返回问题列表，空 = 合法

# adapters.py
class OrchestrationAdapter(ABC):
    framework_id: str
    def start(self, task: OrchestrationTask, workdir: Path, budget: Budget) -> RunHandle
    def collect(self, handle: RunHandle, timeout_sec: float = 30.0) -> str
    def artifacts(self, handle: RunHandle) -> OrchestrationArtifacts

ADAPTERS: dict[str, type[OrchestrationAdapter]]   # 只读常量，实例每 run 新建

# judge.py
def judge_run(task: OrchestrationTask, run_dir: Path, *,
              reference_usage: dict | None = None,
              residual_fn: Callable[[dict], dict] | None = None) -> dict
def judge_artifacts(task: OrchestrationTask, artifacts: OrchestrationArtifacts, *,
                    reference_usage: dict | None = None,
                    residual_fn: Callable[[dict], dict] | None = None) -> dict
def usage_from_trace(trace: list[dict]) -> dict

# runner.py
def run_matrix(task_ids: list[str] | None = None,
               adapter_ids: list[str] | None = None,
               results_root: Path | None = None,
               run_id: str | None = None,
               with_fixtures: bool = True) -> dict
def evaluate_gates(summary: dict, runs: dict) -> dict
```

### 4.1 五件套契约

| 文件 | 必填键 | 说明 |
|---|---|---|
| `plan.json` | `schema/task_id/nodes[]`；node = `id/depends_on/inputs/outputs/acceptance/assignee` | 子目标 DAG；`id` 必须与任务 `subgoals` 一一对应 |
| `delegations.json` | `schema/task_id/delegations[]`；delegation = `subgoal/worker/capability/depends_on/parallel_with/inputs/outputs/start/end/span_id` | 一次委派一条；`start/end` 为相对秒 |
| `aggregate.json` | `schema/task_id/rows[]/invalid[]/conflicts[]/summary{}` | 行按 `aggregate.key` 唯一；`conflicts` 只在需要时非空 |
| `trace.jsonl` | 每行 `schema/trace_id/span_id/parent_id/name/kind/start/end/pid/thread_id/attributes` | `kind ∈ {orchestrator, worker, tool}`；`attributes` 含 `subgoal/worker/tokens_in/tokens_out` |
| `usage.json` | `schema/task_id/adapter/prompt_tokens/completion_tokens/tool_calls/llm_calls/wall_seconds/max_concurrency/charged_tokens/exceeded/truncated/budget{}` | judge 用 trace 重算 token，不一致即成本 0 |

## 5. 评分算法（确定性）

### 5.1 维度规则

| 维度 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|
| 分解 | 节点 id 集合 = 必答子目标；依赖边 = 必答边；每节点 inputs/outputs/acceptance 非空 | 覆盖完整，但 1 处契约/依赖瑕疵 | 单节点机械桶，或覆盖缺 1 项 | 无 plan / 与目标无关 / 节点数 > 2× 必答（过度拆分） |
| 委派 | 每题必答子目标均有委派；能力匹配；`distinct_roles` 时 worker 互异；依赖按 DAG；声明并行的兄弟区间真实重叠；≤ max_workers/depth | 能力匹配但有 1 处冗余/顺序瑕疵（无虚假并行声明） | 轮询均分或角色冗余明显 | 无委派 / 全塞一个 worker / 能力错配 / **声明并行但实测串行（OB-3，总分 0）** |
| 聚合 | 行完整且与期望值逐键相等；invalid 按策略处理；冲突检测 + 证据裁决与期望一致；算术可复算 | 行完整但冲突未处理或算术缺失 | 有重复行/部分拼接，但无编造 | 缺行 / 编造 / 与 worker 输出矛盾 / schema 不合法 |
| 成本 | 相对 gold ≤0.8× | ≤1.0× | ≤1.5× | >1.5× / `budget_exceeded` / `timeout` |

规则：
- `aggregation == 0` → `total = 0`（正确性门控）。
- OB-3 违例 → `delegation = 0` 且 `total = 0`。
- 分类满分：D/L/A = 12；C = 9（只计分解/委派/成本）。
- 成本参考缺失（直接调用 judge）→ 成本维给 2（中性），并在 `checks.cost_reference_missing=true` 标出；矩阵路径始终有 gold 参考。
- 允许 `residual_fn` 注入（0/1），只调整分解维 ±1；默认 `None`，结果里 `residual.enabled=false`。

### 5.2 聚合期望值

```
expected_rows = truth.expected_rows 若存在
                否则 [r for r in truth.rows if r.get("valid", True)]
invalid_ids   = truth.invalid_subgoals（从 rows 中 valid=false 的 subgoal 汇总）
expected_conflicts = truth.expected_conflicts
```

- `invalid_policy="exclude"`：`aggregate.invalid` 的 id 集合必须等于 `invalid_ids`，`rows` 不含这些行。
- `invalid_policy="keep_with_flag"`：`rows` 保留这些行且 `valid=false`。
- 行比较：按 `aggregate.key` 建索引，逐列比较；浮点容差 `1e-6`；多行/少行/额外键均判 0。
- 冲突比较：`aggregate.conflicts` 与 `expected_conflicts` 按 `id` 对齐，`chosen` 与 `rule` 必须一致；缺冲突 → 聚合 ≤2。
- 冲突规则语义（公开规则，gold 实现一份，judge 不实现只对答案）：
  - `prefer_higher_n`：同键多条证据取样本量 `n` 大者；`n` 相同则取绝对偏差小者。
  - `dedupe_overlap`：重叠区间合并为并集，保留覆盖最大的来源集合。
  - `method_evidence`：以方法学证据（如 BCa 对偏态更稳健）为裁决依据，记录被拒来源。
- `arithmetic="mean_by_group"`：从 `rows` 重算 `group_by` 均值，与 `summary` 比较（容差 `1e-6`）。

### 5.3 并行判定（OB-3）

1. 取 `kind="worker"` 的 span；同 `parent_id` 为一组。
2. 对组内区间做扫描线，`max_concurrency = max(活跃区间数)`。
3. 对每个 `delegations[i].parallel_with` 中的 `j`：要求 `delegation[i]` 与 `delegation[j]` 对应 worker span 的时间区间有正重叠，且 `thread_id` 不同（同线程不可能真并行）。
4. 任一声明对不满足 → `checks.ob3_parallel_claim_ok=false` → 委派 0、总分 0。
5. 未声明并行但实测重叠：不扣分，只记录 `unclaimed_parallel=true`。

### 5.4 预算与 usage（OB-4）

- 适配器只能经 `BudgetTracker.charge_tokens/check_wall/register_worker/enter_depth` 计费；任一超限抛 `BudgetExceeded`。
- `start` 捕获 `BudgetExceeded` → 写 `usage.exceeded=true`、`truncated=false`，句柄 `status="budget_exceeded"`。
- judge 断言：`status=="budget_exceeded"` ⇒ `usage.exceeded=true` 且 `truncated=false`；否则 `checks.ob4_budget_state_ok=false`，成本 0。
- `usage` 与 trace 的 token 汇总必须相等（`prompt_tokens == Σ tokens_in`，`completion_tokens == Σ tokens_out`），否则 `usage_matches_trace=false`，成本 0。

### 5.5 OB-5 与散文隔离

- `judge_run` 只打开：`task.json`（内存对象）、`plan.json`、`delegations.json`、`aggregate.json`、`trace.jsonl`、`usage.json`；`inputs_whitelist` 写入结果。
- `prose_only` fixture = gold 的五件套 + `paper.md`（含夸大结论）+ `README.md`；得分必须与 gold 逐任务相等。
- `over_split` fixture 把 C 类拆成 10 节点 → 分解 ≤1、总分 < gold。

## 6. OB 映射与本段判定

| ID | 断言 | 本段落点 | 本段判定口径 |
|---|---|---|---|
| OB-1 | 15 任务 × 3 适配器 dry-run 可复现；gold ≥10/12，单发 ≤7/12 | `run_matrix` + `evaluate_gates` | 15×3 全跑；gold：D/L/A ≥10、C ≥8；single_shot：D/L/A 逐任务 ≤7；重跑两次逐任务 total 相同 |
| OB-2 | dummy 经 `run_baseline.py` 产出 submission/judge_result | `dummy` + `submission.build_submission` + `run_orchestration.py` | **baseline-compatible 入口**满足：`submission/{code/,results/metrics.json,README.md,claims.json,reproduce.sh,reproduce.log,reproduce.log.creation_time}` + `judge_result.json` 存在；`run_baseline.py` git diff 为空。字面路径未通 → U-6 |
| OB-3 | 串行却声明并行 → 委派 0 + 总分 0 | `serial_claiming` fixture + §5.3 | D1 上 `ob3_parallel_claim_ok=false`、`delegation=0`、`total=0` |
| OB-4 | 超预算落 `budget_exceeded` | `over_budget` fixture + §5.4 | D1 上 `status="budget_exceeded"`、`exceeded=true`、`truncated=false`、成本 0 |
| OB-5 | 删散文分数变化 <0.05；C 类过度拆降分 | `prose_only`/`over_split` fixture + §5.5 | 15 任务 gold 与 prose_only total 逐任务相等；C1..C3 over_split total < gold |

## 7. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | judge 只读五件套 + 任务对象；散文文件永不进入评分输入 |
| J-2 | 聚合期望值来自任务真值，不来自适配器代码或 worker 代码复算 |
| J-3 | 任何自适应分都从 trace 重算 usage；自报与 trace 不一致即成本 0 |
| J-4 | 声明并行必须由「区间正重叠 + 不同 thread_id」双条件证明 |
| J-5 | 预算检查在计费前；超限只落 `budget_exceeded`，不静默截断 |
| J-6 | 每 run 独立目录、独立适配器实例、无模块级可变注册表 |
| J-7 | 任务加载返回新对象；修改一次加载结果不影响下一次加载 |
| J-8 | 评分只依赖文件内容与任务真值；同一输入重跑得到同一 total |
| J-9 | `aggregation=0` 或 OB-3 违例时 `total=0`，不因其他维度补偿 |
| J-10 | C 类满分 9；节点数 > 2× 必答 → 分解 0，且过度拆分 fixture 总分必须低于同任务 gold |

## 8. 回退点

| 编号 | 回退动作 | 影响面 |
|---|---|---|
| R-1 | 删除 `experiments/arc_bench/orchestration/`、`run_orchestration.py` 与对应测试 | 零运行时影响；主流水线不 import 该包 |
| R-2 | 保留包但删除 4 个 fixture 与 gate | 只能跑 15×3 正常矩阵 |
| R-3 | 删除 `submission.py` 的 submission 写出 | OB-2 退化为纯五件套 |

## 9. 非目标（职责边界）

- **职责外**：真实框架排名（AIS v2/AgentLab/AIDE）、A7-2/A7-3/A7-5/A7-6/A7-7、FA-1..FA-3、真实科学运行、论文写作质量——各有独立验收面。
- **能力边界**：本设计能证明“编排五件套可被机械化评分、三类作弊可被判红”，**不能**证明真实框架在 ARC 任务上的编排能力；后者需要 field run 与真实 LLM 预算。
- **构念边界**：gold 与任务共同设计，gold 高分是构造保证；因此 OB-1 的效力来自 `single_shot ≤7` 的负向控制，不来自 gold 的绝对分。

## 10. Review 记录（Step 4，自查·单视角）

> **RULE-4**：本节与正文同一会话，属自查（单视角）；未经异构基座复审。

| 检查项 | 结论 |
|---|---|
| 设计基于已验证调研 | D-2 ← RESEARCH F-1/F-2/F-3；D-5/D-6 ← RESEARCH §5.1-5/5.1-8；D-7 ← E7/E8；D-9 ← E4/E11；D-12 ← F-3；D-13 ← C-5 |
| 无未经验证假设 | 15 任务为**本批新写**的冻结语料，不声称科学正确性；OB-2 字面路径未通已显式标 U-6；LLM residual 未启用 |
| 无归因扭曲 | 未把 SwarmBench/Anthropic 的数字当作本仓能力；仅借维度与陷阱 |
| 替代方案 ≥2 并被否决 | D-1/D-2/D-3/D-4/D-6/D-7/D-9/D-13 均列替代与代价 |
| 职责边界 | §9 区分“职责外”与“能力边界/构念边界” |

## 11. 未决项（承接 RESEARCH U-1..U-5）

| 编号 | 判据 | 触发条件 | 当前倾向 | 证据 |
|---|---|---|---|---|
| U-1 任务清单与冻结 | 15 个 `tasks/*.json` 有 `id/class/source_manifest/version/truth`，T01 全过 | 已闭合（§3） | D4/L4/A4/C3；真值行 + 陷阱内置 | E1（T01） |
| U-2 OB-2 入口 | dummy 经新入口产出 `submission/` + `judge_result.json`，旧 runner 零 diff | 已裁决（D-2） | 新入口；字面 `run_baseline.py` 路径转 U-6 | E1/E3 |
| U-3 LLM judge 角色 | 确定性层可独立出总分；residual 有注入钩子但默认关闭 | 已裁决（D-7） | 本段 deterministic-only；校准留给 field run | E1（T 测试） |
| U-4 trace 信任边界 | 每个 worker span 有 `pid/thread_id/start/end`；串行 fixture 判红 | 已裁决（D-5/§5.3） | OTel 风格；无法证明的字段标 `self_reported` 且不进承重分 | E1（T12） |
| U-5 “3 框架”定义 | 15×3 矩阵中 3 个 adapter 固定且含负向控制 | 已裁决（D-1/D-14） | gold / single_shot / dummy；fixture 另计 | E3（plan §2/§6） |
| U-6 `run_baseline.py` 字面 OB-2 与 F-1/F-2 | `run_baseline.py --dry-run` 可运行且能注册编排 adapter | 下一次 ARC-Bench runner 修复批 | 先修五域 topic/manifest 加载，再加通用 adapter/judge 分派 | E1（实测 FileNotFoundError） |
| U-7 语义残差校准 | ≥30 条人工标注与 LLM residual 一致率 | 首次接真实 LLM judge 前 | 本段不启用，不产生读数 | E5 |
