---
id: arc-ci-dispatch-group-isolation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-16
depends: [arc-ci-dispatch-group-isolation-IMPLEMENTATION, arc-ci-dispatch-group-isolation-DESIGN]
upstream: null
---

# 审查验收 Checklist：dispatch × push 组键隔离（P-131）

> **Feature**：P-131。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：提交前可完成的项以静态断言与只读远端读数兑现；跨事件隔离与同事件取消的**行为读数**需合并后制造 push 事件，列 §11 观察，不作为验收前置。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的决策可追溯到 RESEARCH | ✅ | DESIGN §2 六条决策逐条指向 RESEARCH §4/§5 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | DESIGN §4 目标形态 ↔ IMPLEMENTATION §2 前后对照，逐行一致 |
| IMPLEMENTATION 的功能点在本 checklist 有验收项 | ✅ | IMPL §3/§4/§5/§6 ↔ §2 / §4 / §5 |
| 术语一致（K 编号 / 组名 / 事件名） | ✅ | 「K-1..K-6」「push / workflow_dispatch / pull_request」四文档逐字一致 |

## 2. 功能验收

### 2.1 工作流形态

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| YAML 可解析 | `yaml.safe_load` | 解析成功 | ✅ | IMPL §3 第 1 行 |
| 触发器集合未变 | 断言 `on` 键集合 | `{push, pull_request, workflow_dispatch}` | ✅ | IMPL §3 第 2 行 |
| `push` 仍限 main | 断言 `on.push.branches` | `["main"]` | ✅ | IMPL §3 第 3 行 |
| 组键含事件维 | 断言 `concurrency.group` | 逐字等于目标表达式 | ✅ | IMPL §3 第 4 行 |
| 取消语义保留 | 断言 `cancel-in-progress` | `True` | ✅ | IMPL §3 第 5 行 |

### 2.2 结构与范围

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| job 结构未变 | 断言 job 条目与 5 个 `name:` | 5 条且逐字一致 | ✅ | IMPL §3 第 6 行 |
| 矩阵未变 | 断言 `matrix` | 3.11-3.13 必需 + 3.14 experimental | ✅ | IMPL §3 第 7 行 |
| 范围卫生 | `git diff --stat` | 仅 `ci.yml`；`heavy.yml` diff = 0 | ✅ | IMPL §1、§3 末行 |

## 3. 接口验收

本批不新增或修改任何公共接口（无 `researchclaw/` 代码、无 CLI/HTTP/事件面变更），故无接口验收项。

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| K-1 三类组名不同 | 静态表达式分析 | push / dispatch / PR 三段两两不同 | ✅ | RESEARCH §4.1；行为读数见 §11 |
| K-2 push→push 取消 | 字符串恒等 + 历史基线 | 同 event 同 ref 逐字相同 | ✅ | RESEARCH §4.2；P-124 行 |
| K-3 PR→PR 取消 | 字符串恒等 | 同 event 同 PR ref 逐字相同 | ✅ | RESEARCH §4.2 |
| K-4 main push 1 run | 触发器与白名单未动 | 静态成立；合并后计数见 §11 | ✅ | IMPL §3 |
| K-5 7 检查名不变 | 只读 `protection.contexts` | 7 名逐字一致 | ✅ | IMPL §4 E1-1 |
| K-6 范围卫生 | `git diff --stat` | 仅 `ci.yml` 3 行 | ✅ | IMPL §1 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| YAML 结构损坏 | 本机 `yaml.safe_load` | 解析失败即报错（本批解析 OK） | ✅ | IMPL §3 |
| 组键表达式笔误 | 逐字断言完整表达式 | 断言通过 | ✅ | IMPL §3 第 4 行 |

## 6. 性能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| run 数与时延路径不变 | 表达式求值 + 触发器未变 | 单 push 仍 1 run；无新增 job | ✅ | IMPL §3；P-127 基线 544 s/run |

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 7 必需检查名不变 | 只读 `contexts` + job 名断言 | 7 名逐字一致 | ✅ | IMPL §4 E1-1 |
| `heavy.yml` 不受影响 | `git diff --exit-code` | exit 0；其组键本就含事件维 | ✅ | IMPL §3 末行 |

## 8. ADD 审计

本批为 CI 配置一行变更，无 ADD（架构决策记录）新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 组键加事件维后，跨事件组名两两不同；同事件组名逐字不变，取消语义不受误伤 |
| 可逆性 | 删除 `-${{ github.event_name }}` 一段即完全回退 |
| 风险 | 行为读数需合并后制造 push 事件；探针会额外产生 2 个 dispatch run（可手动取消） |
| 卫生 | 1 文件 +2/−1；`heavy.yml`、`tests/`、`researchclaw/`、分支保护零改动 |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 6 | 6 | 0 | 0 |
| 接口 | 0 | 0 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **21** | **21** | **0** | **0** |

算术自洽：21 = 4+6+0+6+2+1+2+0；通过 21 = 总数 21。

### 10.2 验收结论

- [x] 验收通过：21/21 全通过；静态断言与只读远端读数均有一手证据，行为读数明确列为 §11 观察项，无回填冒充。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 本批 PR 合并 | 待执行 | 合并产生 push run `P` 后立即执行行为探针 |
| 合并后行为探针 | 待执行 | ① 触发 `D1`（dispatch）：`P` 应保持 `in_progress` 并最终 `success`；② 立即触发 `D2`：`D1` 应 `cancelled`；取得读数后手动取消 `D2` |
| U-1 组名无 API 直读 | 观察 | 静态表达式 + 合并后行为双证据；官方新增字段时补直读 |
| U-3 未来加 schedule | 观察 | 组键已含事件维，天然隔离 |
| U-4 探针 run 成本 | 执行时处置 | 取得取消读数后 `gh run cancel` 掉 `D2` |
