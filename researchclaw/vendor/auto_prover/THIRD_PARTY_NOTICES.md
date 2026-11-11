# Third-party notices — vendored Auto_Prover kernel

审计日期：2026-11-11（P-049，承接 P-044 的第三方血统审计）

## 结论

本目录的 27 个内核文件均为 **Auto_Prover 作者自有代码**（版权主体 `Aiming Lab`），未发现需要额外归属的第三方代码：

- `datatypes/`、`verdict/`、`sandbox/`、`semantic_verdict.py`、`model_gateway.py`、`kg/`、`stages/` 与 `scripts/verdict_recheck.py` 均为 AP 仓内原创；
- 与 P-044 已核验的 `atlas_*.py` / `lean4_cases` 不同，本目录**不包含**教材语料或 vendored 第三方模块；
- `sandbox/lean_filter.py` 只是 Lean 危险构造的字符串过滤，不包含 Lean 本体或 Mathlib。

## 运行时依赖（不随本目录分发）

| 依赖 | 用途 | 许可 |
|---|---|---|
| `numpy` | 数值沙箱与数值辅助模块 | BSD-3-Clause（由 ARC 依赖声明安装，未复制代码） |

## 许可边界

- 本目录按文件保持 **Apache-2.0**；`LICENSE`/`NOTICE` 为 AP 原文。
- ARC 自有代码仍为 **MIT**；两者并存，不互相覆盖。
- 若未来 vendor 新文件，必须先复核本清单并在 `SOURCE.json` 记录 sha256。
