---
id: arc-stage10-workspace-hygiene-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-workspace-hygiene-IMPLEMENTATION]
upstream: arc-stage10-workspace-hygiene-IMPLEMENTATION
---

# 检查表：Stage 10 工作区卫生与失败面前移（P-227）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 孤儿文件被隔离 | `_quarantine_stale` 移动未声明 `.py`，声明文件保留 | ✅ |
| C-2 | 证据可回溯 | quarantine 内内容可读回，与原文件一致 | ✅ |
| C-3 | 非 Python 不受影响 | `notes.txt` 原地保留 | ✅ |
| C-4 | 蓝图文件名归一 | `src/data.py` → `data.py`；脏输入返回空集 | ✅ |
| C-5 | 符号前移 | 深修前执行 `check_symbol_contract`，并入 `[symbols]` issue | ✅ |
| C-6 | 重生成蓝图锚定 | prompt 含文件+符号清单；输出按蓝图过滤 | ✅ |
| C-7 | 缺失文件保留旧版 | `files = {**files, **filtered}` | ✅ |
| C-8 | 深修零进展即停 | `fixed == 0` 不进第二轮 | ✅ |
| C-9 | 回归 | 5 例 + 既有三套 **75 passed** | ✅ |
| C-10 | 零部署 | B 站未改动 | ✅ |
