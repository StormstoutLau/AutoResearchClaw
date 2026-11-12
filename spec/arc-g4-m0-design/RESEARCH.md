---
id: arc-g4-m0-design-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-mcp-alignment-RESEARCH]
upstream: arc-g4-mcp-alignment-RESEARCH
---

# 调研：G4 M0 工具注册表与沙箱边界现状与缺口（P-099）

> **Feature**：P-099，G4 开工批次（M0 设计冻结）。
> **Spec 步骤**：Step 1-2（T1；本批零生产代码，施工从 M1 开始）。
> **结论先行**：G4 的**地基多数已存在但未接线**——`EVENT_TYPES` 已声明 `tool.call`/`tool.result`（无生产者）、`safe_join` 与 `build_subprocess_env` 已在用（覆盖不全）、`docker_sandbox.py` 已有网络策略与 `--rm`（无配额/TTL/标签）、MCP SDK 2.3.0 提供 `send_tool_list_changed()`。**完全缺失**的是：工具注册表（`tools/registry.yaml`）、启动期 schema 校验、按 risk 的审批门、`HostProfile`、`GET /api/tools`、MCP 动态注册。10 项验收（A4-1..A4-10）映射为 9 个缺口 G-1..G-9，拆为 M1..M5 五批施工。

## 1. 调研目标

1. 逐项核对 A4-1..A4-10 的**仓内现状**（有/无/半接线），形成缺口矩阵。
2. 回源 MCP 2026-07-28 对 `tools` capability / `listChanged` / `inputSchema` 的要求（承 P-093 已有 T1 结论）。
3. 冻结 G4 架构与批次拆分，使每个验收项有唯一归属批次与可失败测试。
4. 登记待裁决决策点 Q-1..Q-6。

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1/E3） | 总纲 G4 条款、MCP 模块、沙箱、事件、工具函数 | ✅ 逐项定位 |
| 本机 SDK 探针（E2） | `mcp` 2.3.0 的 `listChanged` 能力面 | ✅ server 侧 `send_tool_list_changed` 存在 |
| 依赖面读码（E1） | `pyproject.toml` 运行时/extras 依赖 | ✅ `jsonschema` 仅在 dev extras |
| 总纲与 P-093 回源（E1） | A4 条款原文、MCP 版本对齐结论 | ✅ |

**降级链记录**：E2B / Daytona / Firecracker / OpenHands 四家产品的隔离档位**未在本批回原文**——仅作路线图 R-05 转述引用（T3），不支撑任何 A 类断言；本批 A 类断言全部落在仓内文件与 SDK 探针（T1/E2）。

## 3. 现状取证

### 3.1 十项验收逐项现状

| A4 | 要求 | 仓内现状（E1 路径） | 判定 |
|---|---|---|---|
| A4-1 | 100% 已注册工具有 schema；缺 schema 启动即失败 | `researchclaw/mcp/tools.py` 6 个工具**硬编码**含 `inputSchema`（L8-87）；**无注册表**、**无校验** | ❌ 缺 |
| A4-2 | 路径逃逸/符号链接/网络外联/fork bomb 四类全拒 | `docker_sandbox.py` 有 `network` 策略四档（L104-108）、`--rm`、`--gpus all`（L225）；脚本入口有 `validate_entry_point_resolved` | ⚠️ 半 |
| A4-3 | 资源超限 → 退出码 137 + 落 `tool.result` | `--memory`（L389，默认 8192MB）与 `--shm-size` **已存在**（P-100 D-7 订正：原判「无」不成立）；**无** `--pids-limit/--cpus/--label`，有 `timeout_sec` 但超时非 137 语义；无 `tool.result` | ⚠️ 半（P-100 订正） |
| A4-4 | 每 `tool.call` 有对应 `tool.result`；缺失标 `orphan_call` | `EVENT_TYPES` 已含 `tool.call`/`tool.result`（`runtime/event_log.py` L40），**无生产者**、无 orphan 扫描 | ❌ 缺 |
| A4-5 | `risk=high` 未审批拒绝执行 | 有 `approval.required` 事件类型；无 risk 字段、无审批门 | ❌ 缺 |
| A4-6 | 容器 TTL 到期回收、产物已落盘 | 仅 `--rm`（进程退出即删）；**无 TTL 看护**（挂起容器残留） | ❌ 缺 |
| A4-7 | 全部沙箱后端用 env allowlist | `utils/env.py::build_subprocess_env` 存在，**3 个文件**使用 | ⚠️ 覆盖不全 |
| A4-8 | 全部产物写入点用 `safe_join` | `utils/paths.py::safe_join` 存在，**2 个文件**使用 | ⚠️ 覆盖不全 |
| A4-9 | `HostProfile` 只返回数据；无 `shell=True`/外发脚本 | **无 HostProfile**；`subprocess` 调用面需建清单 | ❌ 缺 |
| A4-10 | 注册表与 MCP `listChanged` 一致；新增工具无需改代码 | `server.py` **手工注册 6 个** handler（`_register_tools`）；SDK 2.3.0 `ServerSession.send_tool_list_changed()` 存在（E2） | ❌ 缺 |

### 3.2 SDK 能力面（E2，mcp 2.3.0）

| 探针 | 结果 |
|---|---|
| `MCPServer` 类是否含 list_changed 方法 | ❌ 无（仅 `_handle_list_tools`/`list_tools`） |
| server 侧通知入口 | ✅ `mcp/server/connection.py:441`、`mcp/server/session.py:461` `send_tool_list_changed()` |
| 订阅协商 | ✅ `mcp/server/subscriptions.py:150` `tools_list_changed=True` |
| client 侧订阅 | ✅ `Client.listen(tools_list_changed=True)`（`client/client.py:696-719`） |

**推论**：A4-10 的 `listChanged` 需在服务端持有 session/connection 引用后主动发送；`MCPServer` 需暴露该钩子（或经 `server.connection` 取得）。

### 3.3 依赖面（E1，`pyproject.toml`）

- 运行时依赖：`pyyaml` / `rich` / `arxiv` / `numpy`（L6-11）。
- extras：`server = fastapi+uvicorn`、`mcp = mcp>=2.1,<3`、`voice`。
- `jsonschema>=4.20` **仅在 dev extras**（L43）→ 若启动期做完整 2020-12 校验，需把 `jsonschema` 并入 `server`/`mcp` extras（见 Q-1）。

## 4. 缺口矩阵

| # | 缺口 | 覆盖 A4 | 施工批 |
|---|---|---|---|
| G-1 | 无 `tools/registry.yaml` 与加载器 | A4-1 | M1 |
| G-2 | 无启动期 schema 校验（fail-closed） | A4-1 | M1 |
| G-3 | MCP 工具手工注册、无动态装载、无 listChanged | A4-10 | M2 |
| G-4 | 无 `GET /api/tools` | A4-10（交付物） | M2 |
| G-5 | 无 `tool.call`/`tool.result` 生产者与 `orphan_call` 扫描 | A4-4 | M3 |
| G-6 | 无 `risk`/`approval` 审批门 | A4-5 | M3 |
| G-7 | 沙箱缺 pids/cpus 配额、无 TTL 看护、退出码 137 未映射（`--memory` 已有，P-100 D-7 收窄） | A4-2/A4-3/A4-6 | M4 |
| G-8 | env allowlist 与 `safe_join` 覆盖不全（3/2 文件） | A4-7/A4-8 | M5 |
| G-9 | 无 `HostProfile`；`subprocess` 调用面未建清单 | A4-9 | M5 |

## 5. 待裁决决策点

| # | 决策 | 建议 | 备选 |
|---|---|---|---|
| Q-1 | schema 校验依赖 | `jsonschema>=4.20` 并入 `server` 与 `mcp` extras；核心 pipeline 不受影响 | 运行时核心依赖 / 手写结构校验 |
| Q-2 | 注册表位置 | `tools/registry.yaml`（总纲 L455 显式指定） | `researchclaw/tools/registry.yaml` |
| Q-3 | 动态注册触发 | 启动装载 + 显式 reload（文件 mtime 变化）→ 发 `send_tool_list_changed` | 仅启动装载，listChanged 只做启动后一次 |
| Q-4 | 沙箱隔离档位 v1 | Docker + `--network none` 默认 + cpu/mem/pids/disk 配额 + label + TTL 看护 | 引入 E2B/Firecracker（超本期） |
| Q-5 | `orphan_call` 判定时点 | run 收尾扫描 events.jsonl：call 无同 `call_id` 的 result → 标记事件 | 实时超时标记 |
| Q-6 | `HostProfile` 依赖 | 纯 stdlib（`shutil.disk_usage`/`os.cpu_count`/`subprocess` 只跑固定白名单命令） | 引入 psutil |

## 6. 对上文的输入

1. 9 个缺口与 5 个施工批的映射冻结（DESIGN §10）。
2. A4-1 的「启动即失败」必须在**注册表加载器**而非 MCP 层实现，使 REST/MCP 双入口同源。
3. A4-10 的「新增工具无需改代码」= registry 驱动注册循环；`listChanged` 经 reload 钩子发送。
4. A4-2/A4-3/A4-6 同属沙箱批 M4：配额、TTL、137 一次改完，避免三次改同一执行路径。

---

## 7. 参考文献

- [总纲 G4](../../arc-master-roadmap.md) L448-484（交付物与 A4-1..A4-10）
- [P-093 MCP 版本对齐](../arc-g4-mcp-alignment/RESEARCH.md)（pin 与 Modern/Legacy 结论，T1）
- 仓内：`researchclaw/mcp/{server,client,tools}.py`、`researchclaw/runtime/event_log.py`、`researchclaw/experiment/docker_sandbox.py`、`researchclaw/utils/{paths,env}.py`、`researchclaw/server/routes/`、`pyproject.toml`
- MCP spec 2026-07-28（tools capability / listChanged / JSON Schema 2020-12）：经 P-093 已回原文（T1），本批不重复抓取
- 外部沙箱产品（E2B/Daytona/Firecracker/OpenHands）：**T3 转述，未回原文**，仅作档位背景

---
