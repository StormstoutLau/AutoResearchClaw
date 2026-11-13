# 实施文档：G4-M4 沙箱配额 / TTL / 137 / 四类逃逸

---
id: arc-g4-m4-sandbox-limits-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g4-m4-sandbox-limits-DESIGN, arc-g4-m4-sandbox-limits-RESEARCH]
upstream: arc-g4-m4-sandbox-limits-DESIGN
---

> **Feature**: arc-g4-m4-sandbox-limits（P-105，G4-M4）
> **创建日期**: 2026-11-13
> **状态**: verified
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md)（及 [RESEARCH.md](./RESEARCH.md)）

---

## 1. 实现目标

按 DESIGN §2.2 D-1..D-6 与 §4 接口，把配额 flags、`rc.run` 标签、inspect 归因、TTL 看护、harness 信号兜底、调用点 `run_id` 传递落进代码，并以 TDD（先红后绿）交付 DESIGN §10.3 验收测试矩阵。**测试通过 ≠ 设计落地**（ADD Iron Law）。

## 2. 环境与依赖

| 项 | 版本 | 说明 |
|----|------|------|
| Python | 3.13.5（开发）/ 3.11.15（兼容目标） | 既有双环境纪律 |
| Docker | 29.9.2（本机，linux OSType） | 仅 e2e 证据层需要 |
| 新增依赖 | **无** | stdlib threading/signal/atexit |
| 基线 | HEAD `844eabc` | P-104 已推送 |

## 3. 文件清单（改动面）

| # | 文件 | 动作 | 内容 | 回退点 |
|---|------|------|------|--------|
| 1 | `researchclaw/config.py` | 改 | `DockerSandboxConfig` +5 字段；`_parse_experiment_config` docker 段解析 | 单文件 revert |
| 2 | `researchclaw/experiment/sandbox.py` | 改 | `SandboxResult` + `limit_reason: str\|None = None` | 单行 revert |
| 3 | `researchclaw/experiment/docker_sandbox.py` | 改 | `_build_run_command` flags/标签/去 `--rm`；`_inspect_container`；`_TtlWatcher`；`_execute` 生命周期与映射；`run/run_project` 加 `run_id` | 单文件 revert |
| 4 | `researchclaw/experiment/harness_template.py` | 改 | SIGTERM handler + `atexit` → `finalize()`（幂等） | 单文件 revert |
| 5 | `researchclaw/pipeline/stage_impls/_execution.py` | 改 | stage-14 主执行与重跑调用点传 `run_id=runs_dir.name` | 按调用点 revert |
| 6 | `tests/test_sandbox_boundary.py` | 新 | T-1..T-14（先红） | 删除文件 |
| 7 | `tests/test_rc_docker_sandbox.py` | 改 | 命令构造断言扩展（36 项零回退） | 按 hunk revert |
| 8 | `tests/e2e_docker_sandbox.py` | 改 | 增 OOM/TTL/fork-bomb/符号链接场景（证据层） | 按 hunk revert |
| 9 | `.github/workflows/ci.yml` | 改 | contract tests 固定清单 + `test_sandbox_boundary.py` + `test_rc_docker_sandbox.py` | 单 hunk revert |
| 10 | `spec/arc-g4-m4-sandbox-limits/` | 新 | 四文档 | 删除目录 |
| 11 | `spec/arc-g4-m0-design/DESIGN.md` | 改 | §6/§9 受控回边（P-099 rebind 语义落地） | 单 hunk revert |
| 12 | `docs/PROGRESS.md` / `arc-master-roadmap.md` | 改 | P-105 行 / v1.4r | 单 hunk revert |

## 4. 实现顺序（TDD）

1. **红**：写 `tests/test_sandbox_boundary.py`（T-1..T-14，基于 CHECKLIST §2 DoR/DoD）→ 运行确认失败（ImportError/AttributeError/断言失败均算红）。
2. **绿**：config.py → sandbox.py → docker_sandbox.py → harness_template.py → _execution.py 调用点 → 逐段跑绿。
3. **扩展**：test_rc_docker_sandbox.py 命价新断言（`--rm` 不存在、`--cpus`/`--pids-limit` 默认存在）+ ci.yml 清单。
4. **e2e**：本地 build 镜像 → 四类逃逸/OOM/TTL 场景取证（不阻塞，quarantine 登记）。
5. **回归**：五套件 + wheel 三连。

## 5. 接口实现细节

### 5.1 config.py

```python
# DockerSandboxConfig 新增（frozen=True 不变）
cpu_limit: float = 2.0
pids_limit: int = 512
ttl_sec: int = 1800
kill_grace_sec: int = 10
ttl_poll_sec: float = 30.0

# _parse_experiment_config docker 段
cpu_limit=max(0.0, _safe_float(cfg.get("cpu_limit"), fallback=2.0)),
pids_limit=max(0, _safe_int(cfg.get("pids_limit"), fallback=512)),
ttl_sec=max(0, _safe_int(cfg.get("ttl_sec"), fallback=1800)),
kill_grace_sec=max(0, _safe_int(cfg.get("kill_grace_sec"), fallback=10)),
ttl_poll_sec=max(0.05, _safe_float(cfg.get("ttl_poll_sec"), fallback=30.0)),
```

约束：坏值回退默认（沿用 `_safe_*` 纪律）；`ttl_poll_sec` 下限 0.05 防忙等。

### 5.2 docker_sandbox.py

- `_build_run_command`：初始块去 `--rm`；`--cpus={cpu_limit:.6g}`（>0 时）、`--pids-limit={pids_limit}`（>0 时）、`--label rc.run={run_id}`（run_id 非空时）；签名加 `run_id: str | None = None`。
- `_inspect_container(container_name)`（staticmethod）：`["docker","inspect","--format","{{.State.OOMKilled}} {{.State.ExitCode}}", name]` → stdout 按 `"true 137"` 形态解析（`stdout.strip().split()`，首段小写化 == "true"，次段 int()）→ `(bool,int)`；任何异常/不可解析 → None。
- `_TtlWatcher(threading.Thread)`：`daemon=True`；字段 `container_name/ttl_sec/kill_grace_sec/poll_sec/_stop/_fired`；`run()`：循环 `self._stop.wait(min(poll_sec, max(0.05, deadline - now)))`，`now >= deadline` → `docker kill -s TERM <name>`（子进程调用，异常 warning）→ `self._stop.wait(kill_grace_sec)` → **未 stop** 则 `docker kill <name>`（SIGKILL）→ 置 `_fired=True`；`stop()` 置 `_stop`；`fired` 属性。
- `_execute`：签名加 `run_id`；`ttl = _TtlWatcher(...) if (run_id and cfg.ttl_sec > 0) else None`，启动前 `ttl.start()`；try 内 `subprocess.run` 既有逻辑不变，`TimeoutExpired` 分支保持 `_kill_container`；正常返回后 `inspected = self._inspect_container(self._last_container_name)`；finally：`if ttl: ttl.stop(); ttl.join(timeout=cfg.kill_grace_sec + 1.0)` → 既有 `_remove_container`；结果构造处 `limit_reason=self._attribute_limit(ttl_fired=(ttl and ttl.fired), timed_out=..., inspected=...)`。
- `_attribute_limit`（staticmethod，D-5 唯一映射）：`ttl_fired → "ttl_timeout"`；`inspected is not None and (inspected[0] or inspected[1] == 137) → "resource_limit"`；`timed_out → "timeout"`；否则 None。
- 容器名可达性：`_next_container_name` 生成的名字在 `_execute` 内落局部变量传给 inspect/watcher（避免读实例态）。
- `run()` / `run_project()`：加可选 `run_id: str | None = None` 透传 `_execute`。

### 5.3 harness_template.py

```python
import atexit
import signal

def _finalize_default() -> None:
    if _default_harness is not None:
        _default_harness.finalize()

atexit.register(_finalize_default)

def _install_sigterm_handler() -> None:
    if threading.current_thread() is not threading.main_thread():
        return
    def _on_sigterm(signum: int, frame: object) -> None:
        _finalize_default()
        sys.exit(128 + signum)
    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        pass

_install_sigterm_handler()
```

要点：幂等由 finalize 既有 `json.dump` 覆盖写保证（I-M4-5）；`sys.exit(143)` 经由解释器关闭再触发 atexit 二次 finalize——幂等无害；模块顶部补 `import threading`（模板内已用 threading 则复用）。

### 5.4 _execution.py 调用点

stage-14 主执行与重跑路径（`runs_dir` 在作用域内处）：`run_project(..., run_id=runs_dir.name)` / `run(..., run_id=runs_dir.name)`。experiment_repair / code_agent 调用点**不改**（DESIGN §2.3 边界，quota 由 config 默认仍生效）。

### 5.5 sandbox.py

仅加一行字段与注释行（`# ttl_timeout | resource_limit | timeout | None`）。

## 6. 测试计划

### 6.1 新增 tests/test_sandbox_boundary.py（T-1..T-14）

| # | 用例 | 手段 | 断言 |
|---|------|------|------|
| T-1 | cpu flag | mock subprocess，cfg.cpu_limit=1.5 | cmd 含 `--cpus=1.5` |
| T-2 | pids flag | cfg.pids_limit=256 | cmd 含 `--pids-limit=256` |
| T-3 | 标签 | run_id="r1" | cmd 含 `--label rc.run=r1`；无 `rc.tool` |
| T-4 | 无 run_id | run_id=None | 无 `rc.run`；ttl 线程为 None；cmd 无 `--rm` |
| T-5 | OOM 归因 | inspect stdout "true 137" | `limit_reason=="resource_limit"` |
| T-6 | 正常退出 | inspect stdout "false 0" | `limit_reason is None` |
| T-7 | timeout 归因 | subprocess.run side_effect TimeoutExpired | `limit_reason=="timeout"` 且 kill/remove 恰一次 |
| T-8 | TTL TERM→KILL | 小 ttl/poll/grace + 假 sleep | 先 `-s TERM` 后 KILL；`limit_reason=="ttl_timeout"` |
| T-9 | 线程生命周期 | run 返回后 | watcher stop + join 完成（`is_alive() is False`） |
| T-10 | 跨 run 隔离 | watcher 名称即本容器 | kill 调用仅含本容器名 |
| T-11 | inspect 不可解析 → None | stdout 噪声 | `limit_reason is None`（I-M4-4） |
| T-12 | yaml 解析新字段 | _parse_experiment_config | 5 字段入 config；坏值回退默认 |
| T-13 | harness 信号兜底 | 源码断言 | `atexit.register`、`signal.SIGTERM`、`_finalize_default`、主线程判定存在 |
| T-14 | run_id=None 归因仍可达 | 无标签路径 + inspect true 137 | `limit_reason=="resource_limit"`（配额归因不依赖标签） |

手段：`unittest.mock.patch("subprocess.run")` + `DockerSandboxConfig(..., ttl_poll_sec=0.05, ...)`；T-8 用真线程 + 微秒级参数（等待 `fired`，超时 fail）。

### 6.2 test_rc_docker_sandbox.py 扩展

新增断言类：命令构造含默认 `--cpus` / `--pids-limit`；不含 `--rm`。既有 36 项不动（I-M4-6）。

### 6.3 e2e（证据层，不阻塞）

复用 `tests/e2e_docker_sandbox.py` 场景骨架追加：OOM（memory 64m + 大数组 → 137 + resource_limit）、TTL（ttl_sec=5 长跑 → TERM 宽限内 results.json 存在）、fork bomb（pids_limit=64 + fork 循环 → 返回非零且宿主存活）、符号链接逃逸（staging symlink → validate 拒绝）、网络外联（network none + urlopen → 非 0 退出）。

## 7. 兼容性与迁移

- `SandboxResult` 新字段带默认 → 既有构造点（含 ssh/agentic 后端）零改动。
- `run/run_project` 新参数可选 → `SandboxProtocol` 不动，factory/协议合规不变。
- config 新键缺省即默认值 → 既有 yaml 零迁移。
- 行为变更登记：默认 `--cpus=2.0`/`--pids-limit=512`（原无限制）、去 `--rm`（keep_containers 语义由失效转为有效）。

## 8. 低效操作排除

| 排除项 | 理由 |
|--------|------|
| 全局 docker ps reaper | 跨 run 干预违反 §11；U-2 登记 |
| signal handler 写入 multiprocessing 队列等花式兜底 | finalize 已幂等，单通道足够 |
| registry profile 注入 | D-1 拒绝 B 案 |
| 给 ssh/colab 后端同步加 label/TTL | 职责外（§2.3），Protocol 兼容即可 |

## 9. 版本核验表（Step 6 Review）

| 依赖 | 声明版本 | 验证方式 | 状态 |
|------|---------|---------|------|
| threading/signal/atexit | stdlib 3.11+ | docs.python.org（T1，既有冻结） | ✅ |
| Docker inspect --format | 29.9.2 本机 | e2e 实测 | ✅ |
| python 3.11/3.13 语法面 | f-string/union 语法既有 | 五套件回归 | ✅ |

## 10. 回退方案

每文件独立可 revert（§3 回退点列）；全批回退 = revert 单 commit；无数据迁移、无配置迁移。

---

**Review 签字**: GLM-5.3-Flash（实施会话自审） 日期: 2026-11-13
