# P-105「G4-M4 沙箱配额 / TTL / 137 归因 / 四类逃逸」的独立异构复核（2026-11-13）

> **性质**：Layer-0 独立异构复核（T3 轻批，零生产代码/零门禁写入）。不采信 [P-105 实施](../spec/arc-g4-m4-sandbox-limits/IMPLEMENTATION.md) 的任何结论，全部一手重验：HEAD `6f8a72e`（19 文件 / +1548 −23）、两套件复跑、CI 固定清单全量复跑、wheel 独立构建、session digest 逐文件复算、**真 Docker 容器对抗探针 7 组 + 读码探针 6 组**（临时目录，零仓内残留）。
> **异构性**：实施会话为 **GLM-5.3-Flash**（`specwf-p105-arc-g4-m4-sandbox-limits.jsonl` model 字段实测 5/5 行），本复核为 **DeepSeek-V4.1-Flash**——RULE-5 交叉成立。
> **编号**：复核**并入 P-105 不占号**（沿用 P-103/P-104 先例）；M5=P-106 不变。
> **单向权限**：只标记问题，不改实现；本报告为唯一新增文件。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | 新增 17 用例 | `pytest tests/test_sandbox_boundary.py -q` | ✅ 17 passed |
| V-2 | docker 套件 45 | `pytest tests/test_rc_docker_sandbox.py -q` | ✅ 45 passed（36 既有 + 9 新增，零回退；审计 F-2 订正） |
| V-3 | 两套件合计 62 | 合并复跑 | ✅ 62 passed |
| V-4 | CI 43 文件 687/13skip | 按 `ci.yml` 固定清单全量复跑 | ✅ **687 passed / 13 skipped，0 failed** |
| V-5 | e2e 22/0 | `python tests/e2e_docker_sandbox.py`（本地 Docker 29.9.2 + slim 证据镜像） | ✅ **22 passed / 0 failed**，读数与 CHECKLIST C-13 一致 |
| V-6 | digest 8 文件零 mismatch | 本地 sha256 复算（raw/CRLF 双口径）+ 锚点回源 | ✅ 8/8 命中；`docs/PROGRESS.md#L112`、`arc-master-roadmap.md#L128` 均落在 P-105 / v1.4r 实体行 |
| V-7 | wheel 三连 | 独立 `python -m build --wheel`（临时 outdir） | ✅ 431 entries，`docker_sandbox.py` / `harness_template.py` 均在包内 |
| V-8 | session 五步 + 异构 | 逐行解析 jsonl | ✅ 5 行（research/design/implement/verify/finalize），model 全为 GLM-5.3-Flash |
| V-9 | 零残留 | `docker ps -a --filter name=rc-exp-` + `git status` | ✅ 全部探针后无容器残留；工作树仅 `docs/arc-g4-midpoint-20261113.md`（未入仓，与实施方声明一致） |

## 2. 对抗探针（X 表实测）

### 2.1 缺陷

| # | 探针 | 实测 | 判定 |
|---|---|---|---|
| X-1 | 真 OOM：`memory_limit_mb=64` + `np.ones((20000,20000))` | `rc=137`、`inspect` = `OOMKilled=true`、`limit_reason=resource_limit` | ✅ A4-3 正向成立（非 mock） |
| X-2 | 自愿 `sys.exit(137)` | `rc=137`、`OOMKilled=false` → **`limit_reason=resource_limit`** | **D-4 P3：137 归因仍不可证伪**（`_attribute_limit` 用 `inspected[1] == 137` 单独即判 resource_limit，见 [docker_sandbox.py#L745](../researchclaw/experiment/docker_sandbox.py)）；C-4「纯 137 启发式不存在」的措辞强于实现 |
| X-3 | TTL：`ttl_sec=6 / grace=15 / poll=1`，容器内 `report_metric` 后 sleep 120 | 6.2s 结束、`rc=143`、`limit_reason=ttl_timeout`、**`results.json` 落盘且 metrics 合并** | ✅ A4-6 正向成立；harness SIGTERM→finalize 真机可达 |
| X-4 | 容器内 `SIG_IGN` SIGTERM（强杀分支） | 4s+2s grace 后 KILL、`rc=137`、`limit_reason=ttl_timeout`（`ttl_timeout` 优先于 `resource_limit`） | ✅ 优先级正确；`docker kill`（SIGKILL）在 Docker 29.9.2 有效 |
| X-5 | `keep_containers=True` + `cpu_limit=1.5 / pids_limit=128` | `HostConfig.NanoCpus=1500000000`、`PidsLimit=128`、`Labels["rc.run"]=probe-d` | ✅ A4-2 真值落到 Docker 而非仅命令文本 |
| X-6 | kill 不可达时 `fired` 语义（monkeypatch `subprocess.run` 抛 `FileNotFoundError`，直接驱动 `_TtlWatcher`） | **`fired=True`，但 TERM 从未送达任何容器** | **D-2 P2：`_fired` 在 kill 之前置位**（[docker_sandbox.py#L97](../researchclaw/experiment/docker_sandbox.py)），归因可被伪造——违反 I-M4-4「不伪造归因」 |
| X-7 | TTL 与 `time_budget_sec` 耦合（读码） | `_execute` 只用 `cfg.ttl_sec`（默认 1800）；`timeout_sec` 独立传入，无 max/clamp | **D-3 P2：`time_budget_sec > 1800` 的长跑被提前截断**（CLI 明示 `7200 for HEP runs`，[cli.py#L1990](../researchclaw/cli.py)） |
| X-8 | `run_id` 覆盖点枚举（读码） | 有：`_execution.py:551/557/1644`；**无**：`:1770`（同函数 refine 修复重跑）、`:289`（bio/stat agent）、`:472`（code agent）、`runner.py:131`（ExperimentRunner）、`experiment_repair.py:810`、`code_agent.py:1394` | **D-1 P2：TTL/标签只覆盖 3/9 个 live 调用点**；IMPLEMENTATION §5.4 只登记 repair/code_agent，**漏登 `:1770` 与 `runner.py:131`** |
| X-9 | 证据与断言一致性（读码） | [test_sandbox_boundary.py#L252](../tests/test_sandbox_boundary.py) 为 `assert release.is_set() or True`（**恒真**）；T-10 只断言 `kill_cmds[0]` 是 TERM（[:L297](../tests/test_sandbox_boundary.py)），**KILL 分支无单测断言** | **D-5 P3：C-5「单测时序断言（TERM 先于 KILL）」不成立**——该时序实际由 X-4 证据层与读码支撑 |
| X-10 | harness 模块导入副作用（读码） | `harness_template.py` 模块底部调用 `_install_sigterm_handler()`；`tests/test_rc_executor.py` 运行期 import 该模块 → **pytest 宿主进程的 SIGTERM handler 被替换** | **D-6 P3：模板模块对宿主有信号层副作用**（容器内无害，宿主侧不该由 import 决定进程退出语义） |

### 2.2 通过项

| # | 探针 | 结果 |
|---|---|---|
| X-11 | `docker ps -a` 残留扫描（全探针后） | ✅ 零 `rc-exp-*`；去 `--rm` 后 finally 幂等清理真实有效 |
| X-12 | `keep_containers` 语义 | ✅ 由「被 `--rm` 架空」转为真实保留（X-5 依赖此点才可 inspect） |
| X-13 | 路径逃逸 `../` | ✅ 既有 `tests/test_entry_point_validation.py` 覆盖（本批未改，零回退） |
| X-14 | 网络外联 | ✅ e2e `--network=none` 拒绝分支 22/22 中复跑通过，I-6 未回退 |
| X-15 | `limit_reason` 默认值兼容 | ✅ `SandboxResult` 新字段带默认值，ssh/agentic 后端零改动（V-3 全绿旁证） |
| X-16 | 不可解析 inspect → 不归因 | ✅ e2e + T-11 双证；真机 `docker inspect` 格式串与解析器一致（X-1/X-5 实测） |

## 3. 缺陷

### D-1（P2）TTL / `rc.run` 标签只覆盖 3 个调用点，边界登记不完整

- **根因**：`run_id` 作为可选参透传到 `_execute`，只有 stage-14 主执行（`_execution.py:551/557`）与一处重跑（:1644）传了值；同文件的 refine 修复重跑（:1770）、bio/stat agent（:289）、code agent（:472）、`ExperimentRunner.run_experiment`（`runner.py:131`，**形参收了 `run_id` 却未下传**）均为 live 路径且无 `run_id`。
- **影响**：① 这些路径无 `rc.run` 标签、无 TTL 宽限 TERM → 产物落盘保障缺失，只剩 `timeout_sec` 直接 SIGKILL；② IMPLEMENTATION §5.4 与 CHECKLIST C-8 的边界清单**不完整**（漏 `:1770`/`runner.py:131`），登记的可信度受损；③ A4-6 的「TTL 看护」在这些路径上不成立。
- **修复建议（供收敛批）**：`ExperimentRunner.run_experiment` 直接把已接收的 `run_id` 传给 `sandbox.run`；`:1770` 补 `run_id=stage_dir.name`；agent 路径（:289/:472）若容器名可构造则补，否则显式登记「无 TTL，仅 timeout」。
- **回归护栏**：加一条「全仓 `run(`/`run_project(` 调用点必须显式传 `run_id` 或在 IMPLEMENTATION §5.4 白名单内」的守卫（可用 AST 扫描，复用 M5 的守卫思路）。

### D-2（P2）`_fired` 先于 kill 置位、deadline 早于容器创建 → `ttl_timeout` 可被伪造

- **根因**：① `_TtlWatcher._fire()` 第一行 `self._fired = True`，之后才尝试 `docker kill`，且 `_kill` 吞掉失败只告警（[L96-117](../researchclaw/experiment/docker_sandbox.py)）；② `run()` 的 `deadline = time.monotonic() + ttl` 在线程启动时计算（L85），而线程 `start()` 发生在 `subprocess.run(docker run)` **之前**（L381 vs L388）——镜像冷拉取/启动耗时被计入 TTL。
- **影响**：X-6 实证「kill 从未送达仍 `fired=True`」。两类可复现场景：镜像冷拉取超过 `ttl_sec`（容器尚未创建）；容器恰在 deadline 前自行正常退出（`_stop` 与 `_fire` 竞态，[L92-94](../researchclaw/experiment/docker_sandbox.py)）。两者都会把一个**正常完成**的 run 标成 `ttl_timeout`，与 I-M4-4 冲突。
- **修复建议**：`_fired` 改为「TERM 返回码 0 或 `docker inspect` 证实容器仍 running」后再置位；deadline 锚定容器启动（最简：watcher 在 `subprocess.Popen` 之后/`docker run` 入口处 start，或先 `docker create` 再 `start`）。
- **回归护栏**：把 X-6 形态固化为用例（kill 抛 `FileNotFoundError` → `limit_reason` 必须为 `None`）。

### D-3（P2）TTL 与 `time_budget_sec` 脱钩，长跑被 1800s 静默截断

- **根因**：`_execute` 只读 `cfg.ttl_sec`（默认 1800），与调用方传入的 `timeout_sec`（= `experiment.time_budget_sec`）无任何约束关系。
- **影响**：默认预算 300s 下无感；但 CLI 明示「1800 for quick ML, **7200 for HEP runs**」，wizard 亦有 1800 档。用户把预算调到 3600/7200 后，容器在 1800s 被 TERM/KILL，run 以非零码收尾，而 `limit_reason` 在生产路径无消费点（O-3）→ 用户看到的是「莫名失败」而非「TTL 截断」。这是本批引入的行为回归。
- **修复建议**：`effective_ttl = max(cfg.ttl_sec, timeout_sec + cfg.kill_grace_sec + 60)`，或 `ttl_sec <= 0` 语义改为「跟随 timeout」；并在 DESIGN §4.3 写明二者关系。
- **回归护栏**：构造 `timeout_sec=3600, ttl_sec=1800` 的用例，断言 watcher 的 deadline 不早于 `timeout_sec`（或显式断言截断并记录）。

### D-4（P3）自愿 `exit(137)` 被判 `resource_limit`，「可证伪」只成立于 OOMKilled 维度

X-2 实证。`_attribute_limit` 的 `inspected[1] == 137` 分支等价于「inspect 读取的 137 即资源限制」，无法区分程序自愿 `sys.exit(137)`（也无法区分容器外部的非 OOM SIGKILL，虽然那种归类尚可接受）。建议二选一：`resource_limit` 仅在 `OOMKilled=true` 时给出，其余 137 归 `None`/`nonzero_exit`；或保留实现但把 CHECKLIST C-4 与 DESIGN §2.2 的措辞降为「OOM 可证伪，137 为兜底」。

### D-5（P3）C-5 的证据指针与测试实际断言不符

原文称「T-8 真线程，TERM 先于 KILL」，实际 T-8 只有 `assert release.is_set() or True`（恒真），KILL 未断言；T-10 只断言首条 kill 为 TERM（注释写了「last (if any) is KILL」但无断言）。时序正确性目前只由 X-4 真机探针与读码支撑。建议删恒真行、补 `kill_cmds[1][:2] == ["docker","kill"]` 且不含 `-s`。

### D-6（P3）`harness_template` 导入即安装 SIGTERM handler，宿主进程受影响

模块底部无条件调用 `_install_sigterm_handler()`。容器内这是设计意图（`exec python3` 后 PID 1 需要 handler），但该模块同时被宿主测试 import（`test_rc_executor.py`），副作用是**宿主进程的 SIGTERM 语义被改写**（改为 `atexit` + `exit 143`）。建议：安装动作移入 `get_harness()` / `main` 入口，或由环境变量（容器内设置）门控；容器内行为不变。

## 4. 观察项（O 表）

| # | 内容 | 处置 |
|---|---|---|
| O-1 | 超时路径不做 inspect（`except TimeoutExpired` 只 kill）→ 「OOM 与 timeout 同时发生」归 `timeout` | 与 DESIGN §3.1 一致，记录；若收敛 D-2 可顺带在 kill 后补一次 inspect |
| O-2 | `_TtlWatcher._kill` 只捕 `FileNotFoundError`/`TimeoutExpired`，其它 `OSError` 会让守护线程异常终止（`_fired` 已置位） | 建议 `except OSError`；与 D-2 同一收敛点 |
| O-3 | `limit_reason` 在生产流水线**无消费点**（仅 e2e/单测读取），`ExperimentRunner` 也不把它并入 `error` | A4-3 属机制验收口径成立；建议后续批次在 `experiment_history`/`tool.result` 承接（与 M3 的 F-5 同类问题） |
| O-4 | 符号链接解引用把**宿主内容拉进 staging**（e2e Test 11 分支 B 实证；`copytree` 未传 `symlinks`，默认 `False` 即解引用）；`validate_entry_point_resolved` 只保证入口在 staging 内解析 | 既有行为（非本批引入），但在默认 `network=setup_only` 下可被 setup 阶段外发。建议登记为后续「宿主读取面」议题，或拒绝项目内指向仓外的符号链接 |
| O-5 | M0 §6 冻结文本「每 30s 扫描 `rc.run` 标签容器」→ 实现为 per-sandbox 线程（不跨 run 扫描） | 已在 M0 §6 回边与 §11 登记；建议在 §6 表内加一行指针，避免后续按字面审查 |
| O-6 | `ttl_poll_sec` 默认 30s → 实际截断点可晚于 `ttl_sec` 最多 30s | 可接受，登记 |

## 5. 取证矩阵（RULE-6）

| 手段 | 覆盖 | 结果 |
|---|---|---|
| pytest（E1） | V-1..V-4 | 17 / 45 / 62 / 687+13skip |
| digest 复算（E1） | V-6 | ✅ 8 文件零 mismatch、锚点真实 |
| 真容器运行时探针（E2，10 项） | X-1..X-7、X-11、X-12、X-16 | **2 P2 + 1 P3**（D-2/D-3/D-4 的 D-2 由 X-6 直接实证） |
| e2e 复跑（E2） | V-5 | ✅ 22/0 |
| wheel（E2） | V-7 | ✅ 431 entries |
| 读码（E3） | X-7..X-10（4 项）+ D-1 根因 + D-3 耦合点 + D-6 副作用 | ✅ |
| 盲区扫描（E4） | 全仓 `run(`/`run_project(` 调用点枚举、container 残留、`limit_reason` 消费点 | ✅ 9 个调用点全枚举 |

## 6. 结论与处置

- **主线机制成立**：A4-2（配额三 flag + `rc.run` 标签真机落到 `HostConfig`）、A4-3（真 OOM → 137 → `resource_limit`；cpus throttling 不产 137）、A4-6（TTL → TERM → harness finalize → `results.json` 落盘 → `ttl_timeout`；SIGKILL 分支优先级正确且不宣称产物）均一手复验为真，非 mock。I-M4-1/2/3/5/6/7 未见违反。
- **3 项 P2 阻塞验收关闭**：
  - **D-1**：TTL/标签仅覆盖 3/9 个 live 调用点（含 `runner.py` 收了 `run_id` 却不下传），边界登记漏项；
  - **D-2**：`_fired` 先于 kill 置位 + deadline 早于容器创建 → 可伪造 `ttl_timeout`（X-6 实证）；
  - **D-3**：TTL 与 `time_budget_sec` 脱钩，>1800s 的长跑被静默截断（本批引入的行为回归）。
- **3 项 P3**（D-4 137 可证伪性口径、D-5 证据指针失实、D-6 宿主信号副作用）+ **O-1..O-6** 登记。
- **复核意见**：**P-105 暂不能验收关闭**（同 P-103/P-104 先例：主线成立 + P2 待收敛）。建议收敛批沿用「并入 P-105 不占号」模式，修 D-1/D-2/D-3，补 X-6 与 `time_budget_sec>ttl_sec` 两条回归护栏，并订正 CHECKLIST C-4/C-5/C-8 的措辞与 IMPLEMENTATION §5.4 的边界表；随后 M0 §9 M4 行保持「已完成」但加注复核收敛记录。
- 按 RULE-5 单向权限，本复核未改任何实现文件；探针脚本与 wheel 产物均在 `$env:TEMP`。**审计订正（F-1）**：复核收尾声明「已清理」失实——`rc_m4_probe` 残留由审计于 2026-11-13 删除并复验 `Test-Path=False`。工作树仅保留实施方未入仓的 `docs/arc-g4-midpoint-20261113.md` 与本报告。
