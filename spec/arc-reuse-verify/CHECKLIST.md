---
id: arc-reuse-verify-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-reuse-verify-IMPLEMENTATION, arc-reuse-verify-DESIGN]
upstream: null
---

# 审查验收 Checklist：账本查询 CLI 与复现性校验（P-147）

> **Feature**：P-147。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：1 新模块 + 2 既有文件最小接入 + 1 测试文件；`pipeline_manifest.py` 零改动。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 决策可追溯到 RESEARCH | ✅ | D-1..D-7 逐条指向 RESEARCH §2/§3/§4 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 两文档均为「1 新模块 + 2 接入 + 1 测试」 |
| IMPLEMENTATION 读数在 checklist 有验收项 | ✅ | 红→绿读数 ↔ §2/§10 |
| 术语一致（命令、字段、退出码） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 账本全量查询 | `query_actions` | 返回 1 条且字段齐全 | ✅ | `test_query_all` |
| tool/status/limit 过滤 | 参数组合 | 命中/空表正确 | ✅ | `test_filters` |
| 完整 run 判复现 | `verify_reproducibility` | `reproducible=true`、四组检查全过 | ✅ | `test_passes_on_intact_run` |
| 产物哈希篡改检出 | 改写 out.txt | `hash_mismatches` 指明 path/expected/actual | ✅ | `test_detects_hash_mismatch` |
| 产物缺失检出 | 删 out.txt | `missing_outputs` 含 rel 路径 | ✅ | `test_detects_missing_output` |
| 动作缺失检出 | 注入伪 action_id | `unresolved_actions` 含 id | ✅ | `test_detects_unresolved_action` |
| readpoint 校验 | summary 存在 | 通过（失败路径由实现覆盖） | ✅ | 集成用例 |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `actions` 命令 | CLI 调用 | exit 0、`--json` 机读、`--tool` 过滤空输出 | ✅ | `test_actions_cli_filters` |
| `pipeline-skill verify` 命令 | CLI 调用 | 0=REPRODUCIBLE / 1=DRIFT / 2=不可用 | ✅ | `test_verify_cli_*` |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 只读 | mtime 前后对照 | 无任何文件变化 | ✅ | `test_is_read_only` |
| J-2 篡改检出 | 改产物 | `reproducible=false` 且指明文件 | ✅ | hash_mismatch 用例 |
| J-3 动作缺失检出 | 伪 id | `unresolved_actions` | ✅ | `test_detects_unresolved_action` |
| J-4 链坏检出 | 篡改既有事件记录 | `chain_ok=false` | ✅ | `test_detects_broken_chain` |
| J-5 完整 run 通过 | 干净 run | `reproducible=true` | ✅ | intact 用例 |
| J-6 过滤与机读 | CLI | 过滤正确、JSON 可解析 | ✅ | actions CLI 用例 |
| J-7 空 manifest 假绿封堵 | 无 stages | `reproducible=false`、`checks=0` | ✅ | `test_empty_manifest_fails_closed` |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 技能目录缺失 | CLI | exit 2 + stderr | ✅ | `test_verify_cli_unusable_input` |
| run 目录缺失 | CLI | exit 2 + stderr | ✅ | 同上 |
| manifest 加载失败 | CLI（合成工具被真实注册表拒绝） | exit 2 + 原因 | ✅ | 同上 |

## 6. 性能验收

本批为一次性文件读取与哈希，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 既有模块回归 | 41 条相关用例 | 全绿 | ✅ | IMPL §2 |
| `--help` 黑盒 | pre-commit blackbox | Passed | ✅ | 门禁读数 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8 文档一致性）

- RESEARCH §4 方案 A ↔ DESIGN D-1/D-2 模块归属一致（评审中修正过一次归属）。
- DESIGN §4 校验语义 ↔ IMPLEMENTATION §3.2 逐条对应；空 manifest 封堵在两文档均有。
- CHECKLIST 用例名 ↔ `tests/test_reuse_verify.py` 实名核对，12 条全对得上。
- 测试修正诚实记录：三处初稿断言缺陷（撕裂尾语义、注册表严格性、checks 类型）在实现前修正，非实现迁就。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 2 | 2 | 0 | 0 |
| 不变式 | 7 | 7 | 0 | 0 |
| 错误处理 | 3 | 3 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **25** | **25** | **0** | **0** |

算术自洽：25 = 4+7+2+7+3+0+2+0；通过 25 = 总数 25。

### 10.2 验收结论

- [x] 验收通过：25/25；红→绿 TDD 读数与 41 条回归齐备。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 引导式重执行 | U-1 登记 | 需先决策 manifest 携带配置的形态，P-148 候选 |
| 聚合统计/跨 run 查询 | 未做 | 非本批目标 |
