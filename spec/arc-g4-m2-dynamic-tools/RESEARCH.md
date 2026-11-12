---
id: arc-g4-m2-dynamic-tools-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-14
depends: [arc-g4-m1-registry, arc-g4-m1-registry-review]
upstream: arc-g4-m1-registry-review
---

# 调研：G4-M2 动态注册 + listChanged + `GET /api/tools`（P-103）

> **Feature**：P-103，G4-M2（A4-10：注册表与 MCP `listChanged` 一致；新增工具无需改代码）。
> **Spec 步骤**：Step 1-2（T1 实施批）。**批内前置**：先收敛 P-102 的 D-1/D-2/D-3。
> **结论先行**：D-5 spike 已由简报完成并有 E2 实据——SDK 不支持外部 schema 参数，但**路径 B（注册后直写 `tool.parameters`）可行且原样保留注册表 schema**；listChanged 运行时通知在 stdio（单连接）下不可达（`session_manager` 懒加载、未建连即抛 RuntimeError），本批实现「reload → 重新注册 + notifier 接缝」，真 session 通知登记阻塞点。D-1/D-2/D-3 三项修复方案冻结。

## 1. 调研目标

1. D-5 spike：SDK schema 注入机制定案（简报 §2 已有 E2，本批复验关键两项）。
2. listChanged 可达性：`MCPServer.session_manager` → `ServerSession` 路径是否可行。
3. D-1/D-2/D-3 修复方案与 REST 路由形态确认。

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| SDK 探针（E2） | `MCPServer` 公共面、`ToolManager.add_tool` 签名、合成签名与 parameters 直写 | ✅ 路径 A/B 双验证 |
| SDK 读码（E3） | `session_manager` 懒加载抛 RuntimeError（`lowlevel/server.py:697`）；`ServerSession.send_tool_list_changed` 签名 `(self) -> None`；`("tools/list", …, on_list_tools)` 注册于 L341 | ✅ |
| 读码（E3） | REST 路由形态：`APIRouter(prefix="/api")` + `app.include_router`（`server/app.py` L123-140） | ✅ |
| 复核报告回源（E1） | P-102 D-1/D-2/D-3、P-100 D-5 | ✅ |

**降级链记录**：一次 Python 进程崩溃（access violation，探针脚本 import 冲突）→ 改用分次小探针重跑，无静默跳过。

## 3. 发现

### 3.1 D-5 spike（E2 复验）

| 探针 | 结果 |
|---|---|
| `tool()`/`add_tool()` 有无 `inputSchema` 参数 | ❌ 无（仅 name/title/description/annotations/icons/meta/structured_output） |
| schema 来源 | `MCPServer._tool_input_schema(name) → ToolManager.get_tool(name).parameters`（签名生成） |
| 路径 A：合成 `fn.__signature__` | ✅ 生成含 type/required/default 的 schema；**丢失 properties.description 与 anyOf** |
| 路径 B：注册后 `tool.parameters = registry_schema` | ✅ 直写成功，`list_tools()` 原样返回注册表 schema（含 anyOf/description） |
| 路径 B 风险 | 依赖 SDK 内部 `_tool_manager`/`Tool.parameters`（`mcp>=2.1,<3` 已锁版本；deep equality 测试在升级时立即变红） |

### 3.2 listChanged 可达性

- `MCPServer.session_manager` → `lowlevel.Server._session_manager`，**懒加载**：未调用 `streamable_http_app()` 前访问即抛 `RuntimeError`（E3 读码）。
- stdio（`run_stdio_async`）为单连接阻塞模型：**无多 session，通知无意义**。
- `ServerSession.send_tool_list_changed()` 签名 `(self) -> None` 存在，但需持有一个已连接的 session 实例；从 `MCPServer` 无公共路径可直接取得运行期 session。
- **裁决（Q-R1）**：本批实现「reload → remove 旧 tool → 重新注册 → 调用 `notifier` 接缝（callable，可注入 fake）」；`server.py` 接线时 notifier=None 并**显式登记阻塞点**（真 session 通知留 M4/M5 或 HTTP 场景批次）。

### 3.3 D-1/D-2/D-3 修复方案

| # | 方案 | 细节 |
|---|---|---|
| D-1 | 包内资源 + force-include | 新增 `researchclaw/tools/registry.yaml`（canonical 副本）；`pyproject.toml` `[tool.hatch.build.targets.wheel]` 加 `force-include = {"tools/registry.yaml" = "researchclaw/tools/registry.yaml"}`；`_default_registry_path()` 改 `importlib.resources.files("researchclaw.tools").joinpath("registry.yaml")`（traversable）；`RC_TOOL_REGISTRY` 仍最高优先 |
| D-2 | 只读包装 | `_freeze(obj)` 递归：dict → `types.MappingProxyType`（一层嵌套均包）；list → tuple。`Registry.sandbox_profiles`/`ToolSpec.input_schema`/`output_schema` 走 freeze |
| D-3 | 错误码拆分 | 新增 `E_REGISTRY_UNREADABLE`（OSError/不存在/目录）与 `E_REGISTRY_PARSE`（YAML 解析失败/非映射）；`E_REGISTRY_VERSION` 仅 version 类型与取值 |

### 3.4 REST 形态（E3）

`APIRouter(prefix="/api", tags=[...])` + `app.include_router(...)`（app.py L123-140）；路由测试沿用 `pytest.importorskip("fastapi")` 先例（P-031）。

## 4. 幻觉抑制审查（Step 2 Review）

| 引用/声明 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| 路径 B 直写可行且原样保留 | 简报 spike + 本批复验 | E2 | ✅ |
| session_manager 懒加载抛错 | `lowlevel/server.py:697` 读码 | E3 | ✅ |
| D-1/D-2/D-3 依据 | P-102 报告 §3 | 回源 | ✅ E1 |
| REST 路由形态 | `routes/pipeline.py` + `app.py` | 读码 | ✅ E3 |

### 待修正项

- [x] M0 DESIGN §9 编号（P-102..P-105 → P-103..P-106）与「M2 前置 D-1/D-2/D-3」→ 随本批受控回边落 M0 文档。

## 5. 对设计的输入

1. 路径 B + deep equality 守卫（若实施会话判定内部 API 风险不可接受改路径 A，须显式改述 A4-10「一致」为「投影一致」——不得静默弱化）。
2. listChanged 阻塞点显式登记，notifier 接缝可注入（fake 可测）。
3. D-1 的仓库根 `tools/registry.yaml` 保留为开发态真值源，包内副本为发布态；T-R1 一致性测试防漂移。

## 6. 参考文献

- P-103 简报（`p103-m2-brief.md`，工作区根目录、不入仓；spike 证据与测试矩阵）
- [P-102 复核](../../docs/arc-g4-m1-registry-review-20261114.md)（D-1/D-2/D-3）
- [P-100 复核 D-5](../../docs/arc-g4-m0-design-review-20261114.md)
- SDK：`mcp/server/mcpserver/server.py`、`mcp/server/lowlevel/server.py`、`mcp/server/session.py`

## 7. 复核收敛输入（v1.1，受控回边）

复核批（DeepSeek-V4.1-Flash，**并入 P-103 不占号**，用户裁决 2026-11-12）报告：[arc-g4-m2-review-20261114.md](../../docs/arc-g4-m2-review-20261114.md)。一手取证结论作为本批收敛设计的输入：

| # | 发现 | 复核证据（取证等级） |
|---|---|---|
| D-1 P1 | **wheel 构建失败**：`force-include` 把仓库根文件映射到已存在的包内副本同一路径 → `ValueError: duplicate archive entry`；且违反既有打包契约测试 `test_packaging.py::test_wheel_does_not_force_include_package_data` | E2 实构建 `uv build --wheel` 中止；E1 CI 全清单 1 failed / 600 passed |
| D-2 P2 | **可选参数以 `None` 注入**：pydantic 按合成签名默认值填充缺省可选参数并原样下发；`run_pipeline.auto_approve` 由 legacy 默认 `True` 变 `bool(None)=False` 静默翻转（MCP 42 项只锁 schema，未覆盖参数语义，故未捕获） | E2 X-4/X-16 实测 dispatcher 实收 kwargs；E1 `git show 0648e2a` legacy 签名 `auto_approve: bool = True` |
| D-3 P2 | **handler 指向类对象**：6 条 handler 均为 `researchclaw.mcp.server:ResearchClawMCPServer`，`resolve()` 返回类——V-5b 只证「可导入」，invoker 调用会构造而非分发 | E2/E4 X-17 实测 `isclass=True`×6 |
| D-4 P3 | DESIGN 三处漂移：`register_from_registry` 声明带 `notifier`（实现无）/ `_dispatch_tool` 返回 `_as_result(...)`（实现为裸 dict）/ 「启动时模块级 load」（实现为 lazy） | E3 读码 |
| D-5 P3 | 自报读数失准：dynamic「12 项」实为 10；「宽回归 295/5」口径不可复现；「packaging 冒烟绿」未经真实构建 | E1 |
| O-6 | `__registry_handler__` 死属性（全仓只写不读） | E4 扫描 |

另：复核证实 §3.2 的 listChanged 阻塞判断（X-11：`connection` 属性不存在、`session_manager` 属性激活即抛 RuntimeError），阻塞点登记成立。

---
