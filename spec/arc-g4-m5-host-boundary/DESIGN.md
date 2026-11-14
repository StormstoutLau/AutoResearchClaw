# 设计文档：G4-M5 宿主边界（env allowlist / safe_join / HostProfile / AST 守卫）

---
id: arc-g4-m5-host-boundary-DESIGN
type: design
version: 1.6
status: verified
date: 2026-11-14
depends: [arc-g4-m5-host-boundary-RESEARCH]
upstream: arc-g4-m5-host-boundary-RESEARCH
---

> **Feature**: arc-g4-m5-host-boundary（P-106，G4-M5）
> **创建日期**: 2026-11-14
> **状态**: verified（Step 4 自审 + 跨基座核对 + §13 异构复核订正 v1.1；U-5..U-9 于 2026-11-14 按建议裁决确认，v1.2 定稿；v1.3 四文档一致性审计订正；v1.4 六步 TDD 实施后按实测回填 U-9/U-7 口径订正，裁决实质不变；v1.5 独立异构复审订正（§13.7），裁决实质不变；v1.6 F-1 负向用例补录（T-14 锁定 R1 别名盲区行为），裁决实质不变）
> **修订**: v1.0（2026-11-14）初稿 → v1.1（2026-11-14）§13 异构复审 8 处订正 + N-1..N-6 → v1.2（2026-11-14）§11 U-5..U-9 裁决确认（用户授权「按照建议裁决」），判据与施工输入不变 → v1.3（2026-11-14）四文档一致性审计订正 6 处（§13.6）→ **v1.4**（2026-11-14）六步 TDD 实施回填：§11.2 登记 U-9 谓词与目标参数位的实施订正、U-7 豁免 1 条、注册表 60 调用 / 31 写点 → **v1.5**（2026-11-14）独立异构复审（GLM-5.3-Flash 复审 vs DeepSeek-V4.1-Flash 实施）：F-1..F-5 订正 + F-6/F-7 观察（§13.7），裁决实质不变 → **v1.6**（2026-11-14）F-1 负向用例补录：`test_t14_alias_spawn_is_outside_scan`（17 用例 / 30 passed），§4.6/§11.1/§13.3/§13.7 宣称同步闭环
> **基于调研**: [RESEARCH.md](./RESEARCH.md)（v1.2，含 §5.4 异构复审）
> **上游契约**: [M0 DESIGN §7/§8](../arc-g4-m0-design/DESIGN.md)（不得静默弱化）

---

## 1. 设计目标

把 M0 §7/§8 冻结的三件事落到可机械判定的门禁：**A4-7**（全部执行后端使用 allowlist 环境）、**A4-8**（全部动态名写点经 `safe_join`）、**A4-9**（`HostProfile` 只读快照 + 无 `shell=True`）；并以 **M4-D6** 的注册制守卫（`tests/test_boundary_coverage.py`）作为「新增调用点未登记即红」的常驻闸门。

判定口径（RESEARCH §6.6 四条裁决，v1.2 复审全部成立）：
- **A4-7** 按「是否执行模型生成物/用户内容」划界，而非按类型字面（U-3=B）→ 改造 **7 处**；
- **A4-8** 收敛为「变量名驱动」子集，而非 319 处全量（U-4=A）→ 约 **30 处**；
- **A4-9** 由 `runtime/host_profile.py` 包装既有探测，不建第二套口径（U-1=C）；
- **守卫** 外置注册表 + AST 双向一致校验（U-2=A）。

## 2. 设计依据

### 2.1 调研结论 → 设计决策

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| F-1 58 处真实 subprocess、researchclaw/** 内 `shell=True` 为 0 | 守卫以「全量登记 + 双向一致」实现 A4-7，`shell=True` 零容忍 | RESEARCH §3.1 / §5.4 |
| F-3/F-13 全量 env 透传 6 处 + `renderer.py:264` 无 env | D-3：7 处统一改为 `env=build_subprocess_env(overrides)` | RESEARCH §6.6 U-3 |
| F-6 写点 319、`safe_join` 消费点仅 1 | D-4：只改动态名子集（~30），其余登记豁免 | RESEARCH §6.6 U-4 |
| F-8/F-10/F-11 `runtime/` 无 host_profile、宿主探测已存在（`_detect_nvidia` 只取首行）、`DockerSandboxConfig` 无宿主维度 | D-1：包装 + 新增 `hardware.list_gpu_devices()` | RESEARCH §6.6 U-1 |
| U-2 复审实证行号漂移（`code_agent.py` 456→462） | D-2：注册键 = `(relpath, qualname, ordinal)` | RESEARCH §5.4 U-2 |
| F-15 AST 判 env 来源误报 2/60 | D-2：注册制为主、扫描为兜底，误报率如实登记 | P-102 X-6 |

### 2.2 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|------|------|---------------|
| D-1（U-1=C） | 新建 `researchclaw/runtime/host_profile.py`：`HostProfile` **只读** snapshot，探测委托 `hardware.detect_hardware()`；并在 `hardware.py` 新增 `list_gpu_devices() -> tuple[str, ...]`（迭代 `nvidia-smi -L` 全部非空行，失败 → `()`）。`detect_hardware` 首行行为**不变** | M0 §8 冻结形状；hardware.py:172-173 首行折叠 | 拒「扩 `HardwareProfile`」（frozen 契约 5 构造点 62/85/140/195/232 + 2 消费模块）；拒「纯包装」（拿不到设备列表）；拒「自写探测」（第二套口径） |
| D-2（U-2=A） | 外置 `tests/boundary_registry.yaml`，键 `(relpath, qualname, ordinal)`；守卫 `tests/test_boundary_coverage.py` 做**双向一致**（未登记→红；陈旧→红）+ `shell=True`→红 | M0 §7「豁免清单显式登记，默认空」 | 拒内联 `# nosec`（侵入 58+37 处）；拒纯扫描（误报 2/60）；拒 Bandit 当门禁（无写点规则，仅作补充） |
| D-3（U-3=B） | 按「执行模型生成物/用户内容」判定，改造 **7 处**（E-1..E-7）：stat:381 / biology:457 / collider:682 / code_agent:462 / hitl/hooks:211 / opencode_bridge:462 / renderer:264；同源 docker 形态 **renderer:329**（E-8，容器内执行、env 仅达 docker 客户端）显式登记 B 类豁免；纯宿主运维 CLI（docker/git/ssh/pdflatex）登记豁免 | sudo `env_reset`+`env_keep`；Python `subprocess` env 替换语义（T1）；renderer:329 一致性见 §13 N-2 | 拒「按类型字面」（漏 renderer，密钥暴露面最大）；拒「58 处全收口」（打断 docker/ssh/git 认证） |
| D-4（U-4=A） | 动态名子集 ~30 处改 `safe_join(base, name)`；`utils/paths.py` 仅补 TOCTOU docstring；`_safe_filename` 保留但**不替代** `safe_join` | CWE-22 canonicalize→prefix；MCP SDK `path_security.safe_join` 同语义 | 拒「319 处全量」（大 diff 零收益）；拒「仅入口校验」（`fname` 内联 `../` 可绕过） |
| D-5 | `HostProfile` **不承载策略**：无 `env_allowlist` / `network_policy` / cpu 配额；这三项分别归 `utils/env.py`、`DockerSandboxConfig` | P-105 D-Q1=C 的延续（防第三真值源） | 拒「HostProfile 兼作策略载体」（同一字段两处解释→漂移） |
| D-6 | **不新增 `sandbox_env` 别名**；7 处直接调既有 `build_subprocess_env(overrides)` | `utils/env.py:50` 签名已是「allowlist + overrides」 | 拒「薄封装别名」（零行为增量、多一层间接，违反最小改动）；见 §2.4 修订 R-1 |
| D-7 | 守卫扫描根 = `researchclaw/**`（写在注册表 `scan.roots`，可一行扩展）；`tools/spec_runner/**` 不在本批口径 | F-1 口径；M0 §8 负向用例同为 `researchclaw/**` | 拒「全仓扫描」（`tools/` 域有 1 处 `shell=True` 的 gate 执行器，纳入即需先改工具链，超本批范围） |

### 2.3 职责边界

- **职责内**：`runtime/host_profile.py`（新增）、`hardware.list_gpu_devices()`（+21 行，实测）、7 处 env 接入、~30 处写点、`utils/paths.py` docstring、`tests/test_boundary_coverage.py` + `tests/boundary_registry.yaml` + `tests/test_host_profile.py`。
- **职责外**：多 GPU 首行折叠修复（既有缺陷，登记已知限制）；SSH 命令行前缀 env 形态（U-5）；`tools/` 域 `shell=True`（U-6）；`pipeline/runner.py:1756/1766/1773` 按复审建议登记 exempt（U-7，§11）；并发改树的 TOCTOU 防护（仅声明边界，不实现 `O_NOFOLLOW`）；`build_subprocess_env` / `safe_join` 本体语义（I-6 冻结）。

### 2.4 相对 RESEARCH 的修订（须显式登记）

| # | RESEARCH 原文 | DESIGN 收敛 | 理由 |
|---|---|---|---|
| R-1 | U-3 注入点「`utils/env.py` 增 `sandbox_env(overrides)` 薄封装」 | 直接调 `build_subprocess_env(overrides)` | 既有签名已同语义；别名无行为增量。**裁决语义不变**，仅去掉多余间接 |
| R-2 | 影响面「改 12 个源文件（有重叠）」 | **15 个**：7 env 文件 + 6 写点文件 + `hardware.py` + `utils/paths.py`；两集合**有交集**——`code_agent.py` 横跨 E-4 与 `_seed_workdir` 写点（code_agent.py:135），去重后 **14 个** | v1.1 复审订正（§13 订正 #2）：「无交集」被证伪，RESEARCH「有重叠」更近事实；写点文件集最终依 U-9 重扫定稿（§10.3） |
| R-3 | 注册键 `(relpath, qualname)` | `(relpath, qualname, ordinal)` | v1.2 复审输入：同函数多调用点需消歧；`ordinal` 按 `(lineno, col_offset)` 排序取 1-based，重构换行不失效 |

## 3. 架构设计

### 3.1 三件产物的关系

```text
                 ┌──────────────────────────────┐
                 │ tests/boundary_registry.yaml │  单一登记源（人写、可 review）
                 └──────────────┬───────────────┘
                                │ 读取
                 ┌──────────────v───────────────┐
   researchclaw/** │ tests/test_boundary_coverage │ AST 扫描 + 双向一致 + 负向自测
   （AST）────────>│      （新增门禁）             │────────> 任一不一致 → 红
                 └──────────────────────────────┘

   7 处执行点 ──> utils/env.py:build_subprocess_env(overrides)   [不改本体]
   ~30 写点   ──> utils/paths.py:safe_join(base, name)            [仅补 docstring]

   runtime/host_profile.py ──> hardware.detect_hardware() + list_gpu_devices()
                          └──> 只读快照（无策略、无 callable）
```

**单一真值源**：边界策略只有两处——`SAFE_ENV_KEYS`（env 允许什么）与 `boundary_registry.yaml`（哪些点豁免）。`HostProfile` 不参与决策，只做快照。

### 3.2 模块划分

| 模块 | 变更 | 内容 |
|---|---|---|
| `researchclaw/runtime/host_profile.py` | 新增 | `HostProfile`（frozen）+ `detect_host_profile()`；仅依赖 stdlib + `researchclaw.hardware` |
| `researchclaw/hardware.py` | +21 行（实测） | `list_gpu_devices()`；`detect_hardware` / `_detect_nvidia` 不动 |
| `researchclaw/utils/env.py` | 不动 | 7 处调用点改为 `env=build_subprocess_env({...})` |
| `researchclaw/utils/paths.py` | docstring | 补 TOCTOU point-in-time 边界说明 |
| `tests/test_boundary_coverage.py` | 新增 | AST 守卫（R1..R6） |
| `tests/boundary_registry.yaml` | 新增 | 60 调用 + 31 写点 + 豁免子表（1 条 exempt，§11.2） |
| `tests/test_host_profile.py` | 新增 | HostProfile 契约用例（T-1..T-4） |

### 3.3 守卫执行时序（fail-closed）

```text
pytest tests/test_boundary_coverage.py
  ├─ 1. 载入 registry（缺失/版本不符 → 直接 fail）
  ├─ 2. AST 扫描 scan.roots（默认 researchclaw）
  │    ├─ R1 未登记调用点        → fail（列出 relpath:qualname#ordinal）
  │    ├─ R2 注册表陈旧条目      → fail（AST 中不存在）
  │    ├─ R3 shell=True          → fail（无豁免通道）
  │    ├─ R4 env= 非 build_subprocess_env 且非登记常量 → fail
  │    └─ R5 动态名写点未登记    → fail
  └─ 3. 负向自测 R6：内存中删 1 条注册 → 断言守卫必红（防「守卫形同虚设」）
```

## 4. 接口定义

### 4.1 `HostProfile`（冻结形状，M0 §8 逐字段对齐）

```python
# researchclaw/runtime/host_profile.py
@dataclass(frozen=True)
class HostProfile:
    """Read-only host snapshot. No policy, no callables (M0 §8)."""

    cpu_count: int                 # os.cpu_count() or 0
    memory_total_mb: int           # 探测失败 -> 0
    disk_free_gb: float            # shutil.disk_usage(root).free / 2**30
    gpu_devices: tuple[str, ...]   # hardware.list_gpu_devices()；失败 -> ()
    toolchains: dict[str, str]     # 固定白名单命令的版本首行；缺失 -> 省略该键

    def as_dict(self) -> dict[str, Any]:  # 值仅标量/列表/字典，无 callable
        ...


def detect_host_profile(
    *,
    disk_root: Path | None = None,
    toolchains: tuple[str, ...] = ("python", "docker", "git"),
) -> HostProfile: ...
```

- `memory_total_mb` 跨平台实现（stdlib，不引入 `psutil`）：POSIX `os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")`；Windows `ctypes` `GlobalMemoryStatusEx`；任一异常 → `0`。
- `toolchains` 元素必须匹配 `^[a-z][a-z0-9_-]{0,31}$`，否则 `ValueError`（防「配置即任意命令执行」）；命令固定为 `<name> --version`，`shell=False`，`timeout=5`。
- `as_dict()` **不得**包含可调用对象；`gpu_devices` 序列化为 `list`。

### 4.2 `hardware.list_gpu_devices()`

```python
def list_gpu_devices() -> tuple[str, ...]:
    """All GPU lines from ``nvidia-smi -L``; () when unavailable."""
```

- 固定命令 `["nvidia-smi", "-L"]`，`shell=False`、`timeout=10`、`check=False`；`FileNotFoundError/TimeoutExpired/OSError` 或 `returncode != 0` → `()`。
- 逐行 `strip()`，跳过空行；**原文返回**（含 `GPU 0: ... (UUID: ...)`），下游自行解析。
- **不改** `_detect_nvidia` 的 `splitlines()[0]` 行为（既有缺陷，见 §11 已知限制）。

### 4.3 env 接入约定（7 处）

```python
env=build_subprocess_env({"<该点既有显式键>": "<value>"})   # 无既有键 -> 省略参数
```

| # | 位置 | overrides 来源 |
|---|---|---|
| E-1 | `experiment/stat_agent_sandbox.py:381` | 该后端既有显式键（API base 等），逐点照搬 |
| E-2 | `experiment/biology_agent_sandbox.py:457` | 同上 |
| E-3 | `experiment/collider_agent_sandbox.py:682` | 同上 |
| E-4 | `experiment/code_agent.py:462` | `self._env_extra` |
| E-5 | `hitl/hooks.py:211` | `RC_*` 既有显式集 |
| E-6 | `pipeline/opencode_bridge.py:462` | `OPENAI_API_KEY`（配置解析所得）等既有键 |
| E-7 | `agents/figure_agent/renderer.py:264` | 无（当前无 `env=`）→ `env=build_subprocess_env()` |
| E-8 | `agents/figure_agent/renderer.py:329` | **不改**——docker 形态执行同源脚本（:319/:325 挂载 `/workspace/script.py`），env 仅达 docker 客户端；登记 B 类豁免（§13 N-2） |

**约束**：overrides 只减不增——不得引入任何此前未透传的敏感键；`os.environ` 直读（`os.environ.get`）保留，不入本批范围。
**形态约束（R4 前置，v1.1）**：E-1..E-7 改造后必须**内联** `env=build_subprocess_env({...})`，消灭中间变量形态（现状即中间形态：stat:88 `env=self._build_env()`→:92 `env=env`、hooks:211 构造→:225 `env=env`、opencode:462 构造→:487 `env=env`）；`evidence/sidecar.py:222` `env=_build_env(config)` **不改码**——其本体 :87-104 为自建 allowlist（:98 `PYTHONPATH` 为构造值 `config.ap_root`、:99-102 透传 `ARB_*` 三个显式键、:103 合入 `config.env_extra` 配置字段——均非宿主环境隐式继承；语义合规、形态不匹配），经注册表 `env: sourced:_build_env` 登记为合法来源（§4.6 R4(b)）。

### 4.4 `utils/paths.py` docstring

追加一段：symlink 检查是 **point-in-time**，并发替换目录可绕过；本函数不提供 `O_NOFOLLOW` 级保证；跨进程并发写树的需求须在调用侧序列化。**无行为变更**。

### 4.5 `tests/boundary_registry.yaml` schema

```yaml
version: 1
scan:
  roots: ["researchclaw"]
  exclude: []                 # 相对 scan.roots 的前缀

subprocess_calls:             # 存量登记非空（实施落盘 60 条：58 存量 + 2 新增）
  - id: S-001
    relpath: researchclaw/experiment/sandbox.py
    qualname: ExperimentSandbox.run
    ordinal: 1                # 同 (relpath, qualname) 内按 (lineno, col) 排序的 1-based 序号
    category: B               # A=宿主工具 / B=工作负载执行 / C=生命周期管理
    env: allowlist            # inherit | allowlist | overrides | sourced:<callable> | prefix
    reason: ""                # 非豁免可空；sourced/prefix 须注明理由（如消毒口径）
    owner: P-106
    expires: null             # 仅 policy=exempt 时必填 ISO 日期

write_sites:                  # 仅登记动态名子集（safe_join 改造 + exempt 豁免）；固定字面量不触发 R5、不登记（口径依 U-9 裁决）
  - id: W-001
    relpath: researchclaw/pipeline/stage_impls/_code_generation.py
    qualname: <函数名>
    ordinal: 1
    policy: safe_join         # safe_join | exempt
    reason: ""
    owner: P-106
    expires: null
```

- **豁免子表实施落盘 1 条 exempt**（U-7 裁决 `runner.py` 固定名写点；实施扫描确认仅 `current_dir / fname` 一处触发 U-9，另两处为纯 Name 目标，§11.2；renderer:329 走 `subprocess_calls` B 类登记，不入此表）：`policy: exempt` 必须给 `reason`+`owner`+`expires`，三项任一缺失 → 守卫 fail。M0 §7「显式登记，默认空」的语义 = 有 reason 的豁免合法，非「豁免表恒空」。
- 键不含行号（行号会漂移）；`ordinal` 在同函数内稳定。
- 注册表与 AST 的**双向**一致：多登记（陈旧）与少登记（遗漏）都是红。

### 4.6 守卫规则

| 规则 | 判定 | 失败信息 |
|---|---|---|
| R1 | `researchclaw/**` 内每个 `subprocess.*` / `Popen(` 调用必须命中一条 `subprocess_calls`。**已知限制（§13 N-1）**：方法别名形态不可静态判定（现存实例 `runtime/supervisor.py:71` `self._spawn = spawn or subprocess.Popen` + :102 调用，威胁面低：worker_cmd 为默认命令，非模型生成物）——登记为 R1 已知限制，人工审查兜底；负向用例已补录 `test_t14_alias_spawn_is_outside_scan`（2026-11-14 F-1 补录批，锁定盲区行为） | `unregistered subprocess call at <relpath>:<qualname>#<ordinal>` |
| R2 | 每条登记必须在 AST 中存在（含 `ordinal` 可达）。失败信息**附该 qualname 下全部已登记 ordinal 与各调用点首行文本**；键存在但 ordinal 错位 → 输出「疑似 ordinal 漂移」（U-8 增强） | `stale registry entry <id> (<relpath>:<qualname>#<ordinal>)` |
| R3 | 扫描根内出现 `shell=True` → 直接 fail，**无豁免通道** | `shell=True forbidden at <relpath>:<lineno>` |
| R4 | 带 `env=` 的调用，其值满足其一：(a) 内联 `build_subprocess_env(...)`；(b) 注册表 `env: sourced:<callable>` 登记的本地构造函数（如 sidecar `_build_env`，本体自建 allowlist）；(c) 同函数内**单层赋值**别名 `env = build_subprocess_env(...)`。其他中间变量形态 → fail。E-1..E-7 改造强制 (a)（§4.3 形态约束） | `env from unregistered source at ...` |
| R5 | 写点目标**路径参数**含非字面量**名称成分**且未登记 → fail。判定面：`write_text/write_bytes/open(..., mode 含 "w"/"a"/"x"/"+")/shutil.copy*/os.replace`（`Path.replace` 不判，避免 `str.replace` 误报）；`copy2/copytree` 判**目标**参数。目标参数位：`write_text`/`write_bytes`/`Path.open` → **接收者**，内建 `open` → `args[0]`。精确机械定义依 **U-9** 冻结 + **§11.2 实施订正** | `unregistered dynamic write at ...` |
| R6 | 元测试：内存删除一条登记后，守卫必须失败。**接口约束**：守卫判定签名 `check(registry, ast_findings)` 与 `load()` 分离、registry 可注入（元测试 monkeypatch 注入，不落临时文件） | `guard is vacuous` |

## 5. 替代方案

U-1..U-4 的完整比选见 [RESEARCH §6.6](./RESEARCH.md)。摘要：

| 项 | 选择 | 已否决 |
|---|---|---|
| U-1 | 包装 + `list_gpu_devices()` | 扩 `HardwareProfile`、纯包装、自写探测 |
| U-2 | 外置 YAML + 双向一致 | 内联 nosec、纯 AST、Bandit 门禁 |
| U-3 | 按执行内容判定（7 处） | 按类型字面（3 处）、全量收口（58 处） |
| U-4 | 动态名子集（~30） | 全量 319、仅入口校验 |

## 6. 数据结构

注册表为唯一新增数据结构（§4.5）。`HostProfile` 为冻结 dataclass，序列化后形如：

```json
{
  "cpu_count": 16,
  "memory_total_mb": 32768,
  "disk_free_gb": 412.7,
  "gpu_devices": ["GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-...)"],
  "toolchains": {"python": "Python 3.11.9", "docker": "Docker version 27.3.1"}
}
```

约束：所有值为标量或列表/字典；**不含**命令字符串、不含 callable（A4-9 负向用例）。

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| 宿主探测任一失败（无 GPU / 无 docker / 无 nvidia-smi） | 降级：`gpu_devices=()`、`toolchains` 省略该键、`memory_total_mb=0`；**不抛异常**（宿主差异不得阻断 pipeline） |
| `toolchains` 名称非法 | `ValueError`（开发期契约违规，非运行时降级） |
| `safe_join` 越界 | `ValueError("path escapes base directory: ...")`（既有语义，向上传播为 stage 失败） |
| 注册表缺失/`version != 1`/YAML 解析失败 | 守卫 fail，**不跳过**（fail-closed） |
| 豁免条目缺 `reason/owner/expires` | 守卫 fail（RULE-3 防 skip-and-forget 同源口径） |
| `expires` 已过期 | 守卫 fail，提示续期或改代码 |

## 8. 不变式（Invariants）

- **I-1** `HostProfile` 只读、frozen、无策略字段、`as_dict()` 无 callable。
- **I-2** `researchclaw/**` 内 `shell=True` 恒为 0（守卫阻断，无豁免）。
- **I-3** 新增 subprocess 调用点未登记 → 红；登记陈旧 → 红（双向）。
- **I-4** 动态名写点未登记 `safe_join`/`exempt` → 红。
- **I-5** `build_subprocess_env` / `safe_join` 语义不变，既有 9 用例（4+5）保持绿。
- **I-6** 7 处 overrides **只减不增**：不得新增此前未透传的敏感键。
- **I-7** 守卫先红后绿：先以现有缺口跑红，再逐点修至绿（M0 §7）。
- **I-8** `HostProfile` 不参与任何运行时决策（仅快照/上报）。

## 9. 幻觉抑制审查（Step 4 Review）

| 门禁点 | 结论 |
|---|---|
| 设计基于已验证调研 | §2.1 全部映射到 RESEARCH 事实编号；无新造读数 |
| 替代方案已审查 | §5 四项均有否决理由与代价 |
| 职责边界 | §2.3 明确「不做」五项，杜绝范围膨胀 |
| 断言可证伪 | 每条守卫规则可写出红/绿用例（§12 映射） |
| 假设转未决项 | SSH 前缀 env / tools 域 / runner 豁免 / ordinal 稳定性 → §11 U-5..U-8 |

**跨基座核对**：本文档作者 = DeepSeek-V4.1-Flash，RESEARCH 签署模型 = GLM-5.3-Flash，构成跨基座单点核对；**异构独立复核待指派**（RULE-5 完整形态）。

## 10. 对实施的输入

### 10.1 施工顺序（先红后绿）

1. 建注册表骨架（仅 `version/scan`）→ 写守卫 R1..R6 → 跑红（实施实测 60 调用全未登记；R3 = 0）。
2. 全量登记 `subprocess_calls`（机械生成 + 人工核对 category/env；实施落盘 60 条）。
3. 改 7 处 env 接入（E-1..E-7）→ R1/R4 对 7 处转绿。
4. 改 31 处动态名写点 + 登记 → R5 转绿。
5. 新增 `host_profile.py` + `list_gpu_devices()` + `test_host_profile.py`。
6. 补 `utils/paths.py` docstring；跑全量套件（含既有 9 用例）。

### 10.2 风险与缓解

| 风险 | 缓解 |
|---|---|
| 7 处改造漏配 overrides → CLI/OpenCode 认证失败 | 逐点回归；overrides 只减不增（I-6）；保留 `_env_extra` 通道 |
| 注册表 58 条人工登记出错 | 由 AST 脚本生成初稿 + 双人核对；R2 兜住陈旧条目 |
| 守卫误报导致「为过守卫而改代码」 | 豁免表 + 理由审查 + R6 元测试 |
| `memory_total_mb` 平台差异返回 0 | 作为已知降级登记；不做平台特化超范围实现 |
| 行号漂移使人工排查困难 | 失败信息用 `qualname#ordinal`，附 `lineno` 仅供参考 |

### 10.3 影响面（v1.1 复审订正口径）

- **新增 4 文件**：`runtime/host_profile.py`、`tests/test_boundary_coverage.py`、`tests/boundary_registry.yaml`、`tests/test_host_profile.py`。
- **确定改动 23 个源文件**（实施实测 `git diff --stat`）：7 个 env 点（stat/biology/collider/code_agent/hooks/opencode_bridge/renderer）+ `hardware.py` + `utils/paths.py`（docstring）+ 15 个写点文件；`code_agent.py` 横跨 E-4 与写点集，去重后 23；`renderer.py` 兼跨 E-7 与 E-8（:329 不改码、仅登记）。
- **写点文件集**：依 U-9 动态名定义裁决后重扫定稿——v1.0 的「6 写点文件 / 合计 15」被 §13 订正 #2 证伪（`code_agent.py:135` 证明 env 集与写点集**有交集**）；实施实测动态名写点 31 处 / 15 文件（§11.2）。
- **不动**：`build_subprocess_env` / `safe_join` 本体、既有 9 用例。

## 11. 未决项裁决（四元块 + v1.2 已裁决）

**裁决确认（2026-11-14）**：用户授权「按照建议裁决」，下列五项**全部按 v1.1 复审建议落定**，不再是待确认项。裁决值即为实施输入；如实施中发现判据不成立，须回到本节以新四元块显式改判，不得静默偏离。

| 项 | 裁决 | 落点 |
|---|---|---|
| U-5 | 豁免登记不改造（`env: prefix` + reason） | 注册表 `subprocess_calls` |
| U-6 | 本批不纳入 `tools/**`；登记为后续 allowlist 改进项 | DESIGN 结论 + 后续批次 |
| U-7 | `policy: exempt` 1 条（runner.py `current_dir / fname`），不改 `safe_join`（§11.2 订正） | 注册表 `write_sites` |
| U-8 | 接受 `(relpath, qualname, ordinal)`，不上参数指纹 | §4.5 键 + R2 |
| U-9 | 候选 A：拼接触发（详见本条） | §4.6 R5 + 步骤 4 重扫 |

- **U-5 SSH 命令行前缀 env 形态** —— **已裁决：豁免登记，不改造**（2026-11-14）
  - **判据（v1.1 订正）**：前缀注入实为**三类**——`env_prefix`（任意 `env_overrides`，ssh_sandbox.py:281-286，经 `_SAFE_ENV_NAME` 正则 :280 + `shlex.quote` 逐值消毒）、`gpu_env`（:288-290）、`HOME={rd}`（:300/306）；整条命令经 ssh 交**远端 shell** 执行——前缀形态是 SSH 后端的结构约束而非疏漏。
  - **登记形态**：`subprocess_calls` 该条 `env: prefix` + reason 注明三类消毒；改造（`ssh -o SendEnv`）需远端 sshd `AcceptEnv`，不可移植且超本批。
  - **实施附带核验**：pipeline 侧 `env_overrides` 传值链（`run()` 上游）须确认不含密钥（复审未追到最终传值，留实施核验）。
  - **证据等级**：E1（§13 复审亲测）
- **U-6 `tools/` 域扫描范围** —— **已裁决：本批不纳入，落为结论**（2026-11-14）
  - **判据**：`tools/spec_runner/spec_runner.py:171` `shell=True` 属实；`args.cmd` 来自 argparse 显式配置项（:899），非模型生成物/用户内容——威胁面 = 可信配置 + shell 元字符，属工具链自用执行器。
  - **后续改进项登记**：spec_runner `--cmd` 来源 allowlist 化（防「域外即免责」误读）；后续批次一行扩 `scan.roots` 即纳管。
  - **证据等级**：E1（§13 复审亲测）
- **U-7 `pipeline/runner.py:1766` 豁免判定** —— **已裁决：登记 `policy: exempt`，不改 `safe_join`**（2026-11-14）
  - **判据**：`fname` 来自 :1758-1763 固定字面量四项（`analysis.md`/`results_table.tex`/`figure_plan.json`/`figure_plan_final.json`），无外部可控面；改 `safe_join` 收益为零，且 `resolve()` 对符号链接挂载点的语义变化引入回归风险。
  - **豁免表非空不破契约**：M0 §7 原文「显式登记，默认空」= 有 reason 的豁免合法；R2/R6 不依赖豁免表为空。
  - **附带登记（v1.4 实施订正）**：原拟一并登记 :1756 `copy2(best_summary, current_summary)`、:1773 `copytree(best_charts, current_charts)`；实施扫描确认二者目标均为**纯 `Name` 接收者**，按 U-9 不触发 R5，故**不登记**（§11.1 纯 Name 盲区已覆盖）。最终 exempt 仅 1 条。
  - **证据等级**：E1（§13 复审亲测）
- **U-8 `ordinal` 在重构中的稳定性** —— **已裁决：接受 ordinal，不上调用点指纹**（2026-11-14）
  - **理由**：参数哈希指纹的漂移面更大——参数含变量名时，任何重命名都变指纹，等于把「顺序漂移」换成「全量漂移」。
  - **两条低成本增强**（已并入 §4.6 R2）：失败信息列出该 qualname 下全部已登记 ordinal 与调用点首行文本；ordinal 错位输出「疑似 ordinal 漂移」。
  - **证据等级**：E3（设计判断，复审无异议）
- **U-9 R5「动态名」机械定义** —— **已裁决：候选 A（拼接触发），定义冻结如下**（2026-11-14）
  - **判据**：全量写点机械扫描 = 328 处/82 文件（含 `open` 写模式；不含则 319/87 与 RESEARCH F-6 吻合），与「变量名驱动 37 处 / 改造 ~30」之间**无法互相推导**——F-7 的语义筛选无机械规则，R5 按现文本落地与登记口径必然脱节。
  - **触发条件**：IMPLEMENTATION 步骤 4（写点登记）前必须裁决。
  - **候选**：A=拼接触发（目标路径含 `BinOp /`/`+`/`join()`/f-string 且成分含 Name；纯 Name 接收者不触发）；B=纯 Name 接收者亦触发 + 存量全量登记豁免（注册表膨胀换完备性）；C=以 RESEARCH F-7 清单人工冻结为初版注册表，R5 仅做机械双向一致。
  - **裁决定义（冻结，实施按此写 R5；v1.4 按 §11.2 订正）**：写点**目标路径参数**的表达式树满足以下任一，且**名称成分**（而非接收者/基目录）含 `Name`，即判「动态名」：
    1. `BinOp`：`op == Div` 时看**右操作数**（`base / name`）；`op == Add` 时看**任一操作数**（`dir + name`）；
    2. `Call` 且 `func` 为 `Attribute`，`attr ∈ {"join", "joinpath"}`（`str.join` / `Path.joinpath`），**任一实参**含 `Name`；
    3. `JoinedStr`（f-string）且任一 `FormattedValue.value` 递归含 `Name`。
    **不触发**：纯字面量；纯 `Name`/`Attribute` 接收者（路径已在别处拼好，如 `p = base / n; p.write_text(...)`）；`%`/`format()` 形态（现状无实例，出现即由 R1 式人工审查补登记）。
    **目标参数位**：`write_text`/`write_bytes`/`Path.open` → **接收者**；内建 `open` → `args[0]`；`shutil.copy*`/`copytree` → 第二参数（dst）；`os.replace`（仅 `os.` 根）→ 第二参数（dst）。
  - **证据等级**：E1（§13 复审实测 328/82）+ E3（定义为本节裁决）+ E1（实施重扫 31 处 / 15 文件，§11.2）

### 11.1 已知限制（复审 v1.1 登记，非未决项）

- **PATH 信任残留**：toolchains 探测执行 PATH 上首个 `<name>`——PATH 劫持下探测结果不可信；与 `SAFE_ENV_KEYS` 含 PATH 的全仓口径一致，属体系性边界，不做本批特化。
- **多 GPU 首行折叠**：`_detect_nvidia` 首行行为保留（§4.2）；`list_gpu_devices()` 提供全量但不回改旧口径。
- **R1 别名盲区**：方法别名形态不可静态判定（§4.6 R1 / §13 N-1），人工审查兜底；负向用例已补录锁定盲区行为（§13.7 F-1 已闭环）。
- **R4 间接引用深度**：仅追踪单层赋值别名（(c) 通道）；多层管道/跨函数传递不识别——由「E-1..E-7 强制内联 + 存量 sourced 登记」覆盖现状全量，超出现状的深度由 R1 未登记红兜底。
- **R5 纯 Name 盲区**（U-9 候选 A 的代价）：路径先在别处拼好再以纯 `Name` 传入写点时 R5 不触发（如 `p = base / n; p.write_text(...)`）。与 R4 同一诚实口径：机械判定面只覆盖拼接触发形态，遗留由人工审查兜底；改判候选 B 需接受注册表膨胀。

### 11.2 实施订正记录（v1.4，2026-11-14，六步 TDD 后回填）

六步 TDD 实施完成（两新套件 29 用例、合并回归 60 passed）后，按实测回填以下 5 项口径订正。**裁决实质不变**（U-9 仍为候选 A、U-7 仍为豁免），仅把「文字定义」校正为「可机械复现的定义」：

| # | 文档原文 | 实施口径 | 理由（证据） |
|---|---|---|---|
| V-1 | U-9 BinOp「递归作用于两侧操作数」/ join「接收者或任一实参」 | 改为**名称成分触发**：Div 看右侧、Add 看任一、join/joinpath 只看实参、f-string 看插值 | 「两侧递归」实测命中 **194 处**（`stage_dir / "paper.tex"` 等基目录为变量即触发），与 DESIGN 已否决的「319 全量、大 diff 零收益」同质；名称成分口径实测 **31 处 / 15 文件**，与「~30」影响面一致 |
| V-2 | 目标参数位 `write_text`/`write_bytes`/`open` → `args[0]` | `write_text`/`write_bytes`/`Path.open` → **接收者**；仅内建 `open` 用 `args[0]` | `output.write_text(...)` 的 `args[0]` 是写入内容而非路径，按原文会产出大量假阳性 |
| V-3 | 判定面含 `Path.replace` | 仅 `os.replace`（`root == "os"`） | `str.replace`/`Path.replace` 普遍出现，按原文会误报（如 `final_paper.replace(...)`） |
| V-4 | U-7 豁免 3 条（runner.py :1756/:1766/:1773） | 豁免 **1 条**（`current_dir / fname`，现 :1767） | 另两处目标为纯 `Name`（`current_summary`/`current_charts`），按 U-9 不触发 R5，已由 §11.1 纯 Name 盲区覆盖 |
| V-5 | 注册表 58 调用 | **60 调用** | 本批新增 `hardware.list_gpu_devices`（S-059）与 `runtime/host_profile._probe_toolchain`（S-060），均按 A 类登记：前者 `inherit`、后者 `allowlist` |

**实施留痕**：R1 首跑红（89 条：60 subprocess + 31 write，R3 = 0）→ 逐步转绿 → 合并回归 `60 passed`；守卫全量扫描 0.93s、`detect_host_profile()` 0.15s（本机 Windows，见 CHECKLIST §6）。

## 12. 验收映射

| 验收项 | 用例 | 断言 |
|---|---|---|
| **A4-7** | T-7 / T-10 / T-11 | 扫描根内 `shell=True` → 红；`env=` 不满足 R4 三通道（内联 / sourced 登记 / 单层别名）→ 红；7 处改造后子进程环境不含未 allowlist 键（以 `AWS_SECRET_ACCESS_KEY` 等哨兵键验证不泄漏） |
| **A4-8** | T-8 / T-12 | 动态名写点未登记 → 红（「动态名」机械口径依 U-9 裁决冻结）；`safe_join` 后 `../`/绝对路径/符号链接逃逸 → `ValueError` |
| **A4-9** | T-1 / T-2 / T-3 / T-4 | `as_dict()` 值全为标量/列表；多行 `nvidia-smi -L` 全解析；探测失败 → `()`；非法 toolchain 名 → `ValueError`；扫描根无 `shell=True` |
| **M4-D6** | T-5 / T-6 / T-9 | 未登记调用 → 红；陈旧条目 → 红；删一条注册后守卫必红（R6 元测试） |
| 回归 | T-13 | 既有 9 用例（4 env + 5 paths）全绿 |

> T-1..T-4 定义于 §3.2（`test_host_profile.py` 契约用例）；T-5..T-13 的断言即本表第三列（编号-断言一一对应，无悬空引用，§13 F 项核对）。

## 13. 异构复审记录（v1.0 → v1.1，2026-11-14）

**方式**：独立上下文子代理（devil's advocate，零锚定证伪式）复审 DESIGN v1.0 与 U-5..U-8；复审会话对其 8 处关键主张逐一亲验读码后采纳（stat:88/:381、hooks:211/:225、opencode:462/:487、sidecar:222 + :87-97、code_agent:135、renderer:329、supervisor:71/:102、runner:1756-1773、ssh_sandbox:280-311），全部订正已回填正文。

### 13.1 判定表

| 项 | 判定 | 要点 |
|---|---|---|
| A 决策表 D-1..D-7 | PARTIAL | D-1/D-4/D-6/D-7 CONFIRM；D-3 七处行号与现状全证实，但 renderer:329 同源漏处置（→ E-8 补登记）；「~30/6 文件」写点口径不可机械复现（→ U-9） |
| B 守卫 R1..R6 | R4/R5 REFUTE，其余 PARTIAL | R4 中间形态无通道（实锤四处：stat:88、hooks:225、opencode:487、sidecar:222）；sidecar 本体 :87-97 为**自建 allowlist**（语义合规、形态不匹配——排除「第 8 处全量透传」疑点，坐实形态缺口）；R5 机械判定面 328/82 与 ~30 口径脱节（→ U-9）；R1 别名盲区现存实例（N-1）；R2 缺上下文行、R6 缺接口约束（均已补） |
| C HostProfile vs M0 §8 | CONFIRM | 逐字段一致、无静默弱化；PATH 信任残留转 §11.1 已知限制；「原文返回」vs M0「解析结果」有解释空间，维持原文返回（可证伪点后移给下游） |
| D U-5..U-8 | PARTIAL | 四处锚点行号全部亲验属实；U-5「单变量」表述订正为三类前缀（env_prefix/gpu_env/HOME，均消毒）；建议裁决见 §11 各条 |
| E 施工顺序/影响面 | REFUTE（15 文件口径） | 「无交集」被 code_agent.py:135 证伪；「6 写点文件」清单不可复现；§10.3 已订正为「9 确定 + 写点集依 U-9 定稿」。R6 元测试需至少 1 条登记后方可行——施工顺序步骤 1 的「跑红」= R1 全红，R6 属步骤 2 后验证 |
| F 验收映射 | PARTIAL | T-1..T-13 无悬空编号；T-5..T-13 定义位置为 §12 行内（已补说明行） |

### 13.2 订正清单（全部回填正文）

| # | 订正 | 落点 |
|---|---|---|
| 1 | R4 补三通道（内联 / `sourced:<callable>` 登记 / 单层赋值别名）；E-1..E-7 强制内联形态 | §4.3 形态约束 / §4.5 / §4.6 R4 |
| 2 | 「写点与 env 集无交集」证伪（code_agent.py:135 `(workdir / fname).write_text` 横跨 E-4 与写点集） | §2.4 R-2 / §10.3 |
| 3 | §4.5「固定名豁免」注释与 R5 判定矛盾 → 订正为「仅登记动态名子集」 | §4.5 |
| 4 | F-1 文件数 23 → 实测 21~22（复审读数 21，复核读数 22，差异在 vendor 模块计入；**调用数 58 不变**） | §13.4 勘误表 |
| 5 | 写点路径缺 `stage_impls` 层级（实际 `pipeline/stage_impls/_execution.py` 等）——注册表 relpath 须写全路径 | §13.4 勘误表；§4.5 示例已改 |
| 6 | U-5「单变量」→ 三类前缀（env_prefix/gpu_env/HOME，均经正则 + `shlex.quote` 消毒） | §11 U-5 |
| 7 | R2 失败信息补上下文行 + ordinal 漂移提示（U-8 增强并入） | §4.6 R2 |
| 8 | R6 补 `check(registry, ast_findings)` 与 `load()` 分离、registry 可注入的接口约束 | §4.6 R6 |

### 13.3 新发现

| # | 级别 | 发现 | 处置 |
|---|---|---|---|
| N-1 | 高 | `runtime/supervisor.py:71` `self._spawn = spawn or subprocess.Popen` + :102 调用——**现存**别名形态子进程通道，不在 58 计数内（威胁面低：worker_cmd 为默认命令 cli.py:491，非模型生成物） | R1 已知限制（§4.6 / §11.1）；负向用例已补录（2026-11-14，§13.7 F-1 闭环） |
| N-2 | 高 | `renderer.py:329` docker 形态执行同源模型生成脚本（:319/:325 挂载 `/workspace/script.py`），按 U-3 自家判据须显式处置；实际泄漏面 < :264（env 仅达 docker 客户端，容器无 `-e` 透传） | 登记 E-8 B 类豁免（§4.3） |
| N-3 | 中 | R5 机械判定面 328/82 与「~30」差一个数量级，RESEARCH F-7 语义筛选无机械规则 | → U-9 未决项 |
| N-4 | 中 | `shutil.copy2/copytree` 来源/目标参数歧义（`runner.py:1766` 两参皆变量） | R5 已补「判目标参数」（§4.6） |
| N-5 | 低 | toolchains 探测的 PATH 信任残留（`python` = PATH 首个 python） | §11.1 已知限制 |
| N-6 | 低 | R6 元测试可实现性依赖 load/check 分离 | §4.6 R6 接口约束 |

### 13.4 RESEARCH 读数勘误（RESEARCH 版本不动，实施以本表 + DESIGN 为准）

- F-1「23 文件」→ 21~22（见订正 #4）；58 调用数不变（分子为准，文件数为次要描述）。
- F-2「消费点 2 处」实为 2 文件 3 调用点（sandbox.py:329/430 + mcp/client.py:71）。
- `pipeline/_execution.py` / `_code_generation.py` → 实际层级 `pipeline/stage_impls/`。
- F-6 口径注明：319/87 为不含 `open` 写模式的机械计数；含后 328/82（复审与复核双读数吻合）。**v1.3 审计补全**：F-6 括号清单误列「写模式 `open`」——该计数实际未含；两读数的扫描根/去重口径差异不复盘（文件数 87→82 变动不可直接比较），U-9 重扫以 §11 判据栏 328/82（含 `open`）为完整判定面基线。

### 13.5 异构性诚实声明

- **上下文异构**：达成——复审子代理为全新独立上下文（零锚定、证伪式指令、与 DESIGN 作者零信息共享）。
- **基座**：DESIGN 作者 = DeepSeek-V4.1-Flash；复审子代理与复核会话 = GLM-5.3-Flash——构成跨基座单点核对；**基座级异构（外部模型家族）仍未发生**，与 RESEARCH §5.4 同一诚实口径，待指派。
- **复核**：复审会话对子代理 8 处关键主张逐一亲验读码后采纳，2 处低危读数差异如实标注（订正 #4/#5）。

### 13.6 四文档一致性审计订正（v1.3，2026-11-14）

独立子代理对 RESEARCH/DESIGN/IMPLEMENTATION/CHECKLIST 做全链交叉审计，7 项发现全部经审计会话亲验实锤后订正（裁决实质均不变）：

| # | 发现 | 级别 | 订正落点 |
|---|------|------|---------|
| A-1 | CHECKLIST §1.3 声称「T-1..T-13 全覆盖」但 T-10 无绑定验收项（白名单封闭性断言无落点） | P1 | CHECKLIST v1.1：C-A47-2 绑 T-10（测试方法 + 通过条件） |
| A-2 | sidecar `_build_env` 本体行号 DESIGN 记 :87-97、IMPL 记 :87-104；实测 :98-103 尚有 `PYTHONPATH`/`ARB_*`/`env_extra` 段，原窗口截掉了透传段 | P2 | §4.3 行号窗口统一 :87-104 + 成分说明 |
| A-3 | 319/87 口径二义：RESEARCH F-6 括号清单含「写模式 `open`」与本条「不含 `open`」互斥 | P2 | §13.4 F-6 条目审计补全（明确 U-9 重扫基线 328/82） |
| A-4 | §11 U-9 第 2 分支「`attr="join"`」字面无法涵盖 joinpath，与裁决本意（join/joinpath 两形态）及 IMPL §5.2 落地 `attr in {"join","joinpath"}` 不符 | P3 | §11 措辞笔误订正 |
| A-5 | IMPL §5.2 写点判定面含 x/+ 模式与 `Path.replace`，DESIGN §4.6 R5 判定面未登记（IMPL §12 自检「无未覆盖实施」严格口径下不成立） | P3 | §4.6 R5 判定面补齐（对齐 IMPL） |
| A-6 | CHECKLIST §4 标题引「DESIGN §11 冻结语义」而 I-1..I-8 定义于 DESIGN §8 | P3 | CHECKLIST v1.1 标题章节指向订正 |
| A-7 | §2.1 两行编号错位：「runtime 无 host_profile」实为 F-8（误记 F-10/F-11/F-12，F-12 与 D-1 无关）；「行号漂移实证」实为 §5.4 U-2（误记 F-2） | P3 | §2.1 勘误 + CHECKLIST §1.1 证据列同步 |

审计通过项（无须订正）：front-matter 链（id/depends/upstream/版本/日期）、E-1..E-8 清单（文件+行号+改/不改口径）、U-7 三条 exempt、I-1..I-8 对应、T-1..T-9 / T-11..T-13 绑定、关键术语四文档统一（豁免三口径/键三元组/R1..R6/A4-x）、CHECKLIST 计数 84=17+67 逐节复核吻合（dc_validator 0 违规）、诚实边界（67 项全 ☐、§10.2 声明）、session seq1-4 决策链与 evidence 锚点。

### 13.7 独立异构复审订正（v1.5，2026-11-14）

独立上下文异构复审（复审方 GLM-5.3-Flash vs 实施批 DeepSeek-V4.1-Flash），不照抄文档叙述自证——以独立重写的 AST 扫描器（谓词按 §11.2 + IMPL §5.2 规格文本独立转写，不导入守卫代码）、独立 grep、门禁复跑为证据核对全部文档声明。

**一手复验（全真）**：自建扫描 60 subprocess + 31 写点与注册表双向零偏差、env 形态/policy 零失配、`shell=True` 0 命中；29 passed 复跑（全扫描用例 0.90–1.01s ↔ §11.2 宣称 0.93s）；dc_validator 4 文件 0 违规；step-gate legacy exit 0（4/5 步、seq5 回边受理）；U-5（ssh_sandbox 零 diff、S-033 prefix 登记）/U-6（tools/** 零 diff、scan.roots=researchclaw）/U-7（W-014 唯一 exempt，:1756/:1773 未改）/U-8（键三元组）/U-9（名称成分触发）逐条实证；禁改面（`utils/env.py` 本体、`safe_join` 本体仅 docstring、`_execution.py:1258`、renderer:329/E-8）全部未动；四处计数（60/31/1、16/13、0.93s/0.15s）CHECKLIST↔IMPL↔PROGRESS↔session seq5/6 一致；ci.yml 已列两新测试。

| # | 级别 | 发现（证据锚点） | 处置 |
|---|---|---|---|
| F-1 | P2 | N-1 缓解措施「负向用例」五处宣称（§4.6 R1 / §11.1 / §13.3 N-1 / IMPL §8 / CHECKLIST §8.2）——`tests/test_boundary_coverage.py` 16 用例中无 supervisor.py:71 别名盲区负向测试，缓解宣称与交付物不符 | 五处宣称如实降级为「登记已知限制 + 人工审查兜底，负向用例列为待办」；负向用例补录留待后续实施小批（**已闭环 2026-11-14 补录批**：`test_t14_alias_spawn_is_outside_scan` 落地，17 用例 / 30 passed，五处宣称同步订正） |
| F-2 | P3 | CHECKLIST 测试名引用漂移 8 处（3 个测试名）：`test_t5_unregistered_call_is_red`×3（实际 `test_t5_unregistered_subprocess_is_red`）、`test_t8_unregistered_dynamic_write_is_red`×1（该名不存在，覆盖在 `test_t8_dynamic_write_is_red_but_literal_is_not`）、`test_t7_shell_true_is_red`×4（实际 `..._without_exemption`） | CHECKLIST v1.3 全部订正 |
| F-3 | P3 | C-A47-4 证据列「`test_t10_env_is_closed_over_allowlist` 反向断言」高估测试范围：测试仅断言 MAGNUS_ADDRESS + RC_STAGE_NUM 两键；MAGNUS_TOKEN/RC_* 4 键/OPENAI_API_KEY 由 `git diff` 逐点佐证（复审已核，事实成立） | CHECKLIST 证据列措辞收窄 |
| F-4 | P3 | hardware.py 行数：§2.3/§3.2「+8 行」与 IMPL §3「约 14 行」均与实测 diff +21 不符 | §2.3/§3.2/IMPL §3 改为 +21 行（实测） |
| F-5 | P3 | CHECKLIST §10.2 条件②「以发布说明登记」无目标工件（全仓无 RELEASE/CHANGELOG 类文档；E-4 行为变更实登记于 IMPL §7 行为变更登记表） | 条件② 改指 IMPLEMENTATION §7 |
| F-6 | 观察 | E-5/E-6 落地为 `overrides` 局部变量 + `env=build_subprocess_env(overrides)`，与 IMPL §5.5 全内联 dict 示例形态不同；R4 判 allowlist、独立扫描零失配，§4.3 形态约束意图（消灭 `env=env` 间接层）已满足 | 不改码；登记形态差异 |
| F-7 | 观察 | step-gate 口径澄清：`scripts/spec/step_enforce.py:597` 本地模式从 git INDEX 读 PROGRESS——未暂存时裸跑 exit 1 属按设计行为；本批「exit 0」= session 级 step-gate legacy（复审复跑 exit 0 证实）；完整 step_enforce（含 digest 绑定）随 finalize 步交付 | 无需订正；口径登记 |

**异构性诚实声明**：上下文异构达成（复审为全新独立上下文，证伪式核对，未照抄叙述自证）；基座异构 GLM-5.3-Flash（复审）vs DeepSeek-V4.1-Flash（实施/文档批）跨基座单点核对延续 §13.5 口径；基座级异构（外部模型家族）仍未发生。
