---
id: arc-g4-m0-design-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m0-design-DESIGN]
upstream: arc-g4-m0-design-DESIGN
---

# 实施记录：G4 M0 设计冻结（P-099）

> **状态**：设计冻结完成；本批**零生产代码/零测试/零 schema 文件**。施工从 M1（P-100）开始，按 DESIGN §9 顺序推进。
> **依据**：[DESIGN.md](DESIGN.md) §1-§8（契约）、§9（批次）、§10（不变式）。

## 1. 冻结的接口

| # | 接口 | 冻结内容 |
|---|---|---|
| 1 | `tools/registry.yaml` | `version/tools[]/sandbox_profiles` 三段；7 字段/工具；7 条校验规则与 7 个错误码 |
| 2 | `researchclaw/tools/registry.py` | `Registry.load(path) -> Registry`、`Registry.reload()`、`resolve_handler()`；失败即抛（fail-closed） |
| 3 | `mcp/registry_adapter.py` | `register_from_registry(server, registry)`；reload 后 `send_tool_list_changed()` |
| 4 | `server/routes/tools.py` | `GET /api/tools` 返回 `{version, tools[]}`（不暴露 handler/profile） |
| 5 | `tools/invoker.py` | `invoke(tool, args)`：审批门 → 沙箱 → 事件（call/result）三段式 |
| 6 | tool 事件 schema | `tool.call`/`tool.result` 字段表（digest+摘要）；`orphan_call` 扫描时点 = `pipeline.summary` 前 |
| 7 | 沙箱 profile | label/network/quota/TTL/137 五要素；四类逃逸测试口径 |
| 8 | `HostProfile` | 6 字段 frozen dataclass；纯数据；固定白名单命令 |

## 2. 关键决策落点

| 决策 | 落点 |
|---|---|
| Q-1 schema 依赖 | `jsonschema>=4.20` 并入 `server`/`mcp` extras（DESIGN §2） |
| Q-2 注册表位置 | `tools/registry.yaml`（总纲 L455 指定） |
| Q-3 动态注册触发 | 启动装载 + reload（mtime）→ listChanged（DESIGN §3） |
| Q-4 沙箱 v1 档位 | Docker + `--network none` + cpu/mem/pids + TTL 看护 |
| Q-5 orphan 判定 | run 收尾扫描（DESIGN §4） |
| Q-6 HostProfile 依赖 | 纯 stdlib |

## 3. 施工顺序（M1..M5）

| 批次 | 交付 | 验收 | 关键测试 |
|---|---|---|---|
| M1 P-100 | 注册表 + 启动校验 | A4-1 | 合法装载；缺 `inputSchema` 启动失败；非法 enum/handler/profile 各一例 |
| M2 P-101 | 动态注册 + listChanged + REST | A4-10 | 新增注册表条目即出现在 `list_tools()`；reload 发出通知；`GET /api/tools` 字段白名单 |
| M3 P-102 | 事件 + orphan + 审批 | A4-4/A4-5 | call/result 配对；删 result → `orphan_call`；high risk 拒绝且无副作用 |
| M4 P-103 | 沙箱配额/TTL/137/逃逸 | A4-2/A4-3/A4-6 | 四类逃逸全拒；OOM → 137 + tool.result；TTL 回收且产物落盘 |
| M5 P-104 | env/safe_join/HostProfile | A4-7/A4-8/A4-9 | AST 守卫先红后绿；`HostProfile` 纯数据；无 `shell=True` |

## 4. 测试计划（施工批落地）

- 注册表：7 条校验规则的正/负用例各 ≥1；schema 版本非法；重名工具。
- MCP：与注册表 `list_tools()` 逐字段相等（I-4 等价搬迁）；`listChanged` 通知可观测。
- 事件：`args_digest` 与参数 JCS 一致；`result_summary` 截断；orphan 扫描幂等。
- 沙箱：路径/符号链接/网络/fork bomb 四类；137 映射；TTL kill 后产物存在。
- 覆盖守卫：AST 扫描当前 3/2 文件缺口先红，修复后绿；豁免清单为空。

具体用例数与文件在对应批次登记，不在 M0 预估。

## 5. 验证（本批）

| # | 检查 | 结果 |
|---|---|---|
| V-1 | DC 契约（四文档 front-matter/链接/type/status） | ✅ Passed（DC1-DC5 + R7；1 处相对链接 `../arc-master-roadmap.md` → `../../` 修正后 0 违规） |
| V-2 | step-gate 5/5（P-099 session） | ✅ exit 0 |
| V-3 | step-enforce（feature 绑定 + digest） | ✅ `digest_bound=1`（双 feature 五文档：M0 四文档 + P-093 RESEARCH） |
| V-4 | pre-commit 9 钩子 | ✅ 全绿（DC / repo_stats / step-enforce / console / 私网守卫 / blackbox） |
| V-5 | 生产代码/测试/schema 文件变更数 | ✅ **0**（T1 设计冻结；`git status` 仅 4 新文档 + PROGRESS/roadmap/派生视图/session） |

## 6. 未纳入本批

- 任何生产代码、`tools/registry.yaml` 实体文件、迁移脚本。
- M1..M5 的测试与读数。
- 多后端沙箱、disk 配额强制、G7 并发编排。

---
