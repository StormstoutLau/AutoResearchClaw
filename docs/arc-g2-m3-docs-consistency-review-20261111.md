# P-054..P-058 四文档一致性审查报告（2026-11-11）

> **性质**：Layer-0 一致性审查（T3，零代码/零门禁）。对象：[RESEARCH v1.1](../spec/arc-g2-m3-implementation/RESEARCH.md) / [DESIGN v1.0](../spec/arc-g2-m3-implementation/DESIGN.md) / [IMPLEMENTATION v1.0](../spec/arc-g2-m3-implementation/IMPLEMENTATION.md) / [CHECKLIST v1.1](../spec/arc-g2-m3-implementation/CHECKLIST.md) 全文交叉比对 + 机检 + 探针。

## 1. 审查方法

| 手段 | 内容 |
|---|---|
| 全文交叉 | 退出码/require_lean/深度映射/文件清单/测试计数四文档逐项比对 |
| 机检 | front-matter 版本与状态；DESIGN JSON 样例 × C1/C4 schema；跨文档关键词计数 |
| 探针 | 白名单去 `USERPROFILE` 后 `lake --version`（O 风险点实证） |
| 读码 | `policy.py` 优先级 vs DESIGN §7 O-B 注；`proving_runtime.py:161/287-289` 指针 |

## 2. 一致性确认（T 表）

| # | 项 | 结果 |
|---|---|---|
| T-1 | JSON 样例 3 处（request.claim / response.run / response.claim_record）schema | ✅ 全 PASS（O-2 修复后复跑） |
| T-2 | 退出码表三文档一致（0/65/75/78；77/85 保留） | ✅ 无残留「77=能力不可用」「failed→stage1」旧文 |
| T-3 | `require_lean` 语义（DESIGN §4.2 = IMPL §3.1/§2.3 = CHECKLIST §1） | ✅ |
| T-4 | `timed_out` 机制（DESIGN §2/§6.3 = IMPL §1/§2.3 = CHECKLIST §2） | ✅ |
| T-5 | 文件清单（DESIGN §2 ⊆ IMPL §1 九行） | ✅ |
| T-6 | 单元 8 / live L-A..L-H 计数 | ✅ 三文档一致 |
| T-7 | C4 14 必填（DESIGN §5.1/§5.2 = IMPL §3.2 = CHECKLIST §3） | ✅ |
| T-8 | DESIGN §7 O-B 优先级注 vs `policy.py` 短路顺序 | ✅ 逐条一致（sidecar 流程内） |
| T-9 | 指针类引用（`config.py:194`、`proving_runtime.py:161/:287-289`） | ✅ 全部实存 |
| T-10 | 超时缓冲 `timeout_s+30`（DESIGN §5.1/§6.1 = IMPL §3.2 默认 330） | ✅ |
| T-11 | **白名单探针**：去 `USERPROFILE` 后 `lake --version` | ✅ rc=0（elan 4.2.0 known-folder 兜底），白名单不阻塞 |
| T-12 | P-056/P-058 session 五步链 + 锚点 | ✅（commit 时 step-enforce 全过） |

## 3. 发现

### 缺陷：无

四文档无幻觉、无 D 级不一致；D-A/D-B/D-C 与 O-1..O-5、O-A..O-D 的修复在四文档中口径统一。

### 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | **版本号未随修订递增**：DESIGN/IMPLEMENTATION 经 P-056/P-058 两轮内容修订仍为 `version: 1.0`（RESEARCH 1.1、CHECKLIST 1.1 已递增）。P-059 顺带 DESIGN→1.1、IMPLEMENTATION→1.1 | 治理 |
| O-2 | RESEARCH §7「接口草案」与 DESIGN §5 已漂移（claim 为投影、`toolchain` 字段已废、`lean_available` 扁平键、`inputs_digest` 占位符），且无「以 DESIGN §5 为准」指针。草案是历史记录可保留，建议 §7 头部加一行指针 | 文档 |
| O-3 | DESIGN §7 两行措辞过时：「编译失败」行 status 上限写 "≤ latex"——修正后实为 `FAILED`（`latex_ok=False` 直落）；「lake 缺失」行 "≤ latex_verified/numerically_verified" 在 lean_check 模式下**无数值证据**，应写「不提升（保持请求 status）」 | 文档 |
| O-4 | `request_id` 字符集约束（`[A-Za-z0-9._-]`）仅在 IMPL §3.3；DESIGN §5.1 应补一行 | 文档 |
| O-5 | **vendor 同步**：P-057/AP 将改 `datatypes/config.py`（`timed_out`），该文件在 P-049 vendor 清单内，vendored 副本停于 `bd95f02`。P-059 须择一：随批 re-vendor（文件头 Modified 声明 + `SOURCE.json` 重算 sha256）或在 `SOURCE.json` 登记 pending-divergence；否则 vendor 与上游漂移无痕 | 合规（V-6） |
| O-6 | 白名单建议补 `USERPROFILE`：探针证实本机 elan 4.2.0 兜底可用，但不同 elan 版本的 home 解析有差异，一行保险；L-A 会兜住 | 实现注意 |
| O-7 | IMPL §2.3 无 O-C 判定指针（DESIGN §7 为权威）；建议 step 7 加半句 `startswith("rejected:")`，避免施工者只读 IMPL | 文档 |

## 4. 结论

- **排除幻觉**：12 项一致性确认全部通过；所有文件/行号/提交指针实存；优先级注与 `policy.py` 源码逐条吻合；无残留旧口径（77/failed→stage1 均已清除）。
- **无 D 级不一致**；O-1（版本号）为治理项，O-2..O-4/O-6/O-7 为文档级，O-5 为 vendor 合规项（V-6）——均随 **P-060**（施工批，编号由 P-059 让位）落实，其中 O-A 类一行订正可随施工批先改文档再写码。
- 四文档自 P-054 以来经 P-055/P-057 两轮复审 + P-056/P-058 两轮修复，D 级问题清零；设计包达到可施工状态。
