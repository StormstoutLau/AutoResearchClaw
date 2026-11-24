---
id: arc-reuse-plan-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-reuse-plan-IMPLEMENTATION, arc-reuse-plan-DESIGN]
upstream: null
---

# 审查验收 Checklist：配置快照与复用计划（P-148）

> **Feature**：P-148。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：1 新模块 + 2 扩展 + 1 测试；P-147 的 verify 行为不变。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-6 对应 RESEARCH §1/§2 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「1 新 + 2 扩展 + 1 测试」 |
| 读数在 checklist 有验收项 | ✅ | 11 + 32 ↔ §2/§7 |
| 术语一致（字段、命令、退出码） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 凭据键脱敏 | `sanitize_config` | `api_key`/`s2_api_key` → `***REDACTED***` | ✅ | `test_redacts_secrets_and_paths` |
| `*_env` 保留 | 同上 | `api_key_env` 原值保留 | ✅ | 同上 |
| 绝对/`~`/UNC 路径脱敏 | 同上 | 三类均 → `<REDACTED_PATH>` | ✅ | 同上（含修正记录） |
| 快照无密钥字节 | 读快照文件 | 原文密钥不出现 | ✅ | `test_snapshot_has_no_secret_bytes` |
| 导出 v2 | `config_path` | 版本=2、config 块齐全 | ✅ | `test_export_with_config` |
| v1 兼容 | 不传 config | 版本=1、无 config 块 | ✅ | `test_export_without_config_stays_v1` |
| plan 输出 | CLI `--json` | command/stages/redacted_keys 齐全 | ✅ | `test_plan_v2` |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `export_manifest` 扩展 | 关键字参数 | 旧调用不受影响 | ✅ | v1 用例 + 32 回归 |
| `validate_manifest` v1/v2 | 两版本 | v1 通过、v2 校验快照 | ✅ | 加载用例 |
| `pipeline-skill plan` | CLI | 0/2 两态 | ✅ | `test_plan_*` |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 快照无凭据 | 字节扫描 | 无密钥原文 | ✅ | 快照用例 |
| J-2 脱敏规则 | 键名/值判定 | 凭据脱敏、env 保留 | ✅ | 脱敏用例 |
| J-3 快照篡改拒绝 | 改文件 | 加载报 hash mismatch | ✅ | `test_loader_rejects_tampered_snapshot` |
| J-4 v1 可加载、不可 plan | 两用例 | v1 加载成功、plan exit 2 | ✅ | `test_plan_v1_rejected` |
| J-5 v2 缺 config 拒绝 | 删 config 块 | 加载报 missing | ✅ | `test_v2_requires_config_block` |
| J-6 不修改入参 | 调用后检查 | 原 dict 不变 | ✅ | `test_does_not_mutate_input` |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 配置根不是 mapping | `sanitize_config` | 抛 `ConfigSanitizeError` | ✅ | `test_rejects_non_mapping` |
| 快照缺失 | 删文件 | 加载报 missing | ✅ | 校验分支 |
| 技能目录不存在 | CLI | exit 2 | ✅ | `test_plan_missing_dir` |
| v1 请求 plan | CLI | exit 2 + 提示 | ✅ | `test_plan_v1_rejected` |

## 6. 性能验收

一次性配置读取与小文件哈希，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| P-146/P-147 回归 | 32 条 | 全绿 | ✅ | IMPL §2 |
| `verify` 行为不变 | 复用 P-147 用例 | 全绿 | ✅ | 回归读数 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8）

- RESEARCH §2 脱敏规则 ↔ DESIGN §1 D-6 ↔ 实施 `SECRET_KEY_RE`/`ABS_PATH_RE` 三方一致。
- DESIGN §2 字段 ↔ 实施 `config` 块 ↔ CHECKLIST 功能项逐一对得上。
- 测试与实现交替推进，已在 IMPLEMENTATION §2 如实记录「非严格 TDD」。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 4 | 4 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **26** | **26** | **0** | **0** |

算术自洽：26 = 4+7+3+6+4+0+2+0；通过 26 = 总数 26。

### 10.2 验收结论

- [x] 验收通过：26/26；11 条新用例 + 32 条回归。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 自动重跑 | 未做 | 需人工补齐脱敏项 |
| 重跑等价性 | 未验证 | 需对照实验，另立批次 |
| 脱敏完备性 | 已知边界 | 命名启发式，非完备保证 |
