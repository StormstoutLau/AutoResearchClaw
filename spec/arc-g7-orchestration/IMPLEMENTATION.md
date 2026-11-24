---
id: arc-g7-orchestration-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-orchestration-DESIGN, arc-g7-orchestration-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 第二段「编排评测」（P-162）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **实施面**：新增 `experiments/arc_bench/orchestration/`（8 个模块 + 15 份任务 JSON）、`experiments/arc_bench/scripts/run_orchestration.py`、`tests/test_orchestration_*.py`；不修改 `run_baseline.py` / `judge.py` / topic 注册表 / `researchclaw/` 运行时。
> **环境**：Python ≥3.11（本机 3.13.5，`pyproject.toml` requires-python `>=3.11`）；只使用标准库；pytest 8.3.4（`>=7.0`）。零新增三方依赖。

---

## 1. 文件清单

| 路径 | 类型 | 职责 |
|---|---|---|
| `experiments/arc_bench/orchestration/__init__.py` | 新增 | 包导出（任务加载、judge、runner 入口） |
| `experiments/arc_bench/orchestration/model.py` | 新增 | schema 常量、数据类、`Budget`/`BudgetTracker`、异常 |
| `experiments/arc_bench/orchestration/tasks.py` | 新增 | 任务加载 + 校验 |
| `experiments/arc_bench/orchestration/workers.py` | 新增 | 确定性 worker 模拟器 |
| `experiments/arc_bench/orchestration/adapters.py` | 新增 | ABC + 3 正常适配器 + 4 fixture |
| `experiments/arc_bench/orchestration/judge.py` | 新增 | 确定性评分 |
| `experiments/arc_bench/orchestration/submission.py` | 新增 | baseline-compatible submission 布局 |
| `experiments/arc_bench/orchestration/runner.py` | 新增 | 矩阵执行、汇总、OB gate |
| `experiments/arc_bench/orchestration/tasks/D1.json` … `C3.json` | 新增 | 15 份冻结任务 |
| `experiments/arc_bench/scripts/run_orchestration.py` | 新增 | CLI |
| `tests/test_orchestration_tasks.py` | 新增 | T01 |
| `tests/test_orchestration_budget.py` | 新增 | T02 |
| `tests/test_orchestration_matrix.py` | 新增 | T03/T04/T05/T10/T11 |
| `tests/test_orchestration_negative.py` | 新增 | T06/T07/T08 |
| `tests/test_orchestration_ob2.py` | 新增 | T09 |
| `tests/test_orchestration_trace.py` | 新增 | T12 |

## 2. 接口签名（含回退点）

### 2.1 `model.py`

```python
SCHEMA_TASK = "arc-orchestration-task/1"
SCHEMA_PLAN = "arc-orchestration-plan/1"
SCHEMA_DELEGATIONS = "arc-orchestration-delegations/1"
SCHEMA_AGGREGATE = "arc-orchestration-aggregate/1"
SCHEMA_TRACE = "arc-orchestration-trace/1"
SCHEMA_USAGE = "arc-orchestration-usage/1"
SCHEMA_RESULT = "arc-orchestration-result/1"
SCHEMA_SUMMARY = "arc-orchestration-summary/1"

@dataclass(frozen=True)
class Budget:
    tokens: int
    wall_seconds: float
    max_workers: int
    max_depth: int

class BudgetExceeded(RuntimeError):
    kind: str          # "tokens" | "wall" | "workers" | "depth"
    limit: float
    observed: float

class BudgetTracker:
    def __init__(self, budget: Budget, *, clock: Callable[[], float] = time.monotonic) -> None
    def charge_tokens(self, tokens: int, *, reason: str) -> None
    def check_wall(self) -> None
    def register_worker(self) -> None      # 活跃子 agent 计数 +1，超限抛
    def release_worker(self) -> None
    def enter_depth(self, depth: int) -> None
    @property
    def total_tokens(self) -> int
    @property
    def exceeded(self) -> dict | None
```

**回退点 R-B1**：预算追踪若在 Step 9 发现与 barrier 线程计数冲突，退化为“每个 subgoal 执行前 `register_worker`、结束后 `release_worker`”，不改变对外签名。

### 2.2 `tasks.py`

```python
TASK_ORDER = ("D1","D2","D3","D4","L1","L2","L3","L4","A1","A2","A3","A4","C1","C2","C3")

def load_tasks(tasks_dir: Path | None = None) -> list[OrchestrationTask]
def load_task(task_id: str, tasks_dir: Path | None = None) -> OrchestrationTask
def validate_task(task: OrchestrationTask) -> list[str]
```

校验项：
1. `schema` 等于 `SCHEMA_TASK`；文件名与 `id` 一致。
2. `class ∈ {D,L,A,C}`；`source_manifest` 在仓库根下存在。
3. 子目标 id 唯一；`depends_on` 引用存在且无环（Kahn）。
4. 每个 `capability` 至少被一个 `worker_pool` worker 覆盖。
5. `aggregate.key ⊆ columns`；`invalid_policy ∈ {exclude,keep_with_flag}`；`conflict_required` ⇒ `conflict_rule` 非空。
6. `budget` 四项 >0；**最大层宽 ≤ budget.max_workers**（保证 gold 可并行）。
7. `truth.rows` 非空；每行含 `subgoal`；`valid:false` 的 subgoal 与 `invalid_subgoals` 一致；A 类 `expected_conflicts` 非空。

**回退点 R-B2**：第 6 条（层宽）若使某任务预算过紧，改为“层宽 ≤ max_workers 或该层串行且不声明并行”；只影响任务校验，不影响 judge。

### 2.3 `workers.py`

```python
@dataclass(frozen=True)
class WorkerOutput:
    subgoal: str
    worker_id: str
    rows: tuple[dict, ...]
    status: str                 # "ok" | "infeasible"
    tokens_in: int
    tokens_out: int

class WorkerSimulator:
    def __init__(self, task: OrchestrationTask) -> None
    def capabilities(self, worker_id: str) -> tuple[str, ...]
    def worker_for(self, subgoal: Subgoal) -> Worker
    def run(self, subgoal: Subgoal, worker_id: str, tracker: BudgetTracker) -> WorkerOutput
```

- 行来源：`[r for r in task.truth["rows"] if r["subgoal"] == subgoal.id]`；返回副本，去掉 `valid` 前的原样保留。
- 计费：`tokens_in = 32 + 6 * len(rows)`，`tokens_out = 16 + 10 * len(rows)`；先 `charge_tokens` 再返回。
- 全 `valid:false` → `status="infeasible"`，仍返回行（供聚合侧显式标记），不编造数值。
- 无 `sleep`；并行重叠由调用方 barrier 保证。

### 2.4 `adapters.py`

```python
class OrchestrationAdapter(ABC):
    framework_id: str
    def start(self, task, workdir: Path, budget: Budget) -> RunHandle
    def collect(self, handle: RunHandle, timeout_sec: float = 30.0) -> str
    def artifacts(self, handle: RunHandle) -> OrchestrationArtifacts

ADAPTERS: dict[str, type[OrchestrationAdapter]] = {
    "gold_orchestrator": GoldOrchestratorAdapter,
    "single_shot": SingleShotAdapter,
    "dummy": DummyAdapter,
    "serial_claiming": SerialClaimingAdapter,
    "over_budget": OverBudgetAdapter,
    "prose_only": ProseOnlyAdapter,
    "over_split": OverSplitAdapter,
}
```

#### 通用基类

- `start`：新建 `RunHandle`，在 daemon 线程执行 `_execute(task, handle, budget)`；捕获 `BudgetExceeded` → `status="budget_exceeded"`；其他异常 → `status="failed"` + `handle.error`；正常 → `status="completed"`。
- `collect`：`thread.join(timeout)`；仍在运行 → `timeout`；返回 `handle.status`。
- `artifacts`：读取 workdir 五件套（不存在则返回空结构，不抛）。

#### gold_orchestrator

1. 记录 orchestrator `plan` span；`charge_tokens(64 + 24*n)`。
2. `plan.nodes` 与 `task.subgoals` 一一对应；`assignee = first worker covering capability`。
3. Kahn 分层；每层：
   - `Barrier(len(level), timeout=5.0)`；
   - 每子目标一线程：`tracker.register_worker()` → 写 worker span 起点 → `barrier.wait()` → `sim.run()` → span 终点 → `release_worker()`；
   - join；任一异常重抛。
4. 记录 `aggregate` span；`charge_tokens(96 + 32*n)`；按 `aggregate` 规则合并：
   - 有效行加入；无效 subgoal 进入 `invalid`（`exclude`）或保留 `valid:false`（`keep_with_flag`）；
   - `conflict_required`：按 `conflict_rule` 分组裁决，写入 `conflicts[{id, values, chosen, rule}]`；
   - `arithmetic="mean_by_group"`：写 `summary[group][metric] = mean`（`round(..., 9)`，metric = 非 key/非 group 列）；
   - 行按 key 排序。
5. `delegations`：`parallel_with` = 同层其他子目标；`inputs/outputs` 复制任务声明；`start/end` 取自 span；`thread_id` 写入 trace span。
6. 写五件套；`usage` 由 trace 汇总 + `charged_tokens/exceeded/truncated/budget`。

#### single_shot

- 单节点 plan（id=`all`）；`delegations=[]`；串行执行全部子目标（不 barrier）；
- 聚合：按 key first-wins，丢弃 `valid:false` 行，**不写 `invalid`、不写 `conflicts`、不写 `summary`**；
- 预期得分（实测口径）：分解 1、委派 0；聚合 D=2（算术摘要缺失）/L=3（无冲突无算术）/A=2（冲突未处理）；成本 3（无编排开销）→ **D/L ≤7、A ≤6**。

#### dummy

- plan `nodes=[]`、delegations `[]`、aggregate 空、trace 单 span、usage 全 0；`status="completed"`；用于 OB-2 契约烟测。

#### serial_claiming

- 与 gold 相同的 plan/聚合；执行改为**串行**；`delegations.parallel_with` 仍声明同层并行 → OB-3 判红。

#### over_budget

- 写一条 tool span（`tokens_in = budget.tokens + 1`），随后 `charge_tokens(budget.tokens + 1)` 抛 `BudgetExceeded`；
- `usage.exceeded=true`、`truncated=false`、`charged_tokens=budget.tokens+1`；其余 artifacts 最小化。

#### prose_only

- 继承 gold；五件套写完后额外写 `paper.md` / `README.md`（含夸大结论与分数自评）；评分必须与 gold 相等。

#### over_split

- 仅用于 C1..C3：plan 每子目标拆 5 个节点（共 10），delegations 10 条、轮询 2 个 worker；
- 仅每个子目标的第 1 个节点真实执行 worker，其余节点写 10 token 的占位 span；
- 聚合与 gold 相同（行完整，聚合维不参与 C 类总分但参与 0 门控）→ 分解 0（10 > 2×2）、委派 1、成本 1–2 = **总分 2–3 < gold 8**。

### 2.5 `judge.py`

```python
def judge_run(task, run_dir: Path, *, reference_usage: dict | None = None,
              residual_fn: Callable[[dict], dict] | None = None) -> dict
def judge_artifacts(task, artifacts, *, reference_usage=None, residual_fn=None) -> dict
def usage_from_trace(trace: list[dict]) -> dict
```

执行顺序（任何阶段异常 → 结构化 `failed` 结果，不抛给 runner）：

1. **白名单读入**：`plan.json` / `delegations.json` / `aggregate.json` / `trace.jsonl` / `usage.json`；`task.json` 用内存对象。缺失/坏 JSON → `total=0` + `checks.missing_files/parse_errors`。
2. **schema 校验**：五个 `schema` 与 `task_id`。
3. **分解**（§DESIGN 5.1）。
4. **委派 + OB-3**（§DESIGN 5.1/5.3）。
5. **聚合**（§DESIGN 5.2）。
6. **成本 + OB-4**（§DESIGN 5.4）。
7. **门控**：`aggregation==0` 或 `ob3_parallel_claim_ok==false` → `total=0`，`gate_reasons` 记录。
8. **residual**（若注入）：只传白名单字典；`decomposition_delta ∈ {-1,0,1}`；结果记 `residual.enabled=true` + `prompt_hash`（`sha256(json.dumps(payload, sort_keys=True))`）。

结果字段固定：`schema/task_id/class/adapter/scores/max_score/total/gate_zeroed/gate_reasons/checks/inputs_whitelist/reference/residual`。

**回退点 R-B3**：若冲突比较因 `values` 顺序不稳定，`expected_conflicts` 比较只取 `id/chosen/rule` 三字段（DESIGN §5.2 已允许）。

### 2.6 `submission.py`

```python
def build_submission(workdir: Path, task: OrchestrationTask, aggregate: dict,
                     *, adapter_id: str) -> Path
```

写出（与旧基线布局同名）：
- `submission/code/`（空目录）
- `submission/results/metrics.json`（`{"task_id", "adapter", "aggregate"}`）
- `submission/README.md`（固定一句“dry-run harness 不产论文散文”）
- `submission/claims.json`（空 claims）
- `submission/reproduce.sh` / `reproduce.log` / `reproduce.log.creation_time`
- 运行目录级：`pipeline_summary.json` + `stage-14/experiment_summary.json`（无 paper）

### 2.7 `runner.py`

```python
FIXTURE_TASKS = {
    "serial_claiming": ("D1",),
    "over_budget": ("D1",),
    "prose_only": TASK_ORDER,
    "over_split": ("C1", "C2", "C3"),
}

def run_matrix(task_ids=None, adapter_ids=None, results_root=None, run_id=None,
               with_fixtures=True, repeat_gold=True) -> dict
def evaluate_gates(summary: dict, runs: dict) -> dict
```

流程：
1. 任务顺序固定 `TASK_ORDER`；适配器顺序：`gold_orchestrator` → `single_shot` → `dummy` → fixtures。
2. 每个任务先跑 gold，保存 `reference_usage`；`repeat_gold=True` 时在 `_repeat/` 子目录再跑一次 gold，比较逐任务 total。
3. 每个 run：`workdir = root/run_id/adapter/task`；实例化 adapter → `start` → `collect(30)` → `artifacts` → `judge_run` → 写 `judge_result.json` / `orchestration_meta.json` → `build_submission`。
4. fixture 按 `FIXTURE_TASKS` 限定任务。
5. `summary.json`：`per_adapter` 均值/极值、`gates`、`ob1` 读数、`runs` 计数；`evaluate_gates` 返回：
   - `ob1`: gold 阈值 + single_shot 上限 + repeat 相等；
   - `ob2`: dummy 五件套 + submission 文件 + judge_result；
   - `ob3`: serial_claiming D1 `ob3=false` 且 total=0；
   - `ob4`: over_budget D1 状态/exceeded/truncated；
   - `ob5`: prose_only 与 gold 逐任务相等 + over_split C 类低于 gold。

**回退点 R-B4**：`repeat_gold` 默认开；若运行时长超标，CLI 提供 `--no-repeat`，但 `--gate` 下强制开启。

### 2.8 CLI

```
python experiments/arc_bench/scripts/run_orchestration.py \
  [--tasks all|D1,L1,...] [--adapters gold_orchestrator,single_shot,dummy] \
  [--results-dir PATH] [--run-id ID] [--no-fixtures] [--no-gate] [--list-tasks]
```

- 退出码：`0` = 运行完成且 gate 全绿；`1` = gate 有红；`2` = 参数/加载错误。
- `--list-tasks` 打印 15 任务表（id/class/source/subgoals）后退出。

## 3. 低效操作排除

| 低效操作 | 排除方式 |
|---|---|
| 每次 run 重新解析全部 15 份任务 | 单次 `load_tasks()` 后按需 `load_task()`；任务对象冻结，跨 run 复用只读数据 |
| 每个适配器复制一份 truth | worker 输出只复制该子目标的行；judge 只建期望索引 |
| 45+ 次 subprocess 启动 | 全部进程内线程，无 shell / 无子进程 |
| 真实 `sleep` 制造并行 | `threading.Barrier` 同层同步；无 sleep |
| 全量重跑两次 15×N | 仅 gold 重复（15 次），其余单次 |
| 大文件哈希 | `prompt_hash` 只对 residual 白名单字典（不含 trace 全量） |
| 每次 judge 重算全部 trace 区间 | 单次扫描线 O(n log n)，n ≤ 20 |
| 结果目录无限增长 | `run_id` 时间戳；测试用 `tmp_path`；runner 不自动清理（留证） |

## 4. 版本与 API 核验（Step 6）

| 依赖/API | 声明 | 核验方式 | 状态 |
|---|---|---|---|
| Python | `>=3.11` | `pyproject.toml:5`；本机 3.13.5 | ✅ |
| `threading.Barrier` | 3.2+ | CPython 文档已知 API；3.11 可用 | ✅ |
| `threading.get_ident` | 3.x | 标准库 | ✅ |
| `uuid.uuid5` | 3.x | 标准库 | ✅ |
| `dataclasses` / `field` | 3.7+ | 标准库 | ✅ |
| `pathlib.Path.is_relative_to` | **3.9+** | 3.11 下限内 | ✅ |
| `datetime.timezone.utc` | 3.x | 不用 3.11 新增 `datetime.UTC` | ✅ |
| `hashlib.sha256` | 3.x | 标准库 | ✅ |
| `statistics.mean` | 3.x | 标准库 | ✅ |
| `pytest` | `>=7.0` | 本机 8.3.4 | ✅ |
| 三方依赖 | 无 | `pyproject.toml` 不加条目 | ✅ |

无网络依赖、无 LLM SDK 调用。

## 5. 错误处理

| 场景 | 处理 | 用户可见 |
|---|---|---|
| 任务 JSON 缺失/坏 JSON | `load_task` 抛 `ValueError`，CLI exit 2 | 文件名 + 解析错误 |
| 任务校验失败 | `validate_task` 返回问题列表；`load_task` 汇总抛出 | 逐条问题 |
| 适配器抛非预算异常 | `status="failed"`，`error` 落 `orchestration_meta.json` | run 目录 meta |
| `BudgetExceeded` | `status="budget_exceeded"`；`usage.exceeded=true`、`truncated=false` | judge `checks.ob4_budget_state_ok` |
| `collect` 超时 | `status="timeout"`；judge 成本 0 | meta + judge |
| 五件套缺文件 | judge 返回 `total=0` + `checks.missing_files` | judge_result |
| trace 自报与 usage 不一致 | `checks.usage_matches_trace=false` → 成本 0 | judge_result |
| 结果目录越界 | `workdir.is_relative_to(results_root)` 断言失败 → 抛 `ValueError` | CLI exit 2 |

## 6. TDD 计划（红 → 绿）

| 测试 | 先写的失败断言（红） | 实现后（绿） |
|---|---|---|
| T01 任务语料 | `load_tasks()` 不存在 → ImportError；15 任务/4-4-4-3/来源存在/校验零问题 | 15 任务加载，DAG 合法 |
| T02 预算 | `BudgetTracker` 不存在；超 tokens/wall/workers/depth 未抛 | 四类超限均抛且 `exceeded.kind` 正确 |
| T03 gold 矩阵 | `run_matrix` 不存在 | 15 任务 gold 全 ≥10（C ≥8）；两次 total 相同 |
| T04 single_shot | 无 single_shot | D/L/A 逐任务 ≤7，无 gate 清零 |
| T05 dummy | 无 dummy | 五件套齐全，status completed |
| T06 OB-3 | 无 serial_claiming | `ob3_parallel_claim_ok=false`、delegation=0、total=0 |
| T07 OB-4 | 无 over_budget | status/exceeded/truncated 三断言 |
| T08 OB-5 | 无 prose_only/over_split | prose total == gold；C 类 over_split < gold |
| T09 OB-2 | 无 CLI/submission | dummy run 目录有 submission 七项 + judge_result.json |
| T10 runner 汇总 | 无 summary | 计数 15×3+fixtures；gate 全绿；exit 0 |
| T11 隔离/确定性 | 无重复运行断言 | 两次矩阵 total 相同；两次加载互不影响 |
| T12 trace/usage | 无 trace 校验 | span 唯一/父存在/并发≥2；篡改 usage → 成本 0 |

红阶段先提交测试文件并运行 `python -m pytest tests/test_orchestration_*.py -q`，记录全部 ImportError/失败读数，再写实现。

## 7. 回退点汇总

| 编号 | 回退动作 | 影响 |
|---|---|---|
| R-B1 | 预算计数改为每子目标 register/release | 只影响并行宽度计数 |
| R-B2 | 层宽校验放宽为“串行且不声明并行” | 只影响任务预算校验 |
| R-B3 | 冲突比较只取 `id/chosen/rule` | 放宽 `values` 顺序约束 |
| R-B4 | `--no-repeat` 关闭 gold 复跑 | OB-1 可复现性由 T03 单独保证 |

## 8. Step 6 Review（自查·单视角）

| 检查项 | 结论 |
|---|---|
| 依赖版本真实存在 | 全部标准库；Python 3.11 下限内（§4） |
| 签名可实现 | 七个适配器均可在进程内线程完成；无外部服务 |
| 无虚构库/函数 | 未引用未安装包；未用 3.12+ API |
| 兼容性 | 不 import `researchclaw`、不 import 旧 arc_bench 脚本，避免污染 |
| 低效操作已排除 | §3 八项 |
| 与设计对齐 | 每个 DESIGN 模块/决策在 §2 有对应实现；OB-2 的 U-6 口径一致 |
