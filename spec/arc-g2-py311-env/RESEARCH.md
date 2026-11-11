---
id: arc-g2-py311-env-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-11
depends: [arc-g2-decisions, arc-master-roadmap]
upstream: arc-master-roadmap
---

# 调研：G2 的 Python 3.11 隔离环境与沙箱兼容性

> **Feature**：P-045，G2 开工前置（U-2）的环境方案。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行；零生产代码/零门禁）。
> **结论先行**：3.11 **可以**跑通 65 项判定测试，但 Windows 上「venv + Job Object」有一个可复现的冲突；根因不是 Python 版本，而是 venv 的 `python.exe` 是 redirector/trampoline，被 `JOB_OBJECT_LIMIT_ACTIVE_PROCESS=1` 禁止创建子进程。修复点应落在 sandbox 启动器（用 `sys._base_executable`），**不得**通过关闭内存上限来绕过。
> **修订**：v1.1（2026-11-11，P-046）**G2 前置 U-2 关闭（§8 U-1 同步关闭）**——AP 上游已按方案 A 修复（commit `bd95f02`，含 2 项 venv 回归用例）；冻结清单 [`testset-3.11.txt`](testset-3.11.txt) 落盘（65 项 node ID + 解释器/依赖版本）；按清单逐项复跑，3.11.15 **65 passed**、3.13.5 全局 **65 passed**；`I-9` 维持为 G2 强制输入。

## 1. 问题与验收口径

A2-3 要求「判定内核在 Python 3.11 跑通判定内核测试集」，且该集合须在 G2 开工时用 `pytest --collect-only` 冻结。P-042 记录的目标集合是 R-03 §1 的 65 项：

- `tests/test_d110_verdict_policy.py`
- `tests/test_d110_verdict_recheck.py`
- `tests/test_semantic_verdict.py`

本调研要回答三件事：

1. 3.11 环境怎样隔离才可复现（不污染 3.12/3.13，也不修改 uv 托管解释器）；
2. 3.11 下 65 项是否真的能全绿；若有失败，失败属于语言/版本不兼容还是环境机制；
3. 若属环境机制，修复应落在哪一层，且不能削弱 `sandbox/evaluator` 的隔离保证。

## 2. 本机一手复现（F）

环境：Windows，`uv 0.11.14`，可用 3.11.15（uv 托管）与 3.13.5（系统全局）。

| # | 事实 | 证据 |
|---|---|---|
| F-1 | AP `requires-python = ">=3.12"`；但内核目录 `datatypes` / `verdict` 只用标准库，`sandbox` 只额外依赖 `numpy` | `pyproject.toml`；三个目录的 import 扫描 |
| F-2 | 3.11 用 `pytest --collect-only` 收集到的正是 **65** 项，且只需 `pytest + numpy` 即可完成收集 | `uv venv --python 3.11` + `uv pip install pytest numpy`；输出 `65 tests collected` |
| F-3 | 在 3.11 venv 中直接运行：**64 passed, 1 failed** | 失败项 `test_run_test_cases_backfills_and_keeps_passed`；诊断脚本显示 `error_message="exec failed: sandbox worker exited unexpectedly"` |
| F-4 | 同一个集合在 3.13 全局解释器下：**65 passed** | `python -m pytest ... -q` |
| F-5 | 失败与内存上限数值无关：256/512/1024 MiB 全部失败 | `SafeEvaluator(memory_limit_mb=...)` 探针 |
| F-6 | 失败发生在 Job Object 附着之后；不附着 Job 时 worker 正常返回 `{"ok": true, "value": 0.0}` | 直接 `subprocess.run` + `_sandbox_env(256)` |
| F-7 | uv venv 的子进程 stderr：`uv trampoline failed to spawn Python child process ... os error 1816`；stdlib venv 的 stderr：`Unable to create process using '"<base python>" -u -c ...'` | `WindowsJobLimits.attach` + `communicate` |
| F-8 | 把 worker 启动器换成 `sys._base_executable`，并把 venv 的 `site-packages` 加进 `PYTHONPATH`：`attached=True, rc=0`，输出 `{"ok": true}` | `probe_baseexe.py` |
| F-9 | 用 pytest 插件做同样替换后，3.11 下 **65 passed** | `sys.executable = sys._base_executable` + `PYTHONPATH=venv site-packages` |
| F-10 | uv 拒绝修改托管解释器：`This Python installation is managed by uv and should not be modified` | `uv pip install --python <uv-managed 3.11>` |
| F-11 | 依赖解析随解释器版本变化：3.11 解析到 `numpy 2.4.6`，3.13 全局为 `2.1.3` | 两个环境的 `numpy.__version__` |
| F-12 | `uv venv --python 3.11 --no-project` 不再触发 `requires-python >=3.12` 的告警 | 在临时目录执行 |

## 3. 根因

因果链（Windows）：

1. Python 3.7.2 起，venv 的 `Scripts\python.exe` 不是解释器本体，而是 **redirector**：读取 `pyvenv.cfg` 后启动 base prefix 里的真实解释器。`sys.executable` 仍报告 redirector 路径。
2. uv 的 venv 也生成 trampoline（`python.exe` / `pythonw.exe` 均由小启动器代理 base 解释器）。
3. `sandbox/evaluator._start` 用 `[sys.executable, "-u", "-c", _WORKER]` 启动 worker。
4. `WindowsJobLimits` 设置 `JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 1`，禁止作业内出现第二个活动进程。
5. redirector 要「启动 base 解释器」= 创建子进程 → 被作业限制拒绝；`CreateProcess` 返回 **1816 = ERROR_NOT_ENOUGH_QUOTA**，worker 未真正运行，父侧只看到 EOF。
6. 父侧把 EOF 归一为 `WorkerCrashed("sandbox worker exited unexpectedly")`，语义层因此没有回填 `falsifiability`，测试失败。

这解释了两个反直觉现象：**换内存上限无效**（问题在进程数，不在内存），**3.13 全局解释器通过**（全局 `python.exe` 是本体，不创建子进程）。

## 4. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [virtualenv · Environment layout](https://virtualenv.pypa.io/en/stable/reference/environment-layout.html) | Windows 的 `python.exe` "References the host interpreter"；3.13+ 使用 `venvlauncher.exe` redirector，"hands off to the interpreter in the base prefix" | T1 官方文档 |
| S-2 | [Python C API · Init config](https://docs.python.org/3/c-api/init_config.html) | `base_executable` 对应 `sys._base_executable`，由 `__PYVENV_LAUNCHER__` 设置 | T1 官方文档 |
| S-3 | [CPython issue 38905](https://bugs.python.org/issue38905) | 3.7.2 起 venv 的 `python.exe` 是 redirector；`sys.executable` 报告 redirector 而非实际运行 exe | T1 缺陷跟踪 |
| S-4 | [Microsoft · JOBOBJECT_BASIC_LIMIT_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information) | `ActiveProcessLimit`：关联进程导致活动进程数超限时，"the process is terminated and the association fails" | T1 官方文档 |
| S-5 | [Microsoft · System Error Codes 1700-3999](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--1700-3999-) | `ERROR_NOT_ENOUGH_QUOTA` = 1816，"Not enough quota is available to process this command" | T1 官方文档 |
| S-6 | [uv · Using environments](https://docs.astral.sh/uv/pip/environments/) | `uv venv --python 3.11`；缺版本时自动下载；`--system` 适合 CI/容器 | T1 官方文档 |
| S-7 | [uv · Python versions](https://docs.astral.sh/uv/concepts/python-versions/) | 托管 Python 的发现/下载策略，`--managed-python` 可只用托管版本 | T1 官方文档 |
| S-8 | [tox · Configuration](https://tox.wiki/en/4.65.1/reference/config.html) | `py311` 自动映射 `python3.11`；generative `env_list` 可声明多版本矩阵 | T1 官方文档 |
| S-9 | [pytest · Parametrizing tests](https://docs.pytest.org/en/stable/how-to/parametrize.html) | `--collect-only` 展示生成的 test ID；node ID 可用于精确选择 | T1 官方文档 |
| S-10 | [PEP 751](https://peps.python.org/pep-0751/) | `pylock.toml` 用于可复现安装，已 Final | T1 标准 |
| S-11 | [py-launch-lab · Windows launch semantics](https://joelvaneenwyk.github.io/py-launch-lab/windows-launch-semantics/) | uv-venv 的 `pythonw.exe` 是 "CUI trampoline ... internally launches the base interpreter"；作者注明 "known uv behaviour ... may change" | T2 社区实验 |
| S-12 | [Microsoft Q&A · Job Object cleanup](https://learn.microsoft.com/en-au/answers/questions/6048510/does-windows-job-object-termination-provide-a-docu) | 讨论 Job 终止的清理边界与 `KILL_ON_JOB_CLOSE` 语义 | T2 社区问答 |

## 5. 方案对比

判据（非补偿，任一不过即淘汰）：

- **L-1**：3.11 下 65/65 全绿（A2-3）；
- **L-2**：不削弱沙箱（Job Object 的进程数/内存限制保留）；
- **L-3**：可复现（固定解释器与依赖，不随全局环境漂移）；
- **L-4**：不修改机器全局解释器（不污染 3.12/3.13，不改 uv 托管目录）。

| 方案 | L-1 | L-2 | L-3 | L-4 | 结论 |
|---|---|---|---|---|---|
| **A. venv + worker 改用 `sys._base_executable` + `PYTHONPATH`** | ✅ 65/65（F-9） | ✅ 限制不变 | ✅ venv 固定 | ✅ | **采纳** |
| B. 安装真实 3.11（python.org/winget）后直接 pip install | ✅ | ✅ | ⚠️ 依赖机器安装 | ❌ 全局变更 | 仅作 CI 备选（setup-python） |
| C. tox `py311` | ❌ 仍是 venv redirector（F-7） | ✅ | ✅ | ✅ | 淘汰（不解决根因） |
| D. 测试时 `memory_limit_mb=0` | ✅ | ❌ 关闭 Job Object | ⚠️ 双环境行为分叉 | ✅ | 仅诊断，不得作验收 |
| E. Linux 容器 | ⚠️ POSIX rlimit 路径 | ✅ | ⚠️ 非目标 OS | ✅ | 可作补充矩阵，不替代 Windows |
| F. `uv run --python 3.11` | ❌ 临时 venv，同 C | ✅ | ✅ | ✅ | 淘汰 |

## 6. 裁决与修复规格

**裁决：A。** 在 AP `proof_pipeline/sandbox/evaluator.py` 的 `SafeEvaluator._start` 中：

1. 启动器优先取 `getattr(sys, "_base_executable", None)`；存在且可执行时用它，否则回退 `sys.executable`；保留 `sys.executable` 作为非 venv 场景的默认。
2. 当启动器与 `sys.executable` 不同（即处于 venv）时，把 `site.getsitepackages()` 追加到 worker 的 `PYTHONPATH`，确保 `numpy` 可导入；不改变 `_KEEP_ENV` 的凭据白名单语义。
3. **保留** `JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 1` 与内存上限；不引入 `breakaway`。
4. 新增回归用例（Windows-only）：在 venv 内创建 `SafeEvaluator(memory_limit_mb=DEFAULT)`，断言 `evaluate({"mu":0}, "mu + 0", 0.0, 0.5) == 0.0`；非 Windows skip。
5. AP 上游修复后，vendor 到 ARC 时按 V-3 在文件头记录修改，并在 `SOURCE.json` 重算 sha256、重跑 3.11 用例。

**配方（本地验收）**：

```powershell
$venv = "$env:TEMP\arc-ap-py311"
uv venv $venv --python 3.11 --no-project --clear
uv pip install --python "$venv\Scripts\python.exe" pytest numpy
# 冻结：先 collect-only，再按冻结清单跑
& "$venv\Scripts\python.exe" -m pytest --collect-only -q `
  tests/test_d110_verdict_policy.py tests/test_d110_verdict_recheck.py tests/test_semantic_verdict.py `
  > spec/arc-g2-py311-env/testset-3.11.txt
& "$venv\Scripts\python.exe" -m pytest `
  tests/test_d110_verdict_policy.py tests/test_d110_verdict_recheck.py tests/test_semantic_verdict.py -q
```

预期：修复前 `64 passed, 1 failed`；修复后 `65 passed`。冻结清单是本批的真值源，后续以 node ID 逐项比对，不用文件名/关键字计数（S-9）。

### 6.1 落地与验收读数（P-046）

实现（AP `bd95f02`）：

- `evaluator._worker_executable()`：优先 `sys._base_executable`（存在且为文件时），否则回退 `sys.executable`；
- `evaluator._worker_env()`：仅当启动器与 `sys.executable` 不同时，把 `site.getsitepackages()` 去重后追加到 `PYTHONPATH`；`_sandbox_env` 的凭据白名单不变；
- `SafeEvaluator._start` 改用上述两项；`JOB_OBJECT_LIMIT_ACTIVE_PROCESS=1` 与内存上限原样保留；
- `tests/test_w8_resource_limits.py::TestVenvLauncher` 增 2 项：启动器偏好 base、worker env 暴露 venv site-packages；非 venv 环境 skip。

读数（2026-11-11，本机）：

| 环境 | 解释器 | pytest / numpy | 冻结清单结果 |
|---|---|---|---|
| 3.11 venv（`%TEMP%\arc-ap-py311`） | 3.11.15 | 9.2.0 / 2.4.6 | **65 passed**（0.62s） |
| 3.13 全局 | 3.13.5 | 8.3.4 / 2.1.3 | **65 passed**（0.62s） |
| W8 资源用例（3.11 venv） | 3.11.15 | — | 20 passed, 5 skipped |

冻结方式：`--collect-only -q` 输出 65 条 node ID，加解释器/依赖版本头写入 [`testset-3.11.txt`](testset-3.11.txt)；验收命令为 `pytest @<清单中的 node ID>`，避免用文件名计数。

## 7. 对 G2 的影响

- **U-2 已关闭**：3.11 解释器、依赖面、冻结方式与启动器兼容性均已验证；M2 可直接按本清单验收。
- **新增 G2 强制输入**：`I-9`——sandbox worker 启动器必须兼容 venv redirector（`sys._base_executable` + `PYTHONPATH`），且保留 Job Object 限制；否则 A2-3 在 Windows 本地验收不成立。
- **依赖锁定**：3.11 与 3.13 解析出的 `numpy` 版本不同（F-11），验收清单须记录解释器与依赖版本；若要跨机复现，使用 `pylock.toml`（S-10）或至少把 `pytest`/`numpy` 版本写入清单。
- **CI**：GitHub Actions 的 `setup-python` 提供真实解释器（非 venv），CI 不受 redirector 影响；但本地/离线验收仍需要 A。

## 8. 未决

- **U-1（关闭，P-046）**：修复放 AP 上游而非只改 ARC vendor 副本——已在 `bd95f02` 落地，含 `TestVenvLauncher` 2 项；vendor 时按 V-3 记录修改并在 `SOURCE.json` 重算 sha256。
- **U-2（开放）**：macOS/Linux 的 POSIX `RLIMIT_AS` 路径是否也存在类似「启动器子进程」问题？本批未测；按 F-7 的机制推断不适用（无 redirector），但需在 CI 的 ubuntu job 上补一条探针。
- **U-3（开放）**：是否把 3.11 环境固化为 `tox -e py311`？当前倾向：本地用脚本 + 冻结清单，CI 用 `setup-python`，暂不引入 tox 依赖。

## 9. 引用

1. 仓内：`F:\Auto_Prover\pyproject.toml`、`proof_pipeline/sandbox/{evaluator,limits}.py`、`proof_pipeline/stages/stage2_numerical.py`、`tests/test_{d110_verdict_policy,d110_verdict_recheck,semantic_verdict}.py`；[testset-3.11.txt](testset-3.11.txt)；[R-03 §1](../../arb-v2-decisions-research-design.md)、[P-042 §8](../arc-g2-decisions/RESEARCH.md)。AP 修复：`bd95f02`（evaluator + W8 用例 + CHANGELOG v3.58-d173 + DECISIONS D173）。
2. 外部：S-1..S-12（§4 表，URL 已逐条解析）。
