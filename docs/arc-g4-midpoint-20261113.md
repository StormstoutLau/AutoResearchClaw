# G4 中期盘点（M0–M3 完成，M4–M5 待开工）

> **归档说明（P-135，2026-11-16）**：本文是 2026-11-13 的 G4 中期盘点快照，自本批起纳入版本控制，正文保持原样、仅作证据留存。部分计数已被后续复核订正：M4 相关以 [M4 RESEARCH](../spec/arc-g4-m4-sandbox-limits/RESEARCH.md) 的 F-12/F-13 为准，M5 相关以 [M5 RESEARCH](../spec/arc-g4-m5-host-boundary/RESEARCH.md) 的 F-3/F-6 为准。引用本文时请以上述订正为准。

> **基线**：`844eabc`（P-104 已推送）。**日期**：2026-11-13。**方法**：E1（git/测试读数）+ E3（读码/grep 覆盖扫描）；不做新实现、不改门禁。
> **范围**：G4 全部 6 批（M0–M5）与 A4-1..A4-10 验收矩阵、复核返工统计、开放遗留、M4/M5 准备度。

## 1. 进度总览

| 批次 | 编号 | 交付 | 状态 | 验收 | commit |
|---|---|---|---|---|---|
| M0 | P-099 | 设计冻结（A4-1..A4-10 映射、V-1..V-8、事件/沙箱契约） | ✅（P-100 复核 2 P2 + 5 P3） | DC/门禁 | `eec472b` / `ada3645` |
| M1 | P-101 | `tools/registry.yaml` + 9 条校验 + fail-closed 启动 | ✅（P-102 复核 1 P2 + 2 P3） | A4-1 | `fbe27d3` / `0648e2a` |
| M2 | P-103 | 动态注册 + schema 注入 + REST + listChanged 接缝 | ✅（复核 1 P1 + 2 P2 + 2 P3，v1.1 收敛） | A4-10 | `d0eea78` / `9bb829a` |
| M3 | P-104 | invoker + tool 事件 + orphan_call + 审批门 + CLI grant | ✅（复核 2 P2 + 3 P3，v1.1 收敛） | A4-4/A4-5 | `844eabc` |
| M4 | P-105 | 沙箱配额/TTL/137 + 四类逃逸 | 🔲 未开工 | A4-2/A4-3/A4-6 | — |
| M5 | P-106 | env/safe_join 全覆盖 + HostProfile | 🔲 未开工 | A4-7/A4-8/A4-9 | — |

**RULE-5 链**：M0 实施 DeepSeek → 复核 GLM；M1/M2 实施 GLM → 复核 DeepSeek；M3 实施 DeepSeek → 复核 GLM。**四批全部异构交叉，无自审**。

## 2. 验收覆盖矩阵（A4-1..A4-10）

| ID | 断言 | 状态 | 证据 / 缺口 |
|---|---|---|---|
| A4-1 | 100% 工具有 schema；缺 schema 启动失败 | ✅ | P-101 正负向 + P-102 V-9 |
| A4-2 | 四类逃逸（路径/符号链接/网络/fork bomb）全拒 | 🔲 **M4** | `docker_sandbox.py` 仅有 `--network`/`--memory`（L389/L403-417）；**无 `--pids-limit`/`--cpus`/label**（grep 零命中） |
| A4-3 | 资源超限 → 137 + `tool.result` | 🔲 **M4** | grep `137`/`resource_limit` 零命中；现有 `_execute` 只有 timeout 强杀（L300-316） |
| A4-4 | call/result 成对；缺失标 orphan | ✅（机制） | P-104 T-1/T-10/T-11/T-12；**生产可观察性为零**（F-5：MCP 外部调用 `event_log=None`） |
| A4-5 | high 未审批拒绝 | ✅ | P-104 T-5/T-9/T-20（v1.1 后公开 API 与协议路径均拦截） |
| A4-6 | TTL 到期回收、产物已落盘 | 🔲 **M4** | `ttl_sec` 只在注册表 profile（`registry.yaml` L142）且**零消费**；无看护线程/无 `rc.run` label；harness 无 `atexit`/SIGTERM handler + `entrypoint.sh` L57 `exec python3 -u` → **「产物先落盘再 kill」当前不可达**（需新增信号处理） |
| A4-7 | 全部沙箱后端用 env allowlist | 🟡 **部分** | `build_subprocess_env` 仅 `sandbox.py` L325/L426 + `mcp/client.py` L71；**4 处裸 `os.environ.copy()`**（stat_agent L381、collider_agent L682、biology_agent L457）+ `code_agent.py` L462 `{**os.environ}` |
| A4-8 | 全部写入点用 safe_join | 🟡 **部分** | `safe_join` 仅 `utils/paths.py` + `pipeline/stage_impls/_execution.py`（4 处）；覆盖面未清点，M5 需 AST 全扫 |
| A4-9 | HostProfile 纯数据、无脚本入口 | 🔲 **M5** | grep `HostProfile` 零命中 |
| A4-10 | 注册表与 listChanged 一致；新增工具无需改代码 | 🟡 | 注册表/`list_tools()` 一致 ✅；新增工具无需改代码 ✅；**真 `listChanged` 通知仍阻塞**（stdio 无 session，notifier 接缝 + fake 测试） |

**结论**：10 项中 **3 项达成**（A4-1/4/5）、**3 项部分**（A4-7/8/10）、**4 项未开工**（A4-2/3/6/9）。M4 承担 3 项、M5 承担 2 项（A4-7/8/9）。

## 3. 质量读数

| 项 | 读数 |
|---|---|
| 五套件（registry 25 + dynamic 12 + MCP 42 + tool_events 21） | **100 passed**（3.13.5 实测，HEAD `844eabc`） |
| CI 固定清单 | 41 文件 **625 passed / 13 skipped，0 failed** |
| wheel | **431 entries，零重复路径**；registry/invoker/approvals/handlers 均在包内 |
| 门禁 | step-enforce `digest_bound=1`；pre-commit 9 项全绿；session digest P-104 8 文件 / P-099 rebind 5 文件零 mismatch |
| 运行时 | Docker **29.9.2**（OSType=linux）本地可用，但 `researchclaw/experiment:latest` **镜像不存在**（仅 github-mcp-server / welcome-to-docker）→ M4 e2e 需先 build 或用轻量镜像替代；CI 无 Docker |

## 4. 复核返工统计（质量趋势）

| 批次 | 复核发现 | 阻塞级别 | 收敛 |
|---|---|---|---|
| M0（P-100） | 2 P2 + 5 P3 | 2 P2 阻塞 M1 开工 | M1 吸收（V-8/jsonschema） |
| M1（P-102） | 1 P2 + 2 P3 | 1 P2 阻塞 M2 开工（wheel 缺注册表） | M2 批内修 |
| M2（P-103） | **1 P1** + 2 P2 + 2 P3 | P1 构建阻断 | v1.1 收敛（force-include/None 注入/handler 类） |
| M3（P-104） | 2 P2 + 3 P3 | P2 双路径/异常逃逸 | v1.1 收敛（单执行路径/digest 兜底） |

**趋势**：四批全部被复核发现实质缺陷（0 批「一次通过」），但级别从 P1 降到 P2，且收敛均在批内完成。**重复出现的教训**：①「测试只覆盖主路径」——P-103 None 注入、P-104 直调绕门都因既有测试走同一路径而未暴露；②「异常/错误路径未纳入配对/验收」——P-104 digest 逃逸；③「声明先行、构建后验」——P-103 force-include。M4/M5 的验收设计应显式覆盖错误路径与「测试是否走生产路径」。

## 5. 开放遗留（按优先级）

| # | 项 | 级别 | 归属 |
|---|---|---|---|
| L-1 | 真 `listChanged` 通知不可达（stdio 单连接）；A4-10 仅接缝 | P2（验收边界） | HTTP/多 session 批次 |
| L-2 | 全局 MCP 调用审计 sink 缺失；A4-4 生产无可观察事件 | P2（覆盖边界，已声明 F-5） | G4 后续 |
| L-3 | approvals 无 revoke/过期；外部调用无全局授予通道 | P3 | 后续 |
| L-4 | handler 签名加载期不校验（U-6） | P3 | M4 可顺带 |
| L-5 | `EventLog.append` 不校验事件类型（U-7） | P3 | 后续 |
| L-6 | `grant` 不校验工具名（U-8） | P3 | 后续 |
| L-7 | M2 DESIGN §1/§2.1 仍写 force-include（O-9） | P3（文档） | 下次触碰 M2 文档 |
| L-8 | M2 DESIGN §10 拒绝理由「无 default 会变 required」不成立（O-12） | P3（文档） | 下次触碰 M2 文档 |
| L-9 | P-102 O-1..O-5：未知键静默、outputSchema 无返回体证据、YAML 重复键、`RC_TOOL_REGISTRY` 无来源校验、`mcp/tools.py` 双源 | P3 | M4/M5 |
| L-10 | M4 修正输入：137 仅 memory/pids（cpus 是 throttling）；TTL kill 前产物落盘 | 设计输入 | M4 |
| L-11 | M5 修正输入：AST 守卫改注册制白名单 + 兜底扫描 | 设计输入 | M5 |

## 6. M4 准备度与风险（P-105：A4-2/A4-3/A4-6）

**已有地基**：`docker_sandbox.py` 有 `--network`、`--memory`、timeout 强杀；Docker 29.9.2 本地可用（**研究镜像需自建**，或 e2e 用轻量镜像）。
**缺口**：`--pids-limit`/`--cpus`/`--label rc.run/rc.tool`、TTL 看护、137/`resource_limit`、四类逃逸测试；harness 无 SIGTERM/atexit（A4-6 落盘前置）。

| 风险 | 缓解 |
|---|---|
| CI 无 Docker → 测试红/挂 | 命令构造单测不依赖 Docker；e2e 用 `skipif(shutil.which("docker") is None)`；本地实跑记录 |
| 137 与 timeout 混淆 | 明确 `reason` 区分：配额超限=`resource_limit`，TTL/超时=`ttl_timeout`/`timeout`；只对前者断言 137 |
| TTL kill 丢产物 | kill 前 flush/落盘；测试用短 TTL + 产物探针 |
| fork bomb 测试危险 | `--pids-limit` + 短 timeout + 只允许在受限容器内 |
| label 清理误伤 | 只清 `rc.run=<run_id>` 精确标签；dry-run 模式 |

## 7. M5 准备度与风险（P-106：A4-7/A4-8/A4-9）

**缺口实证**：4 处 `os.environ.copy()` + 1 处 `{**os.environ}`；`safe_join` 仅 2 文件；`HostProfile` 零命中。

| 风险 | 缓解 |
|---|---|
| AST 扫描误报/漏报 | 注册制白名单 + 兜底扫描（D-6）；先以现有 5 处 env 缺口跑红 |
| safe_join 覆盖面大 | 先全仓扫描出清单，再逐点修复；白名单默认空 |
| HostProfile 纯数据边界 | 只返回 dataclass/dict；禁止 subprocess/脚本字段；AST 断言 |

## 8. 建议下一步

1. **M4 先行**（独立于 M5；本地 Docker 可用），出 P-105 简报：命令构造单测 + e2e skip 策略 + 137/timeout 语义分离 + TTL 产物探针。
2. **L-7/L-8 文档小修**随 M4 文档触碰一并做（零风险，避免 M2 DESIGN 残留误导）。
3. **M5 最后**（覆盖扫描依赖 M4 的写入点落位）。
4. **保留 L-1/L-2 为显式残余**：A4-10 只可按「注册表一致 + 接缝」验收，A4-4 只可按「机制验收」验收，不得在总纲写成「生产全覆盖」。
5. RULE-5：P-105 若由本会话（DeepSeek）实施，复核须换 GLM；也可反之以保持交替。

---

**一句话结论**：G4 完成 4/6 批、A4 达成 3 项 + 3 项部分 + 4 项未开工；质量读数全绿；复核四批均有实质发现但均已收敛；M4 是当前最大缺口（3 项验收），本地 Docker 具备开工条件。
