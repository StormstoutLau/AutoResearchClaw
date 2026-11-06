---
id: arc-roadmap-fix-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-06
depends: [arc-roadmap-fix-RESEARCH, arc-roadmap-fix-DESIGN]
upstream: arc-roadmap-fix-DESIGN
---

# 实施：六处订正的落点与验证命令

> **实施依据**：[DESIGN.md](DESIGN.md) D-1..D-6。

## 1. 改动落点

| # | 文件 | 锚点 | 操作 |
|---|---|---|---|
| E-1 | `arc-master-roadmap.md` | 第 4 行 | `version: 0.1` → `version: 0.2` |
| E-2 | `arc-master-roadmap.md` | 第 11 行 | 标题 `（v0.1）` → `（v0.2）` |
| E-3 | `arc-master-roadmap.md` | 第 17 行后 | 插入 `> **修订**：v0.2（2026-11-06，P-003）…` |
| E-4 | `arc-master-roadmap.md` | G2 A2-3 | 「65 项 verdict 测试」→ 可冻结口径 |
| E-5 | `arc-master-roadmap.md` | G3 交付物第 5 条 | 「H-4 已落地」→「待 G-1 的 H-4 落地」 |
| E-6 | `arc-master-roadmap.md` | §5 表 + 规则 | 新增 C-9、「生效起点」列、`N/A` 语义、覆盖范围声明 |
| E-7 | `arc-master-roadmap.md` | §6 硬出口 | 「C 套件全绿」→「已生效成员全绿」 |
| E-8 | `arc-master-roadmap.md` | §7 标题 / Q11 / §10 第 1 条 | 10→16 项；3 道→4 道钩子 |

**约束**：不改 106 条计数、不改阶段依赖图、不改任何代码、不动 15 份已忽略的调研文档。

## 2. 验证命令（可原样重放）

```bash
# V1 契约（作用域 = pre-commit 钩子同款：spec/** + PROGRESS/CONSOLE）
# 注：裸跑 `python scripts/dc_validator.py` 会扫全仓并报 141 条既有违规
# （.claude/、external/、第三方 SKILL.md 与 SPEC_PROCESS.md 的历史链接），与本批无关。
python scripts/dc_validator.py spec/arc-roadmap-fix/RESEARCH.md spec/arc-roadmap-fix/DESIGN.md \
  spec/arc-roadmap-fix/IMPLEMENTATION.md spec/arc-roadmap-fix/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md

# V2 验收计数复算（必须仍为 106）
python -c "import re,io; t=io.open('arc-master-roadmap.md',encoding='utf-8').read(); \
print(sum(map(int, re.search(r'验收总数：(.*?)= (\d+) 条', t).group(1).replace(' ','').split('+'))), \
      re.search(r'= (\d+) 条', t).group(1))"

# V3 G-1 回归覆盖：H-1..H-4 必须出现在某个 C 套件
python -c "import re,io; t=io.open('arc-master-roadmap.md',encoding='utf-8').read(); \
s=t.split('## 5.')[1].split('## 6.')[0]; \
print({h:(h in s) for h in ['H-1','H-2','H-3','H-4']})"

# V4 矛盾项清零：全文不得再出现「H-4 已落地」
python -c "import io; print('H-4 已落地' in io.open('arc-master-roadmap.md',encoding='utf-8').read())"

# V5 派生视图与批次
python scripts/console_gen.py --check
python tools/spec_runner/spec_runner.py step-gate --session specwf-p003-arc-roadmap-fix \
  --expect research design implement verify finalize
python scripts/rework_graph_check.py
```

## 3. 未执行项

- **总纲已纳入版本控制**（2026-11-06 用户裁决，覆盖初稿的"只改本地副本"）：删除 `.gitignore` 中的 `/arc-master-roadmap.md` 行，总纲 v0.2 随本批提交；其余调研文档仍不入库。
- 未修改 `spec/arc-roadmap-review/` 四文档与审查报告：其结论仍绑定 v0.1，属历史记录。
- 未修 P2-01（涉及文件不可提交，见 RESEARCH §2.2）。
- 未处理 P2-08 的平台判据（留待 G1 的 RESEARCH 定死）。
- 提交范围：P-002 + P-003 全部产物与总纲 v0.2，2026-11-06 经用户授权一并提交。
