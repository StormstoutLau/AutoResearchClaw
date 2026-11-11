---
id: arc-g2-m1-ar-checks-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m1-ar-checks-DESIGN]
upstream: arc-g2-m1-ar-checks-DESIGN
---

# 实施记录：G2 M1 学术八条判据

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `researchclaw/evidence/__init__.py` | 新增 | 导出 `Finding/SEVERITIES/CHECKS/check_claim` |
| `researchclaw/evidence/ar_checks.py` | 新增 | AR-01..08 八个纯函数 + 注册表 + 确定性排序 |
| `tests/fixtures/g2/ar/*.json` | 新增 | 16 个 fixture（每判据 1 正 1 反） |
| `tests/test_g2_ar_checks.py` | 新增 | 分类、变异、schema 回验，共 28 项 |
| `.github/workflows/ci.yml` | 修改 | M1 测试加入 tests 矩阵固定清单 |

## 2. 关键实现

- **纯函数**：8 个 `arNN(claim) -> list[Finding]`，无 IO、无全局状态；缺失字段按「未提供」处理，不抛异常。
- **注册表**：`CHECKS: dict[code, callable]`；`check_claim` 动态遍历 `CHECKS.values()`，因此 `monkeypatch.setitem` 可模拟「删判据」。
- **严重度**：只允许 `fail/warn/downgrade`；`cap` 仅 AR-05/06 使用（`latex_verified`），供 A2-4..A2-6 的谓词层消费。
- **确定性**：findings 按 `(code, field, message)` 排序，跨次运行一致。
- **AR-03**：禁用短语大小写不敏感匹配；引用标记冻结为 `[e-xxxx]`；标记必须解析到 `evidence[]`，且命中证据必须有 `locator`。
- **AR-08**：与 M0 的 C4/C5 结构校验形成纵深防御——schema 管持久化，检查管内存态与 `inline_copy`。

## 3. 测试结果

| 环境 | 命令 | 读数 |
|---|---|---|
| 3.13.5（全局） | `python -m pytest tests/test_g2_ar_checks.py -q` | **28 passed**（0.21s） |
| 3.11.15（`%TEMP%\arc-ap-py311`） | 同上 | **28 passed**（0.13s） |

测试结构：

| 测试 | 项数 | 覆盖 |
|---|---|---|
| `test_negative_fixture_triggers_expected_severity` | 8 | 每条判据在其反例上产出预期严重度 |
| `test_positive_fixture_does_not_trigger_its_check` | 8 | 判据不恒红 |
| `test_pre_red_disabling_check_clears_finding` | 8 | 变异：禁用判据后 finding 消失（承重性） |
| `test_declared_formalization_debt_is_warn_not_fail` | 1 | AR-07 的 debt 分支 |
| `test_positive_fixtures_are_valid_claim_records` | 1 | 8 个正例回验 C4 schema |
| `test_all_checks_registered` / `test_findings_are_sorted` | 2 | 注册表完整、排序确定 |

**变异语义**：若某判据被永久替换为空实现，`test_negative_fixture_triggers_expected_severity` 与变异用例的首断言同时变红——即「判据空实现必须失败」。

## 4. 与设计的偏差

| # | 偏差 | 原因 |
|---|---|---|
| D-1 | AR-05 仅以 A/B 类触发，未实现 `claim_type ∈ {model, method}` | 与 C4 v1 的 `exploratory/confirmatory` 枚举冲突（[RESEARCH](RESEARCH.md) §3） |
| D-2 | AR-07 的「已声明 debt」只给 `warn`，不带 `cap` | R-03 原文仅要求 warn；封顶语义留给谓词层，避免两处实现 |
| D-3 | AR-06 的「共识不得提升 tier」未实现 | 需要前态比较，单条记录不可机械判定（R-03 §3.5 同类） |
| D-4 | AR-08 的反例（snapshot `readonly=false`）不是合法 C4 记录 | 该判据本身针对结构违规；正例才回验 schema |

## 5. 未执行

- A2-4..A2-6 发布谓词（`can_enter_deliverables` / `requires_annotation` / `downgrade_missing_citation`）；
- 状态改写（`downgrade` 的落库形态）；
- vendor 3.11 内核（M2）。
