---
id: arc-g4-m2-dynamic-tools-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m2-dynamic-tools-RESEARCH]
upstream: arc-g4-m2-dynamic-tools-RESEARCH
---

# 设计：G4-M2 动态注册 + listChanged + `GET /api/tools`（P-103）

> 基于 [RESEARCH.md](RESEARCH.md)。批内先修 P-102 D-1/D-2/D-3，再交付 A4-10。

## 1. 交付范围

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/tools/registry.yaml` | 新增 | 包内 canonical 副本（D-1） |
| 2 | `researchclaw/tools/registry.py` | 修改 | D-1 路径解析 + D-2 freeze + D-3 错误码 |
| 3 | `pyproject.toml` | 修改 | hatch `force-include`（D-1） |
| 4 | `.github/workflows/ci.yml` | 修改 | packaging job wheel 冒烟（D-1） |
| 5 | `researchclaw/mcp/registry_adapter.py` | 新增 | 动态注册 + schema 注入 + reload/notifier（A4-10） |
| 6 | `researchclaw/server/routes/tools.py` | 新增 | `GET /api/tools`（字段白名单） |
| 7 | `researchclaw/server/app.py` | 修改 | include tools_router |
| 8 | `researchclaw/mcp/server.py` | 修改 | `_register_tools` 改走 adapter（dispatcher 接缝） |
| 9 | `tests/test_tool_registry.py` | 修改 | T-R1..R4（D-1/D-2/D-3） |
| 10 | `tests/test_mcp_dynamic_tools.py` | 新增 | T-1..T-10 |
| 11 | `spec/arc-g4-m2-dynamic-tools/` 四文档 | 新增 | 本批 spec |
| 12 | `spec/arc-g4-m0-design/DESIGN.md` | 修改 | 受控回边（编号 + M2 前置） |

## 2. 修复设计（P-102 D-1/D-2/D-3）

### 2.1 D-1 注册表分发

- canonical 源仍是仓库根 `tools/registry.yaml`（开发态）；包内副本 `researchclaw/tools/registry.yaml` 为发布态真值。
- `_default_registry_path()`：
  ```python
  try:
      return importlib.resources.files("researchclaw.tools").joinpath("registry.yaml")
  except (ModuleNotFoundError, TypeError):
      return Path(__file__).resolve().parents[2] / "tools/registry.yaml"
  ```
  `RC_TOOL_REGISTRY` 环境变量保持最高优先。
- hatch：`force-include = {"tools/registry.yaml" = "researchclaw/tools/registry.yaml"}`。
- CI packaging job：装 wheel 后 `python -c "from researchclaw.tools.registry import load_registry; load_registry()"`。
- 一致性测试 T-R1：仓库根文件与 `importlib.resources` 读取内容相等。

### 2.2 D-2 只读包装

```python
def _freeze(obj):
    if isinstance(obj, dict):
        return types.MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj
```
应用于 `ToolSpec.input_schema`/`output_schema` 与 `Registry.sandbox_profiles`。deep equality 断言（`MappingProxyType == dict` → True）不受影响；`json.dumps` 消费点（若有）改经 `dict()` 展开。

### 2.3 D-3 错误码

`_load_payload`：OSError/不存在/目录 → `E_REGISTRY_UNREADABLE`；YAML 错误/非映射 → `E_REGISTRY_PARSE`；`E_REGISTRY_VERSION` 仅 version。`__init__.py` 导出新增两个错误码。

## 3. 动态注册（A4-10）

### 3.1 `registry_adapter.py`

```python
def register_from_registry(server, registry, dispatcher, *, notifier=None) -> list[str]
def refresh_from_registry(server, old_registry, notifier=None) -> Registry
```

- `register_from_registry`：遍历 `registry.tools` → `_make_call(dispatcher, name)`（async，转发 `dispatcher(name, kwargs)`，设置 `__name__`）→ `server.add_tool(_call, name=..., description=...)` → **路径 B 注入**：`server._tool_manager.get_tool(name).parameters = spec.input_schema` → 返回注册名列表。**零工具名硬编码**（T-4）。
- `refresh_from_registry`：`new = old.reload()` → 对 old 中每个 tool `server.remove_tool(name)` → `register_from_registry(server, new, ...)` → `notifier()`（若提供）→ 返回 new。失败时抛 `RegistryError`（旧注册不变——remove 仅在校验成功后执行）。
- dispatcher 签名：`async (name: str, args: dict) -> Any`；`server.py` 传入 `self._dispatch_tool`（新增小方法：`self._as_result(await self.handle_tool_call(name, args))`）。

### 3.2 listChanged 阻塞点（诚实声明）

- stdio 单连接场景无运行期 session 可通知；`session_manager` 懒加载且仅 HTTP 场景可用。
- **本批交付**：notifier 接缝（callable）+ fake 测试（T-5 断言调用 1 次）；`server.py` 接线 notifier=None。
- **登记阻塞**：真 `ServerSession.send_tool_list_changed()` 通知留待 HTTP/多 session 批次；届时从 session manager 取活跃 session 调用。

## 4. `GET /api/tools`（M0 §3.1）

`routes/tools.py`：`router = APIRouter(prefix="/api", tags=["tools"])`；启动时模块级 `load_registry(strict_handlers=True)`（异常 → 应用启动失败，Q-3）。返回：

```json
{"version": 1, "tools": [{"name","version","description","inputSchema","outputSchema","scope","risk","approval"}]}
```

不暴露 `handler`/`sandbox_profile`。`app.py` `include_router(tools_router)`。

## 5. `server.py` 接线

`_register_tools` 整体替换为：

```python
from researchclaw.mcp.registry_adapter import register_from_registry
from researchclaw.tools.registry import load_registry
def _register_tools(self) -> None:
    registry = load_registry(strict_handlers=True)
    register_from_registry(self._mcp, registry, self._dispatch_tool)
```

`_dispatch_tool`：`self._as_result(await self.handle_tool_call(name, args))`。`get_tools()`/`TOOL_DEFINITIONS` **不动**（T-9 兼容）。`mcp/tools.py` 保留双源。

## 6. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | 路径 B 注入 + deep equality 守卫 | RESEARCH §3.1 | 拒绝路径 A（丢 description/anyOf，静默弱化 A4-10） |
| D-2 | notifier 接缝 + 阻塞点登记 | RESEARCH §3.2 | 拒绝伪造通知（stdio 无 session） |
| D-3 | freeze 单向收紧 | P-102 D-2 | 拒绝仅登记边界（可改真值源风险仍在） |
| D-4 | dispatcher 参数注入而非 invoker | M3 未实现 | 拒绝本批建 invoker（越批）；M3 接入时替换 |
| D-5 | 包内副本 + 仓库根双源 | D-1 | 拒绝仅包内（开发态改 YAML 要重装） |

## 7. 验收映射

| 验收 ID | 落点 |
|---|---|
| D-1 关闭 | T-R1/T-R2 + pyproject/ci diff |
| D-2 关闭 | T-R3 |
| D-3 关闭 | T-R4 |
| A4-10 前半（一致） | T-2 deep equality |
| A4-10 后半（新增不改代码） | T-3 |
| A4-10 listChanged | T-5（接缝）+ 阻塞点登记 |
| REST | T-6 |
| fail-closed 启动 | T-7/T-8 |
| 零回退 | T-9（MCP 42 项） |

## 8. 不变式

- I-1 注册表唯一真值源；adapter 零硬编码（T-4）。
- I-2 fail-closed：坏注册表 → server/app 启动失败。
- I-3 事件只落 digest/摘要（M3 范围，本批不涉及）。
- I-4 6 工具名称/参数不变（T-9 + T-2）。
- I-5 notifier 未提供时不抛错（stdio 合法）。
- I-6 `reload()` 失败旧注册与旧注册到 SDK 的状态不变。

## 9. 非目标

- 真 session 的 listChanged 通知（阻塞点登记）。
- invoker/事件/审批（M3）。
- 沙箱（M4）、HostProfile（M5）。
- 删除 `mcp/tools.py`（M3/M4）。

---
