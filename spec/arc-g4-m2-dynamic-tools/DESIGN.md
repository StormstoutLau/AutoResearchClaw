---
id: arc-g4-m2-dynamic-tools-DESIGN
type: design
version: 1.1
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
def register_from_registry(server, registry, dispatcher) -> list[str]
def refresh_from_registry(server, old_registry, dispatcher, *,
                          notifier=None, path=None) -> Registry
```

- `register_from_registry`：遍历 `registry.tools` → `_make_call(dispatcher, name)`（async，转发 `dispatcher(name, kwargs)`，设置 `__name__`）→ `server.add_tool(_call, name=..., description=...)` → **路径 B 注入**：`server._tool_manager.get_tool(name).parameters = spec.input_schema` → 返回注册名列表。**零工具名硬编码**（T-4）。
- `refresh_from_registry`：`new = old.reload()` → 对 old 中每个 tool `server.remove_tool(name)` → `register_from_registry(server, new, ...)` → `notifier()`（若提供）→ 返回 new。失败时抛 `RegistryError`（旧注册不变——remove 仅在校验成功后执行）。
- dispatcher 签名：`async (name: str, args: dict) -> Any`；`server.py` 传入 `self._dispatch_tool`（新增小方法：返回**裸 dict**——SDK 负责包装 `CallToolResult`，P-103 实测返回预包装结果会双重包装崩溃）。

### 3.2 listChanged 阻塞点（诚实声明）

- stdio 单连接场景无运行期 session 可通知；`session_manager` 懒加载且仅 HTTP 场景可用。
- **本批交付**：notifier 接缝（callable）+ fake 测试（T-5 断言调用 1 次）；`server.py` 接线 notifier=None。
- **登记阻塞**：真 `ServerSession.send_tool_list_changed()` 通知留待 HTTP/多 session 批次；届时从 session manager 取活跃 session 调用。

## 4. `GET /api/tools`（M0 §3.1）

`routes/tools.py`：`router = APIRouter(prefix="/api", tags=["tools"])`；路由模块 **lazy** 持有 `REGISTRY`（`get_registry()` 首次调用时 `load_registry(strict_handlers=True)`），`app.py` include 路由后立即 `get_registry()` → 启动 fail-closed（异常 → 应用启动失败，Q-3）。返回：

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

`_dispatch_tool`：返回裸 dict（`await self.handle_tool_call(name, args)`），由 SDK 包装 content/structured_content。`get_tools()`/`TOOL_DEFINITIONS` **不动**（T-9 兼容）。`mcp/tools.py` 保留双源。

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

## 10. 复核收敛设计（v1.1，受控回边）

复核 [arc-g4-m2-review-20261114.md](../../docs/arc-g4-m2-review-20261114.md) 发现 D-1（P1）/ D-2、D-3（P2）/ D-4、D-5（P3）；输入见 RESEARCH §7。

| # | 缺陷 | 收敛设计 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | wheel 构建失败：`force-include` 与包内副本同路径冲突（duplicate archive entry），且违反既有契约测试 `test_packaging.py`（no-force-include） | **删除 `force-include`**：注册表以普通包数据随 `packages=["researchclaw"]` 分发（hatchling 默认包含包内非 .py 文件，`domains/profiles/*.yaml` 同口径先例）；CI wheel 校验 `required` 清单增加 `researchclaw/tools/registry.yaml` | 拒绝「删包内副本、保留 force-include」——与既有契约测试语义冲突（该测试存在早于本批，是有效护栏） |
| D-2 | 可选参数以 `None` 注入 dispatcher：`run_pipeline.auto_approve` 由 legacy 默认 `True` 变 `bool(None)=False` 静默翻转 | `_make_call` 的 `_call` 在 dispatch 前丢弃「值为 `None` 且非 required」的 kwargs（absent ⇔ None 不下发，handler 侧默认值恢复权威）；required 的 `None` 透传（诚实交给 handler 校验） | 拒绝「从 schema default 生成签名默认值」——无 default 的可选参数在 pydantic 合成签名下会变成 required，破坏注册表声明的可选语义；拒绝仅在六个 handler 内逐个修补——不可维护且不修 invoker 面 |
| D-3 | 6 条 handler 指向类对象，V-5b「可导入」≠「可调用」 | ① handler 改指 `researchclaw.mcp.server:dispatch_tool`（新增模块级 async 函数 + lazy 单例 `handle_tool_call`；`module:attr` 格式无法表达 `Class.method`）；② `ToolSpec.resolve()` 加载期拒绝类/不可调用对象（复用 `E_REGISTRY_HANDLER`） | 拒绝仅登记不改 handler——M3 前置缺陷现在即可廉价关闭；拒绝自造 per-tool 函数族——与 dispatcher 接缝重复 |
| D-4 | DESIGN 与实现三处漂移 | §3.1/§4/§5 原地回填（本版本），实现即真值 | — |
| O-6 | `__registry_handler__` 死属性 | 删除 setattr（全仓无读取点）；M3 invoker 自行 `spec.resolve()` | — |

### 10.1 收敛验收（可失败）

- D-1 三连：`uv build --wheel` 成功、zip 内恰一份 `researchclaw/tools/registry.yaml` 且无重复路径、装 wheel 后 `load_registry()` 成功。
- D-2 关闭：`run_pipeline` 仅传 `topic` → dispatcher 实收 kwargs 不含 `auto_approve`/`config_path` 键（回归用例锁定 legacy 契约）。
- D-3 关闭：handler 指向类 → strict load 抛 `E_REGISTRY_HANDLER`；非 strict（仅格式）仍通过。
- 回归：CI 固定清单 40 文件 0 failed；四套件 79 passed；3.11 双口径（含 extras 79 / 无 extras 24+1skip，skip 为既有 `importorskip("mcp")`）。

---
