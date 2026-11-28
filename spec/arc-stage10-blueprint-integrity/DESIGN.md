---
id: arc-stage10-blueprint-integrity-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-blueprint-integrity-RESEARCH]
upstream: arc-stage10-blueprint-integrity-RESEARCH
---

# 设计：蓝图落盘完整性（P-230）

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| B-1 | 模型输出 YAML 只作**传输格式**：解析成功后用解析后的 dict 经 `yaml.safe_dump` 重写 canonical YAML，并写 `architecture_spec.json` 孪生 | L-1：内存 dict 与磁盘文本不同源 |
| B-2 | 出口前校验：`generate()` 拿不到可用蓝图时写 `codegen_decision.json`（`fallback=fail_closed`）并 `raise RuntimeError("blueprint_unparsable: ...")`，不进入生成 | L-3：空转放行是本次 DONE 未被验证的直接原因 |
| B-3 | 证据门 fail-closed：`evaluate_stage10_evidence` 中蓝图缺失从 warning 改为 `blueprint_unavailable` failure | 同上 |
| B-4 | 同错即停：修复重试把解析器错误回传（delta），若修复后错误与修复前**完全相同**则记 `blueprint_error_repeated=True`，不再重试 | L-4：无 delta 的重发只会重复同一错误 |
| B-5 | 来源标记：`blueprint_source ∈ model / canonical / repaired` 写入 `codegen_decision.json` | L-5：现场无法归因蓝图来自哪条路径 |

## 2. 被拒绝的替代方案

| 方案 | 拒绝理由 | 代价 |
|---|---|---|
| 只做 YAML 折行/加引号预处理（P-232 路线扩展） | 预处理只能覆盖已见过的形态；模型下一种引号错误仍会写坏文件 | 低价但重复踩坑，且**不解决**内存/磁盘不同源 |
| 全部改用 JSON 蓝图 | 蓝图含大量多行自然语言，JSON 更易被模型写坏，且破坏既有 5 份 spec 与解析器 | 兼容性面大 |
| 蓝图不可解析时继续走单发（P-230 前行为） | 证据门全盲，DONE 不可信；运行 N 已实证 | 一次阶段 68.8 分钟白跑 |
| 每次解析失败都无限重试 | 同错重发不产生新信息，只烧 token | 与 P-226 止损纪律冲突 |

## 3. 接口与数据流

```
_phase1_blueprint
  └─ _persist_blueprint(raw)            # 解析前先留原始证据（B-33 语义不变）
  └─ _parse_blueprint(raw)
       ├─ 成功 → _write_canonical_blueprint(dict)
       │           ├─ architecture_spec.yaml（safe_dump）
       │           └─ architecture_spec.json（json.dumps）
       └─ 失败 → _repair_blueprint_yaml(delta=parser error)
                    ├─ 成功 → source=repaired → canonical 写盘
                    └─ 同错 → blueprint_error_repeated=True → 返回 None

generate()
  └─ blueprint is None → 写 codegen_decision.json(fail_closed) → RuntimeError

evaluate_stage10_evidence
  └─ load_blueprint(stage_dir) is None → failures += blueprint_unavailable
```

`load_blueprint` 读盘顺序：`architecture_spec.yaml` → `architecture_spec.json` → `None`。两者皆坏才算不可用。

## 4. 验收

- 合法蓝图：磁盘 YAML 可被 `load_blueprint` 解析，签名等含 `:` 的值不被截断；JSON 孪生存在且等价；
- 双坏文件：`load_blueprint` 返回 `None`，证据门产出 `blueprint_unavailable` 且 `report.ok is False`；
- 不可解析：`generate()` 抛 `RuntimeError("blueprint_unparsable: ...")`，`codegen_decision.json` 记 `fallback=fail_closed`/`reason=blueprint_unparsable`；
- 修复成功：`blueprint_source=repaired`，canonical 写盘；
- 结构非法（解析成功但 `_is_valid_blueprint` 为假）：仍走单发，`reason=blueprint_structure_invalid`；
- 既有回归全过。

## 5. 非目标

- 不改 YAML 预处理/折行规则（P-232 已覆盖）；
- 不改出口门的失败码集合，只补 `blueprint_unavailable`；
- 不改变单发回退在「结构非法」情形下的语义；
- 不部署、不重跑 B 站（部署另批）。
