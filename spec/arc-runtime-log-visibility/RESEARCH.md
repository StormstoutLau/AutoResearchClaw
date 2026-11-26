---
id: arc-runtime-log-visibility-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-longrun-progress-observability]
upstream: arc-master-roadmap
---

# 调研：运行期日志可见性（B-31a）

> **背景**：B 站重定向日志在 Stage 10 启动 20 分钟后仍只有 **208 字节**；`code_agent_log.json` 里 `Blueprint YAML parse error` 等关键行在运行期完全不可见，直到 `logger.warning` 出现。完整调研见 [ARC 长跑进度回传与停滞检测调研](../../docs/arc-longrun-progress-observability-20261126.md) §2.3，复审见 [进度回传复审](../../docs/arc-longrun-progress-review-20261126.md)。
> **本批范围**：只做 B-31 拆分后的 **a 档（日志可见性）**：根日志器配置、`--log-level`/`--log-file`、行缓冲、阶段横幅入日志。心跳 + `STALLED` 归 B-31b。

## 0. 结论

1. **级别与缓冲「双杀」**：全仓 `basicConfig` / `dictConfig` / `setLevel` **零命中**（`Grep` 复核），root logger 保持 30（WARNING）；`CodeAgent._log_event` 走 `logger.info`，全部被丢弃。`print` 在重定向时块缓冲（208 字节为直接证据）。
2. **默认行为可本地一行复现**（§1.1）：未配置时 `info()` 无输出、`warning()` 走 `lastResort` 输出到 stderr。
3. **标准解是官方配方**：`getattr(logging, level.upper())` + `basicConfig(level=...)`（Python HOWTO 原文，§3 A-2）；行缓冲用 `TextIOWrapper.reconfigure(line_buffering=True)`（§3 A-3，本机实测）。
4. **一次配置放在 CLI 入口**，不在库内 `import` 时配置——库应保持沉默，配置是应用的责任（§3 A-1 的 `basicConfig` 语义 + 社区惯例）。
5. 修复后，既有 `logger.info`（含 ACP 子进程 30 秒进度心跳）立即变为可见，不需要改各阶段实现。

## 1. 现场证据

### 1.1 默认级别探针（E1，可重放）

```bash
python -c "import logging; l=logging.getLogger('researchclaw.probe'); \
print('level=', logging.getLogger().getEffectiveLevel()); \
l.info('INFO-SHOULD-BE-VISIBLE'); l.warning('WARNING-VISIBLE')"
```

实测输出：`level= 30`，仅 `WARNING-VISIBLE` 出现（stderr）。与 B 站日志只见到 WARNING 行一致。

### 1.2 现场观测面对照（E1，2026-11-26 07:48Z）

| 观测面 | 实测 | 判读 |
|---|---|---|
| `/tmp/p192_stage12.log` | 208 字节，20 分钟未增 | `print` 块缓冲 + INFO 被丢弃 |
| `events.jsonl` | 停在 `stage.started`，seq=7 | 阶段内无事件生产者 |
| `heartbeat.json` | 时间是上一轮进程 | 只在 DONE 写（B-31b） |
| `code_agent_log.json` | 阶段末一次性落盘 | 运行期不可见 |

## 2. 机制解剖（E3 @HEAD）

| 位置 | 事实 |
|---|---|
| [`CodeAgent._log_event`](../../researchclaw/pipeline/code_agent.py#L1609-L1612) | 统一走 `logger.info`，默认级别下全部丢弃 |
| [`runner.py`](../../researchclaw/pipeline/runner.py#L832-L837) | 阶段横幅只用 `print`，未进日志通道 |
| [`cli.py`](../../researchclaw/cli.py#L1764-L1826) | `run` 无 `--log-level` / `--log-file`；进程内无任何日志配置 |
| [`acp_client.py`](../../researchclaw/llm/acp_client.py#L395-L462) | 已有 30 秒进度心跳日志，但同样被默认级别吞掉 |

## 3. 社区源码级证据锚点

| ID | 来源 | 原文/实现要点 | 验证状态 |
|---|---|---|---|
| A-1 | CPython 3.11.15 `Lib/logging/__init__.py` L1254-1255 | `_defaultLastResort = _StderrHandler(WARNING)`；`lastResort = _defaultLastResort` | ✅ 本机源码逐行核对（版本已记录） |
| A-2 | 同上 L1946-2013 | `basicConfig`：有 `handlers` 就不再建；`level` 设 root 级别；`filename` 建 `FileHandler`；`force=True` 先移除并关闭已有 handler | ✅ 本机源码逐行核对 |
| A-3 | Python HOWTO "Logging" L96 / L112 / L121 / L136-147 | "The default level is `WARNING`"；INFO 示例不输出；`basicConfig(filename=..., encoding='utf-8', level=...)`；`--log=INFO` → `getattr(logging, loglevel.upper())`，且 basicConfig 必须在任何 logger 调用**之前** | ✅ 官方文档原文（2026-11-26 抓取） |
| A-4 | `io.TextIOWrapper.reconfigure`（Python 3.7+） | 支持 `line_buffering=True`，把已有文本流改为行缓冲 | ✅ 本机实测：`f.reconfigure(line_buffering=True); f.line_buffering is True` |

**三条可迁移纪律**：① 级别来自 CLI 字符串映射，不硬编码；② 配置必须在首个 logger 调用前、且只配一次；③ 输出通道要显式解决缓冲，否则「有日志也不增长」。

## 4. 方案（M1-a）

| 项 | 内容 |
|---|---|
| L1 | 新增 `runtime/logging_setup.py`：`resolve_log_level` / `configure_logging` / `force_line_buffering` |
| L2 | `run` 增 `--log-level`（默认 INFO、大小写不敏感）与 `--log-file`（UTF-8 追加） |
| L3 | `cmd_run` 首行配置日志 + 强制行缓冲，早于配置解析与 preflight |
| L4 | 阶段横幅（running / done / failed）同时进 `logger`，`print` 保持不变 |

## 5. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| 是否需要日志轮转 | 单次 soak 的 `--log-file` 超过 100 MB | 暂不做；soak 用独立目录 + 外部清理 | 待核 |
| stdout 行缓冲在 supervisor 管道下是否足够 | B-31b 接入 supervisor 后 | 足够；supervisor 另有事件通道 | 待核 |
