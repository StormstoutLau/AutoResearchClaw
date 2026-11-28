---
id: arc-stage10-blueprint-integrity-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-blueprint-integrity-DESIGN]
upstream: arc-stage10-blueprint-integrity-DESIGN
---

# 实施：蓝图落盘完整性（P-230）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [code_agent.py#L757](../../researchclaw/pipeline/code_agent.py#L757) | 新增 `_write_canonical_blueprint`：`yaml.safe_dump(sorted=False)` 重写 `architecture_spec.yaml` + 写 `architecture_spec.json`；原子替换 |
| [code_agent.py#L520](../../researchclaw/pipeline/code_agent.py#L520) | `_phase1_blueprint` 解析成功后调用 canonical 写盘（B-1） |
| [code_agent.py#L366](../../researchclaw/pipeline/code_agent.py#L366) | `generate()` 中 `blueprint is None` → 写 `fallback=fail_closed` 决策后 `raise RuntimeError("blueprint_unparsable: ...")`（B-2） |
| [code_agent.py#L531](../../researchclaw/pipeline/code_agent.py#L531) | `_repair_blueprint_yaml`：delta 回传解析器错误与引号规则；成功置 `source=repaired` 并 canonical 写盘；同错置 `blueprint_error_repeated`（B-4） |
| [code_agent.py#L600](../../researchclaw/pipeline/code_agent.py#L600) | `_record_codegen_decision` payload 增 `blueprint_source`、`blueprint_error_repeated`（B-5） |
| [code_agent.py#L931](../../researchclaw/pipeline/code_agent.py#L931) | `_parse_blueprint` 异常时记 `_last_blueprint_error = "<ExcType>: <msg>"` |
| [codegen_evidence.py#L85](../../researchclaw/pipeline/codegen_evidence.py#L85) | `load_blueprint` 先 YAML 后 JSON 孪生，双坏返回 `None`（B-1 兜底） |
| [codegen_evidence.py#L602](../../researchclaw/pipeline/codegen_evidence.py#L602) | 蓝图缺失追加 `blueprint_unavailable` failure（B-3） |
| [\_code_generation.py#L1460](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1460) | 仅在 `load_blueprint` 为 `None` 时才用 raw spec 覆盖，避免破坏 canonical |
| [\_code_generation.py](../../researchclaw/pipeline/stage_impls/_code_generation.py) | `_ensure_symbol_contract` 写盘改 `safe_join`（P-229 边界整改，登记 W-033） |
| [boundary_registry.yaml#L924](../../tests/boundary_registry.yaml#L924) | 新增 W-033：`_ensure_symbol_contract` 动态写盘登记（`safe_join`，owner P-229） |

## 2. 测试

| 文件 | 覆盖 |
|---|---|
| [test_blueprint_canonical.py](../../tests/test_blueprint_canonical.py) | 新增 3 例：canonical 可解析且签名保留、JSON 孪生兜底、双坏返回 `None` |
| [test_blueprint_yaml_repair.py](../../tests/test_blueprint_yaml_repair.py) | 修复成功改为 `load_blueprint(...) is not None`；不可解析断言 `RuntimeError("blueprint_unparsable")` + `fallback=fail_closed` |
| [test_codegen_evidence.py](../../tests/test_codegen_evidence.py) | 蓝图缺失断言 `blueprint_unavailable` + `no_compute_unit` + `not report.ok`；写报告用例先落蓝图 |
| [test_blueprint_persistence.py](../../tests/test_blueprint_persistence.py) | 成功用例改为解析结构比对（canonical 会重排缩进）+ 断言 JSON 孪生 |
| [test_rc_executor.py](../../tests/test_rc_executor.py) | 预算注入用例显式关掉 `architecture_planning`（假 LLM 只出代码，不产蓝图） |

## 3. 读数

```
pytest tests/test_blueprint_persistence.py \
       tests/test_rc_executor.py::TestComputeBudgetBlock::test_compute_budget_injected_into_code_generation \
       tests/test_boundary_coverage.py tests/test_blueprint_canonical.py \
       tests/test_blueprint_yaml_repair.py tests/test_codegen_evidence.py -q
56 passed
```

红→绿记录：改动前 `test_artifact_written_on_success`（逐字比对）与 `test_compute_budget_injected_into_code_generation`（`blueprint_unparsable` 抛错）为红；按 canonical 语义更新断言后转绿。

全量回归：

```
pytest tests -q
6 failed, 4236 passed, 108 skipped in 581.32s
```

6 项失败均为本机环境类（`test_hitl_advanced` 壳钩子 WinError 193、`test_memory_system` 4 项 Keras 3、`test_rc_sentinel` bash 路径），与 P-230 改动无交集；P-230 相关套件全绿。

## 4. 现场预期

下一个 Stage 10 运行应出现：

```
Canonical blueprint written (NNNN chars, source=canonical)
```

失败分支应出现：

- `blueprint_unparsable: ScannerError: ...` 且 `stage-10/codegen_decision.json` 含 `fallback: fail_closed`；
- 证据门 `blueprint_unavailable`（不再 `ok=true`）；
- 修复重试 prompt 内含 `- The parser reported: <ExcType>: <msg>`。

## 5. 未做

未部署、未重跑 B 站；未改 YAML 预处理与出口门失败码集合；未实现修复后 `py_compile`/import 冒烟（候选 P-231）。
