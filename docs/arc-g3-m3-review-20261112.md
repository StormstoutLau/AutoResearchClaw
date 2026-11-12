# P-084 对 P-083 G3 M3 claim 脊柱的独立异构复核（2026-11-12）

> **性质**：Layer-0 独立异构复核（T3，零生产代码/零门禁）。不采信 [P-083 实施](../spec/arc-g3-m3-claim-spine/IMPLEMENTATION.md) 结论，全部一手重验：读码、双环境测试复跑、回归复跑、12 组异构探针（标记归属/大小写/代码围栏/重复标题/n 缺省/外部 digest/版本化目录/论文回退顺序/corrupt export/非 dict 决策/digest 口径/示例 id 误阻断链）。**异构性**：复核会话（GLM-5.3-Flash）与实施会话（DeepSeek-V4.1-Flash）为不同模型基座（RULE-5）；审查者单向权限——本报告只标记问题，不改任何实现。
> **编号说明**：本批占用 **P-084**；D-1 修复批与 M4/M5 排期**待用户裁决**（建议：P-085 修复 / P-086 M4 / P-087 M5，沿 P-077「修复批前置」先例）。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | 四文件套件 114 passed（3.13.5） | 复跑 claim_spine + claim_policy + stage_claim_hooks + offline_audit | ✅ 114 passed（1.78s） |
| V-2 | 3.11.15 同读数 | `uv run --python 3.11` 复跑 | ✅ 114 passed（1.59s） |
| V-3 | M1-M5 十文件回归 177 passed | 复跑同组合 | ✅ 177 passed |
| V-4 | `test_rc_executor` 组 270 passed | 复跑七文件 | ✅ 270 passed（121.61s） |
| V-5 | 新增测试 18 项（IMPL §5） | `git diff --cached` 计 `^+def test_` + collect | ❌ **实为 19 项**（14+2+3；stage_claim_hooks 写 2 实 3）→ R-1 |
| V-6 | 改动边界 = IMPL §1 十项 + 四文档 + session | `git diff --cached --stat`（19 文件，+1803/-27） | ✅ 无越界写入 |
| V-7 | 词表互检 = RESEARCH R-1（vendor ⊂ STATUS_ORDER，差集恰 `{speculation}`，等于 C4 enum） | 读码 `test_vendor_label_and_status_order_are_consistent` + 探针 | ✅ |
| V-8 | Stage 22 export 在 `paper_final.md` 落盘后执行 | 读码 `_review_publish.py`（L1794 写 → L2661 导出） | ✅ |
| V-9 | Stage 23 audit 视图无陈旧窗口 | 读码 `run_stage23_consistency`：首写（含 audit）→ trace 读本次 → 补 trace/digests 再写 | ✅ |
| V-10 | P-083 session 5/5 + digest 绑定 | step-gate `--expect` exit 0；`digest_bound=1`；7 行含受控回边（rebind_reason） | ✅ |
| V-11 | PROGRESS P-083 行 T1 档位词、总纲 v1.3u | 比对 | ✅ |
| V-12 | CI 固定清单含 `test_claim_spine.py` | 读 `.github/workflows/ci.yml` | ✅ |

## 2. 异构探针（X 表）

| # | 探针 | 结果 | 定性 |
|---|---|---|---|
| X-1 | 标题紧贴正文（正文与 `##` 间无空行） | 正文标记被归到**后一**标题（`[c-11111111]` 在 Preamble 却得 `§4.2`） | **D-2 P3**：块级 `ref = current` 在整块标题扫描后捕获 |
| X-2 | 大写标记 `[C-11111111]` | 不提取，paragraph_refs 静默为空 | **D-6 P3**：与 `CLAIM_ID_RE` 小写口径一致，但静默；与 U-1 同族 |
| X-3 | 代码围栏/行内代码内 `[c-…]` | 被当作正文引用计数 | 与 D-1 同根（无 fence 跳过） |
| X-4 | 两个同名 `## Results` | 同 ref `§Results`，段引不可区分 | O-1（信息性限制） |
| X-5 | `metrics_summary` 条目缺 `count` | annotation `n=1`（伪造单次样本量） | **D-3 P3** |
| X-6 | 外部 annotation 无 `evidence_digest`/locator | `skipped=1`、`ok=True`，无假红 | ✅ 与 U-3 设计一致（fail-open 面已声明） |
| X-7 | 仅版本化 `stage-14_v2/`（无 live） | annotation 写入 `stage-14_v2/`，Stage 20 live 层读空 | **D-4 P3**：锐化 U-2——不止「不消费」，产物落错目录 |
| X-8 | `paper_final.md` 缺失，17 草稿与 19 修订稿并存 | 段引取自**较旧草稿**（`§Draft`） | **D-5 P3**：实现忠实 DESIGN §8，属设计缺口 |
| X-9 | `claim_export.json` 损坏 | `claim_export_unreadable`，fail-closed 不崩溃 | ✅ 无缺陷 |
| X-10 | decisions 条目非 dict（外源篡改） | 条目被过滤；全空时 trace 早退 `ok=True` 静默放行 | **O-2**：生产 gate 恒产 dict，仅篡改面触发 |
| X-11 | digest 裸 hex（值同）/大写 hex | 值同则过；大写判 `digest_mismatch` | ✅ 与 M1 侧车严格口径一致 |
| X-12/X-12b | **gate pass 的正常 run**，论文含文法示例 id（Stage 17 prompt 自带 `[c-1a2b3c4d]`） | export `unknown_claim_marker` → trace `claim_marker_not_exported` → executor FAILED | **D-1 P2**：生产误阻断链确证 |

## 3. 缺陷

### D-1（P2）示例标记误阻断链

- **链路**：Stage 17 prompt 的文法说明自带示例 id `c-1a2b3c4d` → LLM 在论文正文/说明文字复述该 id（X-12b：gate verdict=pass）→ `export_claim_labels` 报 `unknown_claim_marker` → `verify_claim_trace` 报 `claim_marker_not_exported`（两条：示例 id 与被引用真 claim 各一条）→ `_execute_citation_verify` 返回 FAILED（`E_CLAIM_TRACE_MISMATCH`）→ **正常 run 在 Stage 23 误阻断**。
- **性质**：fail-closed 方向的假阳性（不放行坏 claim，但拦住好 run）；触发面真实——示例 id 由本批自己注入 prompt。
- **修复建议**（供修复批裁决，审查者按 RULE-5 不改实现）：① 最小——Stage 17 prompt 示例改非 hex 占位 `[c-xxxxxxxx]`（`x` 不匹配 `[0-9a-f]`，正则天然不识别）；② 加固——`extract_claim_markers` 跳过 code fence 与行内代码；③ 兜底——trace 对 `unknown_claim_marker`/`claim_marker_not_exported` 降级 warning。建议 ①+② 组合，③ 由用户裁决。

### D-2..D-6（P3）

| # | 内容 | 建议 |
|---|---|---|
| D-2 | `extract_claim_markers` 块级 ref 捕获：正文与后随标题间无空行时归属错位（X-1） | 逐行捕获 ref（标题行即时生效于其后正文、先前正文用旧 ref） |
| D-3 | `count` 缺失时 `n=1` 伪造样本量（X-5） | count 缺失时省略 `n` 或置 null |
| D-4 | 版本化 stage-14 场景 annotation 落错目录 + Stage 20 静默缺席（X-7，锐化 U-2） | annotation 固定写 live `stage-14/`；读取侧用 live-or-latest |
| D-5 | 论文回退顺序 17 草稿先于 19 修订稿（X-8，DESIGN §8 缺口） | 顺序改 22 → 19 → 17；属设计文档修订 + 实现一行 |
| D-6 | 大写标记静默忽略（X-2） | 与 D-1 ② 一并处理（提取侧 casefold 或文档声明） |

## 4. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | 重复标题产生同一段引 ref，无法区分两节（X-4）；`paragraph_refs` 为信息性字段，无阻断影响 | 记录 |
| O-2 | decisions 含非 dict 条目时被 `_load_decisions` 过滤，全空则 trace 早退 `ok=True`（X-10）；生产 gate 恒产 dict 条目，仅外源篡改触发 | 加固（与 D-1 同批可选） |
| O-3 | **P-083 IMPLEMENTATION §5 读数偏差**：新增测试写 18 项、实为 19 项（14+2+3，E1 diff 计数）——RULE-2 统计溯源项；订正须改四文档 → P-083 digest 失配 → 走受控回边（verify step_seq=4 + finalize step_seq=5 带 rebind_reason + 新 digest） | 登记面；修复批处理 |
| O-4 | `_paper_text` 只查 live 固定路径，无 live-or-latest 回退，与 claims/annotations 的 D-1 版本选择口径不一致 | 一致性；随 D-5 统一 |
| O-5 | `CODE_WIKI.md` 不存在 → feature→P 映射退化为 PROGRESS 末行兜底；P-083 与 P-084 同属一个暂存单元（batch 模式）时，P≥82 门禁强制每个声明行含 feature 链接 → P-084 行引用复核对象 `spec/arc-g3-m3-claim-spine/`，末行胜出使派生视图将该 feature 的主 P 显示为 P-084（显示偏差，实现批仍为 P-083） | 登记；A-33 劫持面在「同提交复核」场景的结构性代价，供门禁后续轮评估 |
| O-6 | X-6 证实外部 annotation 无 digest 时 fail-open（skipped 计数）——U-3 边界声明准确，无夸大 | 边界证实 |

## 5. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 复跑（E1） | V-1..V-4 | ✅ 114/114/177/270 |
| git diff --cached 计数（E1） | V-5、V-6 | ❌ 19≠18（V-5）；✅ 边界（V-6） |
| 运行时探针（E2，12 组，含对抗场景：无空行标题/大写/围栏/篡改/示例 id） | X-1..X-12 | **发现 1 P2 + 5 P3** |
| 静态读码（E3） | V-7..V-9、X-9/X-11 定性 | ✅ |
| 登记链核对（E1） | V-10..V-12 | ✅ |
| 盲区扫描（E4，扫描范围：5 接口 × 误阻断/误放行/静默面） | 全部 | **发现 1 项 P2**（D-1） |

## 6. 结论与处置

- **P-083 主线成立**：A3-1/A3-3 机制真实；三出口一致性与 digest 复算的 fail-closed 面完整（X-9/X-11 判红路径全部生效）；双平面语义未破坏（`consistent` 仍只由 diffs 决定）；双环境读数、回归、登记链全部复现属实。
- **1 项 P2（D-1）+ 5 项 P3（D-2..D-6）+ 6 项 O**；D-1 为 fail-closed 假阳性，建议独立修复批（P-085）处理 D-1+O-3，D-2..D-6 可并入或顺延，**待用户裁决**；M4/M5 排期随之顺延（建议 P-086/P-087）。
- 按 RULE-5 单向权限，审查者未改任何实现与 P-083 四文档；探针脚本已按零残留原则不留盘。
- 登记 P-084（T3：Layer-0 独立异构复核报告，零代码/零门禁；同型先例 P-077/P-079/P-072）。
