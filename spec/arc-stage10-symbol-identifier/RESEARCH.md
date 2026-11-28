---
id: arc-stage10-symbol-identifier-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-minimal-edit]
upstream: arc-master-roadmap
---

# 调研：符号契约只接受标识符（P-232）

> **档位**：S1 缺陷型（§2.3）。根因由运行 P 的日志与蓝图原文直接给出。

## 1. 问题

运行 P（P-231 快照）在 23:03:22 失败：

```
23:02:01 main.py: 1 declared symbol(s) missing (if __name__ == "__main__") — targeted repair
23:03:22 main.py: declared symbols still missing after repair (if __name__ == "__main__")
23:03:22 ERROR Stage 10 module generation failed: main.py: module extraction failed (symbols_missing)
23:03:22 Stage 10/23 CODE_GENERATION — FAILED (1291.1s)
```

蓝图把 `if __name__ == "__main__"` 当成 main.py 的一个"函数"声明：

```yaml
functions:
  - name: main
    signature: () -> None
    ...
  - name: if __name__ == "__main__"
    signature: ()
    pseudocode: |
      1. main().
      2. sys.exit(0).
```

`_declared_symbols` 无条件把 `functions[].name` 当符号，于是符号契约要求 main.py 定义一个名为 `if __name__ == "__main__"` 的 Python 定义——任何代码都写不出来。模块级检查（B-34 M5）因此把一份正确的 main.py 判死，并在 21.5 分钟后让整个 Stage 10 FAILED。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | `_declared_symbols` 对 `symbols/required_symbols/classes/functions` 的 `name` 一律接受，无形态校验 | [codegen_evidence.py#L223](../../researchclaw/pipeline/codegen_evidence.py#L223) |
| L-2 | 模块级检查 `missing_symbols` 用 AST 定义名比对，非标识符永远不匹配 | [codegen_evidence.py#L296](../../researchclaw/pipeline/codegen_evidence.py#L296) |
| L-3 | 模块级检查失败会 `raise ModuleExtractionError`，整阶段 FAILED | [code_agent.py#L1188](../../researchclaw/pipeline/code_agent.py#L1188) |
| L-4 | 同一契约也用于出口证据门与 P-231 的 prompt 契约块，伪符号会污染三处 | [codegen_evidence.py#L307](../../researchclaw/pipeline/codegen_evidence.py#L307) |
| L-5 | 运行 P 的蓝图可由 canonical YAML 复读（49 603 字符），伪符号在 `#L1113` | 现场 `architecture_spec.yaml#L1113` |

## 2.3 档位与最小来源

- **档位**：S1。
- **来源**：E1 ≥2 —— 运行 P 的失败日志、蓝图 `#L1113` 原文、`_declared_symbols` 读码。
- **豁免**：根因在本机可复现（把该蓝图喂给 `declared_symbols` 即得到伪符号），无需外部检索。Python 语言层面 `if __name__ == "__main__"` 不是标识符，属语言事实而非需要引证的方法学结论。

## 2.4 降级链

MCP 学术检索（S1 豁免，未调用）→ 运行 P 日志 → 蓝图 canonical 原文 → 仓内代码。

## 3. 结论

符号契约只应接受能作为 Python 定义名的字符串（`str.isidentifier()`）；蓝图中的伪代码片段、守卫语句等形态必须跳过，其余逻辑不变。

## 4. 来源

- 运行 P 现场：B 站 `~/arc-runs/g7-baseline/p231-stage10.log`（23:02:01–23:03:22）
- 蓝图原文：`stage-10/architecture_spec.yaml#L1113`
- [codegen_evidence.py#L223](../../researchclaw/pipeline/codegen_evidence.py#L223)
