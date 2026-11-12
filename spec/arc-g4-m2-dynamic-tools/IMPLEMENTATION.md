---
id: arc-g4-m2-dynamic-tools-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m2-dynamic-tools-DESIGN]
upstream: arc-g4-m2-dynamic-tools-DESIGN
---

# 实施：G4-M2 动态注册 + listChanged + `GET /api/tools`（P-103）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/tools/registry.yaml` | 新增 | 包内 canonical 副本（D-1） |
| 2 | `researchclaw/tools/registry.py` | 修改 | D-1 `importlib.resources` 解析；D-2 `_freeze`/`unfreeze`；D-3 错误码拆分 |
| 3 | `pyproject.toml` | 修改 | hatch `force-include`（D-1） |
| 4 | `.github/workflows/ci.yml` | 修改 | packaging job wheel 冒烟 + 清单加 `test_mcp_dynamic_tools.py` |
| 5 | `researchclaw/mcp/registry_adapter.py` | 新增 | `register_from_registry`/`refresh_from_registry`/`_make_call`（合成签名）/`_inject_schema`（路径 B） |
| 6 | `researchclaw/server/routes/tools.py` | 新增 | `GET /api/tools`（lazy fail-closed + 字段白名单 + unfreeze） |
| 7 | `researchclaw/server/app.py` | 修改 | include tools_router + 启动 `get_registry()` |
| 8 | `researchclaw/mcp/server.py` | 修改 | `_register_tools` 走 adapter + `_dispatch_tool` 返回裸 dict |
| 9 | `tests/test_tool_registry.py` | 修改 | +5 项（T-R1..R4） |
| 10 | `tests/test_mcp_dynamic_tools.py` | 新增 | 12 项（T-1..T-10） |
| 11 | `spec/arc-g4-m2-dynamic-tools/` 四文档 | 新增 | 本批 spec |
| 12 | `spec/arc-g4-m0-design/DESIGN.md` + P-099 session | 修改 | 受控回边（编号第三次顺延 + M2 前置完成） |

## 2. 关键实现记录（含三轮 SDK 兼容修正，诚实记录）

1. **签名参数名**：合成签名用 `__registry_delegate__` VAR_KEYWORD → SDK 校验参数名不能 `_` 开头（`InvalidSignature`，37 failed）→ 改 `kwargs`。
2. **返回值语义**：dispatcher 返回 `_as_result(...)` CallToolResult → SDK 再包装崩溃（`Internal server error`）→ `_dispatch_tool` 返回**裸 dict**，由 SDK 包装 content/structured_content。
3. **structured_output**：显式 `structured_output=False`（dispatcher 已产出完整结果，禁止 SDK 二次包装）。
4. **mappingproxy 序列化**（根因由 server 端日志抓到：`PydanticSerializationError: Unable to serialize unknown type: <class 'mappingproxy'>`）：D-2 的 freeze 会让 schema 无法跨 JSON-RPC 序列化 → 新增 `unfreeze()`，`_inject_schema` 与 REST 输出统一解包；注册表内部仍只读。
5. `server.list_tools()` 为 async → 测试 `asyncio.run`。
6. 路由 lazy 加载（`REGISTRY`/`get_registry`/`load_tools_registry`）+ `app.py` 启动 `get_registry()`（fail-closed）。

## 3. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | `test_tool_registry.py` 19→24；`test_mcp_dynamic_tools.py` 12 项（新增） |
| 红→绿 | 红：collection error（adapter 缺）→ 实现三轮修正（上表 1-4）后全绿 |
| 3.13.5 | 四套件（registry+dynamic+MCP×2）**76 passed** |
| 3.11.15 | 同套件 **74 passed / 2 skipped**（fastapi/importorskip） |
| 宽回归 | 18 文件 **295 passed / 5 skipped**；扩展组 **348 passed** |
| 门禁 | 待回填 |

## 4. 验收边界（诚实口径）

- **listChanged 阻塞点**：stdio 单连接无运行期 session，真 `ServerSession.send_tool_list_changed` 通知**未接线**（notifier 接缝 + fake 测试在位）；留 M4/M5 或 HTTP 批次。
- `tool.parameters` 直写依赖 SDK 内部 `_tool_manager`（`mcp>=2.1,<3` 锁版本；T-2 deep equality 守卫）。
- `mcp/tools.py` 双源保留（M3/M4 迁移后删）。

---
