---
id: arc-ci-trigger-dedupe-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-16
depends: [arc-ci-trigger-dedupe-IMPLEMENTATION, arc-ci-trigger-dedupe-DESIGN]
upstream: null
---

# 审查验收 Checklist：CI 双触发去重（P-127）

> **Feature**：P-127。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：本批全部验收项均可在提交前完成——机械断言（本机 YAML 解析）+ 行为读数（探针分支 commit `992d268` 与草稿 PR #8 的真实 run `43748816610`）。凡标 ✅ 的项均附一手读数或文件行号，无回填窗口。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的决策可追溯到 RESEARCH | ✅ | DESIGN §2.1 五行映射：D-1←E1-5/§4A、D-2←§3、D-3←§4C、D-4←§4B、D-5←§7 U-1 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | DESIGN §3 声明「唯一文件、第 3-6 行」↔ IMPL §2 前后对照与 `git diff --stat`（1 文件 +1 行） |
| IMPLEMENTATION 的功能点在本 checklist 有验收项 | ✅ | IMPL §3/§4/§5 ↔ §2.1-§2.4 / §4 / §6，逐项对应 |
| 术语一致（事件名 / 检查名 / 不变式编号） | ✅ | 「pull_request / push / workflow_dispatch」与「I-1..I-6」四文档逐字一致 |

## 2. 功能验收

### 2.1 触发器收窄

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `push` 仅对 main 生效 | 本机 YAML 断言 `on.push == {branches: [main]}` | 断言通过 | ✅ | IMPL §3 第 1 行 |
| 其余触发器保留 | 断言 `pull_request`、`workflow_dispatch` 存在 | 均存在 | ✅ | IMPL §3 第 2 行 |

### 2.2 行为去重

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 分支 push 不产生 run | `gh api .../actions/runs?head_sha=992d268` | `total_count = 0` | ✅ | IMPL §4 E2-1 |
| 同 commit 开 PR 后仅 1 个 run | 同分支 `gh run list` | 1 条，`event=pull_request` | ✅ | IMPL §4 E2-2（`43748816610`） |

### 2.3 job 与检查名完整性

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 运行时 8 个 job 齐全 | `gh api .../runs/43748816610/jobs` | `total_count = 8` 且全 `success` | ✅ | IMPL §4 E2-3 |
| 7 个必需检查名逐字出现 | 比对 job `name` 与分支保护 contexts | 7 名全命中 | ✅ | IMPL §4 E2-4 |

### 2.4 并发语义未变

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `concurrency` 原值 | 断言 `group` 与 `cancel-in-progress` | 与改前逐字相同 | ✅ | IMPL §3 末行 |

## 3. 接口验收

本批不新增或修改任何公共接口（无 `researchclaw/` 代码、无 CLI/HTTP/事件面变更），故无接口验收项。

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| I-1 PR 单 run | 探针 PR #8 同 commit run 计数 | = 1 | ✅ | E2-2 |
| I-2 7 检查名不变 | job 列表比对 | 7 名全在 | ✅ | E2-4 |
| I-3 main 仍跑 | 读取 `on.push.branches` 白名单 | 含 `main` | ✅ | IMPL §2 |
| I-4 同 ref 取消前序 | `concurrency` 零改动 | 原值 | ✅ | IMPL §3 |
| I-5 触发器集合 | `on` 键集合 | `{push, pull_request, workflow_dispatch}` | ✅ | IMPL §3 |
| I-6 范围卫生 | `git diff --stat` | 仅 `.github/workflows/ci.yml` 1 文件 | ✅ | IMPL §1 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| YAML 结构损坏 | 本机 `yaml.safe_load` | 解析失败即报错（本批解析 OK） | ✅ | IMPL §3 |
| 首次推 main 的 `before=0` | 读 `ci.yml` L182-L185 既有分支 | 显式跳过 range 检查，未被本批破坏 | ✅ | DESIGN §6 R-1 |

## 6. 性能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 重复 run 消除 | 探针 8 job 时长求和 | 每 PR 提交减少约 9.1 分钟（544 s） | ✅ | IMPL §4 E2-5 |

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 草稿 PR 仍触发 | 探针 PR #8 为 draft | `pull_request` run 正常产生 | ✅ | E2-2 |
| fork PR 覆盖不减 | 语义推演 + 事件归属 | `push` 本就在 fork 仓，基线仓无该事件 | ✅ | RESEARCH §5、DESIGN §6 |

## 8. ADD 审计

本批为 CI 配置改动，无 ADD（架构决策记录）新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 去重由事件过滤器实现，不依赖竞态；7 个必需检查与 `BASE_SHA` 逻辑零改动 |
| 可逆性 | 删除 `branches: [main]` 一行即完全回退 |
| 风险 | 仅「无 PR 分支推送失去 CI 反馈」，已登记 U-1 并给出三重回退通道 |
| 卫生 | 1 文件 +1 行；无产品代码、无测试、无其他工作流 |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 4 | 4 | 0 | 0 |
| 接口 | 0 | 0 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **19** | **19** | **0** | **0** |

算术自洽：19 = 4+4+0+6+2+1+2+0；通过 19 = 总数 19。

### 10.2 验收结论

- [x] 验收通过：19/19 全通过；行为读数来自探针真实 run（`43748816610`），无待回填项；status 按 CHECKLIST 词表置 `accepted`。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 本批 PR 合并 | 待执行 | 合入后 main 产生 1 次 push run，用于 I-3 的合并后观察（非验收前置） |
| U-1 无 PR 分支无 CI | 观察 | 缓解：PR 必走；`workflow_dispatch` 手动补跑 |
| U-2 新增触发器重评 | 观察 | 出现 tag/release/schedule 时重评去重矩阵 |
