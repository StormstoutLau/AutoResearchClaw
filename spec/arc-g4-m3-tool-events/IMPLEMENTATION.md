---
id: arc-g4-m3-tool-events-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g4-m3-tool-events-DESIGN]
upstream: arc-g4-m3-tool-events-DESIGN
---

# 实施：G4-M3 tool 事件 + orphan_call + 审批门（P-104）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/tools/invoker.py` | 新增 | `ToolInvoker`（校验/审批/事件）+ `emit_orphan_markers` |
| 2 | `researchclaw/tools/approvals.py` | 新增 | `read_approvals`/`is_approved`/`grant` |
| 3 | `researchclaw/mcp/handlers.py` | 新增 | 6 个 `handle_*` 薄函数 + `HANDLERS` |
| 4 | `researchclaw/mcp/server.py` | 修改 | `_handlers` 由 registry 解析 + `partial(self)`；`ToolInvoker` 注入；删 `dispatch_tool`/`_default_server` |
| 5 | `researchclaw/tools/registry.yaml` + `researchclaw/tools/registry.yaml` | 修改 | handler → `researchclaw.mcp.handlers:<fn>`（双副本同步） |
| 6 | `researchclaw/runtime/event_log.py` | 修改 | `EVENT_TYPES` 增 `tool.orphan_call` |
| 7 | `researchclaw/pipeline/runner.py` | 修改 | `_emit_summary_anchor` 开头调 orphan 扫描（`owns=True`） |
| 8 | `researchclaw/cli.py` | 修改 | `approvals grant` 子命令 + dispatch |
| 9 | `tests/test_tool_events.py` | 新增 | T-1..T-19 |
| 10 | `spec/arc-g4-m3-tool-events/` 四文档 | 新增 | 本批 spec |
| 11 | `spec/arc-g4-m0-design/DESIGN.md` + P-099 session | 修改 | M3 状态 + I-5 裁决；受控回边 |
| 12 | `arc-master-roadmap.md` / `docs/PROGRESS.md` | 修改 | v1.4q + P-104 行 |

## 2. 接口签名与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `read_approvals` | `(run_dir: str \| Path) -> dict[str, dict]` | 返回 `{}` 即退回「全部拒绝」；删除 `approvals.py` 不影响启动 |
| `grant` | `(run_dir, tool, *, by: str) -> Path` | 只写 `approvals.json`；删除 CLI 子命令即回退 |
| `ToolInvoker.invoke` | `async (name: str, args: dict) -> dict` | `server._dispatch_tool` 改回 `handle_tool_call` 即回退事件/审批层 |
| `emit_orphan_markers` | `(event_log) -> list[str]` | runner 调用包在 try/except，删除调用即回退 |
| `HANDLERS` | `dict[str, Callable[[Any, dict], Awaitable[dict]]]` | registry 双副本改回旧 handler 即回退（需同步） |

## 3. 版本与依赖核验（Step 6）

| 依赖 | 声明位置 | 实测 | 状态 |
|---|---|---|---|
| Python 3.11 / 3.13 | CI 矩阵 | 3.11/3.13 可用 | ✅ |
| `jsonschema>=4.20` | `pyproject.toml` dependencies | 已安装，`Draft202012Validator` 可用 | ✅ |
| `mcp>=2.1,<3` | pyproject | 2.3.0 | ✅ |
| `filelock`（仓内） | `researchclaw/runtime/filelock.py` | Windows `msvcrt` / POSIX `fcntl` 双实现 | ✅ 无新依赖 |
| `pytest` | dev extra | 可用 | ✅ |

## 4. 低效排除

- 不在每次 append 前 `read_all()`；唯一全量读发生在 **run 收尾 orphan 扫描**（每 run 一次）。
- 事件摘要只做键名（无大对象序列化）；digest 用现成 `canonical_json`。
- 不新增后台线程/定时器；审批读取每次调用一次小文件（fail-closed 优先）。
- 不改 SDK 注册路径；handler 解析只在 server 构造时一次。

## 5. TDD 记录（Step 9）

| 阶段 | 读数 |
|---|---|
| 红 | 首次 `pytest tests/test_tool_events.py` → **collection error**（`ModuleNotFoundError: researchclaw.tools.approvals`）；实现后首轮 **18 passed / 1 failed**（T-19 任务在 `asyncio.run` 关闭后已被回收，断言时 `_active_tasks` 已空——测试自身缺陷，改为单事件环内断言 `cancelling()>=1` + `done()`）→ **19 passed** |
| 绿 | `tests/test_tool_events.py` **19 passed**；五套件（registry 25 + dynamic 12 + MCP 42 + tool_events 19）**98 passed** |
| 双环境 | 3.11.15 五套件 **98 passed** |
| CI 全清单 | 41 文件 **623 passed / 13 skipped，0 failed** |
| wheel | 431 entries、零重复路径；registry/invoker/approvals/handlers 均在包内；装 target 后 strict load 6 tools 成功 |
| CLI | `researchclaw --help` / `approvals grant --help` exit 0 |

### 5.1 复核收敛修复轮（v1.1，复核报告 arc-g4-m3-review-20261113.md）

先红（T-20/T-21 **2 failed**）→ 修复 → **21 passed**；五套件 **100 passed**：

1. **D-1（P2）**：`handle_tool_call` 改为 invoker 薄壳（**单执行路径**）——直调不再绕过审批门/schema 校验/事件（X-1 实证直调 high-risk 未审批 handler 已执行）；`INVALID_TOOL`/日志语义保留在 invoker。旧的双错误码分流（ValueError→`INVALID_ARGUMENT`）由 invoker 的 handler 异常映射承接。
2. **D-2（P2）**：`_digest`/`_result_summary` 经 `_to_jsonable` 兜底（非 JSON 值降级 `str`，与 `_as_result` 的 `default=str` 同口径）——handler 非 JSON 结果不再逃逸 `invoke`，call/result 配对保持（X-4 实证 `TypeError` 逃逸 + 残留未配对 call）。
3. **诚实记录**：T-20 曾以直改 `server._registry/_handlers/_invoker` 方式注入测试态（保持原构造行为不变）。
4. D-3/D-4/D-5（P3）登记不收敛（见 CHECKLIST §5）。

## 6. 诚实边界

- MCP 外部调用 `event_log=None`：生产环境无 `tool.call/result`（DESIGN §5 F-5），A4-4 由注入式测试验证。
- 审批拒绝路径在无 sink 时不写 `approval.required`（DESIGN §5 F-4，随 M0 回边）。
- `approvals.json` 无 revoke/过期；授予后长期有效（登记后续）。
- `exit_code` 目前只区分 0/1；137/resource_limit 由 M4 提供。

---
