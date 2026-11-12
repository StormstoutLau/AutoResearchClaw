# P-095 对 P-094「G3 遗留 P3 清理批」的独立异构复评（2026-11-13）

> **性质**：Layer-0 独立异构复评（T3，零生产代码/零门禁）。不采信 [P-094 实施](../spec/arc-g3-p3-cleanup/IMPLEMENTATION.md) 与[复评简报](../../p095-review-brief.md) 的任何结论，全部一手重验：HEAD 读码、双环境测试复跑、回归复跑、门禁与 digest 复算、44 组对抗探针。**异构性**：实施会话为 **GLM-5.3-Flash**（`specwf-p094-arc-g3-p3-cleanup.jsonl` model 字段），本复评为 **DeepSeek-V4.1-Flash**，满足 RULE-5 模型基座异构（本条是 P-094 之后唯一可举出真异构的批次）。**单向权限**：只标记问题，不改任何实现、spec 文档或 session 历史；探针脚本存于系统临时目录并在结束后删除，零残留。
> **编号说明**：本批占用 **P-095**；潜在修复批建议 **P-096**。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | 四文件套件 3.13.5 = 125 passed | 复跑 claim_spine + claim_policy + stage_claim_hooks + offline_audit | ✅ 125 passed（2.01s） |
| V-2 | 3.11.15 同读数 | `uv run --python 3.11 --with pytest --with jsonschema --with referencing --with pyyaml` | ✅ 125 passed（1.46s） |
| V-3 | 十文件回归 199 passed；扩展组 348 passed | 复跑两组组合 | ✅ 199 passed（7.60s）；348 passed（218.21s） |
| V-4 | `test_claim_spine` = 25 项；P-083 IMPL §5 订正读数 19 = 14+2+3 | `--collect-only` + 读码 | ✅ 25 collected；订正文「14 + 2 + 3」与 P-084 V-5 的 E1 复计一致 |
| V-5 | 改动边界 = IMPL §1 八项 | `git show --stat HEAD`（15 文件，+610/−30） | ⚠️ **O-1**：实际含 `docs/CONSOLE.md`、`docs/REPO_STATS.md` 两个派生视图，IMPL §1 未列；经比对 `78a88aa`/`e17ca8a` 两历史提交同样含这两个文件 → 属机械重生成的既有惯例，非越界 |
| V-6 | P-094 session 5/5；finalize digest 与 HEAD 逐字节一致 | `step-gate --expect`；本地复算 sha256 | ✅ exit 0；finalize 1 次、8 文件 digest 全部匹配、无 mismatch |
| V-7 | P-083 回边 seq 8-9 生效、rebind_reason 在位、digest 匹配 | `step-gate --legacy`；本地复算 | ✅ exit 0（seq 6/8 两处回边受理）；finalize 3 次、末次 `rebind_reason` 在位、4 文件 digest 全匹配 |
| V-8 | ci.yml 合法，断言用 `importlib.metadata` 元组比较 | `yaml.safe_load` + 读码 | ✅ YAML 解析通过；extras job 末步为「Assert MCP SDK version (P-094 / P-093 §6.3)」，含 `importlib.metadata` |
| V-9 | PROGRESS P-094 行（T1、双 feature、done）；总纲 v1.4f；CI 清单未变 | 比对 | ✅ 三项全真 |
| V-10 | ADD 声明 30/30 | 抽查 ADD-1/ADD-2/ADD-3 | ✅ DESIGN §1 九项 ↔ IMPL F-1..F-9 全覆盖；F-9 断言形式按 RESEARCH R-7 显式订正并留痕；每项挂缺陷编号 |
| V-11 | 六项目标修复（D-3/D-4/D-5/D-6/O-2/O-3）真实关闭 | 探针 L1-L4/F1-F2/G1-G5/D1-D3/A3/A4/A7/B1-B4 | ✅ 六项均有正向与边界证据（**O-2 见 D-1：主体成立，列表形态不成立**） |
| V-12 | P-085/P-086 修复未回退 | 探针 C1-C3、I1 + 既有 19 项测试 | ✅ 占位符（含大写形态）仍不匹配；围栏+行内码示例放行；`c-deadbeef` 判红 |

## 2. 对抗探针（X 表，44 组）

两批探针共 **44 组**（批次一 29 组、批次二 15 组），覆盖缩进块边界/未闭合行内码/IGNORECASE/fail-closed 端到端/annotation 字段面/论文回退矩阵/CI 版本解析/Markdown 形态矩阵。**4 组不符预期，同一根因**（见 D-1）。

### 2.1 不符预期项

| # | 探针 | 输入 | 实测 | 期望 | 定性 |
|---|---|---|---|---|---|
| A5 | 4 空格嵌套列表项 | `- bullet [c-11111111]` + `    - nested [c-22222222]` | 仅 `c-11111111` | 两个都提取 | **D-1a** 真实引用静默丢失 |
| A6 | 4 空格悬挂缩进续行 | 段落行 + `    across three benchmarks [c-11111111].` | `{}` | `c-11111111` | **D-1a** 同上 |
| J8 | 4 空格数字列表嵌套 | `1. step [c-…]` + `    2. nested [c-…]` | 仅首项 | 两项 | **D-1a** 同上 |
| A1 | tab 缩进代码块 | `\t[c-11111111] tab code` | 提取 | 不提取（CommonMark tab=4 空格） | **D-1b** 不对称 |

### 2.2 通过项（分组摘要）

| 组 | 覆盖 | 结果 |
|---|---|---|
| A2-A4/A7 | 3 空格不开块、低缩进闭块（无空行）、块内伪标题不改 ref、空行不断块 | ✅ 4/4 |
| B1-B4 | 行首未闭合反引号、行内三反引号、闭合跨度后标记保留、缩进行内未闭合 | ✅ 4/4 |
| C1-C3 | 小写/大写占位符均不匹配、P-085 围栏+行内码示例放行 | ✅ 3/3 |
| D1-D3 | 大写未知 id → `unknown_claim_marker` → `claim_marker_not_exported` 判红；大写已知 id 正常导出 `§Results` | ✅ 3/3 fail-closed 保持 |
| F1-F2 | 仅 `stage-14_v2/` → annotation 落 live、locator 指向 v2、digest 复算 `checked=1 ok=True` | ✅ 2/2 |
| G1-G5 | 论文回退矩阵：仅 17 / 仅 19 / 17+19 / 19+22 / 三者共存 | ✅ 5/5（19 恒优于 17，22 恒最优） |
| H1-H4 | `2.3`/`2.10`/`3.0` 通过、`1.27` 拒绝（元组比较无字典序陷阱） | ✅ 4/4 |
| I1 | 占位符 + 围栏示例 + 真实 claim → 仅真实 claim | ✅ |
| J2-J7 | 引用块、HTML 注释、`~~~` 围栏、4 空格缩进围栏（围栏优先）、CRLF、NBSP 缩进 | ✅ 6/6 |
| J1 | 标题行内 `[c-…]` 静默丢弃（P-086 O-1 沿袭） | ✅ 与既有声明一致（O-2） |
| K1-K3 | 下游影响：仅出现在嵌套列表的未发布 claim 引用 → **不报** `unpublished_claim_cited`，trace 仍 `ok=True checked=2` | ❌ 证实 D-1a 为 fail-open |
| L1-L4 | bool count → `n=1`（旧行为）、float count → 省略、count=0 → 省略、Stage 20 合并容忍缺 `n` | ✅ 4/4 |

## 3. 缺陷

### D-1（P3）缩进块启发式无列表上下文 / tab 不等价 —— P-094 F-5 引入的 fail-open 回归

**根因**（`claim_spine.py` `_INDENT_CODE_RE = r"^ {4,}\S"` + 状态机）：

1. **a：无列表上下文**——任何 ≥4 空格起首的非空行都开缩进代码块，因此 4 空格嵌套列表项、数字列表嵌套、以及段落的悬挂缩进续行中的真实 `[c-…]` 被当作代码跳过。**P-094 之前这些标记是被提取的**，故属本批引入的回归；方向为 **fail-open**（漏检），与「全部修复单向 fail-closed」的声明不符。
2. **b：tab 不等价 4 空格**——CommonMark 中制表符等价 4 空格缩进，实现只匹配空格，tab 缩进的示例代码块内标记仍被提取。方向为 fail-closed 偏松（D-1 误阻断路径的残留面），与 P-085 的修复目标不一致。

**影响**（探针 K1 实证）：未发布 claim 若仅在 4 空格嵌套列表中被引用，`export_claim_labels` 不产 `unpublished_claim_cited`、`verify_claim_trace` 仍 `ok=True`——A3-1 的「引用-发布」关系被静默绕过。

**严重度判定 P3**：触发需标记落在 4 空格缩进行内；Stage 17/19 提示词以「流动散文、禁止 bullet」为主（[shared.py](../researchclaw/prompts/shared.py) L474-515 仅允许贡献段 2-3 个 bullet），嵌套 bullet 与手工软换行在真实论文中出现概率低-中。但**回归性质与 fail-open 方向**使其不能按纯观察项处理。

**修复建议**（供 P-096 裁决，审查者不改实现）：

- 最小修：`_INDENT_CODE_RE` 只匹配「非列表项」行（排除 `^ {4,}([-*+]|\d+[.)])\s`），并把 `^\t` 纳入缩进判定；
- 更强修（CommonMark 对齐）：缩进代码块不得中断段落——仅当**前一非空行是空行/标题/围栏/列表项**时才开块；当前实现缺此上下文判定，A6 正是「中断段落」的非法形态；
- 回归护栏：把 A5/J8/A6/A1 四形态写入 `test_claim_spine.py`（正反各一），并补 K1 的下游断言。

## 4. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | IMPL §1 改动边界未列 `docs/CONSOLE.md`、`docs/REPO_STATS.md` 两个派生视图（历史提交同样包含 → 惯例而非越界） | 登记；建议后续批在 IMPL 中加一句「派生视图机械重生成」 |
| O-2 | 标题行内 `[c-…]` 仍静默丢弃（J1），且该标记会进入下一节 ref 文本；P-086 O-1 沿袭未变 | 记录；影响面极小 |
| O-3 | `count: true`（JSON 布尔）因 `bool ⊂ int` 产出 `n=1`——旧行为，非本批引入；仅外源篡改可触发 | 记录 |
| O-4 | `count: 2.0`（浮点）不产出 `n`（要求严格 int）；语义上 2.0 是合法样本量 | 记录；可否放宽留后续批 |
| O-5 | `_paper_text` 首个存在文件即返回：空的 `stage-19/paper_revised.md`（0 字节）会遮蔽 Stage 17 草稿并致段引全空 | 记录；写侧空文件属上游缺陷 |
| O-6 | HTML 注释内 `[c-…]` 被计为引用（J3）——注释非渲染正文，是否应视为示例区域无标准答案 | 记录 |
| O-7 | CI 断言取版本前两位做元组比较：`2`（无次版本）会判 <(2,1) 而失败（fail-closed 可接受）；`2.3rc1` 形式会 `ValueError` 崩溃（同样 fail-closed）；`mcp` 缺失时 `PackageNotFoundError` → 该步失败（正确） | 边界证实 |

## 5. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境输出（E1） | V-1/V-2 | ✅ 125 passed ×2 |
| pytest 回归输出（E1） | V-3 | ✅ 199 + 348 |
| collect-only / git diff 计数（E1） | V-4/V-5 | ✅ 25；边界见 O-1 |
| digest 复算（E1，本地 sha256 逐文件） | V-6/V-7 | ✅ 两 session 全匹配、rebind 留痕 |
| 运行时探针（E2，44 组，含对抗：tab/嵌套列表/悬挂缩进/未闭合码/大小写/篡改/端到端） | X 全表 | **发现 1 项 P3（D-1a/b）** |
| 静态读码（E3） | `_INDENT_CODE_RE`、`_strip_inline_code`、`_paper_text`、`_annotation_for`、`stage_hooks._annotations` | ✅ 判红/漏检定性均有代码依据；annotation `n` 无下游消费者（全仓 grep） |
| 盲区扫描（E4，扫描范围：6 类 Markdown 形态 × 误提取/漏提取 + annotation 字段面） | A/B/G/J/L 组 | **发现 2 类形态缺口**（列表上下文、tab） |

## 6. 结论与处置

- **P-094 主线成立**：六项目标修复（D-3 `n` 缺省、D-4 恒写 live、D-5 回退 22→19→17、D-6 casefold、O-2 缩进块、O-3 未闭合行内码）**全部真实关闭**；P-083 计数订正与设计缺口订正留痕完整、受控回边 digest 与 HEAD 逐字节一致；CI mcp 断言按 RESEARCH R-7 订正落地且元组比较无字典序陷阱；双环境/回归/登记链与自报读数完全一致（无 P-083 式计数偏差）。
- **fail-closed 声明不完全成立**：F-5 的缩进启发式在**列表/悬挂缩进**形态下把真实引用当示例丢弃（D-1a，fail-open 回归，K1 下游实证），并在 **tab 缩进**形态下反向漏跳示例（D-1b）。严重度 **P3**，不阻塞 G4，但建议在 G4 开工前或紧随其后以 **P-096** 收敛（改动面局限在 `_INDENT_CODE_RE` 与状态机上下文，约 10 行 + 4 项测试）。
- **处置**：G3 验收不受影响（A3-1 主体、A3-3、A3-6/7/8 均未被触碰）；P-096 修复后按先例出 **P-097** 复评闭环即可。若用户选择延后，D-1 登记为**显式遗留 P3**，不得按「零缺口」叙述。
- 按 RULE-5 单向权限，复评未改任何实现；探针脚本零残留（临时目录删除、`uv.lock` 清理、工作树仅剩本报告与登记改动）。
- 登记 P-095（T3：Layer-0 独立异构复评，零代码/零门禁；同型先例 P-084/P-086/P-090/P-092）。
