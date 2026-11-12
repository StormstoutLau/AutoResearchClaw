---
id: arc-g3-indent-context-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-indent-context-DESIGN]
upstream: arc-g3-indent-context-DESIGN
---

# 实施：上下文感知的缩进代码块判定（P-096）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_spine.py` | 修改 | `_INDENT_CODE_RE` 改 `^(\t| {4,})\S`；新增 `_NESTED_LIST_RE`/`_LIST_ITEM_RE`；`extract_claim_markers` 增 `prev_kind` 上下文判定 |
| 2 | `tests/test_claim_spine.py` | 修改 | 新增 5 项（F-1..F-5）+ 1 项迁移护栏 |
| 3 | `spec/arc-g3-indent-context/` 四文档 | 新增 | 本批次 spec |
| 4 | `docs/PROGRESS.md` + `arc-master-roadmap.md` | 修改 | P-096 登记 + 总纲 v1.4h |

## 2. 接口影响

- `extract_claim_markers(text) -> dict[str, list[str]]` **签名与返回结构不变**。
- 行为变化见 DESIGN §2.3 迁移表（4 处提取收紧为正文、1 处新增跳过）。

## 3. 实施顺序（先红后绿）

1. 写 6 项测试（含 K1 下游）→ 预期 5 failed（F-5 依赖 F-1 生效）。
2. 实现状态机与正则 → 全绿。
3. 双环境四文件 + 十文件/扩展组回归。
4. 登记 + 门禁链。

## 4. 关键实现记录

- `prev_kind` 取值：`None / "blank" / "para" / "list" / "heading" / "fence_close" / "code"`。
- 缩进行判定顺序：**嵌套列表标记 → 开块上下文 → 段落续行**。
- `in_indent` 块内一律跳过（状态优先），块外才有上下文判定。
- 标题行在 `in_indent` 内不生效（既有 A4 语义）。
- 空行只更新 `prev_kind`，不关 `in_indent`。

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | 6 项（claim spine 25→31：F-1..F-5 + 迁移护栏） |
| 红→绿 | 红：**5 failed / 26 passed**（F-5 依赖 F-1 生效，迁移护栏先绿）；绿：**31 passed** |
| 双环境 | 3.13.5 四文件 **131 passed**（1.89s）；3.11.15 **131 passed**（1.21s） |
| 相关回归 | 十文件 **205 passed**；扩展组（rc_executor 等十文件）**348 passed** |
| E2 复核 | A5/J8/A6/A1/A4/A7/A3 + P-085 围栏行内码 8 形态全部符合 DESIGN §2.3 迁移表 |
| 门禁 | DC 0 违规；step-gate 5/5（P-096）；step-enforce `digest_bound=2`（P-095/P-096 双声明）；pre-commit 9 钩子全绿 |

## 6. 验收边界（诚实口径）

- 仍为**行级启发式**而非完整 CommonMark 块解析：块内 `- x` 与「列表项内 6+ 空格续行」等歧义形态按 DESIGN §2.3 表处理，未覆盖形态登记为观察项。
- P-095 O 表各项不在本批范围。

---
