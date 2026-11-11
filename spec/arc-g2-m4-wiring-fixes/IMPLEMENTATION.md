---
id: arc-g2-m4-wiring-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-fixes-DESIGN]
upstream: arc-g2-m4-wiring-fixes-DESIGN
---

# 实施记录：G2 M4 复审缺陷修复（P-063）

> **状态**：D-1..D-3 已修复并机检验证；CHECKLIST accepted。
> **依据**：[DESIGN.md](DESIGN.md) §2（D-1）、§3（D-2）、§4（D-3）。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_policy.py` | 修改 | `REQUIRED_CLAIM_FIELDS`/`CLAIM_ID_RE`/`validate_claim_shape`；`ClaimDecision.problems`；`evaluate_claim` 入口校验 |
| 2 | `researchclaw/evidence/stage_hooks.py` | 修改 | `ClaimStreamError`；`_atomic_write_text`；`_claims_candidates`（非版本优先）；严格 `load_claims`；`_read_json` fail-closed；`_claim_key` 与 `problems` |
| 3 | `tests/test_claim_policy.py` | 修改 | +4 结构校验用例（非法 status、缺字段、坏 id、合法无问题） |
| 4 | `tests/test_stage_claim_hooks.py` | 修改 | +9 用例：D-1 三条、D-2 四条、D-3 二条 |
| 5 | `spec/arc-g2-m4-wiring/DESIGN.md` | 修改 | v1.1：判定链、payload、目录优先级、原子写 |
| 6 | `docs/PROGRESS.md` | 修改 | P-063 执行行 |
| 7 | `arc-master-roadmap.md` | 修改 | v1.3j：M4 复审缺陷关闭 |

**不改**：C4 schema、AR-01..08、A2-4/5/6 语义、Stage 9 抽取规则。

## 2. D-1：目录优先级

```python
candidates.append((1 if version >= 0 else 0, -version, name, path))
candidates.sort(key=lambda item: (item[0], item[1], item[2]))
```

- 活目录 `stage-09/` 永远先于 `stage-09_v{N}/`。
- 无活目录时 `v10` 先于 `v2`（数值排序，非字典序）。
- `stage-20` 复用同一函数。

## 3. D-2：fail-closed 与原子写

- `load_claims`：坏行 → `ClaimStreamError(f"{path}:{line_no}: invalid claim JSON: ...")`；非对象行同样抛错。
- `_read_json`：文件缺失返回默认值；存在但不可解析 → `ClaimStreamError`。
- `_annotations`：非对象 → 抛错。
- `run_stage23_consistency`：`claim_gate.json` 非对象 / `decisions` 非对象 → 抛错。
- `_atomic_write_text`：`mkstemp` 同目录 → 写入 → `os.replace`；异常时 `unlink` 临时文件。
- `_write_claims`/`_write_json` 全部改走原子写。

## 4. D-3：结构校验

`validate_claim_shape` 返回：

- `("claim_id",)`：id 不是 `c-[0-9a-f]{8}`；
- `("missing:a,b,...",)`：缺 C4 必填键；
- `("status",)`：status 不在七值词表；
- 多项按上述顺序并列。

`evaluate_claim` 不合法时短路返回 `invalid_claim_record`，不跑 AR；`as_dict`/gate blocked 条目带 `problems`。

## 5. 修复验证探针（F 表）

| # | 场景 | 结果 |
|---|---|---|
| F-A | D-1：`stage-09`（NEW）与 `stage-09_v2`（OLD）并存 | picked=`NEW` ✅ |
| F-B | D-3：非法 status + 缺字段 | blocked，`invalid_claim_record`，problems 含 `missing:...`/`status` ✅ |
| F-C | D-3：仅 `claim_id` | blocked，problems 含 `missing:...`/`status` ✅ |
| F-D | D-2：claim 文件尾行损坏 | `ClaimStreamError` ✅ |
| F-E | D-2：`claim_gate.json` 损坏 | Stage 23 `ClaimStreamError` ✅ |
| F-F | D-2：`os.replace` 失败 | 原文件保持、无 `.tmp` 残留 ✅ |
| F-G | D-3：审计平面直接评估非法记录 | `deliverable=False`、`invalid_claim_record` ✅ |
| F-H | 回归：合法 claim 全链路 | gate `pass`、`consistent=True` ✅ |

## 6. 测试读数

- `tests/test_claim_policy.py` + `tests/test_stage_claim_hooks.py`：**59 passed**（3.13.5，1.53s）。
- 同一命令 Python 3.11.15 venv：**59 passed**（0.77s）。
- 相关回归（simulated guard / fabrication guards / claim verifier / AR checks / sidecar / contracts）：**105 passed**。
- 原 M4 46 项全部保留通过；新增 13 项（4 + 9）。

## 7. 未尽事项

- O-3（空 claims 空转通过）与 O-4（`message`/`cap` 未进 gate JSON）不在 P-063 范围，留待后续。
- O-1/O-2（annotation 供给与封顶语义）仍为 M5/G3 输入。
