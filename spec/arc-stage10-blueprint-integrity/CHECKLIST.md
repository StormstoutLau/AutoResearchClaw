---
id: arc-stage10-blueprint-integrity-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-blueprint-integrity-IMPLEMENTATION]
upstream: arc-stage10-blueprint-integrity-IMPLEMENTATION
---

# 检查表：蓝图落盘完整性（P-230）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | canonical 写盘 | 解析成功后磁盘 YAML 可被 `load_blueprint` 解析，`signature` 含 `:` 不被截断 | ✅（`test_canonical_yaml_round_trips`） |
| C-2 | JSON 孪生兜底 | 删除/写坏 YAML 后 `load_blueprint` 仍从 `architecture_spec.json` 返回 dict | ✅（`test_json_twin_is_used_when_yaml_breaks`） |
| C-3 | 双坏 fail-closed | YAML+JSON 均坏 → `load_blueprint is None` | ✅（`test_both_formats_broken_returns_none`） |
| C-4 | 出口前早停 | 不可解析蓝图 → `RuntimeError("blueprint_unparsable: ...")` 且 `fallback=fail_closed` | ✅（`test_unparsable_fails_closed`） |
| C-5 | 证据门缺失即失败 | 蓝图缺失 → `blueprint_unavailable` ∈ failures 且 `report.ok is False` | ✅（`test_missing_blueprint_fails_closed`） |
| C-6 | 结构非法语义不变 | 解析成功但文件数不足 → `reason=blueprint_structure_invalid`、仍走单发 | ✅（`test_structure_invalid_reason`） |
| C-7 | 来源标记 | `codegen_decision.json` 含 `blueprint_source` 与 `blueprint_error_repeated` | ✅（`_record_codegen_decision` + 决策用例） |
| C-8 | canonical 不被覆盖 | 阶段层仅在 `load_blueprint(stage_dir) is None` 时写 raw spec | ✅（读码 `_code_generation.py#L1462`） |
| C-9 | 回归 | 六套定向 **56 passed**；全量 `pytest tests` **4236 passed / 6 failed**（6 项均为环境类：壳钩子、Keras 3、bash 路径） | ✅ |
| C-10 | 边界登记 | W-033（`_ensure_symbol_contract`，`safe_join`）登记且 `test_boundary_coverage` 通过 | ✅ |
| C-11 | 零部署 | B 站仍为 P-229 快照 | ✅ |
