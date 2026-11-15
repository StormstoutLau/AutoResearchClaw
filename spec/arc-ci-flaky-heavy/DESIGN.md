---
id: arc-ci-flaky-heavy-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-flaky-heavy-RESEARCH]
upstream: null
---

# 设计文档：F-1/F-2 `heavy` 化（P-125）

> **Feature**：P-125，把两个时序 flaky 用例隔离到 `heavy` 集合，保持覆盖守卫双向闭合与声明源诚实。
> **Spec 步骤**：Step 3-4。
> **基于调研**：[RESEARCH.md](./RESEARCH.md)。
> **结论先行**：采用 **D-1 文件级 `heavy` 隔离 + D-2 语义显式扩写 + D-3 补偿性复核节奏**；拒绝时序稳健化（B）、`pytest-rerunfailures`（C）、拆文件（D）。

## 1. 设计目标

在不改产品代码、不新增依赖、不扩 CI 结构的前提下，让 CI 对 F-1/F-2 的时序竞争脱敏，同时保证：① 覆盖守卫仍能抓住「未登记却离开 CI」的漂移；② `heavy` 的声明语义与真实用途一致，不说谎；③ 被隔离的行为仍有可执行的复核路径。

## 2. 设计依据

### 2.1 调研结论

| 调研发现 | 设计决策 | 引用 |
|---|---|---|
| guard 规则④要求「含 marker ⇔ 在登记表」，且登记粒度是文件 | D-1 文件级隔离，两文件各一条登记 | RESEARCH §3.4 |
| 登记文件的规则②豁免是结构性风险 | D-1.1 登记表 `reason` 写明豁免范围 + I-2 保持未登记文件零漂移 | RESEARCH §6.3 |
| `heavy` 注册描述只覆盖「真实外部依赖/资源」 | D-2 显式扩写 marker 描述，把「已知时序竞争」纳入 | RESEARCH §3.4 / §6.3 |
| 落点覆盖四矩阵、rerun 即绿、根因未定位 | D-3 不做语义改造；以 `pytest -m heavy` 复核 + U-1/U-2 观察项承接 | RESEARCH §3.1-§3.3 |
| 隔离代价 = 8 次执行/run | D-3.1 补偿路径不新增 job，登记 U-2 | RESEARCH §3.5 |

### 2.2 流程依据

| 依据 | 内容 | 对本设计的影响 |
|---|---|---|
| [SPEC_PROCESS.md](../SPEC_PROCESS.md) 的 fail-closed 取向 | 门禁不做「宽恕」分支 | 本设计不引入临时豁免通道；缺登记即红 |
| [SPEC_PROCESS.md](../SPEC_PROCESS.md) 的自包含口径 | 外部机器事实须落为可复核读数 | §2.1 映射全部指向本批 E1 读码/运行读数，无外部引用 |
| [ci_coverage_check.py](../../scripts/spec/ci_coverage_check.py) L5-L13 | 四条闭合规则 | D-1 的文件级粒度由此强制 |

### 2.3 职责边界

**职责内**：测试标记、登记表声明、marker 描述文字、本 feature 四文档。**职责外**：`researchclaw/hitl/file_wait.py` 与 `researchclaw/runtime/lease.py` 的行为修正（属 U-1 的后续批）、CI 触发器结构（属 U-2）。

## 3. 架构设计

### 3.1 整体架构

三层不变，本批只动「用例层」与「声明层」：

```
用例层   tests/test_hitl_advanced.py (F-1)   tests/test_supervisor.py (F-2)
          └ @pytest.mark.heavy                 └ @pytest.mark.heavy
声明层   tests/ci_exclusions.yaml (2 条五字段)   pyproject.toml L63-L65 (marker 描述)
守卫层   ci_coverage_check.py --check（规则①-④）  CI: pytest -m "not heavy"
```

### 3.2 模块划分

| 模块 | 职责 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| 用例打标 | 给两个用例加 `heavy` marker | 用例函数 | 被 `-m not heavy` 过滤 | pytest |
| 登记表 | 声明两文件的隔离理由与责任人 | 五字段条目 | `R` 集合 | `ci_coverage_check.load_right` |
| marker 描述 | 对外说明 `heavy` 的真实语义 | 文本 | `--strict-markers` 下合法、语义诚实 | pyproject |
| 闭合守卫 | 校验 ①-④ | `L`/`R`/`C` | exit 0/1 | git + pytest 收集 |

### 3.3 数据流

`git ls-files` → `L`；`yaml.safe_load(ci_exclusions)` → `R`；`pytest --collect-only -m "not heavy"` → `C`；`closure_violations(L, R, C)` 产出违规行。本批使 `|R| = 2`，且 `R ⊆ L`、`L\R ⊆ C` 保持成立。

### 3.4 控制流

本地：`pre-commit` 的 `ci-coverage` 钩子（entry 与 CI spec-gates job 逐字符一致）在 `tests/*.py` 或登记表变更时触发 `--check`。CI：`tests` job 以 `-m "not heavy"` 运行。

## 4. 接口定义

本批**不新增公共接口**。唯一「接口面」是 marker 与登记表的契约：

### 4.1 登记项（YAML 对象）

```yaml
- path: tests/test_<file>.py      # 必须 ∈ git ls-files tests/test_*.py
  reason: <诚实理由，须区分外部依赖与时序竞争>
  marker: heavy                   # 固定字面量
  owner: P-125
  since: 2026-11-16
```

### 4.2 marker 声明（pyproject.toml）

```toml
markers = [
    "heavy: 需要真实外部依赖/资源，或存在已知时序竞争需隔离的用例（由 tests/ci_exclusions.yaml 登记，CI 默认排除）",
]
```

## 5. 替代方案

### 5.1 方案 A：文件级 `heavy` 隔离（选择）

- 描述：两个用例各加 marker，两个文件各登记一条；marker 描述扩写。
- 优点：零产品代码、零新依赖、契约内、可逆（删两行登记即回到 CI）。
- 缺点：整文件从规则②豁免；被隔离行为不再阻断合入。
- 选择理由：P-123 已按 RI-2 裁决，「连续误红 ⇒ 登记 heavy 并留痕」；本批只执行裁决并补齐语义诚实性。

### 5.2 方案 B：时序稳健化（本批否决）

- 描述：F-1 改为条件等待/文件事件驱动，F-2 改为等待回调而非固定 sleep。
- 优点：根除 flake，覆盖留在 CI。
- 缺点：需改产品侧判定边界；根因未钉死时属盲改，且会扩大本批 T1 边界。
- 否决理由：RESEARCH U-1 判据未满足（无确定性竞争窗口），改为留待专项批。

### 5.3 方案 C：`pytest-rerunfailures`（否决）

- 否决理由：新增依赖；把 flake 转成重试配额，掩盖真实回归信号，违反 fail-closed 取向。

### 5.4 方案 D：拆分成独立 heavy 文件（否决）

- 否决理由：需搬移测试代码与上下文（类、夹具），diff 与回归面大于收益；不解决根因，且使「用例位置」与既有 PROGRESS 证据行脱节。

## 6. 数据结构

### 6.1 登记表

```yaml
version: 1
exclusions:
  - path: tests/test_hitl_advanced.py
    reason: ...
    marker: heavy
    owner: P-125
    since: 2026-11-16
  - path: tests/test_supervisor.py
    reason: ...
    marker: heavy
    owner: P-125
    since: 2026-11-16
```

## 7. 错误处理

| 错误场景 | 处理方式 | 用户可见信息 |
|---|---|---|
| 打了 marker 未登记 | 守卫红（规则④） | `tests/...py: 打了 heavy marker 但未登记（登记到 tests/ci_exclusions.yaml）` |
| 登记项指向已删文件 | 守卫红（规则①） | `tests/...py: 登记项不在 tests/test_*.py（已删除？删除该登记）` |
| 登记 marker 非 `heavy` | 守卫红（规则③） | `tests/...py: marker 必须为 heavy（声明源与运行时开关必须同改）` |
| `pytest -m heavy` 下用例失败 | 不阻断 CI（已隔离），由 U-1 观察项承接 | 本地/定期复核可见失败 |

## 8. 不变式（Invariants）

1. **I-1 双改同步**：marker 与登记项必须在同一 diff 落地；缺一即守卫红。
2. **I-2 未登记零漂移**：`L \ R ⊆ C` 恒成立，即除两个已登记文件外，任何测试文件离开 CI 收集都判红。
3. **I-3 五字段完整**：`path/reason/marker/owner/since` 均非空，`owner` 可回溯到 PROGRESS 批号。
4. **I-4 产品零改动**：`researchclaw/` 下文件变更数 = 0。
5. **I-5 可运行**：两个 heavy 用例在 `pytest -m heavy` 下可独立收集并通过。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 每条决策均可追溯到 RESEARCH §3/§6（见 §2.1 映射表）。
- [x] 无未经验证的假设：不假设根因，只按裁决隔离。
- [x] 无归因扭曲：明确写出「转移而非治愈」。

### 9.2 替代方案审查

- [x] 列 4 个方案（A 采用，B/C/D 否决且各有理由）。

### 9.3 职责边界审查

- [x] 产品行为修正不在本批；CI 结构扩容不在本批。

## 10. 对实施的输入

### 10.1 关键工程约束

1. `tests/test_supervisor.py` 当前未导入 `pytest`，需补 `import pytest`。
2. marker 必须加在**用例函数**上（不是类/模块），避免整类被过滤。
3. 登记表 `reason` 必须写明「时序竞争」且指向 F-1/F-2 的 run 证据，不得套用「外部依赖」模板。
4. 改 `tests/` 会触发 `repo-stats` 与 `ci-coverage` 两个钩子，派生视图需重生成。

### 10.2 风险与缓解

| 风险 | 缓解措施 |
|---|---|
| 整文件被规则②豁免 ⇒ 其余用例静默离开 CI | I-2 在验收中以「无登记文件时 `--check` 红」与「登记后其余文件仍全量收集」双向取证；U-2 观察 |
| marker 语义稀释 | D-2 在真值源（pyproject）改写描述，并在 CHECKLIST 单列验收行 |
| 误把「全部 F-1 相关覆盖」隔离 | marker 只加在 `test_poll_with_delayed_response` 单函数；同文件其余用例仍在 CI |

## 11. 未决项登记（四元块）与决策矩阵

**11.1 未决项登记**

- **U-1 根因未定位**（承接 RESEARCH U-1）：判据 = 钉死竞争窗口并用确定性用例固定；触发 = `pytest -m heavy` 连续 2 次失败或功能回归报告；当前倾向 = F-1 读/解析窗口、F-2 隐式调度前提；证据等级 E2。
- **U-2 heavy 无定期执行路径**（承接 RESEARCH U-2）：判据 = 进入非人工触发路径；触发 = CI 新增 `schedule` 或连续 2 批未跑 `pytest -m heavy`；当前倾向 = 本批不扩 job；证据等级 E1。

**11.2 决策矩阵**：不启动。本决策**可逆**（删两条登记 + 去掉两行装饰器即回退），属 Type-2，按 SPEC_PROCESS「先做再改」处置。
