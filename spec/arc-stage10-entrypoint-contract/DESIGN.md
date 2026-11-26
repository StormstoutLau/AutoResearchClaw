---
id: arc-stage10-entrypoint-contract-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-entrypoint-contract-RESEARCH]
upstream: arc-stage10-entrypoint-contract-RESEARCH
---

# 设计：入口契约与专用 main.py 生成（B-29）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | **删除文件提升**：缺 `main.py` 时不重命名任何文件 | 继续提升首个文件 | 重命名导致 `from config import ...` 悬空（BUG-184），且入口天然错误 |
| D-2 | **共享契约模块** `pipeline/entrypoint_contract.py` | 在两处各写一份校验 | `code_agent` 与 `_code_generation` 都要用；集中避免循环导入与规则漂移 |
| D-3 | **专用生成**：列出其他模块的顶层类/函数，要求 `__main__` + `METRIC_DEF`，32768 tokens，最多 2 次，截断重试 | 复用通用 code_generation 提示 | 通用提示不保证入口结构，实测多次产出配置模块 |
| D-4 | **契约前置**：校验循环前、出口门前各调用一次 `_ensure_entrypoint` | 只在出口门检查 | 出口门失败要整段重跑（约 4h）；前置可分钟级纠正 |
| D-5 | **repair 拒绝不合契约 main.py** | 接受任意可解析文件 | 截断但可解析的 `main.py` 会挤掉可用版本 |
| D-6 | **repair 拒绝不可解析输出** | 接受后交给下一轮 | 与 B-28 一致：语法坏文件不得覆盖旧版 |

## 2. 契约定义

```python
entrypoint_issues(main_code) -> list[str]
# 空列表 = 合规；否则返回：
#   - "main.py is empty or missing"
#   - "main.py has a syntax error: ... (line N)"
#   - 'main.py missing `if __name__ == "__main__":` block'
#   - "main.py never prints METRIC_DEF"
```

## 3. 生成提示（要点）

- 只输出一个 `main.py` 的 ```python 代码块；
- 末尾必须有 `if __name__ == "__main__":` 并调用真实函数；
- 必须打印一行以 `METRIC_DEF:` 开头，并打印 `<metric>: <float>`；
- 必须 `import` 已生成模块，不得重写其类/函数；
- 文件必须完整，禁止占位符、TODO、截断字符串；
- 第 2 次尝试附带上次被拒原因。

## 4. 非目标

- 不改 Stage 12 的指标解析。
- 不改 `config.py` 遮蔽 stdlib 的深度质量告警（另登记）。
- 不改阶段重试次数与退出码（B-8）。
