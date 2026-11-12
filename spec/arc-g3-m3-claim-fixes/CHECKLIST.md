---
id: arc-g3-m3-claim-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-12
depends: [arc-g3-m3-claim-fixes-IMPLEMENTATION, arc-g3-m3-claim-fixes-DESIGN]
upstream: arc-g3-m3-claim-fixes-IMPLEMENTATION
---

# 验收清单：G3 M3 D-1 修复（P-085）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的结论在 DESIGN 中被使用（R-1→D-1、R-2→D-2、R-5→D-4） | ✅ | DESIGN §4 决策表逐条挂来源 |
| DC-2 | DESIGN 的模块在 IMPLEMENTATION 中有对应实施 | ✅ | DESIGN §2 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 的功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-6 / API-1..API-3 |
| DC-4 | 无文档间矛盾（常量名、正则、错误码、③ 未采纳口径） | ✅ | 四文档 grep `MARKER_PLACEHOLDER`/`[0-9a-f]`/`unknown_claim_marker` 一致 |
| DC-5 | 术语一致（占位符 / 围栏 / 行内代码 / 段引归属） | ✅ | 四文档互查 |
| DC-6 | 未决项 U-1..U-3 已登记 | ✅ | RESEARCH §6.4 + CHECKLIST §11 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | 占位符不被识别为 claim id | `test_stage17_prompt_example_is_non_matching_placeholder` | `CLAIM_MARKER_RE.findall(...) == []` | ✅ | 18 passed 套件内 |
| F-2 | Stage 17 不再含合法示例 id | 同上（源码断言） | 无 `c-1a2b3c4d`；含 `MARKER_PLACEHOLDER` | ✅ | 同上 |
| F-3 | 代码围栏内 id 与伪标题均跳过 | `test_extract_markers_skips_code_fence_and_inline_code`、`test_extract_markers_ignores_heading_inside_fence` | 仅围栏外真实 id 被提取 | ✅ | 同上 |
| F-4 | 行内代码内的 id 跳过 | `test_extract_markers_skips_code_fence_and_inline_code` | 单反引号跨度不提取 | ✅ | 同上 |
| F-5 | 标题只作用于其后行（D-2） | `test_extract_markers_heading_applies_to_following_lines` | intro→§Preamble、value→§4.2 | ✅ | 同上 |
| F-6 | 真实未知 hex id 仍判红（fail-closed） | E2 修复验证（`c-deadbeef`） | `trace.ok=False` | ✅ | E2 探针输出 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `MARKER_PLACEHOLDER` | 存在于 `claim_spine`；值 `[c-xxxxxxxx]` | ✅ |
| API-2 | `CLAIM_MARKER_RE` | 正则未改（`c-[0-9a-f]{8}`） | ✅ |
| API-3 | `extract_claim_markers(text) -> dict` | 签名不变；输出结构不变 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §6） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 字面 id 规则不变 | `CLAIM_MARKER_RE` diff 为空 + F-6 | ✅ |
| INV-2 | I-2 export/trace/Stage 23 判定不变 | 既有 118 项套件全绿 | ✅ |
| INV-3 | I-3 跳过只会减少 marker | F-3/F-4 + E2 对照 | ✅ |
| INV-4 | I-4 空白分块语义测试保持通过 | `test_extract_markers_maps_sections` | ✅ |
| INV-5 | I-5 错误码不变 | diff 无错误码增删 | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 幻觉出的合法 hex id | 论文含 `[c-deadbeef]` | `E_CLAIM_TRACE_MISMATCH` | ✅ |
| E-2 | 围栏内伪标题 | 围栏内 `## Fake Section` | 不改变段引 | ✅ |
| E-3 | 未闭合围栏 | 仅有开围栏 | 其后全部视为代码（U-1） | ✅ 文档化 |

## 6. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 四文件套件 118 passed（2.15s） |
| C-2 | Python 3.11.15 | ✅ | 118 passed（3.25s） |
| C-3 | 既有 M1-M5 回归 | ✅ | 十文件 181 passed |

## 7. ADD 审计（Step 10）

### 7.1 四阶段

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §1 四项修复、§2 常量/算法全部有实现 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | ③ 未采纳、判定未改、错误码未改；D-2 为附带修复已登记 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 新增行为均有 R-1/R-2/R-4 依据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | 误阻断链真实关闭（E2）；真实未知 id 真实阻断（E-1） | 意图一致 | ✅ |

### 7.2 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | 未闭合围栏会把其后全部正文视为代码，marker 静默漏检 | 读码 `in_fence` 单向翻转；U-1 | 后续可加「未闭合围栏」warning |
| P3 | 多反引号行内代码未处理 | 读码 `_INLINE_CODE_RE` 仅单反引号；U-2 | 按真实论文形态再评估 |
| P3 | O-3（P-083 IMPL §5 测试计数 18≠19）未在本批订正 | P-084 O-3 | 后续批次订正并走 P-083 受控回边 |

### 7.3 ADD Iron Law 检查

- [x] 断言恒真式：F-1 断言空列表、F-6 断言精确错误路径
- [x] 单文件检查盲区：提取器单测 + 源码提示词断言 + E2 端到端
- [x] 设计文档独有约束无测试：I-2/I-5 由既有套件与 diff 证据覆盖
- [x] 修正阻断性项无测试：D-1 两段各有独立用例

### 7.4 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境输出（E1） | F-1..F-5、C-1/C-2 | ✅ 118 passed ×2 |
| pytest 回归输出（E1） | INV-2/I-4、C-3 | ✅ 181 passed |
| 运行时探针（E2，含占位符/围栏/未知 hex 三场景） | F-6、E-1、ADD-4 | ✅ 前两者放行、未知 hex 判红 |
| 静态读码（E3） | API-1..3、INV-1/3/5 | ✅ |
| 源码断言（E1） | F-2 | ✅ 无 `c-1a2b3c4d` |
| 盲区扫描（E4，扫描范围：30 项验收 + 3 类 U 项） | 全部 | **发现 3 项 P3**（见 §7.2） |

## 8. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用（无框架级决策） | — |
| 开发日志 | PROGRESS P-085 行 | ✅ |

## 9. 验收结论

### 9.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 6 | 6 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 3 | 3 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 30 | 30 | 0 | 0 |

> 统计口径（RULE-2）：来自上表逐项勾选，非事后推算。

### 9.2 验收决定

- [x] **验收通过**（P1/P2 零缺陷；3 项 P3 已登记，不阻塞）
- [ ] **有条件通过**
- [ ] **验收失败**

### 9.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 机械核验；独立异构 pass 待后续批次 | 2026-11-12 |

## 10. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| U-1 未闭合围栏告警 | G3 后续 | 首个真实论文 | pending |
| U-2 多反引号行内代码 | G3 后续 | 真实形态出现 | pending |
| U-3 幻觉 hex id 口径（③ 未采纳） | 用户 | 重裁时 | pending |
| O-3 P-083 测试计数订正 | 后续批次 | M4 前 | pending |
