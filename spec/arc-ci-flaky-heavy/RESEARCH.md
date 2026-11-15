---
id: arc-ci-flaky-heavy-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-cd-research]
upstream: null
---

# 调研文档：F-1/F-2 时序 flaky 的 `heavy` 化取证与边界（P-125 实施批）

> **Feature**：P-125，把两个已登记的 CI flaky 用例（F-1/F-2）从 CI 默认集合隔离到 `heavy` 集合，保持覆盖守卫双向闭合（T1 完整管线，动 `tests/` 与登记表，零产品代码）。
> **Spec 步骤**：Step 1-2。
> **结论先行**：F-1 已在 **四个矩阵位全部误红一次**（3.11 → 3.14 → 3.13 → 3.12），F-2 一次（3.11），两者都是**单测级时序竞争**、rerun 即绿、与任何批次的文档改动零交集。根因尚未定位到可确定性复现的竞争窗口，故本批不猜根因、不做产品语义改造，只执行 P-123 已裁决的登记路径：`heavy` 隔离（声明源 + 运行时开关同改），并把「覆盖损失」转成可复核的补偿项。

## 1. 调研目标

1. **事实**：F-1/F-2 的误红是否稳定落在同一断言、同一机制？落点是否与矩阵位/负载相关？
2. **能力**：本仓现有 `heavy` 机制（marker + 登记表 + 闭合守卫）能承受什么粒度的隔离？边界在哪？
3. **代价**：隔离会移除多少 CI 覆盖？有没有不新增依赖的补偿路径？

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | 两个用例源码、`poll_for_response` 实现、`ci_coverage_check.py` 四条闭合规则、`ci_exclusions.yaml` 空表契约、`pyproject.toml` marker 注册、`ci.yml` tests 命令 | ✅ 全部一手 |
| 远端 run 取证（E1） | `gh run view --log-failed` 四次 F-1 + 一次 F-2 的失败栈与耗时 | ✅ |
| 历史登记（E1） | [PROGRESS.md](../../docs/PROGRESS.md) P-123（首登 + RI-2 触发）/ P-124（第三、四次复现） | ✅ |
| 外部文献 | 未引入 —— 本批为仓内测试治理，外部方案（`pytest-rerunfailures` 等）在 §4.2 按「新增依赖」判否，无需文献支撑 | 降级已记录 |

**降级链记录**：无静默跳过；未联网检索是**显式降级**（判据：问题面完全在仓内，且候选方案取舍由本仓 fail-closed 纪律直接裁决，不依赖外部最佳实践）。

## 3. 调研发现

### 3.1 F-1：轮询超时先于写出落地（E1）

用例 [test_hitl_advanced.py](../../tests/test_hitl_advanced.py) L73-L87：另起线程 `time.sleep(0.3)` 后写 `response.json`，主线程以 `poll_for_response(poll_interval_sec=0.1, timeout_sec=5)` 等待，L87 断言 `result.action == HumanAction.REJECT`。

被测实现 [file_wait.py](../../researchclaw/hitl/file_wait.py)：

- L76 `deadline = time.monotonic() + timeout_sec`；L87 `while time.monotonic() < deadline`；
- L99 `FileNotFoundError` 静默跳过（正常路径）；L101-L110 解析类异常计数，连续 5 次即 `break`；
- L114 `time.sleep(poll_interval_sec)`；L117-L120 退出循环后按 `auto_proceed_on_timeout` 返回 APPROVE 或 **ABORT**。

失败读数为 `ABORT`（P-123 记录 1 failed / 3713 passed / 66 skipped），即循环在收到响应前退出。能产生该结果的路径只有两条：**解析类异常连续 5 次触发 `break`**，或**deadline 到期**。0.3s 的写延迟相对 5s 超时不可能自然耗尽 deadline，故真实竞争面在「读 → 解析」窗口（写入侧 `write_response` 与读取侧的原子性/清理交错），而非超时设置过小。**结论：超时不是根因，单纯放大 timeout 无效。**

### 3.2 F-2：续期线程与断言的时序竞争（E1）

用例 [test_supervisor.py](../../tests/test_supervisor.py) L103-L113：`LeaseKeeper(..., interval=0.02)` 启动后，另一写者以「未来 1 小时」接管租约，随后 `time.sleep(0.15)`、`stop()`，L113 断言 `lost` 非空。

失败为 `AssertionError: keeper 必须在租约丢失时回调`。`interval=0.02` 与 `sleep(0.15)` 理论上留出 7 个续期周期，但线程调度被抢占（矩阵并发、容器 CPU 抖动）时，单次 sleep 被拉长到覆盖不足一个检查周期即失败。**结论：断言依赖「墙钟 sleep ≥ 若干调度周期」的隐式前提，该前提在 CI 上不成立。**

### 3.3 落点分布：与矩阵位无关，与并发负载相关（E1）

| 事件 | run | 矩阵位 | 断言 |
|---|---|---|---|
| F-1 首次 | 43714077075 attempt 1 | 3.11 | `ABORT == REJECT` |
| F-1 二次 | 43718585981 attempt 1（PR #4） | 3.14 | 同上 |
| F-1 三次 | 43727171392 attempt 1（P-124 dispatch） | 3.13 | 同上 |
| F-1 四次 | 43727260130（P-124 连推探针） | 3.12 | 同上 |
| F-2 唯一 | 43715205467 attempt 1 | 3.11 | 「keeper 必须在租约丢失时回调」 |

同一 commit 的另一次事件 run 或 attempt 2 均全绿。P-123 已记录「单点矩阵、落点不固定」；P-124 补足 3.12/3.13 后，**四矩阵位全数命中**，故「某 Python 版本专属」的假设被排除，指向共享宿主资源竞争。

### 3.4 现有 `heavy` 机制的真实能力边界（E1）

[ci_coverage_check.py](../../scripts/spec/ci_coverage_check.py) 的双向闭合有四条（L5-L13）：

| 规则 | 内容 | 对本批的约束 |
|---|---|---|
| ① | R ⊆ L：登记项必须指向 `git ls-files tests/test_*.py` 内的文件 | 登记粒度是**文件**，不是 node id |
| ② | L \\ R ⊆ C：未登记文件必须真被 CI 收集 | 登记文件从闭合校验中豁免 |
| ③ | 登记项 `marker` 必须为 `heavy`，且文件内含 `pytest.mark.heavy` | 打标必须在被登记文件内 |
| ④ | 文件内含 `pytest.mark.heavy` 就必须在 R 内 | **打标与登记必须同 diff 落地** |

`ci_exclusions.yaml` 当前为 `version: 1` + `exclusions: []`（[文件](../../tests/ci_exclusions.yaml) L1-L8，五字段契约写在注释里）；`pyproject.toml` L63-L65 已注册 marker；CI 侧 [ci.yml](../../.github/workflows/ci.yml) L124 为 `python -m pytest tests -m "not heavy" -q`。

**边界**：机制只能按文件隔离。把两个用例拆到独立文件可获得更细粒度，但需移动测试代码（含类/夹具上下文），diff 面与回归面都更大；不拆则整文件从「未登记必须被收集」的守卫中豁免。

### 3.5 覆盖代价可量化（E1）

- 隔离后 CI 少执行 **2 个用例 / 矩阵位**（4 矩阵 × 2 = 8 次执行/run）。
- 文件层面仍会被收集（同文件其余用例照跑），故 `C` 的文件集不变，仅收集的**用例数**下降。
- 本机 `--collect-only` 当前基线 3778（P-114 读数）⇒ 预期 3776。

## 4. 综合分析

### 4.1 关键发现总结

1. 两例均为单测级时序竞争，断言依赖墙钟等待，rerun 即绿，与文档改动零交集。[置信度: ★★★★★]
2. F-1 的 `ABORT` 不可能由 5s 超时自然产生，根因在读/解析窗口；放大 timeout 是无效修复。[置信度: ★★★★☆]
3. 落点覆盖四矩阵位 ⇒ 排除版本特异性，指向宿主负载竞争。[置信度: ★★★★☆]
4. 现有守卫强制「文件级登记 + 双改同步」，这是可执行的最小隔离粒度。[置信度: ★★★★★]
5. 隔离代价 = 8 次执行/run，可用「`pytest -m heavy` 手动/定期复核」补偿而不新增 CI job。[置信度: ★★★★☆]

### 4.2 候选方案与排除理由

| 方案 | 说明 | 判定 |
|---|---|---|
| A `heavy` 隔离 | 打标 + 登记，CI 默认排除 | **采用**（P-123 已裁决；可逆、零依赖、契约内） |
| B 时序稳健化 | 改用事件/`tmp_path` 轮询 + 等待条件替代固定 sleep | 否决于本批：需改产品判定边界（`file_wait` 语义、`LeaseKeeper` 检查周期），根因未定位时等于盲改 |
| C `pytest-rerunfailures` | 单测级重试 | 否决：新增依赖；把信号变成重试次数，会掩盖真实回归 |
| D 拆文件 + 仅登记新文件 | 粒度更细的隔离 | 否决：需搬移测试代码，diff 与回归面大于收益 |

### 4.3 研究空白

仓内尚无「heavy 集合的定期执行路径」——隔离后这两条行为只在本机手动跑时被覆盖。本批不改 CI 结构，故只登记为未决项（U-2），不自行扩权新增 job。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 技术声明验证

| 声明 | 证据 | 状态 |
|---|---|---|
| F-1 失败实得 `ABORT` 且为 1 failed / 3713 passed / 66 skipped | P-123 PROGRESS 行 + run 43714077075 日志 | ✅ E1 |
| F-1 落点含 3.12/3.13 | P-124 CHECKLIST 行 86/行 87 证据列 | ✅ E1 |
| guard 为文件级登记，且规则④强制双改同步 | `ci_coverage_check.py` L90-L121 读码 | ✅ E1 |
| CI 命令为 `-m "not heavy"` | `ci.yml` L124 | ✅ E1 |
| 本机收集基线 3778 | P-114 CHECKLIST §2.4 证据列 | ✅ E1 |

### 5.2 待修正项

- [x] 无文献引用，故无 arXiv/DOI 待核项。
- [ ] 「解析类异常连续 5 次」为代码路径推断，未用插桩证实 —— 按 U-1 保留，不在本批猜测。

## 6. 对设计的输入

### 6.1 可用的技术方案

A（heavy 隔离）为唯一满足「零产品代码 + 契约内 + 可逆」的选项；B/C/D 的否决理由见 §4.2。

### 6.2 关键约束

1. marker 与登记必须同 diff（规则④），否则门禁红。
2. `reason` 字段必须诚实区分「外部依赖」与「时序竞争」，不能沿用模板话术。
3. 产品代码（`researchclaw/`）必须零改动。
4. 每个 heavy 用例需能在 `pytest -m heavy` 下独立运行，否则隔离即掩盖失效。

### 6.3 风险

- **覆盖漂移**：登记文件被规则②豁免，若其未打标用例后续脱离 CI 收集，守卫不会报警（结构性风险，转 I-2 与 U-2）。
- **marker 语义稀释**：`heavy` 的注册描述原为「需要真实外部依赖或资源」，时序 flaky 与之不严格相符，若不改描述则声明源说谎。
- **转移而非治愈**：F-1/F-2 的行为缺陷仍在，只是不再阻断合入。

### 6.4 未决项登记（四元块）

- **U-1 F-1/F-2 根因未定位**
  - **判据**：能钉死竞争窗口（读/解析交错的具体交错点，或续期检查周期的可复现缺口），并用确定性用例固定。
  - **触发条件**：`pytest -m heavy` 复核连续 2 次失败，或该两处行为出现功能回归报告。
  - **当前倾向**：F-1 在读→解析窗口（`file_wait.py` L99-L110），F-2 在「sleep 长度 vs 检查周期」的隐式前提（`test_supervisor.py` L111-L113）。
  - **证据等级**：E2（读码推断 + 失败读数，未插桩）。

- **U-2 heavy 集合无定期执行路径**
  - **判据**：heavy 集合进入至少一条非人工触发的执行路径（夜间/周常 schedule 或本地 pre-push 选项）。
  - **触发条件**：CI 触发器扩容（新增 `schedule`）排期时，或连续 2 个批次未手动跑 `pytest -m heavy` 时。
  - **当前倾向**：本批不新增 job（避免扩权）；由 PROGRESS 观察项记录复核节奏。
  - **证据等级**：E1（现状为空）。

## 7. 参考文献

（无外部文献；证据全部为仓内一手读码与远端 run 日志，见 §5.1。）

## 8. 独立复审（2026-11-16，独立上下文子代理证伪式）

- **方式**：独立上下文复审代理对 17 组宣称做证伪式复核（实施面 4 / 机械校验 6 / 文档面 6 / 范围卫生 1），全部证据为复审侧一手复跑产出，非实施侧转述。
- **判定**：15 组 CONFIRM、2 组 PARTIAL、0 组 REFUTE。机械读数独立复跑零漂移：`ci_coverage_check --check` exit 0（L=149/R=2/C=149）、`pytest -m heavy -q` 2 passed/3778 deselected、`-m "not heavy" --collect-only` 3778/3780、四文档 sha256 与 session evidence_digest 逐字符一致、pre-commit 10 钩子全 Passed 且零残留；并实证 [ci.yml](../../.github/workflows/ci.yml) tests job 含 `-m "not heavy"`（L124），排除面真实生效。
- **PARTIAL ×2**：① 实施侧门禁宣称的 spec_runner 路径笔误（真实路径 `tools/spec_runner/spec_runner.py`，非 `scripts/spec/spec_runner.py`），且 `step_enforce --doc-digest` 模式只打印 digest 块、digest_bound 读数须走默认模式——措辞问题，非批次缺陷；② `dc_validator docs/PROGRESS.md` 实为 skip 级通过（PROGRESS 无 front-matter、不在 DC 契约），exit 0 属实但校验强度有限。
- **复审发现 P3 ×3**：P3-1 路径笔误（如上，实施记录按真实路径为准）；P3-2 session 异构性声明缺失（先例 P-106/P-120 均显式声明 RULE-5）→ 已补入 [PROGRESS.md](../../docs/PROGRESS.md) P-125 行；P3-3 dc_validator 强度表述（如上）。无 P1/P2，结论：可进入 commit 阶段。
- **复审基座**：GLM-5.3-Flash（复审子代理）vs DeepSeek-V4.1-Flash（实施会话，session jsonl model 字段）——基座级异构达成（RULE-5）。边界：远端 run id 属 E1 宣称，复审本机不可复验，按文档内部一致性核对；复审范围为 2026-11-16 快照。
