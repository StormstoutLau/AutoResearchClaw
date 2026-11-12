---
id: arc-g4-m2-dynamic-tools-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-14
depends: [arc-g4-m2-dynamic-tools-IMPLEMENTATION]
upstream: arc-g4-m2-dynamic-tools-IMPLEMENTATION
---

# 检查清单：G4-M2 动态注册 + listChanged + `GET /api/tools`（P-103）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH spike 结论在 DESIGN 被使用（路径 B→§3.1、listChanged→§3.2） | ✅ | DESIGN §6 挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | §1 十二项 ↔ DESIGN §1-§5 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | §2 修复 + §3 A4-10 |
| DC-4 | P-102 D-1/D-2/D-3 全部收敛（T-R1..R4） | ✅ | 修复用例实证 |
| DC-5 | 术语一致（adapter / 注入 / unfreeze / notifier 接缝） | ✅ | |

## 2. 前置修复验收（P-102 D-1/D-2/D-3）

| # | 项 | 用例 | 状态 |
|---|---|---|---|
| D-1 关闭 | 包内资源 + wheel 分发 | T-R1（双副本一致）+ CI packaging 冒烟 | ✅ |
| D-2 关闭 | 嵌套只读 | T-R3（写入抛 TypeError） | ✅ |
| D-3 关闭 | 错误码分离 | T-R4 三组（UNREADABLE/PARSE/VERSION） | ✅ |

## 3. A4-10 验收

| # | 验收项 | 用例 | 状态 |
|---|---|---|---|
| 一致（前半） | `list_tools()` inputSchema 与注册表 deep equality | T-2（unfreeze roundtrip） | ✅ |
| 新增不改代码（后半） | 追加注册表条目 → 新工具出现 | T-3（refresh 流程） | ✅ |
| listChanged 接缝 | reload → notifier 调用 1 次 | T-5；**真 session 通知登记阻塞** | ✅（接缝）/登记 |
| 零硬编码 | adapter 无工具名字面量 | T-4 扫描 | ✅ |
| dispatcher 接线 | 名称与参数透传 | T-dispatcher | ✅ |

## 4. REST 与 fail-closed

| # | 项 | 用例 | 状态 |
|---|---|---|---|
| REST 白名单 | `GET /api/tools` 无内部字段 | T-6 | ✅ |
| 启动 fail-closed | 坏注册表 → 启动/请求失败 | T-7（`RegistryError` 冒出） | ✅ |
| strict handler | 不可解析 → 启动失败 | T-8 | ✅ |
| 零回退 | MCP 42 项 | test_mcp×2 套件 | ✅ |

## 5. 回归与门禁

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 四套件（registry 25 + dynamic 12 + MCP 42） | 79 passed |
| R-2 | 3.11.15 含 extras | 79 passed；无 extras（registry 单套件）24 passed / 1 skipped（既有 importorskip） |
| R-3 | CI 固定清单 40 文件 | 604 passed / 13 skipped，**0 failed**（v1.0 自报「295/5」口径不可复现，D-5 订正） |
| R-4 | wheel 实构建三连（v1.1 D-1） | 构建成功 428 文件零重复；注册表在包内；临时 target 安装 `load_registry()` 成功 |
| R-5 | 门禁链（DC/step-enforce/pre-commit） | 已过（见提交） |

## 6. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | 真 session 的 listChanged 通知 | 阻塞点显式登记（复核 X-11 证实）；留 HTTP/多 session 批次 |
| U-2 | `tool.parameters` 直写依赖 SDK 内部对象 | `mcp>=2.1,<3` 锁版本 + T-2 deep equality 升级守卫 |
| U-3 | `mcp/tools.py` 双源 | M3/M4 迁移后删除 |
| U-4 | 显示 schema ≠ 运行时校验 schema（O-1） | M3 invoker 承担运行时校验；DESIGN §10 登记 |
| U-5 | M2 复核 | 已完成（DeepSeek，并入 P-103 不占号） |

## 7. 复核收敛验收（v1.1）

复核报告：[arc-g4-m2-review-20261114.md](../../docs/arc-g4-m2-review-20261114.md)（D-1 P1 + D-2/D-3 P2 + D-4/D-5 P3 + O-1..O-8）。

| # | 复核发现 | 收敛动作 | 验收 | 状态 |
|---|---|---|---|---|
| D-1 P1 | wheel 构建失败（force-include 同路径冲突 + 违反既有打包契约测试） | 删 `force-include`；CI required 加注册表 | R-4 三连 + `test_packaging.py` 复绿 | ✅ |
| D-2 P2 | 可选参数 None 注入（auto_approve True→False 静默翻转） | `_call` 清洗 None 可选参数 | +2 回归用例（adapter + real registry 最小参数） | ✅ |
| D-3 P2 | handler 指向类对象 | 6 条 handler → `dispatch_tool`；`resolve()` 拒绝类/不可调用 | 类 handler strict load 抛 `E_REGISTRY_HANDLER` | ✅ |
| D-4 P3 | DESIGN 三处漂移 | §3.1/§4/§5 原地回填 | DESIGN v1.1 | ✅ |
| D-5 P3 | 读数失准（dynamic 12→10、宽回归口径） | IMPLEMENTATION §3 订正 + CI 全清单复跑 | 本表 R-1..R-3 | ✅ |
| O-6 | `__registry_handler__` 死属性 | 删除 | 全仓无引用 | ✅ |
| O-1/O-3/O-4 等 | 显示/校验分离、remove_tool 吞错、重复注册覆盖 | 登记不收敛（M3 面） | U-4 + 复核报告 O 表 | 登记 |

---
