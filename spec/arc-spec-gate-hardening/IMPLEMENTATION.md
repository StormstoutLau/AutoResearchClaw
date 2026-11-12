---
id: arc-spec-gate-hardening-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-spec-gate-hardening-DESIGN]
upstream: arc-spec-gate-hardening-DESIGN
---

# 实施记录：Spec 门禁加固（P-081）

> **状态**：两项加固完成；读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `.github/workflows/ci.yml` | 修改 | `spec-gates` checkout `fetch-depth: 0`；新增 range 步骤（`--base` + 变更集 + `rev-list --merges`） |
| 2 | `scripts/spec/spec_map.py` | 修改 | `parse_progress_rows` 增 `basis`；新增 `row_tier()`（档位唯一实现） |
| 3 | `scripts/spec/step_enforce.py` | 修改 | `DOC_COMPLETENESS_MIN_P=81`、`REQUIRED_DOCS`、`_missing_docs()`；`_resolve_declared` 增 T1 四文档检查 |
| 4 | `tests/test_spec_map_tiers.py` | 新增 | basis 保真 + 档位三态 |
| 5 | `tests/test_step_enforce_branches.py` | 修改 | `row()` 支持档位；新增 T-6 五项（T1 缺/齐、T3 跳过、缺档位、低编号不回溯） |

**不改**：`dc_validator`、`grandfather_gate`、既有覆盖/会话/digest 判据、`BATCH_BINDING_MIN_P=129`、`EVIDENCE_MIN_P=137`。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `spec_map.parse_progress_rows` | 增 `basis` 键（向后兼容） | 旧调用方只用 `status/features` |
| `spec_map.row_tier` | `(row: dict) -> "T1" \| "T3" \| None` | 纯函数 |
| `step_enforce._missing_docs` | `(feature: str) -> list[str]` | 文件缺失即返回；测试可注入 |
| CI range 步骤 | `BASE_SHA` 缺失/全 0/不可达 → 打印跳过 | 不静默当作通过 |

## 3. 关键行为

- **CI 兜底**：`git diff --name-only BASE...HEAD` 作为 argv 传给 `step_enforce --base BASE`，覆盖整个推送/PR 范围；`rev-list --merges BASE..HEAD` 逐个跑 `--check-merge`。
- **四文档**：仅对 `docs_features`（本次变更的 feature）检查；所属 P 的档位为 T1 时要求四份齐全，T3 跳过，档位缺失判红。
- **阈值**：81，从本批起生效；P ≤ 80 不回溯。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `git diff A...B` / `rev-list --merges` | CI range | git 2.x | ✅ |
| GitHub Actions `github.event.before` / `pull_request.base.sha` | BASE 选择 | 官方上下文 | ✅（不可达有防御） |
| Python 3.11 | `spec_map` / `step_enforce` | 既有环境 | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数

| 项 | 读数 |
|---|---|
| 新增测试 | **+8**（spec_map 3 + step_enforce 5）；两文件合计 **16 passed** |
| 红→绿 | 红：**8 failed**（`basis` 缺失、`row_tier`/`_missing_docs` 不存在）。绿：**16 passed** |
| 本地 range 模拟 | `--base HEAD~1`（P-078..P-080，29 路径）→ **exit 0**（mode=batch，3 P / 3 session / 3 feature） |
| CI 结构读码 | `fetch-depth: 0`、`BASE_SHA=before\|\|base.sha`、全 0/不可达跳过、`mapfile`、`--base`、`rev-list --merges` 均在位 |
| 回归 | 既有 8 项分支判定零回归；`grandfather_gate --selftest` 11/11；`dc_validator --selftest` 39/39 |
| 门禁 | DC 4 文件 0 违规；step-gate 5/5；console/repo_stats 一致；rework PASS；pre-commit **9/9 Passed** |
| 自证 | 首次提交被**本批新增判据**拦下（P-081 行事项列含 `\|\|` 导致列错位 → 缺档位）；改为文字描述后通过 |

## 6. 验收边界

- **范围而非逐提交**：中间提交违规、末态合规时不判（U-1）。
- **档位标注可信度**：只校验 T1/T3 词存在，不核裁剪理由（U-2）。
- **历史 feature**：不主动扫描全仓；只在本次变更时检查。
- `before`/`base.sha` 语义若变化，代码退化为「打印跳过」而非「静默通过」。
