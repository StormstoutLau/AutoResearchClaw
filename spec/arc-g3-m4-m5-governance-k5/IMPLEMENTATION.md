---
id: arc-g3-m4-m5-governance-k5-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-m4-m5-governance-k5-DESIGN]
upstream: arc-g3-m4-m5-governance-k5-DESIGN
---

# 实施记录：G3 M4+M5 合并批（P-087）

> **状态**：施工完成；读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/runtime/mandate.py` | 新增 | `RunMandate`、`ensure_run_mandate`、`StageHandback`、`write_handback`/`read_handback`/`validate_handback`、`prompt_version` |
| 2 | `researchclaw/knowledge/k5_refs.py` | 新增 | `K5Ref`、`parse_refs`、`resolve_refs`、`check_k5_refs`、`bib_keys_from_text` |
| 3 | `researchclaw/prompts/manager.py` | 修改 | `PROMPT_BANK_VERSION`、`RenderedPrompt.version`、渲染点计算与日志 |
| 4 | `researchclaw/pipeline/runner.py` | 修改 | mandate 幂等写入、handback 暂停路径校验、`retrieval_degraded` summary 字段 |
| 5 | `researchclaw/pipeline/stage_impls/_review_publish.py` | 修改 | retrieval 注记与报告、Stage 22/23 K5 双阻断、`k5_refs.json` |
| 6 | `tests/test_mandate.py` | 新增 | 7 项 M4 测试 |
| 7 | `tests/test_k5_refs.py` | 新增 | 7 项 K5 单元测试 |
| 8 | `tests/test_k5_wiring.py` | 新增 | 3 项 Stage 22/23 接线测试 |
| 9 | `.github/workflows/ci.yml` | 修改 | 固定清单加入三个新测试文件 |

**不改**：C4/AR/claim 判定、既有错误码、Stage 18-21 业务逻辑。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `ensure_run_mandate` | `(run_dir, *, run_id, requester=..., scope=..., strength=..., policy_version=2, created_at=None) -> RunMandate` | 已存在则读；不覆盖 |
| `write_handback` | `(stage_dir, handback, mandate) -> Path` | 先校验后写；越界不落盘 |
| `read_handback` | `(stage_dir) -> StageHandback \| None` | 缺失返回 None |
| `prompt_version` | `(*, system, user_template, model_role, prompt_bank_version) -> str` | 纯函数 |
| `parse_refs` | `(text) -> list[K5Ref]` | 纯函数 |
| `resolve_refs` | `(refs, *, kb_root=None, bib_keys=()) -> list[K5Ref]` | 只读 |
| `check_k5_refs` | `(text, *, kb_root=None, bib_keys=(), file="") -> list[dict]` | 只读 |

## 3. 关键行为

- **mandate**：`execute_pipeline` 开头写入；嵌套/续跑读同一文件；run_id 不一致抛错。
- **handback**：暂停/阻塞时若 `stage-NN/handback.json` 存在则校验；越界把结果改为 FAILED。
- **prompt 版本**：`for_stage` 每次渲染计算并 `logger.info("prompt_version ...")`。
- **K5**：Stage 22 预检、Stage 23 终检；未解析或检查异常均 FAILED；报告写 `k5_refs.json`。
- **retrieval**：Stage 22 注记 + `retrieval_degraded.json`；summary 增布尔字段。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `hashlib` / `json` / `os` / `re` / `dataclasses` | 摘要、解析、原子写 | 3.11 全有 | ✅ |
| `researchclaw.literature.verify.parse_bibtex_entries` | BibTeX key | 仓内既有 | ✅ |
| `researchclaw.knowledge.base` | KB 目录约定 | 仓内既有 | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | **17 项**（mandate 7 + k5 7 + wiring 3） |
| 双环境 | 3.13.5 **17 passed**；3.11.15 **17 passed**（7.01s） |
| 相关回归 | 12 文件 **401 passed**（127.00s，含 `test_rc_executor`） |
| 门禁 | DC 0 违规；step-gate 5/5；step-enforce `digest_bound=2`；pre-commit **9/9 Passed** |
| 红→绿 | 红：首轮 **4 failed / 13 passed**（K5 键把句末 `.` 吃入、测试 fixture 含合法 `paper:key`）；修正末字符文法与 fixture 后 **17 passed** |

## 6. 验收边界（诚实口径）

- **A3-6**：mandate 文件级不可变与 run_id 校验已测；「跨进程并发写」不在本批。
- **A3-7**：版本在渲染点计算并写日志；无独立逐请求日志文件（U-2）。
- **A3-8**：handback 校验器与 runner 接线已实现；当前无阶段生产 handback（U-1）。
- **A3-4**：K5 双阶段阻断已测；`tb:` 用文件名 stem 解析，无 KB 索引（U-3）。
- **A3-5**：summary 字段 + 论文注记 + 报告文件；不阻断。

## 7. 风险

- 未闭合/超大 KB 时 `rglob` 变慢（U-3）。
- handback 生产者尚未出现，校验面暂为「文件存在才生效」（U-1）。
- prompt 版本日志依赖日志级别；默认 INFO 可见。
