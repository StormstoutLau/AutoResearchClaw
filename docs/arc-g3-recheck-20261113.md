# P-090 G3 收口复评（2026-11-13）

> **性质**：Layer-0 独立异构复评（T3，零生产代码/零门禁）。只核 P-088 遗留的 2 项 P2（A3-7/A3-8）+ 1 项 P3（D-3 编号）。**异构性**：复评会话（GLM-5.3-Flash）与实施会话（DeepSeek-V4.1-Flash）为不同模型基座（RULE-5）；单向权限，只标记问题。
> **基线**：`e17ca8a`（P-088/P-089 已提交）。**编号**：本批占用 **P-090**；建议 **P-091** 修复新发现缺陷后 **P-092** 再复评。

## 1. 复评结论速览

| 项 | P-088 缺口 | P-089 修复 | 复评结果 |
|---|---|---|---|
| A3-7 | 仅渲染点日志、claim 无版本 | ContextVar + `LLMClient.chat` 日志 + Stage 17 侧车 + export 字段 | ✅ **闭合**（探针 5/5） |
| A3-8 | 无 handback 生产者/路由 | Stage 17 阻断产 handback + `_apply_handback_guard` | ⚠️ 生产/路由成立，但**子范围误判** → **D-1 P2** |
| D-3 | A3-7/A3-8 编号互换 | 按总纲统一 P-087 文档 | ✅ **闭合**（grep 一致） |

**G3 仍不可收口**：A3-8 的修复在生产路径引入新的误阻断。

## 2. A3-7 复评（✅ 闭合）

| # | 探针 | 结果 |
|---|---|---|
| X-1 | `for_stage` 后 `get_prompt_version() == sp.version` | ✅ |
| X-2 | 请求日志行实际输出：`llm.request prompt_version=sha256:2df3... model=test-model` | ✅ |
| X-3 | `log_prompt_version` 返回当前版本 | ✅ |
| X-4 | Stage 17 侧车 → `claim_export.json` 每条携带 `prompt_version` | ✅ |
| X-5 | 无侧车时 export 不加键（向后兼容） | ✅ |
| V-1 | 既有测试：`test_for_stage_sets_request_context_version`、`test_export_includes_stage17_prompt_version`、`test_export_maps_...`（无版本键） | ✅ 93 passed 套件内 |

## 3. A3-8 复评（⚠️ 1 项 P2）

| # | 探针 | 结果 |
|---|---|---|
| X-6 | 真实跑 Stage 17 `blocked_no_metrics`：PAUSED + `handback.json` 落盘（reason/scope 正确） | ✅ |
| X-7 | runner guard：越界 `tool:shell` → FAILED + `E_HANDBACK_SCOPE` + `decision=handback_scope` | ✅ |
| **X-8** | **子范围误判**：Stage 17 写 `stage:12-14`，默认 mandate 为 `stage:1-23` → `validate_handback` 抛 `E_HANDBACK_SCOPE` | ❌ **D-1 P2** |

### D-1（P2）：scope 离散匹配与范围记法语义不一致

- **根因**：`mandate.scope` 用范围记法 `stage:1-23`，`validate_handback` 却做离散集合匹配（`item not in allowed`）；Stage 17 生产的 `stage:12-14` 不在字面集合中，必然被拒。
- **后果**：真实 run 中 Stage 17 的两个暂停分支（模拟数据/无指标）会被 runner 升级为 FAILED——**fail-closed 假阳性**，暂停语义被破坏（探针日志实证：`Stage PAPER_DRAFT handback out of scope: E_HANDBACK_SCOPE: requested scope outside mandate: ['stage:12-14']`）。
- **CI 盲区**：既有测试要么用与 mandate 相同的字面量（`stage:1-23`），要么只测 Stage 17 函数层不经过 runner guard，因此全绿未报警（相关套件 93 passed 复跑确认）。
- **修复建议（P-091）**：
  1. `validate_handback` 支持范围记法：mandate 条目 `stage:A-B` 覆盖 handback 条目 `stage:C-D` 当且仅当 `[C,D] ⊆ [A,B]`；`tool:*` 保持精确匹配；
  2. 补「子范围放行」端到端测试（真实 scope 组合 + runner guard），封堵本次 CI 盲区；
  3. 备选最简方案：Stage 17 的 `requested_scope` 改为 `stage:1-23`——但粒度信息丢失，不推荐。

## 4. D-3 复评（✅ 闭合）

- 总纲 L423：`A3-7 | 每次 LLM 请求记录 prompt_version...`；L424：`A3-8 | 越界子任务走 StageHandback...`
- P-087 [DESIGN L118-119](../spec/arc-g3-m4-m5-governance-k5/DESIGN.md)、[IMPLEMENTATION L73-74](../spec/arc-g3-m4-m5-governance-k5/IMPLEMENTATION.md)：A3-7=prompt_version、A3-8=StageHandback。
- 两处一致，编号互换已消除。

## 5. 基线与回归

- 基线 `e17ca8a`；P-089 关键套件复跑 **93 passed**（9.23s），确认 CI 盲区而非测试回归。
- 编号顺延：**P-091 修复 / P-092 复评**。

## 6. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| 运行时探针（E2，8 项，含真实 Stage 17 执行与 runner guard） | X-1..X-8 | A3-7 5/5 ✅；A3-8 2/3 ✅ + **1 项 D-1 P2** |
| pytest 复跑（E1） | 既有 P-089 套件 | ✅ 93 passed（CI 盲区对照） |
| grep 一致性（E1） | D-3 | ✅ 编号已统一 |
| 盲区扫描（E4，扫描范围：scope 语义 × mandate/handback 组合） | A3-8 | **发现 1 项 P2** |

## 7. 处置

- 本批零代码/零门禁；未改任何实现。
- 登记 P-090（T3，同型先例 P-088/P-086）；建议 P-091 修复 D-1（范围语义）+ 补端到端测试，P-092 复评后收口 G3。
