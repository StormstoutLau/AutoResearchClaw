---
id: arc-stage10-codegen-truncation-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-stage10-codegen-truncation-DESIGN, arc-stage10-codegen-truncation-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：Stage 10 截断容错与出口门（P-178）

## 1. 交付锚点

| 交付 | 文件 | 符号/行 | 行为 |
|---|---|---|---|
| 围栏闭合助手 | [_helpers.py](../../researchclaw/pipeline/_helpers.py) | `_close_unterminated_fence` [L584-L588](../../researchclaw/pipeline/_helpers.py#L584-L588) | 奇数个 ``` 时补一个 |
| 单块抽取容错 | 同上 | `_extract_code_block` [L592](../../researchclaw/pipeline/_helpers.py#L592) | 截断仍可取到代码 |
| 多文件抽取容错 | 同上 | `_extract_multi_file_blocks` [L636](../../researchclaw/pipeline/_helpers.py#L636) | 最后一个块被补闭合并入 |
| Blueprint 截断重试 | [code_agent.py](../../researchclaw/pipeline/code_agent.py) | [L278-L283](../../researchclaw/pipeline/code_agent.py#L278-L283) | `truncated` → 32768 重试 |
| Blueprint 围栏正则 | 同上 | [L287](../../researchclaw/pipeline/code_agent.py#L287) | 允许以 `\Z` 结尾 |
| Blueprint 解析兜底 | 同上 | `_parse_blueprint` [L352-L359](../../researchclaw/pipeline/code_agent.py#L352-L359) | 剥掉首尾围栏 |
| 单文件截断重试 | 同上 | [L528-L534](../../researchclaw/pipeline/code_agent.py#L528-L534) | 逐文件生成时同样重试 |
| single-shot 截断重试 | 同上 | [L1015-L1024](../../researchclaw/pipeline/code_agent.py#L1015-L1024) | 空或截断都重试 |
| Review 守卫 | 同上 | [L217-L232](../../researchclaw/pipeline/code_agent.py#L217-L232) | 空文件跳过；改写后重校验 |
| 出口门助手 | [_code_generation.py](../../researchclaw/pipeline/stage_impls/_code_generation.py) | `_entrypoint_issues` [L41-L77](../../researchclaw/pipeline/stage_impls/_code_generation.py#L41-L77) | AST 检查 guard + `METRIC_DEF` |
| Stage 10 出口门 | 同上 | [L1838-L1863](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1838-L1863) | 不可执行 → `FAILED` |
| 验收用例 | [test_codegen_truncation.py](../../tests/test_codegen_truncation.py) | 10 用例 | 围栏/blueprint/出口门/评审守卫 |

## 2. TDD 红 → 绿

1. **红**（HEAD `0a534f2` worktree）：`ImportError: cannot import name '_close_unterminated_fence'`（collection 1 error in 0.98s）。
2. **绿**：`tests/test_codegen_truncation.py` **10 passed**。
3. **回归**：`-k "extract or code_agent or validator or codegen or truncat"` → **291 passed**。
4. **全量**：见 §4。

## 3. 派生需求

| ID | 派生需求 | 来源 | 处置 |
|---|---|---|---|
| DR-1 | 围栏奇偶判断需容忍代码内反引号 | 实现 `_close_unterminated_fence` 时 | 接受误判风险；出口门会拦截不可执行结果 |
| DR-2 | 出口门需覆盖「文件不在 `files` 字典但在磁盘」的路径 | 外部 CLI agent 直接写盘 | 回退读取 `stage-10/experiment/main.py` |
| DR-3 | Review 重校验只在文件确实变化时执行 | 避免额外 LLM 调用 | `before_review` 快照比较 |

## 4. 读数

| 测试面 | 读数 |
|---|---|
| 新用例 | 10 passed |
| 相关面 | 291 passed |
| 全量 | 见 CHECKLIST §6（环境态失败与 P-172/P-174/P-175/P-177 记录一致） |

## 5. 边界

- 未修改 `max_tokens` 缺省（blueprint/单文件仍 8192，重试才 32768）。
- 未改变逐文件 vs single-shot 的选择逻辑：blueprint 修好后自然回到逐文件路径。
- 出口门要求 `METRIC_DEF` 字符串，允许以 f-string 或常量形式出现在源码中；不校验运行期是否真的走到该分支（运行期由 Stage 12 守卫负责）。
