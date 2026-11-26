---
id: arc-runtime-log-visibility-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-26
depends: [arc-runtime-log-visibility-DESIGN]
upstream: arc-runtime-log-visibility-DESIGN
---

# 实施记录：B-31a（运行期日志可见性）

> v1.1（2026-11-26，P-198）：补 TDD 红→绿记录（§4.1），C-15 由 ⚠️ 转 ✅。

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/runtime/logging_setup.py`](../../researchclaw/runtime/logging_setup.py)（新增） | `resolve_log_level`（字符串→级别，非法抛 `ValueError`）、`configure_logging`（stderr + 可选 `FileHandler(encoding="utf-8")`，`basicConfig(force=True)`）、`force_line_buffering`（`reconfigure(line_buffering=True)`，不支持则跳过） |
| [`researchclaw/cli.py`](../../researchclaw/cli.py#L158-L172) | `cmd_run` 首部配置日志并强制行缓冲；`run` 新增 `--log-level`（`type=str.upper`、choices、默认 INFO）与 `--log-file` |
| [`researchclaw/pipeline/runner.py`](../../researchclaw/pipeline/runner.py#L832-L837) | 阶段启动追加 `logger.info("%s %s — running...")`；DONE/DEGRADED 追加 `logger.info`，FAILED 追加 `logger.error` |
| `tests/test_logging_setup.py`（新增） | 13 例：级别归一/非法值、INFO 入文件、WARNING 过滤 INFO、重复配置不叠加 handler、root 级别生效、真实文本流行缓冲、无 `reconfigure` 时降级、日志文件在「阶段进行中」增长、CLI 三例 |

## 2. 社区源码级证据映射

| 锚点 | 原文/实现 | 本批如何映射 | 验证 |
|---|---|---|---|
| A-1 CPython `Lib/logging/__init__.py` L1254-1255 | `_defaultLastResort = _StderrHandler(WARNING)` | 解释「为什么现场只有 WARNING 行」；也是默认 INFO 决策的反面依据 | ✅ 本机 3.11.15 源码核对 |
| A-2 同上 L1946-1983 | `basicConfig` 有 handler 即 no-op（除非 `force`）；`level` 设 root；`filename` 建 `FileHandler` | D-4 采用 `force=True`；`level=numeric` 由 `resolve_log_level` 提供；文件走 `FileHandler` | ✅ 源码逐行核对 |
| A-3 HOWTO L136-147 | `numeric_level = getattr(logging, loglevel.upper(), None)`；`basicConfig(level=numeric_level, ...)`；必须早于任何 logger 调用 | `resolve_log_level` + `cmd_run` 首行调用 | ✅ 官方原文 |
| A-4 `TextIOWrapper.reconfigure` | `line_buffering=True` | `force_line_buffering` | ✅ 本机实测 True |

## 3. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| 默认 `run` | `logger.info` 全丢；日志文件只增 WARNING | stderr 输出 INFO 及以上 |
| 重定向 stdout | 块缓冲，阶段内不增长 | 行缓冲，逐行落盘 |
| `CodeAgent._log_event` | 不可见 | 可见（无需改调用点） |
| ACP 30 秒进度心跳 | 不可见 | 可见 |
| 阶段横幅 | 仅终端 | 终端 + 日志 |
| 运维提级 | 改代码 | `--log-level DEBUG` |

## 4. 验证

```bash
python -m pytest tests/test_logging_setup.py -q
# 13 passed

python -m pytest tests/test_cli.py tests/test_rc_cli.py tests/test_rc_runner.py \
  tests/test_runner_events.py tests/test_blueprint_persistence.py -q
# 88 passed
```

缺陷面证据（可重放）：

```bash
python -c "import logging; l=logging.getLogger('researchclaw.probe'); \
print('level=', logging.getLogger().getEffectiveLevel()); \
l.info('INFO-SHOULD-BE-VISIBLE'); l.warning('WARNING-VISIBLE')"
# level= 30；仅 WARNING-VISIBLE 输出
```

**流程偏离（诚实记录）→ 已补证（P-198）**：本批初次落盘时测试首跑即绿，未留下失败记录。P-198 用「剥离实现后重跑」的方式补出真实红态：

```bash
# 1) 红：先把三个实现文件从索引/工作树剥离（保留新增测试）
git stash push -m "b31a-impl-for-red-record" -- \
  researchclaw/runtime/logging_setup.py researchclaw/cli.py researchclaw/pipeline/runner.py
python -m pytest tests/test_logging_setup.py -q
# ERROR tests/test_logging_setup.py
# E   ModuleNotFoundError: No module named 'researchclaw.runtime.logging_setup'
# 1 error in 0.27s  → exit 2
python -c "from researchclaw.cli import build_parser; a=build_parser().parse_args(['run']); \
print(getattr(a,'log_level','MISSING'), getattr(a,'log_file','MISSING'))"
# MISSING MISSING        ← --log-level / --log-file 不存在

# 2) 恢复实现
git stash pop

# 3) 绿：同一测试与同一探针
python -m pytest tests/test_logging_setup.py -q      # 13 passed
python -c "from researchclaw.cli import build_parser; a=build_parser().parse_args(['run']); \
print(getattr(a,'log_level','MISSING'), getattr(a,'log_file','MISSING'))"
# INFO None              ← 默认 INFO，未指定日志文件
```

等价性说明：红态是「模块不存在」的收集错误，而不是断言失败；它证明「测试依赖的接口在实现前不存在」，与行为型红态不等价。真正的行为面红态由 §4 的默认级别探针提供（`level=30`，INFO 无输出）。两者均已留档。

## 5. 边界

- 未实现心跳写入与 `STALLED`（B-31b）；阶段内进度仍依赖既有 INFO 点位。
- `--log-file` 追加不轮转；长 soak 需外部清理。
- `force=True` 会关闭外部安装的 root handler（当前无此调用方）。
- B 站未部署验证；本地只跑单测与回归。
- 未测「真实 Stage 10 期间日志文件持续增长」——单测只验证两次日志写入之间文件变大（§4 已注明）。
