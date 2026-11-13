# 调研文档：G4-M4 沙箱配额 / TTL / 137 / 四类逃逸

---
id: arc-g4-m4-sandbox-limits-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g4-m0-design-RESEARCH]
upstream: arc-g4-m0-design-RESEARCH
---

> **Feature**: arc-g4-m4-sandbox-limits（P-105，G4-M4）
> **创建日期**: 2026-11-13
> **状态**: verified
> **Spec 步骤**: Step 1-2
> **上游依据**: [M0 DESIGN §6/§9/§10/§11](../arc-g4-m0-design/DESIGN.md)、[P-100 复核 D-3/D-4](../../docs/arc-g4-m0-design-review-20261114.md)、G4 中期盘点（docs/arc-g4-midpoint-20261113.md，未入仓工作区文档）

---

## 1. 调研目标

**核心问题**:
1. A4-2（沙箱配额/标签）、A4-3（超限归因 137）、A4-6（TTL 到期产物先落盘）在当前实现中缺什么（E1 一手实证）？
2. 配额与 TTL 的真值源应落在 registry `sandbox_profiles` 还是 `ExperimentConfig`（D-Q1）？
3. 退出码 137 的可证伪判定机制是什么（D-Q2）？TTL 看护归属与「产物已落盘」如何可验证（D-Q3）？四类逃逸在无 Docker 的 CI 上如何验收（D-Q4）？

## 2. 调研方法

### 2.1 使用的工具

| 工具 | 用途 | 查询 |
|------|------|------|
| Read/Grep（本仓一手） | 源码现状实证 | docker_sandbox.py / sandbox.py / config.py / harness_template.py / factory.py / registry.py / registry.yaml / entrypoint.sh / _execution.py |
| Read | 测试与 CI 基线 | test_rc_docker_sandbox.py / e2e_docker_sandbox.py / ci.yml |
| Read | 流程规范 | SPEC_PROCESS.md v1.7.1 / step_enforce.py / spec_runner.py |

### 2.2 调研范围

- **时间**: 2026-11-13，基线 HEAD `844eabc`（P-104 已推送）
- **领域**: Docker 沙箱资源限制、容器生命周期、信号处理
- **排除**: 多 run 编排（M0 §11 / G7 非目标）、disk 配额强制（仅记录）

## 3. 调研发现

### 3.1 现状实证（E1，2026-11-13 本机，基线 844eabc）

| # | 事实 | 证据（一手） |
|---|------|-------------|
| F-1 | `docker run` 命令只有 `--memory=<n>m` / `--shm-size=<n>m`；无 `--cpus` / `--pids-limit` / `--label`；带 `--rm` | docker_sandbox.py `cmd = [...]` 初始块（`--name`/`--rm`/`-v`/`-w`/`--memory`/`--shm-size` 六项） |
| F-2 | `SandboxResult` 字段 = returncode/stdout/stderr/elapsed_sec/metrics/timed_out，**无超限归因字段** | sandbox.py `@dataclass(frozen=True) class SandboxResult` |
| F-3 | `DockerSandboxConfig` 无 cpu/pids/ttl 字段；`memory_limit_mb=8192`、`network_policy="setup_only"` 默认 | config.py `DockerSandboxConfig` |
| F-4 | registry `sandbox_profiles.default = {network: none, cpu: 2, memory: 4g, pids: 512, disk: 10g, ttl_sec: 1800}`，**与 config 8192m 数值冲突** | registry.yaml `sandbox_profiles:` 段 |
| F-5 | `sandbox_profile` 全仓仅出现在 registry.yaml（6 工具引用）+ registry.py（V-6/V-7 校验）+ routes/tools.py 注释（不暴露）——**零运行时消费** | 全仓 grep `sandbox_profile` 18 处逐条核对 |
| F-6 | harness **无** `atexit`、**无** SIGTERM handler；`finalize()` 仅在 NaN≥5 与显式调用路径触发 | harness_template.py 全文 |
| F-7 | entrypoint.sh 末行 `exec python3 -u ...` —— SIGTERM 直达 python（exec 替换 bash，PID 1 = python），**默认 handler 立即终止，finalize 不可达** | entrypoint.sh Phase 2 段 |
| F-8 | 超时路径：`subprocess.TimeoutExpired` → `returncode=-1`、`_kill_container`（SIGKILL）；正常路径直接信任 CLI 退出码，无 `docker inspect` | docker_sandbox.py `_execute` try/except 段 |
| F-9 | finally 清理 = `_remove_container`（`docker rm -f`，幂等）；`keep_containers=True` 语义当前**失效**（`--rm` 先行移除） | docker_sandbox.py `_execute` finally + `_remove_container` |
| F-10 | stage-14 主执行点 `create_sandbox(config.experiment, runs_dir / "sandbox")` 后 `sandbox.run_project(Path(exp_dir_path), timeout_sec=...)`，`runs_dir` 在作用域内可取 `run_id`；experiment_repair.py 与 code_agent.py 另有两类调用点 | _execution.py 主执行段、experiment_repair.py / code_agent.py grep |
| F-11 | 既有测试 36 项全 mock（零真实 Docker）；`tests/test_rc_docker_sandbox.py` **不在** ci.yml 固定清单；e2e 是脚本（7 场景）非 pytest | test_rc_docker_sandbox.py / ci.yml contract tests 清单 / e2e_docker_sandbox.py |
| F-12 | 本机 Docker 29.9.2 可用（OSType linux），但 `researchclaw/experiment:latest` 镜像**不存在** | 中期盘点 §0.1 实测 + e2e preflight 判据 |
| F-13 | `SandboxProtocol`（Structural）只约束 `run` / `run_project` 签名，`SandboxResult` 新增带默认值字段不破坏其它后端 | sandbox.py `SandboxProtocol` |

### 3.2 外部事实（T1）

| 事实 | 来源 | 验证状态 |
|------|------|---------|
| Docker cgroup OOM kill 使容器退出码 137（128+9）且 `State.OOMKilled=true`；`--rm` 容器退出后不可 inspect | Docker 官方文档（run/inspect 语义，P-100 D-3 已复核）；M0 DESIGN §6 | ✅（M0 冻结时已验） |
| `--cpus` 超限是 throttling，不产生 137 | P-100 D-3（复核批一手） | ✅ |
| `docker kill -s TERM` 发送 SIGTERM 至容器 PID 1；`docker kill`（无 -s）= SIGKILL → 137 | Docker CLI 参考 | ✅ |
| `--pids-limit` 下 fork 超限返回 EAGAIN，容器不死 | Docker 官方文档（pids-limit cgroup pids 控制器） | ✅ |

## 4. 综合分析

### 4.1 关键发现总结

1. **A4-2 缺口 = 三处 flag 缺失**：`--cpus`/`--pids-limit`/`--label rc.run` 全部不存在（F-1），且 config 无承载字段（F-3）。[置信度: ★★★★★]
2. **A4-3 缺口 = 无归因通道**：`SandboxResult` 无原因字段（F-2）+ `--rm` 使容器态不可回读（F-1/F-8），137 归因不可证伪。[置信度: ★★★★★]
3. **A4-6 当前不可达**（对中期盘点的定性订正）：不是「有地基待补」而是「需要新增信号处理」——F-6 + F-7 使 TERM 后 finalize 必然不执行。[置信度: ★★★★★]
4. **双源冲突是显式的**：registry 4g vs config 8192m（F-4），且 profile 零消费（F-5）——真值源必须裁决（D-Q1）。[置信度: ★★★★★]
5. **CI 无 Docker 是验收策略约束**：单测（mock）承担验收、e2e（本地实跑）承担证据的分层是唯一合规路径（D-Q4，SPEC_PROCESS RULE-3 禁止 skipif 充验收）。[置信度: ★★★★☆]

### 4.2 技术 landscape

Docker 原生提供 `--cpus`（CFS quota）、`--pids-limit`（pids cgroup）、`--memory`（cgroup OOM）、`--label`（元数据）。超限行为分三类：memory → OOM kill（137+OOMKilled）；cpus → throttle（不死）；pids → EAGAIN（不死）。业界沙箱（E2B/Firecracker）不在 v1 范围（M0 §11 D-4 拒绝）。

### 4.3 研究空白

容器退出后的状态回读（inspect）与父进程侧归因字段之间没有现成管道——需在去 `--rm` 后新增「inspect → 解析 → 单点映射」最小链路。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证

| 引用 | ID/位置 | 验证方式 | 状态 |
|------|---------|---------|------|
| M0 §6 沙箱冻结语义 | spec/arc-g4-m0-design/DESIGN.md §6 | 本会话 Read 全文 | ✅ |
| P-100 D-3/D-4 修正输入 | docs/PROGRESS.md P-100 行 | 本会话 Read | ✅ |
| entrypoint exec 语义 | researchclaw/docker/entrypoint.sh L57 | 本会话 Read | ✅ |
| Docker OOM/137/inspect | M0 冻结 + P-100 复核（T1 先行验证） | 沿用已验证结论 | ✅ |

### 5.2 技术声明验证

| 声明 | 来源 | 验证状态 |
|------|------|---------|
| 命令无 --cpus/--pids-limit/--label | F-1 一手 Read | ✅ |
| sandbox_profiles 零消费 | F-5 一手 grep 逐条 | ✅ |
| harness 无信号处理 | F-6 一手 Read 全文 | ✅ |
| test_rc_docker_sandbox 不在 CI 清单 | F-11 一手 Read ci.yml | ✅ |

### 5.3 待修正项

- [x] 中期盘点「Docker 本地可用」表述 → 订正为「daemon 可用但镜像不存在，e2e 需先 build」（F-12）
- [x] 中期盘点 A4-6「有地基待补」→ 订正为「需新增信号处理才可达」（F-6/F-7）

## 6. 对设计的输入

### 6.1 可用的技术方案

- 配额字段进 `DockerSandboxConfig`（frozen dataclass 扩展，向后兼容默认值）
- 去 `--rm` + finally 内 `docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}'` 回读
- per-sandbox TTL 守护线程（deadline = start + ttl_sec，TERM → grace → KILL）
- harness SIGTERM handler + `atexit` → `finalize()`（幂等双写无害）

### 6.2 关键约束

- M0 §6 冻结语义不得静默弱化；§10 I-6（默认网络行为不回退）；§11（不做多 run 编排、disk 仅记录）
- P-100 D-3：禁止把 `--cpus` 超限误判为 137
- P-100 D-4：TTL SIGKILL 分支不得宣称产物已落盘
- RULE-3：条件 skip 不得充当验收；RULE-5：本批 GLM 实施 → DeepSeek 复核
- SPEC_PROCESS T1 档：四文档齐全 + TDD 先红后绿

### 6.3 风险

- 去 `--rm` 后若清理路径失败，容器残留（缓解：finally 幂等 rm + e2e 取证）
- 默认开启 `--cpus`/`--pids-limit` 是行为变更（对既有长跑实验引入 throttling 面）
- harness 信号 handler 在非主线程导入时会抛 ValueError（缓解：主线程判定 + try/except 降级）

### 6.4 未决项登记（四元块）

- **U-1 registry `sandbox_profiles` 的运行时消费点**
  - **判据**：「实验即工具」批次把 profile 接入工具执行路径（消费点唯一化）
  - **触发条件**：G4 M5 之后的工具化实验批次开工时
  - **当前倾向**：保留 profile 为工具侧真值源，本批不消费（D-Q1-C 分层）
  - **证据等级**：E1（F-5 零消费实证）
- **U-2 父进程崩溃后的僵尸容器回收**
  - **判据**：存在跨进程的全局 reaper 且不误杀并发活跃容器
  - **触发条件**：出现真实僵尸容器事故，或 G7 编排批开工时
  - **当前倾向**：登记边界不实现（per-sandbox 线程随父进程死亡；§11 禁跨 run 干预）
  - **证据等级**：E1（线程生命周期）+ 设计推演

## 7. 参考文献

- [M0 DESIGN](../arc-g4-m0-design/DESIGN.md)（§6 沙箱冻结语义、§9 批次映射、§10 不变式、§11 非目标）
- [P-100 复核报告](../../docs/arc-g4-m0-design-review-20261114.md)（D-3 cpus-throttling、D-4 TTL 产物边界）
- G4 中期盘点（docs/arc-g4-midpoint-20261113.md，未入仓工作区文档；A4 矩阵缺口、M4 风险表；其 §0.1 两处读数以本文 F-12/F-13 订正）
- Docker 官方文档：run / inspect / pids-limit 语义（M0 冻结时 T1 验证沿用）

---

**Review 签字**: GLM-5.3-Flash（实施会话自审） 日期: 2026-11-13
