---
id: arc-stage10-entrypoint-budget-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-entrypoint-budget-RESEARCH]
upstream: arc-stage10-entrypoint-budget-RESEARCH
---

# 设计：入口生成预算、约束与兜底（B-30）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | **第二次尝试用 65536** | 同额度重试 | 现场两次都在 517 行截断，同额度无信息增量 |
| D-2 | **提示硬约束 ≤150 行 + 只调用不重写** | 仅靠截断重试 | 根因是模型把实现搬进入口文件 |
| D-3 | **`synthesize_entrypoint` 兜底** | 直接失败 | 已有模块通常含 `run/train`；薄驱动可让 Stage 12 真正执行 |
| D-4 | **兜底不伪造数值**：取不到就打印 `nan` | 填 0.0 | 0.0 会被当作有效结果，污染研究结论 |
| D-5 | **repair 连续 2 次不可用即止损** | 继续 5 次 | 同一失败重复 4 次无收益，只增加耗时 |
| D-6 | **兜底需模块暴露入口函数** | 任意模块都可以 | 否则生成一个调用不存在函数的文件，仍是假通过 |

## 2. 接口

```python
synthesize_entrypoint(files: Mapping[str, str], metric: str) -> str | None
# 候选函数名优先级：main > run > run_experiment > train > evaluate > experiment > execute
# 跳过 main.py；跳过语法错误文件；无候选返回 None
```

生成的驱动固定形态：
- `import <module> as _impl`
- 先打印 `METRIC_DEF: ...`
- 调用入口函数；dict 取 metric 键，数值直接用，其余打印 `nan`

## 3. 非目标

- 不改 `_entrypoint_issues` 判据。
- 不改 Stage 12 指标解析。
- 不改变 CodeAgent 的蓝图/序列生成策略。
