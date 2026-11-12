---
id: arc-g3-closure-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-closure-fixes-DESIGN]
upstream: arc-g3-closure-fixes-DESIGN
---

# 实施记录：G3 收口缺口修复（P-089）

> **状态**：施工完成；读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/runtime/prompt_context.py` | 新增 | ContextVar、`set/get/log_prompt_version` |
| 2 | `researchclaw/prompts/manager.py` | 修改 | `for_stage` 渲染后写 ContextVar |
| 3 | `researchclaw/llm/client.py` | 修改 | `chat` 入口记录 `prompt_version` |
| 4 | `researchclaw/pipeline/stage_impls/_paper_writing.py` | 修改 | `_write_paper_sections` 返回版本；Stage 17 写 `claim_prompt_versions.json`；两个阻断分支产 handback |
| 5 | `researchclaw/evidence/claim_spine.py` | 修改 | export 读取侧车并附加 `prompt_version` |
| 6 | `researchclaw/runtime/mandate.py` | 修改 | 新增 `write_handback_file` |
| 7 | `researchclaw/pipeline/runner.py` | 修改 | 抽出并调用 `_apply_handback_guard` |
| 8 | `tests/test_mandate.py` | 修改 | +3：上下文版本、配置变更、runner 越界 |
| 9 | `tests/test_claim_spine.py` | 修改 | +1：export 携带版本；旧用例断言无版本 |
| 10 | `tests/test_rc_executor.py` | 修改 | 3 处：阻断分支 handback 断言、`_write_paper_sections` 元组解包 |
| 11 | `spec/arc-g3-m4-m5-governance-k5/{DESIGN,IMPLEMENTATION}.md` | 修改 | A3-7/A3-8 编号按总纲统一 |

**不改**：C4 schema、AR 判定、既有错误码、Stage 18-23 业务逻辑。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `set_prompt_version` | `(version: str) -> None` | 纯上下文写 |
| `get_prompt_version` | `() -> str` | 默认空串 |
| `log_prompt_version` | `(model: str = "") -> str` | 只写日志 |
| `write_handback_file` | `(stage_dir, handback) -> Path` | 原子写；不校验 |
| `_apply_handback_guard` | `(run_dir, stage_num, result, mandate) -> StageResult` | 越界转 FAILED；其余原样 |
| `_write_paper_sections` | 返回 `tuple[str, str]` | 仅 1 个生产调用点 + 1 个测试解包 |
| `export_claim_labels` | 签名不变；条目新增可选 `prompt_version` | 侧车缺失则不加键 |

## 3. 关键行为

- **请求日志**：`PromptManager.for_stage` 设置版本 → `LLMClient.chat` 每次记录 `llm.request prompt_version=...`。
- **claim 追溯**：Stage 17 写侧车（版本 + markers）；Stage 22 export 每条附加版本。
- **handback**：Stage 17 暂停即写 `handback.json`；runner 校验；越界 FAILED。
- **编号**：P-087 文档的 A3-7/A3-8 已与总纲一致。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `contextvars` | 请求上下文版本 | 3.11 全有 | ✅ |
| `json` / `pathlib` | 侧车与 handback | 3.11 全有 | ✅ |
| `StageResult` | runner guard 返回 | 仓内既有 | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | **4 项**（mandate 3 + claim 1）；修改 3 项既有测试 |
| 双环境 | 3.13.5 关键集 **31 passed**；3.11.15 **30 passed**（1 deselected） |
| 相关回归 | 11 文件 **357 passed**（103.02s，含 `test_rc_executor`） |
| 门禁 | DC 0 违规；step-gate 5/5；step-enforce `digest_bound=2`；pre-commit **9/9 Passed** |
| 红→绿 | 红：首轮 **1 failed / 356 passed**（`TestWritePaperSections` 仍按单返回值解包）；修正解包后 **31 passed**，全量 **357 passed** |

## 6. 验收边界（诚实口径）

- **A3-7**：请求日志是 `logger.info` 行，不是独立 JSONL 文件；claim 版本通过 `claim_export.json` 暴露，不改 C4。
- **A3-8**：生产者只覆盖 Stage 17 两个阻断分支；其他暂停场景仍未产 handback。
- **A3-6**：对照测试证明 mandate 不因配置文件变化而重写；未实现运行时 scope 授权判定。
- **D-3**：只改 P-087 文档编号，未改总纲。

## 7. 风险

- 日志级别低于 INFO 时请求记录不可见。
- 侧车只在 LLM 路径写；非 LLM 模板路径无版本。
- handback 写失败仅 warning，不影响暂停结果。
