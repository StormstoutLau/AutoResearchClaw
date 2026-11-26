---
id: arc-runtime-log-visibility-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-26
depends: [arc-runtime-log-visibility-RESEARCH]
upstream: arc-runtime-log-visibility-RESEARCH
---

# 设计：运行期日志可见性（B-31a）

> v1.1（2026-11-26，P-199）：补 D-8（TDD 红态取证口径）与 §5 对应边界；D-1..D-7 不变。

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | 日志配置**只在 CLI `cmd_run` 入口**发生 | 在 `researchclaw/__init__.py` 导入时配置 | 库不该替使用者决定输出通道；导入即配置会污染测试与嵌入式调用。HOWTO 要求配置在首个 logger 调用前（调研 A-3） |
| D-2 | 默认级别 **INFO**（而非 WARNING） | 保持 WARNING，靠用户加 `--log-level` | 现场痛点是「默认什么都看不到」；INFO 是 HOWTO 对「确认按预期工作」的定义级 |
| D-3 | `--log-file` 为 **UTF-8 追加**，不做轮转 | 每次运行覆盖 / 内置按大小轮转 | 长跑需要跨重启保留；轮转属运维面（调研 §5 未决项），现在做是过度设计 |
| D-4 | `configure_logging` 用 `force=True` | 重复调用时检查已有 handler 再添加 | CPython `basicConfig` 在已有 handler 时**什么也不做**（调研 A-2）；`force` 让二次调用幂等且不重复输出 |
| D-5 | 行缓冲用 `reconfigure(line_buffering=True)`，**不支持就跳过** | 用 `PYTHONUNBUFFERED` 环境变量 / 包一层 `-u` 重启 | 无法从进程内部设置环境变量；`reconfigure` 是 3.7+ 的标准方法（A-4），对 StringIO/捕获流自动降级 |
| D-6 | 阶段横幅**追加** `logger.info`，保留既有 `print` | 用 logger 替换 print | 终端人类可读输出不应改变；日志是第二通道 |
| D-7 | 失败阶段用 `logger.error` | 统一 INFO | 与既有 `print("FAILED")` 的严重度一致，便于按级别过滤 |
| D-8 | **TDD 红态取证口径**：红态必须由「剥离实现后重跑同一测试 / 同一探针」产生；收集错误型红（`ModuleNotFoundError`）与行为型红**不等价**，须同时给出行为面探针（未配置时 `getEffectiveLevel()==30`、INFO 无输出）；恢复实现后须复跑同一命令得绿 | 用默认级别探针代替测试红态；或用「首跑即绿」自报通过 | 探针只证明缺陷存在，不证明测试能捕获回归；两者都要，且必须可重放（RULE-2 的教训：无失败记录的「全过」不可核） |

## 2. 接口

```python
# researchclaw/runtime/logging_setup.py
DEFAULT_LEVEL = "INFO"
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

resolve_log_level(name: str | int | None) -> int          # 非法值抛 ValueError
configure_logging(level="INFO", log_file=None, *, stream=None) -> int
force_line_buffering(stream=None) -> bool                 # True = 至少一条流被改
```

```python
# researchclaw/cli.py —— cmd_run 首两行
configure_logging(getattr(args, "log_level", "INFO"), getattr(args, "log_file", None))
force_line_buffering()
```

```text
run --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}   # 默认 INFO，str.upper 归一
run --log-file PATH                                   # 可选，UTF-8 追加
```

## 3. 输出矩阵

| 配置 | stdout（print） | stderr（日志） | 文件 |
|---|---|---|---|
| 默认 | 原样 | INFO 及以上 | 无 |
| `--log-level WARNING` | 原样 | WARNING 及以上 | 无 |
| `--log-file run.log` | 原样 | INFO 及以上 | 同上，UTF-8 追加 |

## 4. 非目标

- 不写心跳、不加 `STALLED`、不改 dashboard 阈值（B-31b）。
- 不实现 `llm.call` / `llm.result` 事件（B-31b）。
- 不改 `ops` / `read_run_state` 的派生逻辑。
- 不动 supervisor 的 `max_wall_seconds=1800`。
- 不引入第三方日志库（structlog / loguru）。

## 5. 边界

- `configure_logging(force=True)` 会关闭此前安装的 root handler；若将来有人嵌入本包并自建 handler，需要改为 `force=False` 或提供 `configure=False` 开关（当前无此调用方）。
- `--log-file` 只追加不轮转，长 soak 需外部清理。
- `force_line_buffering` 对非 `TextIOWrapper`（pytest 捕获、`StringIO`）返回 `False`，属预期降级。
- 子进程（沙箱）的 stdout 不受影响——它们由沙箱捕获，不进入主日志。
- D-8 的红态是「接口不存在」型（pytest 收集错误，exit 2），**不等价于断言失败**；行为面红态由默认级别探针承担，两者都已在 IMPLEMENTATION §4.1 留档。该口径对未来同类批次同样适用。
