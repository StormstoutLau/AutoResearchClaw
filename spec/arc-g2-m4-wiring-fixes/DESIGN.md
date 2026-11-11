---
id: arc-g2-m4-wiring-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-fixes-RESEARCH]
upstream: arc-g2-m4-wiring-fixes-RESEARCH
---

# 设计：G2 M4 复审缺陷修复

> 基于 [RESEARCH.md](RESEARCH.md)。只改 claim 产物边界，不改 AR 判据与 A2-4/5/6 语义。

## 1. 模块与 API

| 文件 | 改动 |
|---|---|
| `researchclaw/evidence/claim_policy.py` | 新增 `REQUIRED_CLAIM_FIELDS`、`CLAIM_ID_RE`、`validate_claim_shape`；`ClaimDecision.problems`；`evaluate_claim` 入口校验 |
| `researchclaw/evidence/stage_hooks.py` | 新增 `ClaimStreamError`、`_atomic_write_text`、`_claims_candidates`、`_claim_key`；`load_claims` 严格解析与目录优先级；`_read_json` fail-closed |

```python
def validate_claim_shape(claim: Mapping[str, Any]) -> tuple[str, ...]
# ("claim_id", "missing:a,b", "status") 的子集；合法时 ()

class ClaimStreamError(RuntimeError): ...
def _atomic_write_text(path: Path, text: str) -> None
def _claims_candidates(run_dir: Path, stage_prefix: str) -> list[Path]
def load_claims(run_dir: Path, stage_prefix: str = "stage-09") -> list[dict]
```

## 2. D-1：目录优先级

候选排序键：

```text
(0, -(-1), name)        # 非版本目录：version=-1 -> (0, 1, name)
(1, -version, name)     # 版本目录：v10 -> (1, -10, name)，先于 v2
```

- 非版本目录存在 `claims.jsonl` → 只读它。
- 否则读版本号最大的目录。
- 前缀同时适用于 `stage-09` 与 `stage-20`。

## 3. D-2：fail-closed 读写

### 3.1 读

- 文件不存在 → `[]` / 默认值（续跑语义）。
- 文件存在但任一行不是合法 JSON 对象 → `ClaimStreamError`（带 `path:line`）。
- `annotations.json` 存在但不是对象 → `ClaimStreamError`。
- `claim_gate.json` 存在但不是对象 / `decisions` 不是对象 → `ClaimStreamError`。

Stage 20/23 的既有 `try/except` 会把异常映射为 `E20_CLAIM_CONTRACT_INTERNAL` / `E23_CLAIM_DRIFT_INTERNAL`，保持 fail-closed。

### 3.2 写

```python
fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
write(...); os.replace(tmp, path)
# 失败：unlink(tmp) 后原样抛出
```

`claims.jsonl`、`claim_gate.json`、`claim_consistency.json` 共用同一原子写。

## 4. D-3：结构校验

`validate_claim_shape` 只做三项：

1. `claim_id` 是字符串且匹配 `^c-[0-9a-f]{8}$`；
2. C4 的 14 个必填键全部存在；
3. `status ∈ STATUS_ORDER`。

不校验 `claim_class`/`claim_type` 枚举（仍由 AR-01/AR-02 处理），不引入 jsonschema。

`evaluate_claim` 在降级前校验；不合法直接返回：

```python
ClaimDecision(
    claim=raw,
    deliverable=False,
    blocked_reasons=("invalid_claim_record",),
    problems=problems,
)
```

`as_dict` 增加 `problems`；`claim_gate.json` 的 `blocked[]` 增加 `problems`。

## 5. 边界

- 空 `claims.jsonl` 仍视为 `total=0` 通过（O-3 不在 P-063 范围）。
- `annotations.json` 缺失仍按「无标注」处理（数值 claim 会被 `missing_annotation` 阻断）。
- 无 claim 的续跑仍 `skipped=no_production_gate`。
- 不改变 `STATUS_ORDER`、`TERMINAL`、AR 判据和封顶规则。
