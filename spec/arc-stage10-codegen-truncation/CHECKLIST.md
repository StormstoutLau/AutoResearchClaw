---
id: arc-stage10-codegen-truncation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-stage10-codegen-truncation-IMPLEMENTATION, arc-stage10-codegen-truncation-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：Stage 10 截断容错与出口门（P-178）

> **计数**：**23 项 = 文档 4 + 功能 8 + 不变式 5 + 错误 3 + 测试 3**。
> **状态**：功能/不变式/错误已回填；门禁与 CI 见 §6。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 有现场读数 | RESEARCH v1.1 | O-1..O-9 可复核 | ✅ | [RESEARCH.md](RESEARCH.md) §1 |
| D-2 DESIGN 覆盖实现 | 四文档 | D-1..D-5 均有落点 | ✅ | D-1↔`_close_unterminated_fence`；D-2↔三处重试；D-3↔Review 守卫；D-4↔`_entrypoint_issues`；D-5↔未改缺省 |
| D-3 IMPLEMENTATION 锚点可达 | 四文档 | ≥10 个文件/行锚点 | ✅ | [IMPLEMENTATION.md](IMPLEMENTATION.md) §1（11 行） |
| D-4 术语一致 | 四文档 | 截断/围栏/出口门/评审守卫同义 | ✅ | 四文档一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 单块截断可解析 | DESIGN §2.1 | 无闭合围栏仍返回代码 | ✅ | `test_single_block_without_closing_fence` |
| F-2 多文件截断可解析 | DESIGN §2.1 | 两个文件都被抽出 | ✅ | `test_multi_file_without_closing_fence` |
| F-3 围栏闭合幂等 | DESIGN §2.1 | 已闭合不变 | ✅ | `test_close_unterminated_fence` |
| F-4 blueprint 剥围栏 | DESIGN §2.1 | 首行 ```yaml 不影响解析 | ✅ | `test_parse_blueprint_strips_unclosed_fence` |
| F-5 blueprint 截断重试 | DESIGN §2.2 | 调用序列 8192 → 32768 | ✅ | `test_blueprint_retries_when_truncated` |
| F-6 单文件截断重试 | DESIGN §2.2 | `truncated` 时 32768 | ✅ | [code_agent.py L528-L534](../../researchclaw/pipeline/code_agent.py#L528-L534) |
| F-7 single-shot 截断重试 | DESIGN §2.2 | 空或截断都重试 | ✅ | [code_agent.py L1015-L1024](../../researchclaw/pipeline/code_agent.py#L1015-L1024) |
| F-8 出口门拦住 config-only | DESIGN §2.4 | 列出缺 guard 与 `METRIC_DEF` | ✅ | `test_config_only_main_is_rejected`、`test_runnable_main_passes` |

## 3. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 截断可解析 | DESIGN §3 | F-1/F-2 通过 | ✅ | 10 passed |
| J-2 blueprint 无闭合可解析 | DESIGN §3 | F-4 通过 | ✅ | 同上 |
| J-3 空文件不评审 | DESIGN §3 | `review_rounds=0` 且 Review 未调用 | ✅ | `test_review_skipped_when_no_files` |
| J-4 Review 改写后必重校验 | DESIGN §3 | 校验看到新内容 | ✅ | `test_review_changes_are_revalidated` |
| J-5 DONE ⇒ 可执行入口 | DESIGN §3 | 出口门在 DONE 前 | ✅ | [L1838-L1863](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1838-L1863) |

## 4. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 空 main.py | DESIGN §4 | 返回 issue | ✅ | `test_empty_main_is_rejected` |
| E-2 仅常量 main.py | DESIGN §4 | 两条 issue | ✅ | `test_config_only_main_is_rejected` |
| E-3 Review 未改动 | DESIGN §4 | 不重复校验 | ✅ | `before_review` 快照比较（[L220-L232](../../researchclaw/pipeline/code_agent.py#L220-L232)） |

## 5. 测试读数

| 项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| T-1 新用例 | CHECKLIST §2-§4 | 全绿 | ✅ | 10 passed |
| T-2 相关面 | extract/code_agent/validator | 全绿 | ✅ | 291 passed |
| T-3 全量 | 全仓 | 仅既有环境态失败 | ✅ | 3983 passed / 6 既有环境态失败（Windows shell hook、Keras 3 ×4、bash 路径）/ 108 skipped |

## 6. 门禁与 CI

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / **0 违规** |
| `step-gate` | **5/5 pass**（research → design → implement → verify → finalize） |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-178 digest_bound=1` |
| `pre-commit` | **10/10 Passed** |
| 两轮 CI | 待跑 |

## 7. 诚实边界

1. 未改 `max_tokens` 缺省；截断仍可能发生，只是可被解析并被出口门兜底。
2. 出口门只做静态检查，不执行 `main.py`；运行期零指标仍由 Stage 12 守卫负责。
3. 围栏奇偶启发式对含奇数个三反引号的代码会误判（极罕见）。

## 8. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | 重试 32768 会增加单次延迟 | 仅在 `truncated` 或抽取为空时触发 |
| P3-2 | medium | 出口门可能拒绝「不打印 METRIC_DEF 但合法」的实验 | 本仓 Stage 12 契约要求打印；拒绝优于静默失败 |
| P3-3 | low | Review 重校验会多花 LLM 调用 | 仅当文件内容变化时触发 |
