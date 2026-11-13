# 设计文档：G4-M4 沙箱配额 / TTL / 137 / 四类逃逸

---
id: arc-g4-m4-sandbox-limits-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-13
depends: [arc-g4-m4-sandbox-limits-RESEARCH]
upstream: arc-g4-m4-sandbox-limits-RESEARCH
---

> **Feature**: arc-g4-m4-sandbox-limits（P-105，G4-M4）
> **创建日期**: 2026-11-13
> **状态**: verified
> **Spec 步骤**: Step 3-4
> **基于调研**: [RESEARCH.md](./RESEARCH.md)
> **上游契约**: [M0 DESIGN §6](../arc-g4-m0-design/DESIGN.md)（不得静默弱化）

---

## 1. 设计目标

把 M0 §6 冻结的沙箱五要素（标签 / 网络 / 配额 / 超限归因 / TTL）落到 `DockerSandbox` 单一执行路径：A4-2（配额与标签生效）、A4-3（137 可证伪归因 `resource_limit`）、A4-6（TTL 到期 TERM 宽限期内产物先落盘再回收）；四类逃逸（路径 / 符号链接 / 网络外联 / fork bomb）具备可验收与可取证两层。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---------|---------|------|
| F-1/F-3 配额三 flag 与 config 字段缺失 | config 新增 5 字段 + 命令构造扩展 | RESEARCH §3.1 |
| F-4/F-5 双源冲突且 profile 零消费 | D-Q1-C 双源显式分层 | RESEARCH §4.1-4 |
| F-1/F-8 `--rm` 使 137 归因不可证伪 | D-Q2-A 去 `--rm` + inspect 回读 | RESEARCH §4.1-2 |
| F-6/F-7 harness 无信号处理 → A4-6 不可达 | D-Q3-A harness SIGTERM + atexit | RESEARCH §3.1 |
| F-11 CI 无 Docker | D-Q4-A 验收层单测 / 证据层 e2e 分层 | RESEARCH §4.1-5 |

### 2.2 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|------|------|---------------|
| D-1（D-Q1-C） | **双源显式分层**：`DockerSandboxConfig` 是实验执行路径唯一真值源（默认 `cpu_limit=2.0`、`pids_limit=512`、`memory_limit_mb=8192` 不回退、`ttl_sec=0` 即 auto 跟随本次运行 timeout 预算）；registry `sandbox_profiles` 保留为工具侧真值源，消费点 =「实验即工具」后续批次（RESEARCH U-1 登记）。4g/8192m 冲突不改 M0 §2 冻结值，登记 O 项 | F-4/F-5；A4-2 必须默认生效否则「文档失信」 | 拒 A（只扩 config、profile 死配置 → §6 语义形同未落实）；拒 B（registry 为唯一真值源 → experiment 层反向依赖 tools 层 + 8GB→4GB 行为回退 + registry 损坏放大面） |
| D-2（D-Q2-A) | **去 `--rm`**；正常退出路径 finally 前置 `docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}'` 回读；`OOMKilled=true 或 inspect ExitCode==137 → resource_limit`；inspect 失败/不可解析 → 不归因（None），**不做纯 137 启发式** | F-1/F-8；A4-3「可证伪」 | 拒 B（保留 `--rm` 仅按 137 分类 → 无法区分程序自愿 exit(137) 与内核 kill，违反可证伪） |
| D-3（D-Q3-A） | **per-sandbox TTL 守护线程**（daemon=True）：deadline = 本容器 start + 有效 TTL（显式 `ttl_sec` 为硬上限；默认 0 跟随 timeout 预算，见 §4.3），到点 `docker kill -s TERM` → 等待 `kill_grace_sec` → 未停则 `docker kill -s KILL`；主流程 finally 中 stop + join。**只管自己的容器**（不等价于全局 reaper，不做 docker ps 跨容器扫描——§11 禁跨 run 干预）；同时 harness 加 SIGTERM handler + atexit → finalize() | F-6/F-7；A4-6 | 拒 B（全局单例看护/跨 run 编排 → M0 §11 非目标）；拒「仅全局 reaper」（父进程存活时主归因通道丢失） |
| D-4（D-Q4-A） | **两层拆分**：验收层 = 单测全 mock（命令构造 / inspect 解析 / TTL 状态机 / 时序），任何机器可跑可失败；证据层 = 本地 Docker e2e 实跑四类逃逸 + OOM + TTL，按 RULE-3 quarantine 四要素登记（Owner=P-105 实施方；Deadline=G4 收尾前；降权=每次运行但不阻塞结论；Re-qualification=CI 具备 Docker 后转阻塞） | F-11/F-12；RULE-3 | 拒 B（pytest `skipif(no docker)` 充验收 → 违反 RULE-3 防 skip-and-forget） |
| D-5 | **退出码/原因映射唯一实现**：`ttl_fired → ttl_timeout`（优先 1）> `OOMKilled/137 → resource_limit`（优先 2）> `TimeoutExpired → timeout`（优先 3）> 正常 → None。映射只存在于 docker_sandbox 的单函数内，禁止调用点二次解释 | M0 §6 + 简报冻结表 | 拒「在各调用点分别归因」（漂移面） |
| D-6 | **诚实边界**：① SIGKILL（grace 耗尽）分支只断言 `limit_reason=ttl_timeout`，不断言产物落盘（P-100 D-4）；② `--cpus` 超限是 throttling，不产生 137（P-100 D-3）；③ `rc.tool` 标签在实验路径省略（无工具上下文）；④ `run_id=None` 时无标签且 TTL 禁用（禁止通配清理他人容器） | P-100 D-3/D-4 | — |

### 2.3 职责边界

- **职责内**：`DockerSandbox`（配额 flag / 标签 / inspect 归因 / TTL 线程）、`DockerSandboxConfig` 及 yaml 解析、`SandboxResult.limit_reason`、`harness_template.py`（信号/退出兜底）、stage-14 主执行点传 `run_id`、新增单测 + e2e 场景。
- **职责外**：ssh_remote / colab / agentic 等其它后端（`SandboxProtocol` 兼容即可）；registry profile 消费（U-1）；全局僵尸容器 reaper（RESEARCH U-2）；disk 配额强制；M3 的 `tool.result` 层 137 承接（实验执行不是注册表工具，**不得**在本批伪造 `tool.call/tool.result` 事件——会被 M3 orphan 扫描判脏）。

## 3. 架构设计

### 3.1 执行时序（单一容器路径）

```text
run()/run_project()
  └─ _execute(staging, entry_point, timeout_sec, run_id?)
       ├─ _build_run_command(): + --cpus --pids-limit --label rc.run（无 --rm）
       ├─ TTL 线程启动（仅 run_id 且 effective_ttl>0；先等容器创建，
       │   deadline = 容器创建 + effective_ttl）
       ├─ subprocess.run(docker run ...)                    # 阻塞至容器退出
       │    ├─ TimeoutExpired → _kill_container(SIGKILL) → timed_out
       │    └─ 正常返回 → _inspect_container() → (oomkilled, exitcode) | None
       ├─ finally: TTL 线程 stop + join；非 keep_containers → _remove_container
       └─ _attribute_limit(): ttl_fired→ttl_timeout > oom/137→resource_limit
                              > timed_out→timeout > 正常→None
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|------|------|------|------|------|
| `DockerSandboxConfig`（config.py） | 承载 cpu_limit/pids_limit/ttl_sec/kill_grace_sec/ttl_poll_sec + yaml 解析 | yaml docker 段 | frozen dataclass | 无 |
| `DockerSandbox._build_run_command` | 追加 `--cpus=<f>`、`--pids-limit=<n>`、`--label rc.run=<run_id>`；删除 `--rm` | config + run_id | cmd list | config |
| `DockerSandbox._execute` | 线程生命周期 + inspect 回读 + 单点映射 | staging/entry/run_id | SandboxResult(+limit_reason) | config |
| `DockerSandbox._inspect_container` | `docker inspect --format ...` → `(bool,int)|None` | container_name | tuple/None | docker CLI |
| `DockerSandbox._ttl_watch` | deadline TERM→grace→KILL；ttl_fired 标志 | container_name/cfg | stop_event + ttl_fired | docker CLI |
| `harness_template.py` | SIGTERM handler（finalize→exit 143）+ atexit finalize | 信号 | results.json | stdlib |
| `sandbox.SandboxResult` | 新增 `limit_reason: str\|None = None` | — | 兼容扩展 | 无 |
| stage-14 调用点（_execution.py） | 传 `run_id=runs_dir.name` | runs_dir | run()/run_project() | factory |

### 3.3 数据流

config.yaml `experiment.docker.{cpu_limit,pids_limit,ttl_sec,kill_grace_sec,ttl_poll_sec}` → `_parse_experiment_config` → `DockerSandboxConfig` → 命令 flags / TTL 线程参数。容器侧：SIGTERM → harness finalize → staging/results.json（volume）→ 宿主 `_execute` 读回并入 metrics（既有路径不变）。

### 3.4 控制流

TTL 线程主循环：先以 `docker inspect` 探测容器创建，成功后才起算 deadline；`stop_event.wait(min(ttl_poll_sec, remaining))`；`now ≥ deadline` → `docker kill -s TERM` → 仅当 TERM 返回码为 0 才置 `ttl_fired`（投递失败不归因）→ `stop_event.wait(kill_grace_sec)` → **未 stop 才** `docker kill -s KILL`。主流程 finally：`stop_event.set()` → `join(timeout=kill_grace_sec+1)`。容器因 TERM 自行退出时 subprocess.run 先返回，stop 置位使 KILL 分支跳过（对已退出容器 KILL 无害但避免噪声调用）。

## 4. 接口定义

### 4.1 SandboxResult 扩展

```python
@dataclass(frozen=True)
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float
    metrics: dict[str, object]
    timed_out: bool = False
    limit_reason: str | None = None   # ttl_timeout | resource_limit | timeout | None
```

### 4.2 run / run_project 签名扩展（可选参，不破坏 Protocol）

```python
def run(self, code: str, *, timeout_sec: int = 300,
        run_id: str | None = None) -> SandboxResult: ...
def run_project(self, project_dir: Path, *, entry_point: str = "main.py",
                timeout_sec: int = 300, args: list[str] | None = None,
                env_overrides: dict[str, str] | None = None,
                run_id: str | None = None) -> SandboxResult: ...
```

`SandboxProtocol` 不改（可选参为超集）；ExperimentSandbox / ssh / colab 等后端零改动。

### 4.3 DockerSandboxConfig 扩展

```python
cpu_limit: float = 2.0          # ≤0 → 不加 --cpus
pids_limit: int = 512           # ≤0 → 不加 --pids-limit
ttl_sec: int = 0                # 0 → auto（跟随本次 timeout 预算）；>0 → 显式硬上限
kill_grace_sec: int = 10        # TERM→KILL 宽限
ttl_poll_sec: float = 30.0      # 线程轮询粒度（测试可调小）
```

有效 TTL（收敛批 D-3 定稿）：`ttl_sec > 0` → 取 `ttl_sec`（显式硬上限，可短于预算；A4-6 正向路径：TERM → harness finalize → grace 内 KILL）；`ttl_sec == 0`（默认）→ `timeout_sec + kill_grace_sec`（从容器创建起算，**绝不早于调用方预算**，仅作容器回收兜底）。默认值不得把 `experiment.time_budget_sec` 调大（CLI 明示 HEP 用 7200）的长跑提前截断；反之，显式设小 `ttl_sec` 即运营者主动选择的硬上限。

默认值语义：`cpu_limit/pids_limit` 与 registry `default` profile 数值一致（D-1 分层下不冲突）；`memory_limit_mb=8192` 保持既有（8192m vs profile 4g 冲突按 D-1 以 config 为准，O 项登记）。**既有行为差异面**：此前命令无 cpus/pids 限制，默认开启后长跑实验可能被 throttling（诚实登记，非回退——原先无保护）。

### 4.4 内部接口

```python
def _inspect_container(cls, name) -> tuple[bool, int] | None:
    """docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}'；
    输出可解析 → (OOMKilled, ExitCode)；失败/不可解析 → None（不归因）。"""

def _attribute_limit(ttl_fired: bool, timed_out: bool,
                     inspected: tuple[bool, int] | None) -> str | None:
    """D-5 唯一映射：ttl_fired→ttl_timeout；inspected 且 (oom or exit==137)→resource_limit；
    timed_out→timeout；否则 None。"""

class _TtlWatcher(threading.Thread):  # daemon=True
    def __init__(self, container_name, ttl_sec, kill_grace_sec, poll_sec): ...
    def stop(self) -> None: ...          # stop_event.set()
    def run(self) -> None: ...           # TERM → grace → KILL（未 stop 时）→ ttl_fired=True
    @property
    def fired(self) -> bool: ...
```

## 5. 替代方案

### 5.1 方案 A：config 分层 + inspect 回读 + per-sandbox TTL（选择）

见 §2.2 D-1..D-4。优点：默认生效、可证伪、零跨 run 干预、兼容面最小。缺点：去 `--rm` 引入清理责任集中到 finally；TTL 覆盖不了父进程崩溃后的僵尸容器（诚实登记 U-2）。选择理由：全部满足 M0 §6 冻结语义且不与 §11 冲突。

### 5.2 方案 B：registry 为唯一真值源（否决）

`create_sandbox` 读 registry default profile 注入。否决理由：experiment → tools 反向依赖；registry 损坏使 pipeline 无法启动（fail-closed 放大面）；8GB→4GB 行为回退。

### 5.3 方案 C：pytest skipif 充当四类逃逸验收（否决）

否决理由：RULE-3 明令禁止「工具链不存在」的条件 skip 当验收依据（skip-and-forget）。

## 6. 数据结构

见 §4.1/§4.3。无新增持久化结构；`limit_reason` 随 SandboxResult 进入既有 runner 结果链路（只增不改）。

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---------|---------|------------|
| inspect 失败/输出不可解析 | 静默降级为 None（不归因），logger.debug | 无（不伪造归因） |
| TTL 线程内 docker kill 失败 | logger.warning，不置 `ttl_fired`、不归因（D-2） | 无 |
| 信号 handler 在非主线程注册 | try/except ValueError 降级（仅主线程注册） | 无 |
| finalize OSError | 既有 warning 路径保持 | stderr WARNING |
| grace 耗尽 SIGKILL | limit_reason=ttl_timeout；**不宣称产物落盘**（D-6①） | results.json 可能缺失 |
| 去 --rm 后清理失败 | `_remove_container` 幂等 + e2e 取证无残留 | 无 |

## 8. 不变式（Invariants）

1. I-M4-1 退出码/原因映射**唯一实现**于 `_attribute_limit`（全仓无第二处解释 137/ttl）。
2. I-M4-2 `run_id=None` ⇒ 无 `rc.run` 标签且 TTL 线程不启动（禁止通配清理）。
3. I-M4-3 TTL 线程只对本批创建的容器名执行 kill（T-10 跨 run 隔离）。
4. I-M4-4 inspect 不可解析，或 TTL 的 TERM 未投递成功 ⇒ `limit_reason=None`（不伪造归因）。
5. I-M4-5 harness `finalize()` 幂等（信号路径 + atexit 双写无害）。
6. I-M4-6 既有 36 项 test_rc_docker_sandbox 零回退（新字段全带默认值、新参数全可选）。
7. I-M4-7 network_policy 默认与 `--network none` 行为不回退（M0 I-6）；GPU/shm 语义不动；disk 不强制（M0 §11）。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 全部决策可追溯到 RESEARCH F-1..F-13
- [x] 无未经验证的假设（Docker 语义沿用 M0/P-100 已验证结论）
- [x] 无归因扭曲（cpus≠137、SIGKILL 不宣称产物均显式登记）

### 9.2 替代方案审查

- [x] ≥2 个替代方案（§5.2/§5.3）且各有否决理由

### 9.3 职责边界审查

- [x] 不吞并 registry 消费（U-1）、不做全局 reaper（U-2）、不伪造 tool.result（M3 边界）

## 10. 对实施的输入

### 10.1 关键工程约束

1. flags 形式：`--cpus=<float>`、`--pids-limit=<int>`、`--memory=<n>m`（既有）、`--label rc.run=<run_id>`；`rc.tool` 实验路径省略（D-6③）。
2. `run_id` 由调用方显式传入（stage-14 = `runs_dir.name`）；experiment_repair / code_agent 调用点本批**不**接 run_id（登记边界，quota 仍由 config 默认生效）。
3. TTL 线程异常一律降级 warning；`ttl_poll_sec` 为 float 以支持测试加速。
4. 映射只实现一次（I-M4-1）。
5. yaml 解析：`_safe_float(cpu_limit)` / `_safe_int(pids_limit|ttl_sec|kill_grace_sec)` + `_safe_float(ttl_poll_sec)`，坏值回退默认（与既有 `_safe_*` 纪律一致）。
6. `harness_template.py` 是注入模板：改动以字符串形态进入容器，单测用源码断言（含 `atexit` / `SIGTERM` / `finalize` 字样与结构）+ e2e 行为验证。

### 10.2 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 默认 --cpus=2 对长跑实验 throttling | DESIGN §4.3 显式登记；配置可显式关闭（≤0） |
| 去 --rm 后容器残留 | finally 幂等 rm + e2e 断言 `docker ps` 无残留 |
| mocked subprocess 下 inspect 误归因 | inspect 解析失败 → None（I-M4-4），单测显式覆盖两分支 |
| TTL 线程与主流程竞态 | stop_event 单向推进 + join 上限；KILL 仅在未 stop 时执行 |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**：

- **U-1 registry profile 消费点**（继承 RESEARCH U-1）：判据=工具化实验批次接入 profile；触发=M5 后；倾向=保留分层；证据等级 E1。
- **U-2 僵尸容器全局回收**（继承 RESEARCH U-2）：判据=全局 reaper 且零误杀；触发=真实事故或 G7；倾向=登记不实现；证据等级 E1+推演。

**11.2 决策矩阵**：不启用——D-1..D-6 均为可逆（Type-2）或有 M0/P-100 先行裁决背书的 Type-2 实施，无需新开矩阵。

---

**Review 签字**: GLM-5.3-Flash（实施会话自审） 日期: 2026-11-13
