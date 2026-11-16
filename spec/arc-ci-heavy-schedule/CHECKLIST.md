---
id: arc-ci-heavy-schedule-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-16
depends: [arc-ci-heavy-schedule-IMPLEMENTATION, arc-ci-heavy-schedule-DESIGN]
upstream: null
---

# 审查验收 Checklist：定时重型执行路径（P-129）

> **Feature**：P-129。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：提交前可完成的项均以本机机械断言与只读远端读数兑现；首次 schedule run、合并后 main push 与 Heavy dispatch 的并发行为列 §11 观察，不作为验收前置。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的决策可追溯到 RESEARCH | ✅ | DESIGN §2 七条决策逐条指向 RESEARCH §3.1/§3.2/§5.1/§5.2/§5.3/§5.4 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | DESIGN §4 目标形态 ↔ IMPLEMENTATION §2 最终形态，逐行一致 |
| IMPLEMENTATION 的功能点在本 checklist 有验收项 | ✅ | IMPL §3/§4/§5/§6 ↔ §2.1-§2.3 / §4 / §5 |
| 术语一致（J 编号 / 触发器名 / 文件路径） | ✅ | 「J-1..J-7」「schedule / workflow_dispatch」「heavy.yml」四文档逐字一致 |

## 2. 功能验收

### 2.1 工作流形态

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| YAML 可解析 | `yaml.safe_load` | 解析成功 | ✅ | IMPL §3 第 1 行 |
| 触发器集合 | 断言 `on` 键集合 | `{schedule, workflow_dispatch}` | ✅ | IMPL §3 第 2 行 |
| cron 取值 | 断言 `schedule[0].cron` | `17 18 * * 1` | ✅ | IMPL §3 第 3 行 |
| 组键四段 | 断言 `concurrency.group` | 含 `heavy-` / `workflow` / `event_name` / `ref` | ✅ | IMPL §3 第 4 行 |
| 取消语义 | 断言 `cancel-in-progress` | `False` | ✅ | IMPL §3 第 5 行 |
| 无 `queue` 键 | 断言 `"queue" not in concurrency` | 不存在 | ✅ | IMPL §3 第 6 行 |

### 2.2 job 与步骤

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 步骤链齐全 | 读取 `jobs.heavy.steps` | checkout / 回显 / setup-python / install / pytest 五段齐全 | ✅ | IMPL §2 |
| 超时 | 断言 `timeout-minutes` | 60 | ✅ | IMPL §3 第 7 行 |

### 2.3 J-1 证据步骤

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 组键回显 | 断言步骤 `run` 含 `concurrency_key=heavy-` | 存在且含三个上下文 | ✅ | IMPL §3 第 8 行 |

## 3. 接口验收

本批不新增或修改任何公共接口（无 `researchclaw/` 代码、无 CLI/HTTP/事件面变更），故无接口验收项。

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 不同组 | 静态断言 + 回显步骤存在 | 组键与 `ci-CI-...` 不同串 | ✅ | IMPL §3；合并后行为读数见 §11 |
| J-2 main push 不被误杀 | `ci.yml` 零变更 + 组键不同 | `git diff` 为空 | ✅ | IMPL §8 |
| J-3 同事件取消不变 | 断言 `ci.yml` 的 `cancel-in-progress: true` | 原值 | ✅ | IMPL §3 末行 |
| J-4 7 检查名不变 | 只读 `protection.contexts` | 7 名逐字一致 | ✅ | RESEARCH §4 E1-5 |
| J-5 `ci.yml` 零变更 | `git diff --exit-code` | exit 0 | ✅ | IMPL §3 |
| J-6 只跑 heavy | 收集与本机运行 | `2 passed / 3778 deselected` | ✅ | IMPL §4 E1-1/E1-2 |
| J-7 停摆可观测 | 检查 `workflow_dispatch` 入口 | 存在；U-4 已登记 | ✅ | DESIGN §2 D-1；RESEARCH §8 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| YAML 结构损坏 | 本机 `yaml.safe_load` | 解析失败即报错（本批解析 OK） | ✅ | IMPL §3 |
| schedule 延迟 / 排队丢弃 | 检查 cron 分钟位与频率 | 分钟位非 0；周级；`workflow_dispatch` 补跑 | ✅ | RESEARCH §3.1、§5.1 |

## 6. 性能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| heavy 套件耗时 | 本机 `pytest -m heavy` 计时 | 4.28 s（2 例）；周级运行不与 PR 路径竞争 | ✅ | IMPL §4 E1-2 |

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `ci.yml` 零变更 | `git diff --exit-code` + 语义断言 | exit 0 且断言全过 | ✅ | IMPL §3 |
| 分支保护不变 | 只读 `contexts` 比对 | 7 名逐字一致，heavy 不在集 | ✅ | RESEARCH §4 E1-5 |

## 8. ADD 审计

本批为 CI 配置新增，无 ADD（架构决策记录）新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 组键在构造上与 `ci.yml` 不同串；`cancel-in-progress: false` 保证定时观测不被新 run 顶掉 |
| 可逆性 | 删除 `heavy.yml` 即完全回退 |
| 风险 | 已知 flaky 用例会周期性红灯（非必需检查）；schedule 延迟/丢弃已登记 U-2/U-4 |
| 卫生 | 新增 1 文件；`ci.yml`、`tests/`、`researchclaw/`、分支保护零改动 |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 8 | 8 | 0 | 0 |
| 接口 | 0 | 0 | 0 | 0 |
| 不变式 | 7 | 7 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **24** | **24** | **0** | **0** |

算术自洽：24 = 4+8+0+7+2+1+2+0；通过 24 = 总数 24。

### 10.2 验收结论

- [x] 验收通过：24/24 全通过；提交前机械断言与只读远端读数均有一手证据，无待回填项；status 按 CHECKLIST 词表置 `accepted`。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 本批 PR 合并 | 已完成 | PR #11 squash 合并为 `e0c9ebb`（2026-11-16）；远端 `spec/p129-ci-heavy-schedule` 已删除，本地 `main` 已同步 |
| 合并后并发观察 | ✅ 已兑现 | 同 sha `e0c9ebb` 两 run 并发：CI push `43788354421`（8/8 job success）、Heavy dispatch `43788370830`（success；日志 `concurrency_key=heavy-Heavy-workflow_dispatch-refs/heads/main`，`2 passed / 3778 deselected in 7.32s`）；CI 在 Heavy 运行期间保持 `in_progress` 并最终 success ⇒ J-1/J-2 行为读数成立 |
| 首次 schedule run | 待观察 | 下周一 17:18 UTC 后核对 `event=schedule` 与 `concurrency_key=heavy-Heavy-schedule-refs/heads/main`（U-2） |
| 回填机制 | 记录 | 按 P-126 先例新建 P-130 五步 session 绑定新文档态；P-129 session 一行未动 |
| U-1 组名无 API 直读 | 观察 | 现以静态 + 回显 + 行为三重证据替代；官方新增字段时补直读 |
| U-2 首次 schedule 延迟 | 观察 | 官方明示整点高负载会延迟/丢弃；本批已避开整点并登记 |
| U-3 heavy 根因专项 | 遗留 | F-1/F-2 的时序竞争未修，周级红灯属已知噪声 |
| U-4 60 天自动禁用 | 观察 | 低活动期用 `workflow_dispatch` 补跑 |
| P-131 接口 | 未立项 | `ci.yml` 组键补 `event_name`，修 dispatch 撞 push |
