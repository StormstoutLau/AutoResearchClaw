---
id: arc-ci-flaky-heavy-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-16
depends: [arc-ci-flaky-heavy-IMPLEMENTATION, arc-ci-flaky-heavy-DESIGN]
upstream: null
---

# 审查验收 Checklist：F-1/F-2 `heavy` 化（P-125）

> **Feature**：P-125。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：本批全部验收项均可在**本机**完成（守卫脚本 + pytest 收集 + 读码），唯一例外是「四矩阵兼容」需 PR checks 的四版本实跑，故该行标 ☐ 并写回填窗口。凡标 ✅ 的项均附一手读数或行号，不预填。（2026-11-16 回填注：四矩阵行已按 PR #6 checks 实跑读数翻 ✅，见 §7 与 §10.1/§10.2。）

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 的决策可追溯到 RESEARCH | ✅ | §2.1 映射表 5 行全覆盖：D-1←§3.4、D-1.1←§6.3、D-2←§3.4/§6.3、D-3←§3.1-§3.3、D-3.1←§3.5 |
| RESEARCH 的关键发现被 DESIGN 使用 | ✅ | 落点四矩阵（§3.3）→ D-3 不做语义改造；覆盖代价（§3.5）→ §6.3 风险；守卫四规则（§3.4）→ §3.2 模块集中「闭合守卫」 |
| 无文档间矛盾 | ✅ | DESIGN 否决 B/C/D 的理由与 RESEARCH §4.2 逐条一致；U-1/U-2 在 DESIGN §11.1 原样承接，判据未漂移 |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 设计的模块在实施中有对应 | ✅ | DESIGN §3.2 四模块 ↔ IMPL §3.1-§3.4 四小节，一一对应 |
| 接口/契约签字一致 | ✅ | DESIGN §4.1 登记项五字段 ↔ `ci_exclusions.yaml` L2-L11 实文；DESIGN §4.2 marker 文本 ↔ `pyproject.toml` L64 实文（逐字符） |
| 不变式有实施落点 | ✅ | I-1..I-5 ↔ IMPL §7 五行，每行给命令或文件面 |
| 无设计未覆盖的实施 | ✅ | 唯一注入项是 `tests/test_supervisor.py` 的 `import pytest`（DESIGN §10.1-1 已预告），非派生需求 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 实施的功能点在本 checklist 有验收项 | ✅ | IMPL §3.1/§3.2/§3.3/§3.4 ↔ §2.1/§2.2/§2.3/§2.4；§5 读数 ↔ §6/§7 |
| 本 checklist 的验收项可追溯到实施 | ✅ | 每行注明 IMPL 小节或命令，无自造验收面 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| 时序竞争 | §3.1/§3.2 根因假设 | §2.1 决策依据 | §3.1/§3.2 行尾注释 | ✅ |
| 声明源 | §3.4「声明源与运行时开关」 | §3.3「声明层」 | §3.4「集合成员唯一声明源」 | ✅ |
| 双改同步 | §3.4 规则④ | I-1 | §4.1 先红即其反态 | ✅ |
| 覆盖闭合 | §3.4 L\R⊆C | §3.3 数据流 | §4.2 `L=149/R=2/C=149` | ✅ |
| 补偿/复核 | §4.3 U-2 | §11.1 U-2 | §9 承接 | ✅ |

## 2. 功能验收

### 2.1 F-1 用例隔离

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| marker 落在单函数 | 读 `test_hitl_advanced.py` | 装饰器在 `test_poll_with_delayed_response` 上方，未加在类/模块 | ✅ | L73 装饰器、L74 函数定义；该类其余 6 个用例在 §5 读数中仍被收集 |
| CI 默认不执行 F-1 | `pytest tests -m "not heavy" --collect-only -q` | 该用例不在收集结果内 | ✅ | 3778/3780（2 deselected = 2 条 heavy） |
| heavy 集合可执行 | `pytest tests -m heavy -q` | 2 passed | ✅ | 2 passed / 3778 deselected / 3.58s |

### 2.2 F-2 用例隔离

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| marker 落在单函数 | 读 `test_supervisor.py` | 装饰器在 `test_lease_keeper_reports_loss` 上方 | ✅ | L105 装饰器、L106 函数定义 |
| 缺失的 pytest 导入已补 | 读文件头 | `import pytest` 位于 stdlib 与 first-party 之间 | ✅ | L7 |
| 该文件其余用例仍在 CI | `pytest tests/test_supervisor.py -m "not heavy" -q` | 除 F-2 外全部执行 | ✅ | 两文件合跑 39 passed / 3 deselected（含 §2.1 的 2 条 + 平台限制 1 条，见 §5） |

### 2.3 登记表契约

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 两文件各一条登记 | 读 `tests/ci_exclusions.yaml` | `len(exclusions)==2`，路径分别为两文件 | ✅ | L2-L11 |
| 五字段完整 | 同上 | `path/reason/marker/owner/since` 全非空，`marker==heavy` | ✅ | L11 后接契约注释块说明粒度与必填 |
| reason 诚实可追溯 | 同上 | 明写「时序竞争」+ run/文档锚点，无「外部依赖」套话 | ✅ | 两条 reason 分别指向 RESEARCH §3.1 / §3.2，并各带 3.11-3.14 落点或隐式前提描述 |

### 2.4 marker 语义声明

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 描述覆盖时序竞争 | 读 `pyproject.toml` L63-L65 | 描述含「已知时序竞争需隔离」，且保留「外部依赖/资源」 | ✅ | L64 实文 |
| 机制未被改动 | 读同段注释与守卫 | `heavy` 仍是纯运行时开关；集合成员唯一声明源仍是登记表 | ✅ | L62 注释未动；`ci_coverage_check` 零改动（本批未触碰 scripts/） |

## 3. 接口验收

本批**不新增或修改任何公共接口**（无 `researchclaw/` 代码变更、无 CLI/HTTP/事件面变更），故无接口验收项。

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| I-1 双改同步 | 先打标不登记跑 `--check` | exit 1，且报「打了 heavy marker 但未登记」×2 | ✅ | IMPL §4.1 原文（2 处 gap / exit=1） |
| I-2 未登记零漂移 | `--check` 全量 | `L\R ⊆ C` 无违规；selftest C2 仍能检出未登记未收集 | ✅ | IMPL §4.2（L=149/R=2/C=149）+ selftest 4/4 |
| I-3 五字段完整 | 读登记表 + 契约注释 | 五字段齐备，owner 可回溯 P-125 | ✅ | 见 §2.3 |
| I-4 产品零改动 | `git diff --stat` | `researchclaw/` 0 文件（批外 vendor CRLF 存量不计） | ✅ | IMPL §7 行 4；本批 tracked 变更限于 tests/、pyproject.toml、spec/ |
| I-5 可运行 | `pytest tests -m heavy -q` | 2 passed | ✅ | IMPL §5 第 1 行 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 打标未登记 | 见 I-1 | 红且信息指向登记表路径 | ✅ | IMPL §4.1 |
| 登记指向已删文件 | `--selftest` C3 | 死项判违规 | ✅ | selftest 4/4（C3 PASS） |
| marker 非 `heavy` | `--selftest` C4 | 声明源与开关不一致判违规 | ✅ | selftest 4/4（C4 PASS） |

## 6. 性能验收

| 指标 | 测试方法 | 目标 | 状态 | 证据 |
|------|---------|------|------|------|
| heavy 集合运行时长 | `pytest tests -m heavy -q` | 不引入秒级膨胀（本机 < 10s） | ✅ | 3.58s |
| CI 执行量变化 | 对比收集数 | 每 run 少 8 次执行（4 矩阵 × 2） | ✅ | 3780 → 3778（`-m "not heavy"`） |

## 7. 兼容性验收

| 项 | 测试方法 | 通过条件 | 状态 | 证据 |
|----|---------|---------|------|------|
| Python 3.11-3.14 | PR checks 四矩阵 | 四矩阵均绿且均 2 deselected | ✅ | PR #6 双 run 43736549562（push）/ 43736560954（pull_request）四矩阵 8 job 全 pass（耗时由 job startedAt/completedAt 复算：3.11 112s+120s / 3.12 117s+120s / 3.13 110s+113s / 3.14 118s+117s）；四个矩阵 job 日志**逐一实证** `3712 passed, 66 skipped, 2 deselected`（3712+66=3778 与本地收集基线一致） |
| CI 命令不变 | 读 `ci.yml` | 仍为 `-m "not heavy"`，无新增 flag/job | ✅ | L124 未改 |
| 本地钩子同判 | `pre-commit run ci-coverage --all-files` | 与 spec-gates job 同 entry 同结论 | ✅ | 本批门禁运行 Passed（entry 未改，P-114 已比对一致） |
| 收集基线 | `--collect-only` | 明确 3780 全量 / 3778 CI 集 | ✅ | IMPL §5 第 2 行 |

## 8. 交付面（ADD）验收

| 项 | 通过条件 | 状态 | 证据 |
|----|---------|------|------|
| 变更文件面 | 恰为 4 个实施文件 + 四文档，无额外改动 | ✅ | `tests/test_hitl_advanced.py`、`tests/test_supervisor.py`、`tests/ci_exclusions.yaml`、`pyproject.toml` |
| 无新依赖 | 依赖清单零变化 | ✅ | IMPL §2.1 |
| 无产品代码改动 | `researchclaw/` 0 文件 | ✅ | I-4 |
| 可回滚 | 删 2 装饰器 + 2 登记 + 1 行描述即回退 | ✅ | IMPL §6 |
| 未扩 CI 结构 | `ci.yml` 零改动、无新 job/触发器 | ✅ | §7 第 2 行 |
| 文档链闭合 | 四文档互链 + PROGRESS 行 | ✅ | 本文与 RESEARCH §1、DESIGN §2.1、IMPL §1 互链；PROGRESS P-125 |

## 9. 审计证据绑定（E1-E5 分类）

| 主张 | 证据类型 | 出处 | 等级 |
|---|---|---|---|
| 打标与登记的双改是守卫强制项 | E1 读码 | `ci_coverage_check.py` L5-L13 / L90-L121 | 最高 |
| 先红后绿 | E1 运行读数 | IMPL §4.1 / §4.2 | 最高 |
| heavy 集合可运行、CI 集少 2 条 | E1 运行读数 | IMPL §5 | 最高 |
| 落点覆盖四矩阵 | E1 远端 run 日志 | RESEARCH §3.3 表 | 最高 |
| 根因为读/解析窗口 | E2 读码推断 | RESEARCH §3.1 / U-1 | 中（已声明未插桩） |
| 平台限制失败与本批无关 | E1 文件史 + 错误码 | IMPL §8 偏差 D-1 | 最高 |

## 10. 验收统计与结论

### 10.1 验收统计

| 验收类别 | 总项数 | 通过 | 失败 | 待办 |
|---------|--------|------|------|------|
| 文档一致性 | 14 | 14 | 0 | 0 |
| 功能验收 | 11 | 11 | 0 | 0 |
| 接口验收 | 0 | 0 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 3 | 3 | 0 | 0 |
| 性能 | 2 | 2 | 0 | 0 |
| 兼容性 | 4 | 4 | 0 | 0 |
| 交付面 | 6 | 6 | 0 | 0 |
| **总计** | **45** | **45** | **0** | **0** |

双算术：45 = 14+11+0+5+3+2+4+6；通过 45 = 14+11+0+5+3+2+4+6；待办 0（§7 四矩阵行已按 PR #6 实跑读数回填，2026-11-16）。

### 10.2 验收结论

- [ ] **有条件通过**（P-125 时点口径，已由下行「验收通过」取代）：本机可验项 100% 通过（44/45），唯一 ☐ 为「Python 3.11-3.14 四矩阵」——它只能由 PR checks 产生，且本批改动不触碰版本相关面；回填窗口 = 本批 PR 的 `gh pr checks` 读数。该条件已于 2026-11-16 由 PR #6 四矩阵全绿满足。
- [x] 验收通过：§7 四矩阵行已按 PR #6 实跑读数回填（run 43736549562 / 43736560954，均 `2 deselected`），45/45 全通过；status 翻 accepted（CHECKLIST 词表：pending/accepting/accepted）。
- [ ] 验收不通过：无阻塞项。

> 诚实边界：本批把两条行为从 CI 阻断面**转移**到 heavy 集合，不修复其竞争本质（RESEARCH §6.3、U-1）。因此「44/45 通过」只表示隔离实施正确，不表示 F-1/F-2 已治愈。

## 11. 后续行动

| 行动 | 负责 | 时机 | 状态 |
|------|------|------|------|
| §7 四矩阵行回填 | 审查者 | 本批 PR checks 完成后 | done（PR #6 读数回填，2026-11-16） |
| U-1 根因专项（F-1 读/解析窗口、F-2 调度前提） | 后续批 | heavy 复核连续 2 次失败或功能回归时 | pending |
| U-2 heavy 定期执行路径（schedule / pre-push） | 后续批 | CI 触发器扩容排期时，或连续 2 批未跑 `pytest -m heavy` | pending |
