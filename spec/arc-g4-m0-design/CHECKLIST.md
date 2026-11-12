---
id: arc-g4-m0-design-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-14
depends: [arc-g4-m0-design-IMPLEMENTATION]
upstream: arc-g4-m0-design-IMPLEMENTATION
---

# 检查清单：G4 M0 设计冻结（P-099）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 缺口在 DESIGN 被使用（G-1..G-9 → §2-§9） | ✅ | §9 批次表逐项挂缺口 |
| DC-2 | DESIGN 接口在 IMPLEMENTATION 有冻结记录 | ✅ | IMPL §1 八接口 ↔ DESIGN §2-§8 |
| DC-3 | IMPLEMENTATION 施工项在 CHECKLIST 有验收项 | ✅ | §2 A4 映射 + §3 批次门禁 |
| DC-4 | 无文档间矛盾（错误码、字段名、批次编号） | ✅ | 四文档 grep `E_REGISTRY_`/`call_id`/`A4-` 一致 |
| DC-5 | 术语一致（registry / invoker / orphan_call / sandbox_profile） | ✅ | 四文档互查 |
| DC-6 | A4-1..A4-10 每项有唯一归属批次 | ✅ | §2 映射表无空缺、无重复 |

## 2. 验收映射（总纲 A4-1..A4-10）

| A4 | 断言 | 批次 | 可失败测试（施工批落地） | 状态 |
|---|---|---|---|---|
| A4-1 | 100% 工具有 schema；缺则启动失败 | M1 | 缺 `inputSchema` → `RegistryError` 且不启动 | 待施工 |
| A4-2 | 四类逃逸全拒 | M4 | 路径/符号链接/网络/fork bomb | 待施工 |
| A4-3 | 超限 → 137 + `tool.result` | M4 | OOM 用例断言 `exit_code=137` 且事件在位 | 待施工 |
| A4-4 | call/result 配对；缺失标 orphan | M3 | 删 result → `orphan_call` 标记 | 待施工 |
| A4-5 | `risk=high` 未审批拒绝 | M3 | 断言 handler 未执行（副作用探针） | 待施工 |
| A4-6 | TTL 回收且产物落盘 | M4 | 挂起容器超 TTL → 被 kill；产物存在 | 待施工 |
| A4-7 | 全部后端 env allowlist | M5 | AST 守卫 + 现有 3 文件缺口先红 | 待施工 |
| A4-8 | 全部写入点 safe_join | M5 | AST 守卫 + 现有 2 文件缺口先红 | 待施工 |
| A4-9 | HostProfile 纯数据；无脚本入口 | M5 | AST 无 `shell=True`；返回值全标量 | 待施工 |
| A4-10 | 注册表与 listChanged 一致；新增工具不改代码 | M2 | 动态追加条目 → `list_tools()` 出现 + 通知 | 待施工 |

## 3. 批次门禁（每批必须）

| # | 检查 | 通过条件 |
|---|---|---|
| B-1 | 四文档 | 本 feature（M0）已冻结；施工批各自 feature 四文档齐全 |
| B-2 | 先红后绿 | 新增测试先跑红（记录失败形态），再实现转绿 |
| B-3 | 双环境 | 3.13.5 + 3.11.15 同读数 |
| B-4 | 回归 | M1-M5 既有套件零失败 |
| B-5 | 门禁链 | DC / step-gate 5/5 / step-enforce digest / pre-commit 9 钩子 |
| B-6 | 登记 | PROGRESS 行（T1）+ 总纲修订 + session 5 步 |

## 4. 不变式（DESIGN §10）

| # | 不变式 | 验证方式 |
|---|---|---|
| INV-1 | 注册表唯一真值源 | 读码：adapter 无工具字面量 |
| INV-2 | 启动校验 fail-closed | M1 负向用例 |
| INV-3 | 事件只落 digest/摘要 | M3 断言事件字段集 |
| INV-4 | 既有 6 工具名/参数不变 | M2 `list_tools()` 与迁移前快照逐字段相等 |
| INV-5 | 不新增顶层事件类型（orphan 以字段表达） | M3 裁决并在该批记录 |
| INV-6 | 沙箱默认 `network: none` 不回退 | M4 读码 + 用例 |
| INV-7 | 覆盖守卫是新增门禁，先红后绿 | M5 门禁登记 + 红态记录 |

## 5. 本批验证（P-099）

| # | 检查 | 结果 |
|---|---|---|
| V-1 | DC 契约校验（DC1-DC5 + R7） | ✅ Passed |
| V-2 | step-gate 5/5 | ✅ exit 0 |
| V-3 | step-enforce（feature 绑定 + digest） | ✅ `digest_bound=1`（双 feature 五文档） |
| V-4 | pre-commit 9 钩子 | ✅ 全绿 |
| V-5 | 生产代码/测试/schema 变更 = 0 | ✅ 0（设计冻结） |

## 6. 遗留与待裁决

| # | 项 | 处置 |
|---|---|---|
| Q-1 | `jsonschema` 并入 server/mcp extras | M1 实施时落 pyproject 变更（影响依赖面，M1 批内声明） |
| Q-3 | reload 触发方式（mtime vs 显式信号） | M2 裁决 |
| Q-5 | `orphan_call` 事件形态（新增类型 vs 字段） | M3 裁决（INV-5 默认字段） |
| U-1 | 外部沙箱产品对比（E2B/Daytona/Firecracker） | T3 未回原文；v1 不引入 |
| U-2 | disk 配额强制 | 非目标，登记 |
| U-3 | 完成 M1..M5 后做 RULE-5 独立复核（建议异构基座交替） | 待用户裁决 |

---
