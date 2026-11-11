# P-077 对 P-075 G3 M1 的独立异构复核（2026-11-12）

> **性质**：Layer-0 独立异构复核（T3，零生产代码）。不采信 [P-075 实施](../spec/arc-g3-m1-artifacts/IMPLEMENTATION.md) 结论，全部一手重验：读码、测试复跑（双环境）、7 个异构探针（并发/遍历/坏行/大小写/事件链尾锚/同内容去重/blob 自愈）。
> **编号说明**：本批占用 **P-077**；M2（stage_events/循环护栏）由 P-076 顺延为 **P-078**（沿 P-054 让位先例）。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | M1 21 passed（3.13.5） | 复跑 `tests/test_artifact_node.py + test_pipeline_summary_check.py` | ✅ 21 passed |
| V-2 | 3.11.15 同读数 | 临时 venv 复跑 | ✅ 21 passed |
| V-3 | runner DONE 接线 | 读码 [runner.py](../researchclaw/pipeline/runner.py) DONE 分支注册 + checkpoint | ✅ |
| V-4 | summary 改侧车写入 | 读码 `_write_pipeline_summary` → `write_summary` | ✅ |
| V-5 | `verify_tree` 五类检查 | 读码 + 既有负例（哈希/父/环/inputs/敏感） | ✅ |
| V-6 | `verify_summary` 双向 + 事件锚定接口 | 读码 | ✅ |
| V-7 | runner/checkpoint/kb/report 回归 92 | 复跑 | ✅ 92 passed |
| V-8 | 「注册失败不阻断」 | 读码 runner try/except warning | ✅ |
| V-9 | DC 四文档 0 违规 | dc_validator 复跑 | ✅ |
| V-10 | CI 清单已加两测试文件 | 读 ci.yml | ✅ |
| V-11 | 文档读数（PROGRESS P-075 行、总纲 v1.3o） | 比对 | ✅ |
| V-12 | session 5/5 | step_enforce | ✅ |

## 2. 异构探针（X 表）

| # | 探针 | 结果 | 定性 |
|---|---|---|---|
| X-1 | 双线程并发 `register_stage_artifacts`（stage 1/2） | **丢失节点**：nodes=1，无报错 | **D-1** |
| X-2 | locator `../outside.txt` | `FileNotFoundError`（register 时 is_file 检查在 run_dir 前缀下解析） | 无缺陷（register 路径安全；build_node 直调可越界，见 O-1） |
| X-3 | `nodes.jsonl` 追加坏行后 `load_nodes` | 抛 `JSONDecodeError`（fail-closed） | 无缺陷（语义同 P-063 claims 约定） |
| X-4 | 侧车摘要大写 | `E_SUMMARY_TAMPERED`（严格匹配） | 无缺陷（fail-closed 取向正确） |
| X-5 | events.jsonl 追加第二条不同 digest 的 `pipeline.summary` | 尾锚覆盖真锚，`verify_summary(require_event=True)` 信任**最后一行** | **D-2** |
| X-6 | 两个 stage 注册同内容文件 | stage-03 节点**静默丢弃**（`node_id` 不含 producer，与 stage-01 同 id） | **D-3** |
| X-7 | blob 毒化后 `build_node` 重建 | 探针判 False，**实为探针缺陷**：`build_node` 本就会用源文件覆盖 blob（自愈成功）；正确检测面是 `verify_tree`（既有测试已覆盖 blob 篡改判红） | 撤回，非缺陷 |

## 3. 缺陷

| # | 级 | 缺陷 | 根因 | 建议修法 |
|---|---|---|---|---|
| **D-1** | P2 | **并发注册丢节点**：`register_stage_artifacts` 是 read→modify→write，无锁。两个线程同时注册时后写者覆盖前写者，X-1 实测 nodes=1 且静默 | 非原子 read-modify-write | runner 内串行化（已有 GIL/单线程事实）或注册处加 `msvcrt/portalocker` 文件锁；至少在 docs 标注「非并发安全」 |
| **D-2** | P2 | **事件链锚定取尾行可被覆盖**：`_last_event_digest` 信任最后一条 `pipeline.summary`；攻击者追加一条伪造 digest 即可让被篡改的 summary 通过三向校验 | 尾锚语义 | M2 接线时改为：事件链内**所有** `pipeline.summary` 的 digest 集合必须包含当前 digest，且任一不匹配即 `E_SUMMARY_TAMPERED`；或取**第一条**（首锚）并要求后续一致 |
| **D-3** | P3 | **同内容跨 stage 节点静默丢弃**：`node_id` 未含 producer，stage-03 与 stage-01 同内容同 id，被 `by_id` 去重后 stage-03 无节点、无警告 | node_id 公式缺 producer 维度 | M0 DESIGN §3 已预留 attempt 语义；修法二选一：(a) node_id 纳入 `producer.stage`；(b) 保留去重但在 payload 记录 `duplicate_locators` 并 warning。倾向 (b)，保持 content-addressed 语义 |

## 4. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | `build_node` 直调时不校验 locator 是否在 run_dir 内（register 路径有 is_file 前缀检查兜底）；建议 M3 统一加「locator 不得含 `..` / 绝对路径」守卫 | 加固 |
| O-2 | `register_stage_artifacts` 每次全量重写 nodes.jsonl，大 run（数百节点）O(n²)；M3 若引入语义父边可改为 append-only | 性能 |
| O-3 | `attempt` 参数已入 producer 但未参与 node_id/去重；与 D-3 相关，M3 定 attempt 语义时一并裁决 | 设计输入 |
| O-4 | `_last_event_digest` 静默跳过坏事件行（与 X-3 的 nodes 坏行 fail-closed 语义不一致）；M2 修复 D-2 时统一 | 一致性 |
| O-5 | `canonical_summary` 为 JCS 兼容子集（IMPLEMENTATION 已诚实登记）；M5 若引入浮点字段需升完整 RFC 8785 | 前瞻 |

## 5. 结论与处置

- **P-075 主线成立**：V-1..V-12 全过；21 项测试与读数属实；AN-1/2/3 与 A3-2 侧车边界登记诚实（IMPLEMENTATION §4）。
- **3 项缺陷**（D-1/D-2/D-3）+ 5 项观察，建议 **P-079 修复批**：
  - D-1：注册加锁或文档标注非并发安全（P2）；
  - D-2：M2 接线事件链时改为全锚/首锚校验（P2，与 P-078 M2 同批最自然）；
  - D-3：去重告警或 node_id 纳入 producer（P3，M3 attempt 语义一并裁决）；
  - O-1..O-5 随相应批次顺带。
- 编号让位：本批占用 P-077，**M2 = P-078**、修复批 = P-079；D-2 建议并入 P-078（M2 正是事件链接线批）。
