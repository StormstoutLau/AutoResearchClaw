---
id: arc-g4-m2-dynamic-tools-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-14
depends: [arc-g4-m2-dynamic-tools-DESIGN]
upstream: arc-g4-m2-dynamic-tools-DESIGN
---

# 实施：G4-M2 动态注册 + listChanged + `GET /api/tools`（P-103）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/tools/registry.yaml` | 新增 | 包内 canonical 副本（D-1）；v1.1 handler 改指 `dispatch_tool` |
| 2 | `researchclaw/tools/registry.py` | 修改 | D-1 `importlib.resources` 解析；D-2 `_freeze`/`unfreeze`；D-3 错误码拆分；v1.1 `resolve()` 拒绝类/不可调用 |
| 3 | `pyproject.toml` | 修改 | v1.0 加 hatch `force-include`（D-1）；**v1.1 删除**（复核 D-1：与包内副本同路径冲突致 wheel 构建失败） |
| 4 | `.github/workflows/ci.yml` | 修改 | packaging job wheel 冒烟 + 清单加 `test_mcp_dynamic_tools.py`；v1.1 wheel `required` 加注册表 |
| 5 | `researchclaw/mcp/registry_adapter.py` | 新增 | `register_from_registry`/`refresh_from_registry`/`_make_call`（合成签名）/`_inject_schema`（路径 B）；v1.1 `_call` 清洗 None 可选参数 + 删 `__registry_handler__` |
| 6 | `researchclaw/server/routes/tools.py` | 新增 | `GET /api/tools`（lazy fail-closed + 字段白名单 + unfreeze） |
| 7 | `researchclaw/server/app.py` | 修改 | include tools_router + 启动 `get_registry()` |
| 8 | `researchclaw/mcp/server.py` | 修改 | `_register_tools` 走 adapter + `_dispatch_tool` 返回裸 dict；v1.1 新增模块级 `dispatch_tool`（registry handler 调用点） |
| 9 | `tests/test_tool_registry.py` | 修改 | +5 项（T-R1..R4）；v1.1 +1（类 handler 拒绝） |
| 10 | `tests/test_mcp_dynamic_tools.py` | 新增 | v1.0 10 项（T-1..T-10）；v1.1 +2（None 清洗 ×2） |
| 11 | `tools/registry.yaml` | 修改 | v1.1 handler 改指 `dispatch_tool`（与包内副本同步，T-R1） |
| 12 | `spec/arc-g4-m2-dynamic-tools/` 四文档 | 新增 | 本批 spec；v1.1 回填复核收敛 |
| 13 | `spec/arc-g4-m0-design/DESIGN.md` + P-099 session | 修改 | 受控回边（编号第三次顺延 + M2 前置完成；v1.1 §3/§9 事实订正） |

## 2. 关键实现记录（含三轮 SDK 兼容修正，诚实记录）

1. **签名参数名**：合成签名用 `__registry_delegate__` VAR_KEYWORD → SDK 校验参数名不能 `_` 开头（`InvalidSignature`，37 failed）→ 改 `kwargs`。
2. **返回值语义**：dispatcher 返回 `_as_result(...)` CallToolResult → SDK 再包装崩溃（`Internal server error`）→ `_dispatch_tool` 返回**裸 dict**，由 SDK 包装 content/structured_content。
3. **structured_output**：显式 `structured_output=False`（dispatcher 已产出完整结果，禁止 SDK 二次包装）。
4. **mappingproxy 序列化**（根因由 server 端日志抓到：`PydanticSerializationError: Unable to serialize unknown type: <class 'mappingproxy'>`）：D-2 的 freeze 会让 schema 无法跨 JSON-RPC 序列化 → 新增 `unfreeze()`，`_inject_schema` 与 REST 输出统一解包；注册表内部仍只读。
5. `server.list_tools()` 为 async → 测试 `asyncio.run`。
6. 路由 lazy 加载（`REGISTRY`/`get_registry`/`load_tools_registry`）+ `app.py` 启动 `get_registry()`（fail-closed）。

### 2.1 复核收敛修复轮（v1.1，复核报告 arc-g4-m2-review-20261114.md）

先红（3 新测试 3 failed）→ 实现 → 全绿：

1. **D-1（P1）**：删除 `pyproject.toml` `force-include`（复核实构建 `ValueError: duplicate archive entry`；既有 `test_packaging.py` no-force-include 契约测试变红为第二证据）；CI wheel 校验 `required` 清单加 `researchclaw/tools/registry.yaml`。
2. **D-2（P2）**：`_make_call._call` dispatch 前丢弃「值为 None 且非 required」的 kwargs——pydantic 会按合成签名默认值把缺省可选参数填成 `None` 下发，legacy `bool(args.get("auto_approve", True))` 因此翻转；required 的 None 透传。
3. **D-3（P2）**：6 条 handler → `researchclaw.mcp.server:dispatch_tool`（新增模块级 async 调用点，lazy 单例）；`ToolSpec.resolve()` 加载期拒绝类/不可调用对象（`E_REGISTRY_HANDLER`）；双 yaml 同步（T-R1 一致性保持）。
4. **O-6**：删除 `__registry_handler__` 死属性（复核 E4：全仓只写不读）。
5. **诚实记录**：修复轮 docstring 曾含工具名字面量，被 T-4 零硬编码扫描当场逮红 → 改措辞（守卫有效）；D-5 读数订正见 §3。

## 3. 读数（Step 9-10 回填，v1.1 订正）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | `test_tool_registry.py` 24→**25 collected**（+类 handler 拒绝）；`test_mcp_dynamic_tools.py` 10→**12**（v1.0 实为 10，v1.0 文档误记 12——D-5 订正；+None 清洗 2 项） |
| 红→绿 | v1.1：3 新测试 **3 failed** → 实现后全绿；CI 全清单复核时 1 failed（test_packaging）→ 修复后 **0 failed** |
| 3.13.5 | 四套件（registry 25 + dynamic 12 + MCP 42）**79 passed** |
| 3.11.15 | 含 extras **79 passed**；无 extras（registry 单套件）**24 passed / 1 skipped**（既有 `importorskip("mcp")`） |
| CI 固定清单 | 40 文件 **604 passed / 13 skipped，0 failed**（v1.0 自报「宽回归 295/5」口径不可复现，D-5 订正；本轮以 CI 清单全量复跑为准） |
| wheel（D-1 关闭三连） | `uv build --wheel` 成功（428 文件、零重复路径）；`researchclaw/tools/registry.yaml` 在包内；临时 target 安装后 `load_registry()` 成功（6 tools，handler0 = `dispatch_tool`） |

## 4. 验收边界（诚实口径）

- **listChanged 阻塞点**：stdio 单连接无运行期 session（复核 X-11 独立证实：`connection` 属性不存在、`session_manager` 属性激活即抛 `RuntimeError`），真 `send_tool_list_changed` 通知**未接线**（notifier 接缝 + fake 测试在位）；留 M4/M5 或 HTTP 批次。
- `tool.parameters` 直写依赖 SDK 内部 `_tool_manager`（`mcp>=2.1,<3` 锁版本；T-2 deep equality 守卫）。
- **显示 schema ≠ 运行时校验 schema**（复核 O-1）：注入的注册表 schema 决定 `list_tools()` 展示；SDK 运行时校验走合成签名的 `arg_model`（类型约束宽松、`anyOf` 不参与）。M3 invoker 承担运行时校验后自然收敛；登记于 DESIGN §10。
- `mcp/tools.py` 双源保留（M3/M4 迁移后删）。

---
