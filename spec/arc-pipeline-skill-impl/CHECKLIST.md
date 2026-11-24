---
id: arc-pipeline-skill-impl-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-pipeline-skill-impl-IMPLEMENTATION, arc-pipeline-skill-impl-DESIGN]
upstream: null
---

# 审查验收 Checklist：pipeline-as-skill 实施（P-146）

> **Feature**：P-146。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：2 个新增文件；既有 loader/schema/账本零改动。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 决策可追溯到 P-145 | ✅ | D-1..D-8 对应 P-145 D-1..D-9 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 两文档均为「2 个新增文件」 |
| IMPLEMENTATION 读数在 checklist 有验收项 | ✅ | 10 + 56 读数 ↔ §2/§7 |
| 术语一致（API、字段、用例名） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 导出 manifest | `export_manifest` | `pipeline.json` 存在且字段齐全 | ✅ | `test_export_writes_manifest_and_skill_md` |
| 导出 SKILL.md | 读 front-matter | `kind=pipeline`、`manifest=pipeline.json` | ✅ | 同上 |
| 阶段子图 | 读 `stages` | `[1, 23]` 升序 | ✅ | 同上 |
| 重试折叠 | `retries=2` | `attempts=3` | ✅ | `test_retries_fold_into_attempts` |
| 动作归属 | 账本 `event_seq_call` | 阶段节点含 `action_id` | ✅ | 导出用例 |
| 产物相对路径 + 哈希 | 读 `outputs` | `out.txt` 键 + sha256 | ✅ | 导出用例 |
| env 键名 | 读 `env_keys` | `["CUDA_VISIBLE_DEVICES"]` | ✅ | 导出用例 |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 三个入口可用 | 调用 | `export/validate/load` 签名与返回符合 DESIGN §2 | ✅ | 用例全集 |
| 既有 loader 兼容 | 运行 loader 用例 | 20 个既有技能不受影响 | ✅ | 既有测试套件 |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 失败 run 不落盘 | 缺 `run.completed` | 抛错且无文件 | ✅ | `test_export_requires_run_completed` |
| J-2 摘要覆盖全字段 | 改 run_id | 校验报 `manifest_sha256` | ✅ | `test_validate_integrity_detects_tamper` |
| J-3 阶段映射不匹配拒绝 | 传异映射 | 报 `stage_map` | ✅ | `test_validate_rejects_stage_map_drift` |
| J-4 路径必须相对 | 注入 `C:/...` | 报 `relative` | ✅ | `test_validate_rejects_absolute_output_path` |
| J-5 工具名缺失拒绝/版本漂移警告 | 注入未知工具/异版本 | error / warning 分流 | ✅ | `test_validate_unknown_tool_and_version_drift` |
| J-6 发现不执行 | `load_pipeline_skill` | 只返回 manifest | ✅ | `test_loader_discovers_and_accepts` |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 有 `stage.failed` | 构造失败 run | 抛 `ManifestExportError` | ✅ | `test_export_rejects_stage_failure` |
| 缺 Stage 23 | 构造无 23 的 run | 抛错 | ✅ | `test_export_requires_stage_23` |
| manifest 不可读 | 删 `pipeline.json` | 返回 `(None, [...])` | ✅ | 发现用例覆盖 |
| 路径越界 | 注入 `..`/盘符 | 校验报错 | ✅ | J-4 用例 |

## 6. 性能验收

本批不引入循环或网络调用；导出为一次性文件读取，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 既有技能不受影响 | 既有 skills 测试 | 全绿 | ✅ | 套件回归 |
| 工具/账本回归 | 56 条相关用例 | 全绿 | ✅ | IMPL §2 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 10 条新用例全绿；56 条相关回归全绿 |
| 可逆性 | 2 个新增文件，删文件即回退 |
| 风险 | 阶段归属为 seq 启发式，已登记 |
| 卫生 | 未触碰既有 loader、执行路径与 workflow |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 2 | 2 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **25** | **25** | **0** | **0** |

算术自洽：25 = 4+7+2+6+4+0+2+0；通过 25 = 总数 25。

### 10.2 验收结论

- [x] 验收通过：25/25；10 条新用例与 56 条回归读数齐备。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 重放 | 未做 | 另开批 |
| 阶段归属精度 | 已知边界 | seq 启发式 |
| CLI 查询 | 未做 | P-147 候选 |
