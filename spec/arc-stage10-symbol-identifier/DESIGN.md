---
id: arc-stage10-symbol-identifier-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-symbol-identifier-RESEARCH]
upstream: arc-stage10-symbol-identifier-RESEARCH
---

# 设计：符号契约只接受标识符（P-232）

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| I-1 | `_declared_symbols` 只接受 `symbol.isidentifier()` 为真的名字；伪代码片段、守卫语句等形态静默跳过 | L-1/L-2；Python 定义名必须是标识符 |
| I-2 | 过滤放在唯一的抽取点，使模块级检查、出口证据门、P-231 的 prompt 契约块同时生效 | L-4 |
| I-3 | 不加"伪符号"计数与告警：蓝图里的自然语言形态本来就不该参与契约，报告噪声无收益 | 最小改动 |

## 2. 被拒绝的替代方案

| 方案 | 拒绝理由 | 代价 |
|---|---|---|
| 在 `check_symbol_contract` / `missing_symbols` 里过滤 | 三处调用各自过滤，易漏一处（P-231 的契约块就是第二处） | 长期漂移 |
| 对伪符号做特殊字符串匹配（`if __name__`、`def ` 等） | 黑名单永远不全，且把语言事实写成规则表 | 维护成本 |
| 让模块生成容忍缺失并继续 | 会退回「部分模块也算交付」，正是 B-34 M5 要封的洞 | 交付质量下降 |

## 3. 接口

```python
# codegen_evidence._declared_symbols
if symbol and symbol.isidentifier():
    out.append((file_name, symbol))
```

影响面：`declared_symbols` / `missing_symbols` / `check_symbol_contract` / `symbol_contract_block` 全部继承该过滤，签名与返回值不变。

## 4. 验收

- 蓝图含 `{"name": 'if __name__ == "__main__"'}` → `declared_symbols` 只返回真实标识符；
- 该蓝图下，含标准 guard 的 main.py 通过 `check_symbol_contract`；
- `symbol_contract_block` 不出现 `__main__`；
- 既有夹具（`symbols/functions/classes` 三种拼写）行为不变；
- 全量回归无新增失败。

## 5. 非目标

- 不改变蓝图解析的其他字段语义；
- 不为伪符号生成告警或 trace；
- 不部署（部署与重跑由同批操作执行）。
