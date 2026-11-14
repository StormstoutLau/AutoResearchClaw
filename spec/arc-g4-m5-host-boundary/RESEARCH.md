# 调研文档：G4-M5 宿主边界 / env allowlist / safe_join / HostProfile

---
id: arc-g4-m5-host-boundary-RESEARCH
type: design
version: 1.2
status: verified
date: 2026-11-14
depends: [arc-g4-m0-design-RESEARCH, arc-g4-m4-sandbox-limits-RESEARCH]
upstream: arc-g4-m0-design-RESEARCH
---

> **Feature**: arc-g4-m5-host-boundary（P-106，G4-M5）
> **创建日期**: 2026-11-13
> **状态**: verified（Step 2 Review 自查 + §5.4 异构复审：U-1..U-4 全部成立，订正 3 处已回填）
> **Spec 步骤**: Step 1-2（本轮只做调研，不改代码）
> **修订**: v1.0（2026-11-13）初稿（AST 盘点 + HostProfile 草案 + U-1..U-4 登记）→ **v1.1**（2026-11-13）新增 §6.6：U-1..U-4 方案比选、注入点裁决、外部先例（MCP SDK / sudo / Bandit / CWE-22），并补测 hardware.py 首行折叠与 8 个后端清点 → **v1.2**（2026-11-14）§5.4 异构复审（U-1..U-4 全部成立）；订正 3 处回填（HF_HUB_CACHE 措辞 / pipeline/ 路径消歧 / shell=True 口径限 researchclaw/**）；新发现 ssh 命令行前缀 env 形态与 tools 域 shell=True 转 DESIGN
> **上游依据**: [M0 DESIGN §7/§8/§9/§10](../arc-g4-m0-design/DESIGN.md)、[M0 RESEARCH A4-7/A4-8](../arc-g4-m0-design/RESEARCH.md)、[P-100 复核 X-6](../../docs/arc-g4-m0-design-review-20261114.md)、[G4 中期盘点](../../docs/arc-g4-midpoint-20261113.md)
> **基线**: `5cf14e7`（P-105 收敛批已推送）

---

## 1. 调研目标

**核心问题**:
1. A4-7（全部沙箱后端 env allowlist）、A4-8（全部写入点 `safe_join`）、A4-9（HostProfile 宿主对齐）三项在当前实现中**分别缺什么、缺多少**（E1 一手实测，不接受中期盘点的二手计数）？
2. M4-D6 的 AST 守卫（`tests/test_boundary_coverage.py`）在**纯静态分析**下能判到什么精度（误报 / 漏报边界）？P-102 X-6 预判的「注册制白名单 + 兜底扫描」是否成立？
3. HostProfile 与既有 `hardware.py`（`HardwareProfile`/`detect_hardware`）**是复用、包装还是新建**？如何避免成为 registry `sandbox_profiles` 与 `DockerSandboxConfig` 之外的**第三真值源**？

## 2. 调研方法

### 2.1 使用的工具

| 工具 | 用途 | 查询 / 对象 |
|------|------|------|
| Grep / Read（本仓一手） | 现状实证 | `researchclaw/**`、`tests/**`、`tools/registry.yaml`、`ci.yml` |
| Python `ast` 只读脚本（临时，不入仓） | subprocess 调用点 / 写入点全量盘点 | `%TEMP%\ast_env_scan.py`、`%TEMP%\ast_write_scan.py` |
| WebFetch（T1 官方文档） | `subprocess` 的 `env`/`shell` 语义 | docs.python.org/3/library/subprocess.html |
| WebSearch（T3 反例） | env 透传的工程陷阱 | 仅作反例发现，不作 A 类依据 |

### 2.2 调研范围

- **时间**: 2026-11-13，基线 HEAD `5cf14e7`
- **代码范围**: `researchclaw/**` 全部 `.py`（含 `vendor/auto_prover`，标注来源）
- **排除**: 不改造 `vendor/` 行为；不做跨 run 编排（G7）；不改 registry 真值源语义（P-105 D-Q1=C 冻结）

## 3. 调研发现

### 3.1 现状实证（E1，2026-11-13 本机，基线 5cf14e7）

| # | 事实 | 证据（一手） |
|---|------|-------------|
| F-1 | `subprocess.{run,Popen,check_call,check_output,call}` 实测 **58 处真实调用 / 23 文件**（朴素 AST 命中 60，剔除 2 处同名 `call` 误报：`mcp/registry_adapter.py:85`、`pipeline/executor.py:618`）；**全部 `shell=False`，0 处 `shell=True`** | 临时 AST 脚本输出；`grep` 文本 72 命中含 import/注释 |
| F-2 | `build_subprocess_env` 定义于 `utils/env.py:50-64`；白名单 = `SAFE_ENV_KEYS`（28 键）+ `LC_*` 前缀 + `PYTHONUNBUFFERED` 默认；**消费点 2 处**：`experiment/sandbox.py:329`、`:430`，`mcp/client.py:71` | utils/env.py 全文；grep `build_subprocess_env` 全仓 21 行（含测试/文档） |
| F-3 | **未改造 env 透传 = 6 处**（中期盘点记为「4 处 + 1」，漏 2 处）：`stat_agent_sandbox.py:381`、`biology_agent_sandbox.py:457`、`collider_agent_sandbox.py:682`、`hitl/hooks.py:211`、`pipeline/opencode_bridge.py:462`（`os.environ.copy()`）+ `experiment/code_agent.py:462`（`{**os.environ, **self._env_extra}`） | grep `os.environ.copy()` / `{**os.environ}` 逐条 Read |
| F-4 | 58 处调用中 **10 处显式传 `env`**（含 `sidecar.py:219`、`vendor/.../evaluator.py:341` 的后端自建 env），**48 处不传 env 即全量继承父进程** | AST 脚本 `has-env` / `no-env` 两组清单 |
| F-5 | 不传 env 的 48 处按行为分三类：**A 宿主工具/CLI**（docker/git/ssh/pdflatex/nvidia-smi/taskkill/opencode/acpx：约 43 处）、**B 工作负载执行**（`agents/figure_agent/renderer.py:264` 本地执行生成脚本；`vendor/.../evaluator.py` 已有 `_worker_env`）、**C 生命周期管理**（`docker kill`/`rm`/`inspect`） | AST 清单逐条分类；renderer.py:264 / evaluator.py:234-243 一手 Read |
| F-6 | 写入点实测 **319 处 / 87 文件**（`write_text`/`write_bytes`/写模式 `open`/`shutil.copy*`/`os.replace`）；`safe_join` **唯一消费点** `_execution.py:1258`（`_write_project`），其余 318 处为裸拼接 | 临时 AST 写入点脚本 + `grep safe_join` 全仓 49 行 |
| F-7 | 变量名驱动的写点 **37 处**（`fname` / `plan_file` / `spec['meta_file']` / `card_id` / `run_id` / `prompt_path` / `results_path` / `script_path` / `output_path` / `target`），其中仅 1 处已 `safe_join`；代表点：`_code_generation.py:326,327,345,1208,1239,1323,1459,1621,1735`、`_literature.py:992`（`cards_dir / f'{card_id}.md'`）、`_execution.py:711,732`（`runs_dir / f'{_safe_filename(run_id)}.json'`）、`hitl/collaboration.py:172`、`pipeline/experiment_repair.py:416`、`pipeline/runner.py:1766` | AST 写入点脚本过滤输出 |
| F-8 | `researchclaw/runtime/` 现有 11 模块（event_log/mandate/prompt_context/stage_events/filelock/attempt/event_stream/exit_codes/lease/outbox/supervisor），**无 `host_profile.py`**；`HostProfile` 全仓零命中（仅 M0 DESIGN §8 文本） | `Glob researchclaw/runtime/*.py` + grep `HostProfile` |
| F-9 | `tests/test_boundary_coverage.py` **不存在**；`tests/test_env_allowlist.py`（4 用例）与 `tests/test_safe_join.py`（5 用例）已在 CI 固定清单（`ci.yml:151` 等） | Glob `tests/test_boundary*.py` 空；ci.yml 一手 |
| F-10 | `hardware.py` 已有 `HardwareProfile`（L30）、`detect_hardware()`（L44）、`_detect_nvidia_remote/_detect_nvidia/_detect_mps`（L98/153/207）、`ensure_torch_available`（L246）——**宿主探测能力已存在**，HostProfile 若重写即产生第二套口径 | hardware.py 结构 grep + 调用点 |
| F-11 | `DockerSandboxConfig` 现有 13 字段（image/gpu/memory/network_policy/pip/auto_install/shm/python/keep_containers/cpu_limit/pids_limit/ttl_sec/kill_grace_sec/ttl_poll_sec），**无宿主维度**（cpu_count/memory_total/disk_free/gpu_devices/toolchains） | config.py:311-332 |
| F-12 | `tools/registry.yaml:135-142` `sandbox_profiles.default = {network: none, cpu: 2, memory: 4g, pids: 512, disk: 10g, ttl_sec: 1800}`；与 config `memory_limit_mb=8192` 数值冲突，P-105 已裁决 **config 优先、profile 留工具化批次**（D-Q1=C，零运行时消费） | registry.yaml + M0 §6 M4 落地状态块 |
| F-13 | `code_agent.py:462` 的 `_env_extra` 承载 CLI 代理认证；`opencode_bridge.py:462-470` 显式注入 `OPENAI_API_KEY`；`hitl/hooks.py:211-216` 注入 4 个 `RC_*`。**直接换 allowlist 会切断这些认证/契约** | 三处一手 Read |
| F-14 | `agents/figure_agent/renderer.py:264` 在宿主本地执行**模型生成的 Python 脚本**且不传 env —— 密钥暴露面最大的一处（非「沙箱后端」，但属等价执行面） | renderer.py:255-270 |
| F-15 | AST 朴素判定「env 来自 `build_subprocess_env`」需变量数据流追踪：`env = build(); run(env=env)` 的中间变量无法纯 AST 判定；本次实测误报率 2/60（3.3%），漏报面（别名/局部重构）不可静态枚举 | P-102 X-6 预判 + 本次实测 |

### 3.2 外部事实（T1/T3）

| 事实 | 来源 | 层级 | 验证状态 |
|------|------|------|---------|
| `env` 非 `None` 时**替换**子进程环境，而非在继承环境上做增量；`None` 才继承父环境 | Python 3 官方文档 `subprocess.Popen`（docs.python.org/3/library/subprocess.html，2026-11-13 抓取） | T1 | ✅ 官方原文 |
| `shell=False` 为默认：args 序列不经过 shell 解释，`shell=True` 是显式开关 | 同上 | T1 | ✅ 官方原文 |
| `Path.resolve()` 解析符号链接并返回绝对路径（`strict=False` 语义），是 `safe_join` 识别 symlink 逃逸的依据 | Python 官方 `pathlib` 文档（同版本文档树） | T1 | ✅（与 utils/paths.py 实现一致） |
| 「子进程继承全量 env 导致密钥泄漏；应使用 allowlist」是安全审计通用规则 | Sourcery 漏洞库 tainted-env-args / dangerous-subprocess 条目 | T3 | ⚠️ 仅作反例与工程陷阱来源，不作 A 类依据 |

## 4. 综合分析

### 4.1 关键发现总结

1. **A4-7 的真实缺口是「分类」而非「计数」**：6 处显式全量透传（F-3）+ 48 处默认继承（F-4）。其中约 43 处是宿主工具/CLI，**必须**保留认证与代理环境（F-13）；真正需要改造的是「工作负载执行面」（F-5 B 类：renderer 本地执行、agent sandbox、code_agent、opencode/acpx）。一刀切替换会打断 CLI 代理认证。[置信度: ★★★★★]
2. **A4-8 的真实缺口是「可控性」而非「319 处」**：319 个写点中 37 处为变量名驱动（F-7），其余为固定字面量文件名；A4-8 的判据原文是「基础目录 / **用户可控文件名**的拼接」（M0 §7），因此验收口径应收敛为「动态名 × run 作用域外」的子集，而非全量改写。[置信度: ★★★★★]
3. **M4-D6 不能用纯 AST 直接判「env 来源」**：F-15 实测误报 2/60，且中间变量形态无法静态追踪。P-102 X-6 的「注册制白名单 + 兜底扫描」成立，但必须把「注册的是什么」（文件+行号+豁免理由）写成可审计清单。[置信度: ★★★★★]
4. **HostProfile 与 `hardware.py` 重叠**（F-10），且 M0 §8 已冻结其形状为**宿主清单快照**（cpu_count/memory_total_mb/disk_free_gb/gpu_devices/toolchains），**不是策略容器**。若把 env_allowlist/network_policy 塞进 HostProfile，会与 F-12 的真值源分层冲突，形成第三真值源。[置信度: ★★★★☆]
5. **守卫缺口是零**：`tests/test_boundary_coverage.py` 不存在（F-9），而 I-7 要求它「先红后绿」——当前无红可跑，必须先建守卫并让它对着真实缺口变红。[置信度: ★★★★★]

### 4.2 技术 landscape

本仓已存在两层边界设施：H-6 env allowlist（`utils/env.py`）与 H-7 路径围栏（`utils/paths.py`），并各有一个既有测试文件挂在 CI。缺口不在「工具函数」而在**覆盖面与机械守卫**。业界同构做法分三档：① 纯静态规则（快、误报高）；② 注册制白名单 + 扫描兜底（本批推荐）；③ 运行时拦截（wrapper 统一收口，改造面最大）。M5 采用档 ②，与 P-102 X-6 结论一致。

### 4.3 研究空白

「env 变量来源」与「文件名可控性」都属**数据流性质**，纯 AST 无法判定；仓内也没有统一的子进程入口 wrapper（58 处直接调用）。因此守卫的诚实边界是：**只保证「显式传 env 的调用点已登记且来源合法」，不保证「遗漏的调用点被自动发现」**——后者需兜底扫描（无 env 的调用点也必须登记分类）。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证

| 引用 | ID/位置 | 验证方式 | 状态 |
|------|---------|---------|------|
| M0 §7 守卫要求、§8 HostProfile 形状 | spec/arc-g4-m0-design/DESIGN.md L137-158 | 本会话 Read | ✅ |
| P-102 X-6 AST 精度预判 | docs/arc-g4-m1-registry-review-20261114.md L34 | 本会话 Read | ✅ |
| G4 中期盘点 A4-7/A4-8 计数 | docs/arc-g4-midpoint-20261113.md L29-30、L88 | 本会话 Read；**计数以本文 F-3/F-6 订正** | ✅（已订正） |
| Python `subprocess` env/shell 语义 | docs.python.org/3/library/subprocess.html | WebFetch 原文（2026-11-13） | ✅ |
| Sourcery env 泄漏实践 | sourcery.ai 漏洞库 | WebSearch 摘要 | ⚠️ T3，仅反例 |
| `safe_join` 同名同语义实现 + symlink 检查为 point-in-time（TOCTOU） | MCP Python SDK 官方文档 `mcp.shared.path_security`（py.sdk.modelcontextprotocol.io，2026-11-13 抓取） | WebFetch 原文 | ✅ T1 |
| 特权边界用「最小环境 + env_keep 白名单」：`env_reset` 默认 ON，仅保留 TERM/PATH/HOME/MAIL/SHELL/LOGNAME/USER 等 | sudo 手册 / SUSE 官方文档（env_reset/env_keep 语义） | WebSearch 摘要 | ✅ T2（机制先例，非本仓依据） |
| 静态扫描 subprocess 以 B602/B603 分族，豁免用 `# nosec <ID>` 显式标注 | Bandit 官方文档 Test Plugins（B602/B603/B607） | WebSearch + 官方插件页 | ✅ T1（工具机制） |
| 路径穿越通用防御：先 canonicalize（realpath/resolve）再比较前缀；`join` 本身不是安全边界 | CWE-22 指南与多家 AppSec 实践 | WebSearch 摘要 | ✅ T2 |

### 5.2 技术声明验证

| 声明 | 来源 | 验证状态 |
|------|------|---------|
| 58 处 subprocess / 23 文件、0 处 shell=True（口径限 researchclaw/**；tools/spec_runner/spec_runner.py:171 有 1 处 shell=True，域外不影响 M0 §8 口径） | AST 脚本全量输出 + v1.2 复审独立重扫（62 文本命中/22 文件，剔 colab 模板 2 + 同名 call 2 = 58 收敛一致） | ✅（可重放：脚本读 `researchclaw/**`） |
| 6 处 env 全量透传 | grep + 逐条 Read | ✅ |
| 319 处写点 / 87 文件、1 处 safe_join | AST 脚本 + grep | ✅ |
| runtime 无 host_profile.py；test_boundary_coverage.py 不存在 | Glob | ✅ |
| registry `sandbox_profiles` 与 config memory 冲突 | registry.yaml L135-142 + config.py L317 | ✅ |

### 5.3 待修正项

- [x] 中期盘点 A4-7「4 处裸 `os.environ.copy()`」→ 订正为 **5 处 copy + 1 处 merge = 6 处**（补 `hitl/hooks.py:211`、`opencode_bridge.py:462`）
- [x] M0 §7「现有 3/2 文件的已知缺口」→ 订正口径为「env **消费点 2 处**（+定义处 1）/ safe_join **消费点 1 处**（+定义处 1）」
- [x] 「HostProfile 承载 env/network 策略」的表述 → 以 M0 §8 冻结形状为准，策略字段留在 config（见 U-1）

### 5.4 异构复审记录（v1.2，2026-11-14）

复审方式：独立上下文子代理，devil's advocate（先核验锚点、再构造最强反驳）；关键争议点由实施会话亲自复核消歧。**异构性如实声明：上下文异构达成（独立会话、零先前推理锚定），基座同为 GLM-5.3-Flash——基座级异构（RULE-5 完整形态）待外部模型补位**（P-102/P-103 先例为 DeepSeek↔GLM 交叉）。

| 裁决 | 判定 | 复审实测读数 | 最强反驳是否致命 |
|---|---|---|---|
| U-1=C | **CONFIRM** | 5 构造点（62/85/140/195/232）、2 消费模块、首行折叠（L172-173）、探测命令逐条命中；「拒绝纯包装」论证坚实——HardwareProfile 不保留原始 stdout，纯映射无法产出设备列表 | HostProfile 草案无 ssh 参数 vs `detect_hardware(ssh_config)` 支持远端——M0 §8 未要求 remote，不致命 |
| U-2=A | **CONFIRM** | 456/462 漂移实证、grandfather.yaml reason/owner/expires、M0 §7「默认空」均吻合；2 处 AST 误报复实（`call(**kwargs)` / 无 import） | grandfather=豁免清单（默认空）vs registry=全量登记（存量非空），语义非完全同构——裁决文本已自区分，不致命；附 DESIGN 输入：`(relpath, qualname)` 需补同函数多调用点消歧规则 |
| U-3=B | **CONFIRM（1 处措辞订正）** | 8 后端类行号 8/8、7 改造点 7/7 命中；SSH 3 处（L145/374/425）均无 env=；**Colab 宿主侧真实 subprocess=0**（L72/86 文本命中在 `COLAB_WORKER_TEMPLATE` 三引号模板内，实施会话亲自复核证实） | 「模板内执行模型生成代码」——但宿主 env 不参与 Colab VM 环境，反驳失败 |
| U-4=A | **CORRECT** | 全部行号命中（含 `pipeline/_code_generation.py` 9 处、`_execution.py:711/732` 为 `_safe_filename` 无 safe_join）；safe_join 唯一消费点、pyproject L21 mcp extra 属实 | `pipeline/runner.py:1766`（shutil.copy2）fname 为固定字面量列表（L1759-1763），按 U-4 自家判据初判落**豁免侧**——「约 30 处」逐点判定机械化程度低于自称，但不推翻子集方案 |

**计数收敛**：复审独立重扫文本命中 62/22 文件 vs 原报告 60/23——口径差异来自正则与模板字符串处理；剔除 colab 模板 2 处 + 同名 call 误报 2 处后 **58 真实调用双口径收敛一致**。建议 AST 扫描脚本随本批入仓固化（替代 %TEMP% 临时脚本）。

**订正清单（已回填 §5.2/§6.6）**：
1. U-3 措辞：docker_sandbox.py:602-655 注入的是 `HF_HUB_CACHE`（L634/640），HF_HOME 仅为宿主挂载读取源（L629）。
2. U-4 路径消歧：repair 点 = `pipeline/experiment_repair.py:416`（仓内唯一）；runner = `pipeline/runner.py:1766`（仓内另有 experiment/runner.py）。
3. F-1「shell=True=0」限定 researchclaw/**：tools/spec_runner/spec_runner.py:171（gate 执行器）有 1 处，域外不影响 M0 §8 负向用例口径。
4. U-2 DESIGN 输入补同函数多调用点消歧。

**新发现（转 DESIGN 输入）**：
- **ssh_sandbox.py:288-290**：`CUDA_VISIBLE_DEVICES=...` 以远程**命令行前缀**注入（env_prefix 形态，shlex.quote）——绕开 `env=` 参数通道；AST 守卫若只扫 env= 参数不覆盖此形态，DESIGN 须显式纳入并登记（单变量非密钥，初判豁免）。
- **opencode_bridge.py:465**：读任意配置变量名后写入 OPENAI_API_KEY 透传（F-13 已覆盖主键，登记动态名读取形态即可）。
- 十余处 `os.environ.get(config.*_key_env)` 挑选式读点（health.py:762、llm/client.py:134/236 等）仅入进程内对象，风险低，登记不动。

**总结论**：四条裁决方案选择与论证链经证伪攻击后成立，**可直接进 DESIGN**。

## 6. 对设计的输入

### 6.1 可用的技术方案

- **env 收口**：新增统一入口 `sandbox_env(overrides)`（薄封装 `build_subprocess_env`），6 处透传点改为「allowlist + 显式 overrides（provider key / RC_* / MAGNUS_*）」；无 env 的「B 类工作负载执行」点补 allowlist；A 类宿主工具登记为豁免（保留继承）。
- **safe_join 收口**：只改造 37 处动态名写点中「基础目录可能被外部影响」的子集，其余登记为固定名豁免；新增白名单文件（默认空 + 逐条理由）。
- **AST 守卫**：`tests/test_boundary_coverage.py` = ① 扫描全部 subprocess 调用 → 每处必须出现在注册表（分类 + 是否传 env + 豁免理由）；② 扫描全部写点 → 动态名必须经 `safe_join` 或在豁免表；③ 负向自测（人为删一条注册 → 红）。
- **HostProfile**：新建 `researchclaw/runtime/host_profile.py`，按 M0 §8 冻结形状实现只读快照，探测委托 `hardware.py` 既有函数；`as_dict()` 仅标量/列表；固定白名单命令 + `shell=False`。

### 6.2 关键约束

- M0 §10 I-6（默认 `network: none` 不回退）、I-7（守卫为新增门禁，先红后绿）
- P-105 D-Q1=C：config 优先，registry profile 零消费——HostProfile 不得成为第三真值源
- P-102 X-6：AST 守卫必须「注册制 + 兜底扫描」，并诚实登记误报率
- RULE-3：不得用 skipif 充验收；CI 无 Docker 的部分沿用 P-105 quarantine 口径
- RULE-5：本批实施与复核须异构（实施/复核不同基座）

### 6.3 风险

- 6 处透传改造若漏配 overrides → CLI 代理/OpenCode 认证失败（缓解：逐点回归 + 保留 `_env_extra` 通道）
- 319 处写点若全量改写 → 高风险大 diff（缓解：只改动态名子集，其余显式豁免）
- AST 守卫误报导致「为过守卫而改代码」（缓解：豁免表 + 负向自测 + 审查豁免理由）
- `renderer.py:264` 属宿主执行面但不在「沙箱后端」字面范围（缓解：登记为 A4-7 扩展点，见 U-3）

### 6.4 未决项登记（四元块）

> **v1.1 更新**：本节四项已于 **§6.6** 完成方案比选并给出裁决（U-1=C 包装+公共辅助 / U-2=A 外置 YAML / U-3=B 按执行内容判定 7 处 / U-4=A 动态名子集）。下方四元块保留原始判据、触发条件与证据等级，供 DESIGN 引用。**v1.2**：四条裁决经 §5.4 异构复审全部成立（U-4 附 `pipeline/runner.py:1766` 豁免侧初判）。

- **U-1 HostProfile 与 `hardware.py` 的关系**
  - **判据**：全仓仅一套宿主探测口径，HostProfile 不重复实现探测，且不承载策略字段
  - **触发条件**：DESIGN 定稿前
  - **当前倾向**：新建 `runtime/host_profile.py` 作**只读快照**，探测委托 `hardware.detect_hardware`；env/network 策略留在 `DockerSandboxConfig`
  - **证据等级**：E1（F-10/F-11/F-12 一手）
- **U-2 守卫注册表的形态与位置**
  - **判据**：注册项可审计（文件+行号+分类+理由），且新增调用点未登记即红
  - **触发条件**：DESIGN 定稿前
  - **当前倾向**：`tests/boundary_registry.yaml`（默认空豁免）+ 守卫测试读取；不引入运行时依赖
  - **证据等级**：E1（F-6/F-9/F-15）
- **U-3 「沙箱后端」的判定边界**
  - **判据**：A4-7 覆盖口径明确到「哪些执行面算后端」（是否含 `figure_agent/renderer` 本地执行、acpx/opencode 宿主 CLI）
  - **触发条件**：DESIGN 定稿前（影响改造点数量：6 处 vs 8 处）
  - **当前倾向**：按「是否执行模型生成物」判定——renderer:264 纳入，纯宿主 CLI（docker/git/ssh/pdflatex）豁免
  - **证据等级**：E1（F-5/F-14）
- **U-4 safe_join 的验收子集**
  - **判据**：A4-8 判据可机械判定，且不要求改写 319 处
  - **触发条件**：DESIGN 定稿前
  - **当前倾向**：仅「变量名驱动 × 基础目录非 run 私有常量」子集（37 处中约 30 处），其余显式豁免
  - **证据等级**：E1（F-6/F-7）

### 6.5 HostProfile 接口草案（按 M0 §8 冻结形状）

```python
# researchclaw/runtime/host_profile.py
@dataclass(frozen=True)
class HostProfile:
    """Read-only host snapshot. No policy, no callables (M0 §8)."""

    cpu_count: int
    memory_total_mb: int
    disk_free_gb: float
    gpu_devices: tuple[str, ...]          # nvidia-smi -L 解析失败 -> ()
    toolchains: Mapping[str, str]         # python/docker/git 版本；固定白名单命令

    def as_dict(self) -> dict[str, Any]:  # 仅标量/列表/字典，无 callable
        ...


def detect_host_profile(
    *, disk_root: Path | None = None, toolchains: tuple[str, ...] = ("python", "docker", "git")
) -> HostProfile:
    """Thin wrapper over hardware.py; subprocess 仅固定白名单 + shell=False。"""
```

> **不在 HostProfile 内**：`env_allowlist` / `network_policy` / cpu 配额。这三项分别归 `utils/env.py`、`DockerSandboxConfig`、`DockerSandboxConfig`（避免第三真值源，见 U-1）。

### 6.6 U-1..U-4 深入分析：方案比选与注入点裁决（v1.1 新增）

#### U-1 HostProfile 注入点

**新增证据（本轮补测）**：
- `HardwareProfile` 是 frozen dataclass，构造点 **5 处**（hardware.py:62/85/140/195/232），消费点 2 个模块（`pipeline/_helpers.py:18`、`pipeline/executor.py:17`）→ 扩字段是破坏性变更。
- **`_detect_nvidia` 只解析首行**（hardware.py:172-173 `splitlines()[0]`）→ 多 GPU 被静默折叠；`gpu_name` 是展示串（"NVIDIA RTX 4090"），**拿不到设备列表**，M0 §8 要求的 `gpu_devices: tuple[str, ...]` 无法由 `detect_hardware` 直接满足。
- 现有探测命令 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`（hardware.py:156-161）与 `nvidia-smi -L` 输出格式不同。

**方案比选**：

| 选项 | 做法 | 收益 | 代价 | 结论 |
|---|---|---|---|---|
| A 扩 `HardwareProfile` | 直接加 `cpu_count/memory/disk/toolchains` | 无新模块 | frozen 契约 5 构造点 + `to_dict` 消费面全改；与 M0 §8 冻结形状冲突 | ❌ 拒绝 |
| B 纯包装 `detect_hardware` | HostProfile = 字段映射 | 零重复探测 | `gpu_devices` 无法实现（首行折叠）；toolchains 仍需新探测 | ⚠️ 不足 |
| **C 包装 + 增公共辅助** | HostProfile 调 `detect_hardware()` + 新增 `hardware.list_gpu_devices()` | 单一口径；不改既有 `gpu_name` 行为；满足 §8 | 需在 hardware.py 增 ~8 行 | ✅ **推荐** |
| D 独立重写探测 | host_profile.py 自带 nvidia-smi/lscpu | 模块自足 | 第二套探测口径（违反 U-1 判据）；双倍子进程 | ❌ 拒绝 |

**裁决**：C。**注入点** = 新建 `researchclaw/runtime/host_profile.py`（只依赖 stdlib + `researchclaw.hardware`）；`hardware.py` 新增 `list_gpu_devices() -> tuple[str, ...]`（迭代**全部** query 行，失败返回 `()`），`detect_hardware` 保持首行行为不变。
**遗留登记**：多 GPU 首行折叠是既有缺陷，本批**不修**（改 `gpu_name/vram` 属行为变更），只由 `list_gpu_devices` 旁路暴露 → 记入 DESIGN 的已知限制。

#### U-2 守卫注册表形态

**新增证据**：M0 §7 已冻结原则——「白名单豁免清单显式登记，默认空」；因此争点仅剩**形态与键**。本轮 review 已实证**行号会漂移**（`code_agent.py` 456→462），故注册键不能用行号。

| 选项 | 做法 | 收益 | 代价 | 结论 |
|---|---|---|---|---|
| **A 外置 YAML** | `tests/boundary_registry.yaml`，键 `(relpath, qualname)` | 零源码侵入；可 diff/可审查；沿用 `spec/grandfather.yaml` 的 `reason/owner/expires` 语义 | 需维护同步 | ✅ **推荐** |
| B 内联标记 | 仿 Bandit `# nosec B603` | 与代码同 diff | 侵入 58 调用 + 37 写点；注释不进审查统计 | ❌ 拒绝 |
| C 纯扫描无注册 | 只做 AST 判定 | 无维护 | 误报 2/60；无法判 env 来源（F-15） | ❌ 拒绝 |
| D 引 Bandit/Semgrep | 外部门禁 | 成熟规则 | Bandit 只看 shell，无「写入点 safe_join」规则，覆盖不了 A4-8 | ⚠️ 仅作补充 |

**裁决**：A。**注入点** = `tests/test_boundary_coverage.py`（AST 扫描 + 载入注册表 + 负向自测）+ `tests/boundary_registry.yaml`（**存量登记非空、豁免子表默认空**）。三类红：① subprocess 调用未登记；② 写点未登记；③ `shell=True` 出现。
**关键设计**：匹配用 `(relpath, qualname)` 而非行号；注册项含 `category`（A/B/C）与 `policy`（inherit/allowlist/overrides），使「豁免」本身可审计。同函数多调用点在 qualname 之外补序号消歧（v1.2 复审输入，DESIGN 固化）。

#### U-3 「沙箱后端」判定边界

**新增证据（全量后端清点）**：实现 run/run_project 的类共 **8 个**——`ExperimentSandbox`(sandbox.py:312)、`DockerSandbox`(docker_sandbox.py:209)、`SshRemoteSandbox`(ssh_sandbox.py:31)、`ColabDriveSandbox`(colab_sandbox.py:120)、`AgenticSandbox`(agentic_sandbox.py:51)、`StatAgentSandbox`(:52)、`BiologyAgentSandbox`(:58)、`ColliderAgentSandbox`(:49)。其中：
- 已 allowlist：`ExperimentSandbox`（sandbox.py:329/430）；
- 容器侧 env 本就显式（`-e` + `_SAFE_ENV_NAME` 正则 + 去 NUL，docker_sandbox.py:665-672；`HF_HUB_CACHE/TORCH_HOME/HOME/HF_TOKEN` 逐条 602-655——HF_HOME 仅为宿主挂载读取源（L629），v1.2 复审订正）→ Docker/Agentic 无宿主侧泄漏面；
- SSH/Colab **无 `env=`** —— 宿主/远端 CLI，依赖 `SSH_AUTH_SOCK`、`DOCKER_HOST`；
- **未收口 7 处**：stat:381、biology:457、collider:682（后端内）+ code_agent:462、hitl:211、opencode_bridge:462、figure renderer:264（后端外，但执行模型/用户内容）。

| 选项 | 判定标准 | 改造点 | 结论 |
|---|---|---|---|
| A 按类型字面 | 只算 SandboxProtocol 后端 | 3 | ❌ 遗漏 renderer（密钥面最大，F-14） |
| **B 按执行内容** | 执行模型生成物/用户内容 → 纳入；纯宿主运维 CLI → 豁免登记 | **7** | ✅ **推荐** |
| C 全量收口 | 58 处全 allowlist | 58 | ❌ 打断 docker/ssh/git 认证（F-13） |

**裁决**：B。外部先例支持「最小环境 + 显式保留」这一形态：sudo 默认 `env_reset`（仅 TERM/PATH/HOME/MAIL/SHELL/LOGNAME/USER 等极简环境）+ `env_keep` 白名单；Python 官方文档明确 `env` 非 None 即**替换**整个环境（T1）。
**注入点** = `utils/env.py` 增 `sandbox_env(overrides)` 薄封装（`build_subprocess_env` 原样保留，不动既有 4 用例），7 处改用它并传各自 overrides（`_env_extra` / provider key / `RC_*` / agent sandbox 的 API base）。

#### U-4 safe_join 验收子集

**新增证据**：MCP 官方 Python SDK 自带 `mcp.shared.path_security.safe_join`，与 `utils/paths.py` **同名同语义**（resolve 后前缀校验，覆盖 `..`、绝对路径、symlink 逃逸），文档称其为 gold-standard，并**明确声明 symlink 检查是 point-in-time（TOCTOU）**，并发改树的场景建议加 `O_NOFOLLOW`/平台路径约束原语。CWE-22 通用口径同为「先规范化（canonicalize）再比较前缀」。

| 选项 | 范围 | 改造点 | 结论 |
|---|---|---|---|
| **A 动态名子集** | 「名来自 LLM/数据/工具输出」或「base 非 run 私有常量」 | 37 中约 **30** | ✅ **推荐** |
| B 全量 319 处 | 所有写点 | 319 | ❌ 固定字面量名无逃逸面，大 diff 零收益 |
| C 仅入口校验 | 在 stage_dir 构造处一次性校验 | 少数 | ❌ `fname` 内联 `../` 可绕过 |

**裁决**：A，且**保持 in-house 实现**（mcp 是可选 extra，`utils` 不应反向依赖 `mcp`）；在 `utils/paths.py` docstring 补 TOCTOU 边界说明；`_safe_filename` 消毒保留但**不能替代** `safe_join`（711 行现状即此形态）。
**注入点**（v1.2 复审路径消歧）= `pipeline/_code_generation.py`(326/327/345/1208/1239/1323/1459/1621/1735)、`pipeline/_literature.py:992`、`pipeline/_execution.py:711/732`、`hitl/collaboration.py:172`、`pipeline/experiment_repair.py:416`、`pipeline/runner.py:1766`（末者 fname 为固定字面量列表，按判据初判落豁免侧，DESIGN 逐点判定）；写点分类进 `boundary_registry.yaml`。

#### 汇总：进入 DESIGN 的四条裁决

| 未决项 | 裁决 | 注入点 | 外部/仓内锚点 |
|---|---|---|---|
| U-1 | 包装 + `hardware.list_gpu_devices()` | 新 `runtime/host_profile.py`；`hardware.py` +8 行 | M0 §8；hardware.py:172 首行折叠 |
| U-2 | 外置 YAML 注册表，键 `(relpath, qualname)` | 新 `tests/test_boundary_coverage.py` + `tests/boundary_registry.yaml` | M0 §7；`spec/grandfather.yaml` 先例；Bandit B603 机制 |
| U-3 | 按「执行模型/用户内容」判定 → 7 处 | `utils/env.py` 增 `sandbox_env`，7 点接入 | sudo `env_reset/env_keep`；Python subprocess T1 |
| U-4 | 动态名子集 ~30 处 | 6 文件 + 注册表写点分类 | MCP SDK `path_security.safe_join`；CWE-22 |

**注入点总影响面（供 DESIGN 量化）**：新建 3 文件（host_profile.py、守卫测试、注册表）；改动 12 个源文件（7 处 env + ~30 处写点分布在 6 文件，有重叠）；新增测试 2 文件；`build_subprocess_env`/`safe_join` 本体不改，既有 9 用例（4+5）保持绿。

## 7. 参考文献

- [M0 DESIGN](../arc-g4-m0-design/DESIGN.md)（§7 A4-7/A4-8 守卫、§8 HostProfile 冻结点、§9 M5=P-106、§10 I-6/I-7）
- [M0 RESEARCH](../arc-g4-m0-design/RESEARCH.md)（A4-7/A4-8 现状计数，本文 F-3/F-6 已订正）
- [P-102 复核](../../docs/arc-g4-m1-registry-review-20261114.md)（X-6 AST 守卫精度）
- [P-105 调研](../arc-g4-m4-sandbox-limits/RESEARCH.md)（真值源分层 D-Q1=C 先例）
- [G4 中期盘点](../../docs/arc-g4-midpoint-20261113.md)（未入仓工作区文档；计数以本文为准）
- Python 3 官方文档：`subprocess.Popen`（env/shell 语义）、`pathlib.Path.resolve`
- MCP Python SDK 官方文档：`mcp.shared.path_security`（safe_join 同语义实现 + TOCTOU 声明）
- sudo 手册：`env_reset` / `env_keep`（最小环境 + 白名单）
- Bandit 官方文档：B602/B603/B607（subprocess 扫描分族 + nosec 豁免机制）
- CWE-22 路径穿越防御口径（canonicalize → prefix check）
- Sourcery 漏洞库：tainted env args / dangerous subprocess（T3，仅反例）

---

**Review 签字**: 自审 GLM-5.3-Flash（2026-11-13）+ 异构复审 GLM-5.3-Flash 独立上下文子代理（2026-11-14，§5.4：U-1..U-4 成立；上下文异构达成、基座级异构待外部模型补位） 日期: 2026-11-14
**Step 2 门禁自检**: (a) 无 FALSIFIED 断言待改写 ✅；(b) 无 CONFLICT/STEP_GAP 未仲裁 ✅；(c) F-1/F-6/F-10 单源但为 E1 本机可重放，已标证据出处 ✅；(d) 假设已转 U-1..U-4 ✅
