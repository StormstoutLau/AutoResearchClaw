---
id: arc-ci-flaky-heavy-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-flaky-heavy-DESIGN, arc-ci-flaky-heavy-RESEARCH]
upstream: null
---

# 实施文档：F-1/F-2 `heavy` 化（P-125）

> **Feature**：P-125。
> **Spec 步骤**：Step 5-6。
> **基于设计**：[DESIGN.md](./DESIGN.md)。
> **基于调研**：[RESEARCH.md](./RESEARCH.md)。
> **结论先行**：4 个文件、8 行净变更落地；`ci_coverage_check --check` 由 **2 处 gap 红**转 **L=149 / R=2 / C=149 绿**；`pytest -m heavy` 2 passed、`-m "not heavy"` 收集 3778（2 deselected）；`researchclaw/` 零改动。

## 1. 实施概述

按 DESIGN §5.1 方案 A 执行：两个用例各加 `@pytest.mark.heavy`，两个文件各登记一条五字段条目，`heavy` 的 marker 描述在真值源（`pyproject.toml`）扩写为「真实外部依赖/资源 **或** 已知时序竞争」。先红后绿顺序由守卫规则④（打标 ⇔ 登记）天然保证，TDD 证据见 §4。

## 2. 工程细节

### 2.1 技术栈与依赖

| 组件 | 技术 | 版本 | 验证状态 |
|---|---|---|---|
| 标记机制 | `pytest.mark`（内置 marker） | 现装 pytest | ✅ 无 `PytestUnknownMarkWarning: heavy` |
| 登记解析 | `yaml.safe_load` | 现装 PyYAML | ✅ `--check` 实跑 |
| 守卫 | [ci_coverage_check.py](../../scripts/spec/ci_coverage_check.py) | 仓内 | ✅ selftest 4/4 |
| 新依赖 | 无 | — | ✅ |

### 2.2 文件结构（本批变更）

```
tests/test_hitl_advanced.py   +1 行装饰器（F-1）
tests/test_supervisor.py      +1 行 import pytest，+1 行装饰器（F-2）
tests/ci_exclusions.yaml      空表 → 2 条登记（+契约注释改写）
pyproject.toml                marker 描述 1 行改写
spec/arc-ci-flaky-heavy/      四文档（本批新增）
```

## 3. 模块实施

### 3.1 用例打标（F-1）

- 位置：[test_hitl_advanced.py](../../tests/test_hitl_advanced.py) L73（`TestFileWait.test_poll_with_delayed_response` 正上方）。
- 实施要点：装饰器只加在单个用例方法上，类内其余 6 个用例仍在 CI；行尾注释写明机制与文档指针（`spec/arc-ci-flaky-heavy/`），避免后人误以为是外部依赖。
- `pytest` 在该文件 L11 已导入，无需新增 import。

### 3.2 用例打标（F-2）

- 位置：[test_supervisor.py](../../tests/test_supervisor.py) L105（模块级函数 `test_lease_keeper_reports_loss` 正上方）。
- 该文件原先**未导入 pytest**（原 L1-L9 只有 stdlib 与 `researchclaw` 导入），按 DESIGN §10.1-1 在 L7 补 `import pytest`，置于 stdlib 与 first-party 之间。

### 3.3 登记表

- 位置：[ci_exclusions.yaml](../../tests/ci_exclusions.yaml) L2-L11。
- 两条五字段条目；`reason` 显式写「时序竞争」并给出 F-1/F-2 的 run 证据指针与文档锚点；`owner: P-125`、`since: 2026-11-16`。
- 原「首条登记形态（占位示例）」注释块改为**契约说明**（粒度=文件、五字段必填、打标⇔登记、reason 须区分外部依赖与时序竞争），避免占位示例与真实条目并存产生歧义。

### 3.4 marker 语义声明

- 位置：[pyproject.toml](../../pyproject.toml) L64。
- 由「需要真实外部依赖或资源」→「需要真实外部依赖/资源，或存在已知时序竞争需隔离的用例」。改的是**声明**而非机制：`heavy` 仍是纯运行时开关，集合成员唯一声明源仍是登记表（L62 注释未动）。

## 4. TDD 双要素

### 4.1 先红（写测试/声明，未登记）

```
$ python scripts/spec/ci_coverage_check.py --check
[gap] tests/test_hitl_advanced.py: 打了 heavy marker 但未登记（登记到 tests/ci_exclusions.yaml）
[gap] tests/test_supervisor.py: 打了 heavy marker 但未登记（登记到 tests/ci_exclusions.yaml）
覆盖未闭合：2 处
exit=1
```

缺口数与预期一致（2 个文件），且失败原因是**规则④**（双改未同步），不是你想要的「文件未收集」——证明守卫抓的是声明漂移而不是运行态噪声。

### 4.2 后绿（补登记）

```
$ python scripts/spec/ci_coverage_check.py --check
覆盖闭合：L=149，R=2，C=149
exit=0

$ python scripts/spec/ci_coverage_check.py --selftest
  PASS C1 闭合 ⇒ 0 违规   PASS C2 未登记未收集 ⇒ 缺口
  PASS C3 死项 ⇒ 违规     PASS C4 缺 marker ⇒ 违规
selftest: 4/4 PASS
```

## 5. 验证读数

| 验证 | 命令 | 读数 |
|---|---|---|
| heavy 集合可运行 | `python -m pytest tests -m heavy -q` | **2 passed**, 3778 deselected, 3.58s |
| CI 集合收集 | `python -m pytest tests -m "not heavy" --collect-only -q` | **3778/3780 collected (2 deselected)** |
| 同文件其余用例仍在 CI | `pytest tests/test_hitl_advanced.py tests/test_supervisor.py -m "not heavy" -q` | 39 passed, 1 failed（见 §8 偏差登记）、2 deselected |
| 排除平台限制后的同文件读数 | 同上 + `-k "not test_shell_hooks"` | **39 passed, 3 deselected** |
| marker 无未知告警 | 上述收集输出 | 无 `PytestUnknownMarkWarning: heavy`（`asyncio` 存量告警与本批无关，P-114 已登记） |

## 6. 回滚

删 2 行装饰器 + 删登记表 2 条条目 + 回退 1 行 marker 描述，`--check` 即回到 `R=0` 且规则④无打标残留；无数据迁移、无配置兼容窗。

## 7. 不变式落点

| 不变式（DESIGN §8） | 落点 |
|---|---|
| I-1 双改同步 | §4.1 先红 / §4.2 后绿即规则④的正反两态；两者同一工作树完成 |
| I-2 未登记零漂移 | `--check` 报 `L\R ⊆ C`（C=149 覆盖全部 147 个未登记测试文件 + 2 个登记文件的其余用例）；selftest C2 保留缺口检测能力 |
| I-3 五字段完整 | 登记表 2 条均含 `path/reason/marker/owner/since`；`load_right` 缺字段即抛错（fail-closed） |
| I-4 产品零改动 | `git diff --stat` 中 `researchclaw/` 为 0 文件（批外 vendor CRLF 存量不计） |
| I-5 可运行 | §5 第 1 行：`-m heavy` 2 passed |

## 8. 外部锚点与偏差登记

- **偏差 D-1（平台限制，非本批引入）**：本地 Windows 跑 `TestHookRegistry::test_shell_hooks` 失败——`[WinError 193] %1 不是有效的 Win32 应用程序。`，因该用例直接执行 `.sh`。文件最后一次变更为 `958fb18`（v0.4.0 HITL 系统），与本批零交集；CI 为 Linux 不受影响。验收读数以 §5 第 4 行（`-k "not test_shell_hooks"`）为准。
- **偏差 D-2（基线漂移）**：P-114 记录 `L=148 / C=148`，本批实测 `L=149`——期间新增了一个 `tests/test_*.py` 文件（非本批引入）。收集基线由 3778 → 3780（heavy 2 条），`-m "not heavy"` 仍为 3778。
- **无文献锚点**：见 RESEARCH §7。

## 9. 未决项

承接 DESIGN §11.1 的 U-1（根因未定位）与 U-2（heavy 无定期执行路径），本批不新增未决项、不关闭未决项。

## 10. 对审查的输入

1. 先红/后绿的**失败原因**必须被核对为规则④，而非误建立「文件未收集」的假红（§4.1）。
2. `C=149` 的语义是**文件集**，不是用例数；验收需同时看 3780/3778 两个用例读数（§5）。
3. `reason` 文本必须能在登记表内自证「时序竞争」，不得只剩 run id。
4. `researchclaw/` 零改动需用 `git diff --stat` 取证，不能凭记忆声明。
