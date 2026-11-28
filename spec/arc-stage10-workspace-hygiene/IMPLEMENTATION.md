---
id: arc-stage10-workspace-hygiene-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-workspace-hygiene-DESIGN]
upstream: arc-stage10-workspace-hygiene-DESIGN
---

# 实施：Stage 10 工作区卫生与失败面前移（P-227）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [\_code_generation.py#L64](../../researchclaw/pipeline/stage_impls/_code_generation.py#L64) | 新增 `_quarantine_stale`：隔离非本次产物的 `.py` |
| 同上 #L98 | 新增 `_blueprint_file_names`：取蓝图声明的文件名（basename） |
| 同上 #L1667 | 写盘前隔离孤儿文件（`tag="pre-attempt"`） |
| 同上 #L1726-L1832 | 符号契约前移到深修前；深修改为最多 2 轮，带「STILL NOT FIXED」，`fixed == 0` 即停 |
| 同上 #L2084-L2145 | 重生成 prompt 注入蓝图文件+符号；输出按蓝图过滤，缺失文件保留旧版；重生成后隔离 |
| [tests/test_workspace_hygiene.py](../../tests/test_workspace_hygiene.py) | 新增 5 例：隔离/空目录/非 py/文件名两种形态/非法蓝图 |

## 2. 读数

```
pytest tests/test_workspace_hygiene.py ... -q  → 75 passed
```

覆盖：
- 孤儿 `data_generator.py` → `quarantine/pre-attempt/`，声明文件保留；
- `notes.txt` 不被移动；
- `src/data.py` / `methods.py` / `main.py` 归一到 basename；
- `None` / `{}` / dict 形式 `files` 返回空集合。

## 3. 现场预期

- 日志出现 `quarantined stale file(s) from experiment/: ...`；
- 符号缺失在「critical code issues found」列表中以 `[symbols]` 出现，而非等到 `evidence gate failed`；
- 深修零进展时不再有第二轮（运行 L 的 `fixed 0/4` 场景）。

## 4. 未做

未部署到 B 站；未清理 `agent_runs/`；未重跑 Stage 10。
