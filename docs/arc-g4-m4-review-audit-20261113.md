# P-105 复核报告的独立审计（audit-of-review，2026-11-13）

> **性质**：对 [arc-g4-m4-review-20261113.md](arc-g4-m4-review-20261113.md)（P-105 独立异构复核报告）的第三方审计。零实现代码、零门禁写入、不改被审报告——订正以本报告为准。
> **异构链**：P-105 实施 = GLM-5.3-Flash → 复核 = DeepSeek-V4.1-Flash → 本审计 = GLM-5.3-Flash（新会话）。被审对象是**复核报告**，故审计人与复核人异构（GLM≠DeepSeek）即满足 RULE-5 交叉；与实施人同族不构成违规（审计输入是复核报告，不是实现）。
> **方法**：不采信复核报告的任何读数——机械复跑（CI 全量 / e2e / Docker 探针 / digest / session）+ 代码逐行回源 + 规范对照（SPEC_PROCESS RULE-1..6）+ 数字逐项重算。

## 结论（先行）

复核报告的**全部事实性主张成立**：V-1..V-9 可复现、12 处行号引用全部命中、3 项 P2 根因全部在源码/真机复现、X 表 7 项 Docker 运行时探针 7/7 复现。发现 **4 项 P3 级订正**（F-1..F-4，均为措辞/账面精度，不动摇任何结论）。分级裁定：**3 项 P2 维持**（阻塞 P-105 验收关闭），3 项 P3 维持。复核报告**可作为收敛批的输入使用**，F 项措辞随收敛批一并订正。

## 1. 审计证据（S 表，逐项独立复现）

| # | 被审主张 | 审计手段 | 结果 |
|---|---|---|---|
| S-1 | V-4：CI 43 文件 687/13skip | 独立解析 ci.yml 清单（`ci_files=43`）并全量复跑 | ✅ **687 passed, 13 skipped** |
| S-2 | V-5：e2e 22/0 | 独立复跑 `tests/e2e_docker_sandbox.py` | ✅ **22 passed, 0 failed**（含 symlink 双分支 `[PASS]`） |
| S-3 | X-1/X-2/X-3/X-5/X-6/X-11 | 重跑复核报告留下的探针脚本 | ✅ 全套复现：自愿 `exit(137)`→`resource_limit`；真 OOM→137+`resource_limit`；TTL 6.2s→`rc=143`+`ttl_timeout`+`results.json` 落盘且 metrics 合并；`HostConfig`=`1500000000\|128\|probe-d`；**kill 不可达仍 `fired=True`**；探针后容器零残留 |
| S-4 | X-4：SIGKILL 强杀分支 | 独立复跑 `probe_kill.py` | ✅ 4s TTL + 2s grace → SIGKILL → `rc=137`、`limit_reason=ttl_timeout` |
| S-5 | V-6：digest 8/8 + 锚点 | 本地 sha256 复算（raw/CRLF 双口径） | ✅ mismatch=[] |
| S-6 | V-8：session 5 步 + 异构 | 逐行解析 jsonl | ✅ 5 个 `decision` 事件（research/design/implement/verify/finalize），model 字段 5/5 = GLM-5.3-Flash |
| S-7 | §0：HEAD 19 文件/+1548/−23 | `git show --stat 6f8a72e` | ✅ 逐位一致 |
| S-8 | D-2 根因 | 读码 | ✅ `_fired=True` 在 [docker_sandbox.py#L97](../researchclaw/experiment/docker_sandbox.py)（先于 L102 kill）；`_kill` 吞错（L114-117）；deadline L85 在线程入口计算、`watcher.start()` L381 早于 `subprocess.run(docker run)` L388 |
| S-9 | D-4 根因 | 读码 | ✅ [L744](../researchclaw/experiment/docker_sandbox.py)：`inspected[0] or inspected[1] == 137`——137 单独即判 `resource_limit`（S-3 复现） |
| S-10 | D-1 根因 | 读码 + 全仓枚举 | ✅ sandbox 接口调用点恰 9 个：有 run_id = `_execution.py:551/557/1644`；无 = `:1770/:289/:472`、`runner.py:131`、`experiment_repair.py:810`、`code_agent.py:1394`。`runner.py` 签名收 `run_id`（L128-129）而 L131 未下传，实证「静默丢参」 |
| S-11 | D-1 登记失实 | 读 IMPLEMENTATION §5.4 原文 | ✅ §5.4 仅写「experiment_repair / code_agent 调用点不改」，**未登记 `:1770` 与 `runner.py:131`**；且 §5.4 首句自称覆盖「主执行与重跑路径」而 `:1770` 正是重跑路径——登记与自述矛盾 |
| S-12 | D-3 前提 | 全仓 yaml 检索 + CLI | ✅ `ttl_sec` 仅出现于 [registry.yaml:142](../researchclaw/tools/registry.yaml)（sandbox_profiles，U-1 未消费）→ 实验 Docker 配置走默认 1800；[cli.py#L1990](../researchclaw/cli.py) 原文「1800 for quick ML, 7200 for HEP runs」 |
| S-13 | D-5 | 读测试 | ✅ [test_sandbox_boundary.py#L252](../tests/test_sandbox_boundary.py) = `assert release.is_set() or True`（恒真）；L296-297 注释写 KILL、断言仅 TERM |
| S-14 | D-6 | 读码 | ✅ [harness_template.py#L163](../researchclaw/experiment/harness_template.py) 模块级安装；`test_rc_executor.py:3033` 运行期 import |
| S-15 | O-3 | 全仓检索 | ✅ `limit_reason` 消费点仅 `docker_sandbox.py`/`sandbox.py`（vendor evaluator 为同名无关字段） |
| S-16 | 过程合规 | git + 文档对照 | ✅ 单向权限（tracked 零修改，仅 2 个 untracked 文档）；「并入不占号」先例在 M0 §9 实载；无 front-matter 与两份既有 review 文档同口径（dc-validator 同为 skip） |

## 2. 订正项（F 表，全部 P3）

| # | 订正 | 证据 | 处置 |
|---|---|---|---|
| F-1 | **清理声明失实**：报告尾注「探针脚本与 wheel 产物均在 `$env:TEMP` 并已清理」。wheel outdir 已清理属实；但 `$env:TEMP\rc_m4_probe\{probe.py, probe_kill.py}` 审计时仍在 | 本审计 `Get-ChildItem` 实测 | 探针脚本已由本审计删除；报告尾注在收敛批提交时订正 |
| F-2 | **V-2 拆分失实**：「35 既有 + 10 新增」→ 实为 **36 既有 + 9 新增**（总数 45 正确；`git show` 计 `+def test_` = 9） | added=9 / total=45 | 收敛批订正数字 |
| F-3 | **O-4 措辞不精确**：「`copytree(symlinks=False)`」——[sandbox.py:404](../researchclaw/experiment/sandbox.py) 未显式传参，解引用系 shutil **默认行为**；行为结论不变 | 读码 | 措辞订正，登记语义不变 |
| F-4 | **取证矩阵计数不严格**：§5 E2 行列 X-1..X-7/X-11/X-12/X-16 共 10 个编号却标「7 组」（X-7 实为读码、X-16 为混合证据层）；§0「读码探针 6 组」与 X-7..X-10（4 项）不对齐 | 对表复核 | 账面精度订正，不涉证据真伪 |

## 3. 分级裁定

- **D-1 / D-2 / D-3 维持 P2**（阻塞验收关闭）：
  - D-2、D-3 各有一个无争议硬核（I-M4-4 归因可伪造；默认 1800 截断 7200 HEP 长跑且 `limit_reason` 无消费点），P2 无可商榷。
  - D-1 的 P2 **依据应收窄表述**：成立点 = 「§5.4/C-8 登记与自述矛盾（S-11）+ `runner.py:131` 静默丢参（S-10，同 stage 重跑路径 `:1770` 亦属可争议的批内遗漏）」；而「9 个调用点都该有 TTL」不是 DESIGN §51 冻结的批内职责（§51 只承诺 stage-14 主执行点传 `run_id`）。复核报告的修复建议（agent 路径显式登记）已与最小面一致——**收敛批按最小面执行，勿扩大为全调用点改造**。
- **D-4 / D-5 / D-6 维持 P3**：均为措辞/证据指针/宿主副作用，无行为回归争议。

## 4. 复核报告可复现性总检

| 维度 | 复现率 |
|---|---|
| Docker 运行时主张（X-1/2/3/4/5/6/11） | **7/7**，两轮独立读数一致 |
| 机械复跑（CI / e2e / digest / session / commit stat） | 5/5 逐位一致 |
| 行号引用（12 处：L85/L97/L102/L114-117/L381/L388/L744-745/cli 1990/test 252+297/runner 131 及 9 调用点） | **12/12 命中** |
| 唯一未重复项 | V-7 wheel 431 entries（复核会话内直接观测；本审计未重复构建，CI 全绿佐证导入面，低风险） |

## 5. 审计处置

1. F-1 的探针残留已删除（`$env:TEMP\rc_m4_probe`），仓内与临时目录均无审计/复核遗留。
2. 本审计报告为唯一新增文件（无 front-matter，与既有 review 文档同口径）；未提交。
3. 建议：复核报告的 F-1..F-4 四处措辞/数字随 P-105 收敛批一并订正（或声明以本审计报告为准）；D-1 收敛范围按 §3 最小面执行。
