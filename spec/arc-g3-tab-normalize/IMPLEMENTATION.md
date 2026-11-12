---
id: arc-g3-tab-normalize-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g3-tab-normalize-DESIGN]
upstream: arc-g3-tab-normalize-DESIGN
---

# 实施：行首 tab 前缀缩进判定补全（P-098）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_spine.py` | 修改 | `_INDENT_CODE_RE` tab 分支 `\t` → `\t[ \t]*`（单处） |
| 2 | `tests/test_claim_spine.py` | 修改 | 新增 2 项（三前缀参数化 + M1d 护栏） |
| 3 | `spec/arc-g3-tab-normalize/` 四文档 | 新增 | 本批次 spec |
| 4 | `docs/PROGRESS.md` + `arc-master-roadmap.md` | 修改 | P-098 登记 + 总纲 v1.4j |

## 2. 实施顺序（先红后绿）

1. 写 2 项测试（红：T2/T3/T4 三前缀提取中）。
2. 改 `_INDENT_CODE_RE` → 绿。
3. 双环境四文件 + 十文件/扩展组回归 + E2 全 tab 形态对照。

## 3. 关键实现记录

- 仅正则一处：`re.compile(r"^(?:\t[ \t]*| {4,})\S")`。
- `_NESTED_LIST_RE` 有意不改（DESIGN D-2）：`\t- x` 保持列表内容；`\t\t- x` 修复后判代码。
- 块内行判定（`in_indent` 分支）复用同一正则，块内 tab+空白行同步受益。

## 4. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | 2 项（claim spine 31→33） |
| 红→绿 | 红：**1 failed / 32 passed**（三前缀用例红；M1d 护栏现状即绿）；绿：**33 passed** |
| 双环境 | 3.13.5 四文件 **133 passed**（1.81s）；3.11.15 **133 passed**（1.26s） |
| 相关回归 | 十文件 **207 passed**；扩展组（rc_executor 等十文件）**348 passed** |
| E2 对照 | P-097 tab 扫描 7 形态（T1-T7）+ 新增 `\t\t-` 形态 + M1d + 迁移表 6 护栏，**15/15 全过** |
| 门禁 | 待回填 |

## 5. 验收边界（诚实口径）

- 行首 tab 归一化按「tab 后任意空白」处理，未实现完整 tab stop 列数计算（如 `\t`+3 空格 = 7 列的精确定位）；对本提取器「≥4 列即代码候选」的目的语义等价。
- O-2（块内深缩进围栏）不在本批。

---
