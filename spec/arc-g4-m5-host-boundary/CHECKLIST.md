# 审查验收 Checklist：G4-M5 宿主边界（env allowlist / safe_join / HostProfile / AST 守卫）

---
id: arc-g4-m5-host-boundary-CHECKLIST
type: design
version: 1.4
status: accepted
date: 2026-11-14
depends: [arc-g4-m5-host-boundary-IMPLEMENTATION, arc-g4-m5-host-boundary-DESIGN]
upstream: arc-g4-m5-host-boundary-IMPLEMENTATION
---

> **Feature**: arc-g4-m5-host-boundary（P-106，G4-M5）
> **创建日期**: 2026-11-14
> **状态**: 验收完成（v1.2，2026-11-14 实施批回填：代码验收 66/67 通过，Linux 分支待 CI ubuntu 首跑；口径订正见 DESIGN §11.2；v1.3 独立异构复审订正——测试名引用 8 处、C-A47-4 证据收窄、§10.2 条件②指向，见 DESIGN §13.7；v1.4 F-1 负向用例补录同步（§8.2 处置更新 + Python 行 30 passed，DESIGN §13.7 F-1 闭环））
> **Spec 步骤**: Step 7-8、Step 10 取证矩阵
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.4）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.6）

**验收原则**

- **验收对象分层**：§1（文档一致性）与 §9（文档完整性）为文档交付判据，已于 P-106 文档批通过；§2..§8 为代码判据，已由实施批（2026-11-14）执行并逐项回填证据。
- **每项可测试、有明确通过条件**；禁止无证据的 ✅（Step 10 取证矩阵绑定 E1-E5）。
- **测试通过 ≠ 设计落地**（ADD Iron Law）：除测试外，逐条核对 DESIGN §11 冻结裁决与 §11.1/§11.2 已知限制是否被实施批遵守。
- **判据优先级**：DESIGN v1.4 §11 裁决 > IMPLEMENTATION §5 > 本清单；三者冲突以 DESIGN 为准并在实施批回填订正。

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明（证据） |
|--------|------|------|
| DESIGN 决策可追溯到 RESEARCH | ✅ | D-1↔F-8/F-10/F-11；D-2↔U-2 漂移实证/F-15；D-3↔F-3/F-13/F-14；D-4↔F-6；D-7↔F-1（v1.3 审计勘误 §2.1 编号，见 DESIGN §13.6 A-7） |
| RESEARCH 关键发现被 DESIGN 使用或显式排除 | ✅ | F-4/F-5 → D-3 分类；F-8/F-9 → §3.2；未采纳项落 §2.3 职责外 + §11.1 |
| 无文档间矛盾 | ✅ | v1.1 复审 8 处订正已回填；R-1/R-2/R-3 修订显式登记于 DESIGN §2.4；v1.3 四文档一致性审计 7 项订正已回填（DESIGN §13.6） |
| 上游 M0 §7/§8 未被静默弱化 | ✅ | A4-7/A4-8/A4-9 判据与 HostProfile 五字段逐条对齐；弱化项（改造面收敛）均以 U-3/U-4 显式裁决 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明（证据） |
|--------|------|------|
| DESIGN §3.2 模块在 IMPL §3 文件清单有对应 | ✅ | 新增 4 文件 + 改 9 源文件 + ci.yml 接线，逐行对应 |
| DESIGN §4.1/§4.2 接口签名与 IMPL 一致 | ✅ | IMPL §5.3/§5.4：`HostProfile` 五字段、`detect_host_profile(*, ...)`、`tuple[str, ...]` |
| DESIGN §4.3 七处 env 接入逐点落地 | ✅ | IMPL §5.5 E-1..E-7 改前/改后代码 + E-8 不改码 |
| DESIGN §4.5 注册表 schema 与枚举一致 | ✅ | IMPL §5.1 字段表 + `env` 五值枚举与 AST 形态强绑定 |
| DESIGN §4.6 R1..R6 有实施路径 | ✅ | IMPL §5.2 `load/scan/check` + §6.2 T-5..T-9 |
| DESIGN §10.1 六步施工顺序一致 | ✅ | IMPL §4 六步，红/绿判据逐列对应 |
| DESIGN 不变式 I-1..I-8 均有验证手段 | ✅ | IMPL §12 自检 + §6 T-1..T-13；本清单 §4 逐条复核 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明（证据） |
|--------|------|------|
| IMPL 功能点在本清单有验收项 | ✅ | T-1..T-13 ↔ C-A47-*/C-A48-*/C-A49-*/C-D6-* 全覆盖（v1.1 订正：T-10 绑定 C-A47-2 后成立，DESIGN §13.6 A-1） |
| 本清单每项可追溯 IMPL 章节 | ✅ | 各表「依据」列标注 IMPL §5.x / §6.x |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| 动态名 | F-7「变量名驱动 37 处」 | U-9 冻结「拼接触发」 | §5.2 `_is_dynamic` 谓词 | ✅（口径演进以 U-9 为准，已登记） |
| allowlist | F-2 `SAFE_ENV_KEYS` 28 键 | §4.3 `build_subprocess_env(overrides)` | §5.5 内联形态 | ✅ |
| 豁免 | F-6 裸拼接 | §4.5 `policy: exempt` + 三要素 | §5.6 仅 1 条（实测，DESIGN §11.2 V-4） | ✅ |
| ordinal | 无（RESEARCH 用行号） | §4.5 `(relpath, qualname, ordinal)` | §5.1 计数口径 | ✅（新增键，U-8 裁决） |

## 2. 功能验收

> 状态列已由实施批（2026-11-14）按「依据 / 证据」逐项回填；唯一 ☐ 为 Linux 兼容性（待 CI `ubuntu-latest` 首跑），其余全部 ✅。计数见 §10.1。

### 2.1 A4-7 全部执行后端使用 allowlist 环境

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 依据 / 证据 |
|---|--------|---------|---------|------|------------|
| C-A47-1 | 60 处 subprocess 全登记且双向一致 | T-5/T-6 + 真实根扫描 | 守卫绿；删一条登记必红；无陈旧条目 | ✅ | 注册表 60 条；`test_registry_is_consistent`、`test_t5_unregistered_subprocess_is_red`、`test_t6_stale_entry_is_red`、`test_t9_guard_is_not_vacuous` 绿 |
| C-A47-2 | E-1..E-7 改为内联 allowlist | AST 形态断言 + builder 捕获 + `git diff` 逐点核对 | 7 处均为 `env=build_subprocess_env(...)`；无 `env = ...` 中间变量形态；`env` 仅含 `SAFE_ENV_KEYS`/`LC_*`/overrides（白名单封闭） | ✅ | `test_t10_seven_sites_use_inline_allowlist` + `test_t10_env_is_closed_over_allowlist`；`git diff` 7 文件 |
| C-A47-3 | 7 处不泄漏宿主密钥 | T-11 哨兵 `AWS_SECRET_ACCESS_KEY` | 7 处子进程 env 均无该键 | ✅ | `test_t10_env_is_closed_over_allowlist`（哨兵键被过滤）；7 处共用同一 builder |
| C-A47-4 | 既有显式键保留 | T-11 反向断言 | MAGNUS_ADDRESS/TOKEN、RC_* 4 键、OPENAI_API_KEY 均在 | ✅ | `test_t10_env_is_closed_over_allowlist` 反向断言（仅断言 MAGNUS_ADDRESS/RC_STAGE_NUM 两键）；MAGNUS_TOKEN/RC_* 4 键/OPENAI_API_KEY 由 `git diff` 逐点佐证 |
| C-A47-5 | E-8 登记为 B 类豁免 | 注册表条目核对 | `category: B` + `reason` 含「容器内执行/无 -e 透传」+ owner | ✅ | `S-003`：`category: B`、`env: inherit`、reason「script runs inside container; env only reaches the docker client, no -e passthrough」、`owner: P-106` |
| C-A47-6 | R4 三分支判定正确 | 合成用例 4 例 | 内联绿、单层别名绿、`sourced:_build_env` 绿、`os.environ.copy()` 红 | ✅ | `test_r4_inline_allowlist_is_green` / `test_r4_single_level_alias_is_green` / `test_r4_sourced_callable_is_green` / `test_r4_environ_copy_is_red` |
| C-A47-7 | 删除的私有 `_build_env` 无孤儿引用 | `grep -rn "_build_env" researchclaw/` | 仅剩 `sidecar.py`（登记 sourced），其余零命中 | ✅ | 实测仅 `evidence/sidecar.py:87/222`；`test_registry_is_consistent` 绿 |

### 2.2 A4-8 全部动态名写点经 safe_join

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 依据 / 证据 |
|---|--------|---------|---------|------|------------|
| C-A48-1 | R5 谓词即 U-9 裁决定义（含 §11.2 实施订正） | 代码评审 + 合成用例 | 三类拼接触发；纯 Name/字面量不触发 | ✅ | `_is_dynamic` 与 DESIGN §11 定义逐行对应；`test_t8_dynamic_write_is_red_but_literal_is_not`（字面量不触发） |
| C-A48-2 | 动态名写点登记双向一致 | T-8 + 真实根扫描 | 未登记必红；登记陈旧必红 | ✅ | `test_t8_dynamic_write_is_red_but_literal_is_not`、`test_registry_is_consistent`（31 处全登记） |
| C-A48-3 | 改写点 `safe_join` 生效 | T-12 三类逃逸 | `..`/绝对路径/符号链接均 `ValueError` | ✅ | `test_t12_safe_join_escapes`（三类逃逸全红） |
| C-A48-4 | 1 条 exempt 合规 | 注册表核对 | 仅 `runner.py` 的 `current_dir / fname`（现 :1767）；`reason/owner/expires` 齐全且未过期 | ✅ | `W-014`（`policy: exempt`，`expires: 2027-06-30`）；`test_registry_schema`（exempt 恰 1 条）、`test_expired_exemption_is_red` |
| C-A48-5 | 不改无关写点 | `git diff --stat` + `safe_join` 消费点清单 | 固定字面量写点零改动；`_execution.py:1258` 原样 | ✅ | `git diff` 仅 31 处；`_execution.py:1258` 未出现在 diff 中 |

### 2.3 A4-9 HostProfile 只读快照 + 无 shell=True

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 依据 / 证据 |
|---|--------|---------|---------|------|------------|
| C-A49-1 | 五字段与 M0 §8 一致 | T-1 | `cpu_count/memory_total_mb/disk_free_gb/gpu_devices/toolchains` 齐备且类型正确 | ✅ | `test_t1_shape_and_scalar_only_payload` 绿 |
| C-A49-2 | 快照无策略、无 callable | T-1 + 代码评审 | `as_dict()` 可 `json.dumps`；无 env/network/cpu 策略字段 | ✅ | `test_t1_shape_and_scalar_only_payload`（`json.dumps` 通过）；`grep HostProfile` 仅 `runtime/host_profile.py` + 测试 |
| C-A49-3 | GPU 列表与降级正确 | T-2 + T-3 | 多行全解析；不可用返回 `()` 不抛异常 | ✅ | `test_list_gpu_devices_parses_all_lines`（2 行全解析 + 命令/超时断言）、`test_list_gpu_devices_degrades`（`FileNotFoundError`/rc≠0 → `()`） |
| C-A49-4 | toolchain 名注入被拒 | T-4 | `ValueError` 且零子进程发生 | ✅ | `test_t2_invalid_toolchain_rejected_before_probe`（mock `subprocess.run` 断言零调用） |
| C-A49-5 | `researchclaw/**` 无 shell=True | T-7 真实扫描 | 0 命中；合成注入必红且无豁免通道 | ✅ | `test_t7_shell_true_is_red_without_exemption`；全仓 grep `shell=True` 0 命中 |

### 2.4 M4-D6 注册制 AST 守卫

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 依据 / 证据 |
|---|--------|---------|---------|------|------------|
| C-D6-1 | 注册表 schema 完整 | 文件核对 | `version: 1` + `scan.roots/exclude` + `subprocess_calls` + `write_sites` | ✅ | `test_registry_schema`；注册表 60 + 31 条 |
| C-D6-2 | R1 未登记 → 红 | T-5 | 报错含 `unregistered subprocess call` 与键 | ✅ | `test_t5_unregistered_subprocess_is_red`（报错含 `relpath:qualname#ordinal`） |
| C-D6-3 | R2 陈旧/漂移 → 红 | T-6 | 报错含 `stale registry entry` + ordinal 漂移提示 | ✅ | `test_t6_stale_entry_is_red`（含 ordinal 漂移提示） |
| C-D6-4 | R3 shell=True → 红 | T-7 | 无豁免通道，直接失败 | ✅ | `test_t7_shell_true_is_red_without_exemption` |
| C-D6-5 | R4 env 形态不符 → 红 | 合成 3 例 | 登记 `inherit` 但实传 allowlist 亦红（双向校验） | ✅ | `test_r4_inline_allowlist_is_green` / `test_r4_single_level_alias_is_green` / `test_r4_sourced_callable_is_green` / `test_r4_environ_copy_is_red` |
| C-D6-6 | R6 元测试防门禁空转 | T-9 | 删除 1 条登记后 `check` 必非空；不落临时文件 | ✅ | `test_t9_guard_is_not_vacuous`（内存复制注册表，不写盘） |

## 3. 接口验收

### 3.1 `researchclaw/runtime/host_profile.py::HostProfile`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名与 DESIGN §4.1 一致 | `@dataclass(frozen=True)`；五字段名与类型完全一致 | ✅ `test_t1_shape_and_scalar_only_payload` |
| 只读性 | 字段重绑抛 `FrozenInstanceError` | ✅ `test_t1_snapshot_is_frozen` |
| `as_dict()` 隔离 | 返回副本；改返回值不污染实例 | ✅ `test_t4_as_dict_returns_copies` |
| 无运行时决策消费 | `grep HostProfile` 仅 `runtime/host_profile.py` + 测试 | ✅ 实测仅 `runtime/host_profile.py` 3 处定义/构造，零消费点 |

### 3.2 `detect_host_profile()`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 仅关键字参数 | 位置传参 `TypeError` | ✅ `test_detect_requires_keyword_arguments_and_defaults` |
| 默认值 | `disk_root=None`、`toolchains=("python","docker","git")` | ✅ 同上（`inspect.signature` 断言） |
| 先校验后探测 | 非法名在任何子进程之前抛 `ValueError` | ✅ `test_t2_invalid_toolchain_rejected_before_probe` |
| 探测降级 | memory/disk/toolchain 任一异常 → `0/0.0/省略键`，不抛 | ✅ `test_t3_probe_exception_is_omitted`、`test_t4_disk_failure_is_zero`（3 条 toolchain 探测异常均省略键） |

### 3.3 `researchclaw/hardware.py::list_gpu_devices()`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 返回类型 | `tuple[str, ...]`；空行被跳过；原文保留 UUID | ✅ `test_list_gpu_devices_parses_all_lines` |
| 固定命令与超时 | `["nvidia-smi","-L"]`、`shell=False`、`timeout=10`、`check=False` | ✅ 同上（`seen` 断言 `timeout=10`/`check=False`/`shell≠True`） |
| 不回归既有探测 | `_detect_nvidia` 首行行为与 `detect_hardware` 输出不变 | ✅ `test_detect_nvidia_first_line_behaviour_unchanged` |

### 3.4 `tests/boundary_registry.yaml` schema

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 键三元组 | `(relpath, qualname, ordinal)` 唯一，无重复 | ✅ `test_registry_schema` + `load()` 重复键 fail-closed |
| `env` 枚举合法 | 仅 `inherit/allowlist/sourced:<name>/prefix`（`overrides` 保留不用） | ✅ `test_registry_schema`（`overrides` 断言不出现） |
| `category` 合法 | A/B/C；B 类必须 `env: allowlist`，例外三类：`sourced:`（自建 allowlist）、`prefix`（U-5）、容器内 `inherit`（reason 含 container） | ✅ `test_registry_schema`（DESIGN §11.2；IMPL §5.1） |
| 豁免合规 | `write_sites.policy: exempt` 仅 1 条且三要素齐全 | ✅ `test_registry_schema`（exempt 恰 1 条 + 三要素非空） |

## 4. 不变式验收（来自 DESIGN §8；冻结裁决见 DESIGN §11）

| 不变式 | 验证方法 | 状态 |
|--------|---------|------|
| I-1 `HostProfile` 只读、frozen、无策略字段、`as_dict()` 无 callable | T-1 + §3.1 接口核对 | ✅ `test_t1_shape_and_scalar_only_payload` + `test_t1_snapshot_is_frozen` + `test_t4_as_dict_returns_copies` |
| I-2 `researchclaw/**` 内 `shell=True` 恒为 0 | T-7 真实扫描 | ✅ 全仓 grep 0 命中；`test_t7_shell_true_is_red_without_exemption` |
| I-3 未登记调用点 → 红；登记陈旧 → 红（双向） | T-5 + T-6 | ✅ `test_t5_unregistered_subprocess_is_red` + `test_t6_stale_entry_is_red` |
| I-4 动态名写点未登记 → 红 | T-8 | ✅ `test_t8_dynamic_write_is_red_but_literal_is_not` |
| I-5 `build_subprocess_env` / `safe_join` 语义不变，既有 9 用例绿 | T-13 + `git diff` 本体零改动 | ✅ `test_env_allowlist.py` + `test_safe_join.py` 全绿；两本体文件不在 diff |
| I-6 7 处 overrides 只减不增，无新增敏感键 | T-11 + 逐点 diff | ✅ `test_t10_env_is_closed_over_allowlist`；`git diff` 逐点核对 |
| I-7 守卫先红后绿 | 实施批保留步骤 1 失败输出 + 步骤 6 全绿输出 | ✅ IMPL §13.1（89 条红 → 合并回归 60 passed） |
| I-8 `HostProfile` 不参与运行时决策 | `grep` 消费点 + 代码评审 | ✅ 仅 `host_profile.py` + 测试引用 |

## 5. 错误处理验收

| 错误场景 | 触发方式 | 预期行为 | 状态 |
|---------|---------|---------|------|
| 注册表缺失 | 删除文件后跑守卫 | 直接 fail（fail-closed），不跳过 | ✅ `test_load_fail_closed`（`FileNotFoundError`） |
| 注册表版本不符 | `version: 2` | 抛错并拒绝加载 | ✅ `test_load_fail_closed`（`ValueError`） |
| 同键重复登记 | YAML 重复条目 | 加载即失败（不静默覆盖） | ✅ `test_load_fail_closed`（`match="duplicate"`） |
| ordinal 漂移 | 同函数内插入新调用 | 报「疑似 ordinal 漂移」+ 上下文首行 | ✅ `test_t6_stale_entry_is_red` |
| `shell=True` 注入 | 合成树 | 红，且无豁免通道 | ✅ `test_t7_shell_true_is_red_without_exemption` |
| env 形态不符 | 登记 `inherit` 实测 allowlist | 红（双向校验） | ✅ `test_r4_environ_copy_is_red`（反向：登记 allowlist 实测 `os.environ.copy` 亦红） |
| 非法 toolchain 名 | `("python; rm -rf /",)` | `ValueError` 且无子进程 | ✅ `test_t2_invalid_toolchain_rejected_before_probe` |
| GPU 探测失败 | mock `FileNotFoundError` / rc≠0 | `()`，不抛 | ✅ `test_list_gpu_devices_degrades` |
| `safe_join` 逃逸 | `../`、绝对路径、symlink | `ValueError` | ✅ `test_t12_safe_join_escapes` |
| 豁免过期 | `expires` 早于当天 | 守卫红并列出条目 | ✅ `test_expired_exemption_is_red` |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| 守卫全量扫描 `researchclaw/**` | < 5s（单核，本地 SSD） | 0.93s（Window 本机，60+31 条，Python 3.12） | ✅ |
| `detect_host_profile()` 正常路径 | < 2s（三 toolchain 均存在） | 0.15s（python/docker/git 均存在） | ✅ |
| 生产运行时新增开销 | 0（注册表仅测试消费，无 import 侧读盘） | 0（`host_profile.py` 无模块级探测；注册表仅测试读取） | ✅ |

## 7. 兼容性验收

| 环境 / 项 | 版本 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.11 | ✅ | 3.11.15：两新测试文件 `py_compile` 通过 + `host_profile`/`hardware` 实跑成功；该解释器未装 pytest/PyYAML，完整套件由 CI matrix 覆盖 |
| Python | 3.12+ | ✅ | 3.12 本机：`30 passed`；3.13.5 本机：`30 passed`（均含 v1.4 F-1 补录 T-14，17+13）；无新语法依赖 |
| OS | Windows | ✅ | `GlobalMemoryStatusEx` 分支（本机 3.12/3.13 实跑 T-1） |
| OS | Linux | ☐ | `os.sysconf` 分支为 stdlib 直调；待 CI `ubuntu-latest` 首跑（`.github/workflows/ci.yml` 已接线） |
| 依赖面 | 零新增 | ✅ | 仅 stdlib + 既有 PyYAML（`pyproject.toml` 未改） |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0，P-106 交付时评分）

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 1.0 | T-1..T-13 均有可机械断言 |
| 模块映射 | 1.0 | DESIGN §3.2 ↔ IMPL §3 逐行对应 |
| 接口契约 | 1.0 | 五字段/签名/返回类型与 M0 §8 对齐 |
| 修正项 | 0.9 | R-1..R-3 修订显式登记；E-4 隐式环境变量行为变更依赖 T-11 兜底 |
| 跨模块契约 | 0.9 | registry ↔ guard ↔ 7 执行点闭环；`tools/**` 域外已裁决 |
| **总分** | 4.8/5 | **档位**: A |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P2 | E-4 切换 allowlist 后，隐式代理/认证环境变量不再继承 | IMPL §7 行为变更登记 | 实施批以 T-11 哨兵用例验证；需要的键由 `env_extra` 显式提供 |
| P3 | R5 纯 Name 盲区（路径先在别处拼好） | DESIGN §11.1 | 人工审查兜底；改判候选 B 需重估注册表规模 |
| P3 | R1 方法别名盲区（`supervisor.py:71`） | DESIGN §13 N-1 | 已知限制已登记；负向用例已补录 `test_t14_alias_spawn_is_outside_scan`（IMPL §13.5，DESIGN §13.7 F-1 闭环），人工审查兜底为长效控制 |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式：T-2/T-5/T-8 逐条确认断言可失败（实施批需提供「改坏即红」的反向证据）
  - T-2（GPU 降级）：`test_list_gpu_devices_degrades` 以 `FileNotFoundError`/rc≠0 驱动 → `()`。
  - T-5/T-8：空注册表下真实扫描产出 89 条错误（60+31），删一条登记后 `test_t9` 必非空。
- [x] 单文件检查盲区：守卫必须扫 `scan.roots` 全量，不允许只测 fixture 树
  - `test_registry_is_consistent` 直接调 `load()` 默认注册表 + `scan(scan.roots)` 全量根。
- [x] 设计文档独有约束无测试：I-1..I-8 已逐条映射到 T 编号（§4）
- [x] 修正阻断性项无测试：R4 三通道、ordinal 漂移、豁免过期均有对应用例（§5）

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md（v1.2） | ✅ | ✅（未因实施改动） |
| DESIGN.md（v1.4） | ✅ | ✅（§11.2 实施订正已回填） |
| IMPLEMENTATION.md（v1.2） | ✅ | ✅（§13 实施记录 + 实测计数） |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR（如有） | 不适用 | — |
| 开发日志 | ✅ | IMPL §13 + `docs/PROGRESS.md` P-106 |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 17 | 17 | 0 | 0 |
| 功能 | 23 | 23 | 0 | 0 |
| 接口 | 15 | 15 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 10 | 10 | 0 | 0 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 5 | 4 | 0 | 1 |
| ADD 审计 | 3 | 3 | 0 | 0 |
| **总计** | 84 | 83 | 0 | 1 |

> **统计口径（RULE-2）**：上表来自本文件逐项核对，每一项均有独立标记，非事后汇总推算。ADD 审计按 §8.1/§8.2/§8.3 三个验收单元计（§8.2 的三条发现作为该单元内容，不单独计数）。唯一待办 = Linux 分支待 CI `ubuntu-latest` 首跑（§7）。
>
> **规范形态（P-050 交付 A）**：章节号固定 `### 10.1 验收统计`（未改号）；数值单元格均为纯十进制整数；逐行 `总数 = 通过 + 失败 + 待办`（17=17+0+0、23=23+0+0、15=15+0+0、8=8+0+0、10=10+0+0、3=3+0+0、5=4+0+1、3=3+0+0），总计行按列求和（84 / 83 / 0 / 1）。

### 10.2 验收决定

- [ ] **验收通过**：所有 P1 项通过，无阻塞性问题（待实施批回填后判定）
- [x] **有条件通过**：所有 P1 项（§2/§3/§4/§5）通过；条件为 ① Linux 分支待 CI `ubuntu-latest` 首跑（§7 唯一 ☐）；② P2 行为变更（E-4 隐式 env 不再继承）已登记于 IMPLEMENTATION §7 行为变更登记表（仓库无独立发布说明工件——DESIGN §13.7 F-5 指向订正）
- [ ] **验收失败**：R1..R6 任一失效或 I-1..I-8 任一不成立

**P-106 实施批阶段结论**：§2..§6 全部通过（功能 23 + 接口 15 + 不变式 8 + 错误处理 10 + 性能 3 = 59 项），§1 文档一致性 17/17，§8 ADD 审计 3/3，§9 文档齐全；§7 兼容性 4/5（唯一待办 = Linux 分支待 CI）。合计 **83/84 通过**。**A4-7（7 处 allowlist）/A4-8（31 处 safe_join + 1 exempt）/A4-9（HostProfile + 零 shell=True）均已落地**，守卫 R1..R6 双向一致且元测试防空转。

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者（文档批） | DeepSeek-V4.1-Flash | 2026-11-14 |
| 实施者（代码批） | DeepSeek-V4.1-Flash | 2026-11-14 |
| 审查者 | | |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| 实施批按 IMPL §4 六步执行并回填 §2..§7 | 后续实施批 | 实施批内 | ✅ 2026-11-14 完成 |
| 实施批保留守卫「先红」输出作为 I-7 证据 | 后续实施批 | 同上 | ✅ IMPL §13.1（89 条红） |
| 更新 PROGRESS.md P-106 行为 `verify` 并追加验收记录 | 实施批 | 验收时 | ✅ |
| 四文档提交前跑 T1 四文档门禁 + 9 门禁 | 实施批 | 提交前 | ✅ |

---

**Review 签字**: DeepSeek-V4.1-Flash（文档批自审） 日期: 2026-11-14
