---
id: arc-stage10-symbol-recheck-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-symbol-recheck-DESIGN]
upstream: arc-stage10-symbol-recheck-DESIGN
---

# 实施：晚写入后的符号契约复检（P-229）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [\_code_generation.py#L370](../../researchclaw/pipeline/stage_impls/_code_generation.py#L370) | 新增 `_missing_symbols_by_file` 与 `_ensure_symbol_contract`：复检 → 一次定向修复 → 复检 → 写盘或保留原文件 |
| 同上 #L1572 | 首个入口修复后复检 |
| 同上 #L2300 | 对齐重生成写盘后复检 |
| 同上 #L2506 | 末尾入口重生成后复检（运行 M 失败点） |
| [tests/test_symbol_recheck.py](../../tests/test_symbol_recheck.py) | 新增 4 例 |

## 2. 读数

```
tests/test_symbol_recheck.py 4 passed
五套回归                     65 passed
```

覆盖：
- 缺失两个符号 → 定向修复、写盘、trace `repaired`；
- 修复仍缺 → 返回原文件、不写盘、trace `still_missing`；
- 无蓝图 → 零 LLM 调用；
- 截断 → `[16384, 32768]` 两次调用。

## 3. 现场预期

运行 M 类场景应出现：

```
Stage 10: symbol contract broken after late rewrite: main.py: set_seed, train_model
Stage 10: symbol contract restored by targeted repair (main.py)
```

若修复失败则保留 `symbol contract still broken after one repair`，出口门语义不变。

## 4. 未做

未部署、未重跑；未改动出口门与证据门。
