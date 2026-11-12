---
id: arc-g4-m0-design-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m0-design-RESEARCH]
upstream: arc-g4-m0-design-RESEARCH
---

# 设计：G4 工具注册表与沙箱边界（M0 冻结，P-099）

> 基于 [RESEARCH.md](RESEARCH.md) 的 G-1..G-9 缺口。本文件冻结 G4 的接口、schema 语义、批次归属与验收映射；施工从 M1 开始。

## 1. 架构

```text
tools/registry.yaml ──> registry.load()  ── 启动期校验（A4-1，fail-closed）
                            │
              ┌─────────────┼──────────────┬───────────────┐
              v             v              v               v
        MCP adapter    REST /api/tools  ToolInvoker     EventEmitter
     （动态注册+listChanged） （A4-10）   （approval/沙箱）  （tool.call/result）
              │                            │                │
              v                            v                v
        mcp.ServerSession          sandbox profile       events.jsonl
                                   （quota/TTL/137）      （orphan_call 扫描）
```

**单一真值源**：`tools/registry.yaml`。任何工具（MCP / REST / 内部调用）的元数据只从注册表读取，禁止在 adapter 内硬编码。

## 2. 注册表 schema（`tools/registry.yaml`）

```yaml
version: 1
tools:
  - name: run_pipeline                 # ^[a-z][a-z0-9_]{2,63}$
    version: "1.0"                     # 语义化字符串
    description: "..."                 # 非空，<= 500 字符
    inputSchema:                       # JSON Schema 2020-12，type=object
      type: object
      properties: { ... }
      required: [ ... ]
    outputSchema: { type: object }     # 可空；有则须为合法 JSON Schema
    scope: run                         # run | global
    risk: low                          # low | medium | high
    approval: never                    # never | always | high_only
    sandbox_profile: default           # 指向 sandbox_profiles
    handler: "researchclaw.mcp.server:pipeline_tool"   # module:attr
sandbox_profiles:
  default:
    network: none                      # none | setup_only | full
    cpu: 2                             # --cpus
    memory: 4g                         # --memory
    pids: 512                          # --pids-limit
    disk: 10g                          # 仅记录（Docker 需 overlay2 配额支持）
    ttl_sec: 1800                      # 看护回收
```

**校验规则（M1，启动期，任一失败即抛 `RegistryError`，进程退出）**

| # | 规则 | 错误码 |
|---|---|---|
| V-1 | `version` 必须为 `1` | `E_REGISTRY_VERSION` |
| V-2 | `tools` 非空、`name` 唯一且匹配 `^[a-z][a-z0-9_]{2,63}$` | `E_REGISTRY_NAME` |
| V-3 | 每个工具**必须**有 `inputSchema`（2020-12 合法、`type=object`） | `E_REGISTRY_SCHEMA_MISSING` / `E_REGISTRY_SCHEMA_INVALID` |
| V-4 | `risk ∈ {low,medium,high}`、`approval ∈ {never,always,high_only}`、`scope ∈ {run,global}` | `E_REGISTRY_ENUM` |
| V-5 | `handler` 形如 `module:attr`；**P-101 拆分**：V-5a 格式校验（fail-closed、必做）；V-5b `importlib` 可解析（strict 入口才做，避免核心路径依赖 mcp extra） | `E_REGISTRY_HANDLER` / `E_REGISTRY_HANDLER_UNRESOLVED` |
| V-6 | `sandbox_profile` 必须在 `sandbox_profiles` 中存在 | `E_REGISTRY_PROFILE` |
| V-7 | `sandbox_profiles` 的 `network/cpu/memory/pids/ttl_sec` 均必填且类型正确 | `E_REGISTRY_PROFILE_INVALID` |
| V-8 | **`risk=high ⇒ approval ∈ {always, high_only}`**（P-100 D-1 双保险之配置层） | `E_REGISTRY_APPROVAL` |

- 校验依赖：**P-101 Q-1 裁决 = `jsonschema>=4.20` 升核心依赖**（registry 属核心包且校验 fail-closed；optional extras 会让 CLI/pipeline 用户被 ImportError 绑架——P-100 D-2）。原「并入 server/mcp extras」方案否决。
- **fail-closed**：`registry.load()` 在应用启动路径最前调用；异常直接终止启动（A4-1 负向用例）。

## 3. MCP 动态注册与 `listChanged`（A4-10）

```python
# mcp/registry_adapter.py（M2）
def register_from_registry(server: MCPServer, registry: Registry) -> None:
    for tool in registry.tools:
        handler = tool.resolve()
        @server.tool(name=tool.name, description=tool.description)
        async def _wrapped(**kwargs) -> CallToolResult:  # noqa: ANN003
            return await invoke(tool.name, kwargs)
    # 启动后一次性通知
    # reload() 时再次 send_tool_list_changed()
```

- `inputSchema` 由 SDK 从函数签名生成 vs **注册表为准**：SDK 2.x 的 decorator 不支持传入外部 schema 时，M2 采用「注册表 schema 为真值源 + 测试断言 SDK `list_tools()` 返回与注册表一致」；若不一致以注册表为准并在 CI 断言（A4-10 的「一致」含义）。
- `listChanged`：**M2 落地验证结论（P-103 复核 X-11 实测）**：`MCPServer` 无 `connection`/运行期 session 属性；`session_manager` 懒加载、未调用 `streamable_http_app()` 前访问即抛 `RuntimeError`——stdio 单连接下真通知不可达。M2 交付 notifier 接缝（reload → 重新注册 → `notifier()`，fake 可测）并显式登记阻塞点；真 `send_tool_list_changed()` 留 HTTP/多 session 批次。
- **新增工具无需改代码**：在 `tools/registry.yaml` 追加条目 + handler 可导入即生效（M2 用例：临时注册表加一个工具，`list_tools()` 出现、无需改 `server.py`）。

### 3.1 REST `GET /api/tools`（M2）

- `researchclaw/server/routes/tools.py`：返回 `{version, tools: [{name, version, description, inputSchema, outputSchema, scope, risk, approval}]}`（**不暴露** `handler`/`sandbox_profile` 内部细节）。
- 与 MCP 同源 `registry.load()`，启动期校验失败则应用启动失败。

## 4. 工具事件（A4-4，M3）

**事件形态**（`runtime/event_log.py` 已有类型，只补生产者）：

| 字段 | `tool.call` | `tool.result` |
|---|---|---|
| `tool` | 工具名 | 工具名 |
| `call_id` | `uuid4` | 与 call 相同 |
| `risk` | 注册表值 | 同 |
| `args_digest` | 参数 JCS 的 SHA-256 | — |
| `args_summary` | ≤200 字符摘要 | — |
| `exit_code` | — | 进程/工具退出码（137 可辨） |
| `result_digest` | — | 结果 JCS 的 SHA-256 |
| `result_summary` | — | ≤200 字符 |
| `duration_ms` | — | 毫秒 |

- **只落 digest + 摘要**（总纲 L458），不落原始参数/结果。
- **`orphan_call`**：run 收尾（`pipeline.summary` 前）扫描 `events.jsonl`，对 `tool.call` 无同 `call_id` 的 `tool.result` 者追加 `{"type":"tool.orphan_call","call_id":...,"tool":...}`；A4-4 负向用例：人为删 result → 必须出现该标记。

## 5. 审批门（A4-5，M3）

- 判定：`approval=always` 或（`approval=high_only` 且 `risk=high`）→ 执行前写 `approval.required` 事件（**若注入事件 sink；无 sink 仍拒绝**——P-104 F-4）并**拒绝**，返回 `{success:false, error_code:"E_APPROVAL_REQUIRED"}`。
- 审批放行来源 v1：run 目录 `approvals.json`（`{tool: {approved: true, by, ts}}`）；无文件即未审批（fail-closed）。
- 负向用例：`risk=high` + 无 approvals → 断言**未**产生 `tool.result`、handler 未执行（副作用探针）。

## 6. 沙箱 profile（A4-2/A4-3/A4-6，M4）

| 项 | 冻结语义 |
|---|---|
| 标签 | `docker run --label rc.run=<run_id> --label rc.tool=<tool>` |
| 网络 | `network: none` → `--network none`；`setup_only` → 阶段 2 前 iptables 关闭（沿用既有实现） |
| 配额 | `--cpus --memory --pids-limit`（disk 仅记录，overlay2 配额不在 v1） |
| 超限语义 | OOM/被 kill（退出码 137）→ `tool.result.exit_code=137` 且 `reason=resource_limit`（A4-3） |
| TTL | 看护线程每 30s 扫描 `rc.run` 标签容器，`started_at + ttl_sec < now` → `docker kill` + 回收；**产物先落盘再 kill**（A4-6） |
| 四类逃逸测试 | 路径逃逸（`../`）、符号链接逃逸（`ln -s /`）、网络外联（`curl` 必失败）、fork bomb（`--pids-limit` 生效） |

## 7. env allowlist 与 safe_join 覆盖（A4-7/A4-8，M5）

- **清单法**：新增守卫测试（`tests/test_boundary_coverage.py`）用 AST 扫描 `researchclaw/**`：
  - 所有 `subprocess.*(env=...)` 的 `env` 必须来自 `build_subprocess_env` 或显式白名单常量；
  - 所有「基础目录 / 用户可控文件名」的拼接必须经 `safe_join`（白名单豁免清单显式登记，默认空）。
- 守卫测试必须在缺一处时变红（先以现有 3/2 文件的已知缺口跑红，再逐点修复至绿）。

## 8. HostProfile（A4-9，M5）

```python
@dataclass(frozen=True)
class HostProfile:
    cpu_count: int
    memory_total_mb: int
    disk_free_gb: float
    gpu_devices: tuple[str, ...]     # nvidia-smi -L 的解析结果（失败 → 空）
    toolchains: dict[str, str]       # python/docker/git 版本（固定白名单命令）
    def as_dict(self) -> dict[str, Any]: ...
```

- 只读数据；**禁止**返回可执行脚本/命令字符串；`subprocess` 调用仅限固定白名单且 `shell=False`。
- A4-9 负向用例：AST 扫描 `researchclaw/**` 无 `shell=True`；`HostProfile.as_dict()` 值全为标量/列表，无可调用对象。

## 9. 批次拆分与验收映射

| 批次 | 编号 | 交付 | 验收 | 主要文件 |
|---|---|---|---|---|
| M0 | **P-099** | 设计冻结（已完成；P-100 复核 2 P2 + 5 P3） | DC + 门禁 | 本 feature 四文档 |
| M1 | **P-101**（原 P-100，P-100 让位于复核批） | 注册表 + 启动校验（已完成；P-102 复核 1 P2 + 2 P3 → **M2 批内先修 D-1/D-2/D-3，已随 P-103 落地**） | **A4-1** | `tools/registry.yaml`、`researchclaw/tools/registry.py`、`tests/test_tool_registry.py` |
| M2 | **P-103**（原 P-102） | MCP 动态注册 + listChanged + `GET /api/tools`（**已完成**；复核并入批（DeepSeek，不占号）发现 D-1 P1/D-2·D-3 P2，批内收敛关闭——force-include 删除、None 可选参清洗、handler→`dispatch_tool` + 拒类校验） | **A4-10** | `researchclaw/mcp/registry_adapter.py`、`server/routes/tools.py`、`tests/test_mcp_dynamic_tools.py` |
| M3 | **P-104**（原 P-103） | tool 事件 + orphan_call + 审批门（**已完成**；复核并入批（GLM，不占号）发现 2 P2——`handle_tool_call` 直调绕过审批门、非 JSON 结果 digest 逃逸——批内收敛关闭，单执行路径） | **A4-4/A4-5** | `researchclaw/tools/invoker.py`、`runtime/event_log.py` 接线、`tests/test_tool_events.py` |
| M4 | **P-105**（原 P-104） | 沙箱配额/TTL/137 + 四类逃逸 | **A4-2/A4-3/A4-6** | `experiment/docker_sandbox.py`、`tests/test_sandbox_boundary.py` |
| M5 | **P-106**（原 P-105） | env/safe_join 全覆盖 + HostProfile | **A4-7/A4-8/A4-9** | `utils/`、`researchclaw/runtime/host_profile.py`、`tests/test_boundary_coverage.py` |

**编号顺延依据**：P-100 复核批、P-102 复核批先后让位（P-084/P-086 先例），M2..M5 = **P-103..P-106**。**D-3 修正输入（M4）**：137 仅 memory/pids（cpus 是 throttling）；**D-4 修正输入（M4）**：TTL kill 产物未必落盘（`reason=ttl_timeout`）；**D-5 已定案（P-103 落地）**：路径 B 注入 + deep equality 守卫；**D-6 修正输入（M5）**：AST 守卫改注册制白名单 + 兜底扫描。

**依赖顺序**：M1 → M2（注册表先行）；M3 可与 M2 并行（只依赖 M1）；M4 独立；M5 最后（覆盖扫描需要 M1-M4 的落点）。

## 10. 不变式

- I-1 注册表是工具元数据**唯一真值源**；adapter 不硬编码。
- I-2 启动校验 fail-closed：任何非法条目 → 进程不启动（不做「跳过坏条目」）。
- I-3 事件只落 digest/摘要，不落原始参数与结果。
- I-4 既有 6 个 MCP 工具的名称与参数**不变**（注册表迁移是等价搬迁，`list_tools()` 输出逐字段相等）。
- I-5 **M3 裁决（P-104）：新增 `tool.orphan_call` 顶层事件类型**（A4-4 的独立控制记录，不复用/改写 `tool.result`）；其余顶层类型不新增。
- I-6 沙箱默认 `network: none` 的现有行为不回退。
- I-7 `safe_join`/env 守卫为**新增门禁**，须登记在 CHECKLIST 且先红后绿。

## 11. 非目标

- 不引入 E2B/Daytona/Firecracker（v1 用 Docker 单档）。
- 不做 disk 配额强制（仅记录）。
- 不改既有 6 工具的业务行为。
- 不做多 run 并发沙箱编排（G7）。

## 12. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | 注册表为单一真值源 | 总纲 L455 | 拒绝在 adapter 内硬编码（A4-10 直接违反） |
| D-2 | 启动期全量校验、fail-closed | A4-1 负向用例 | 拒绝「跳过坏条目」（掩盖错误） |
| D-3 | 事件只落 digest+摘要 | 总纲 L458 | 拒绝落原始参数（泄漏面） |
| D-4 | Docker 单档 + 配额/TTL | RESEARCH Q-4；工期可控 | 拒绝多后端（M0 超期且无验收要求） |
| D-5 | 守卫用 AST 扫描而非人工清单 | A4-7/A4-8「全部」语义 | 拒绝人工核对（不可复现） |
| D-6 | `jsonschema` 并入 server/mcp extras | RESEARCH Q-1 | 拒绝进核心依赖（非 MCP 用户无收益） |

---
