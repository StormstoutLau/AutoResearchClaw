---
id: arc-stage10-repair-minimal-edit-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-minimal-edit-DESIGN]
upstream: arc-stage10-repair-minimal-edit-DESIGN
---

# 实施：Stage 10 修复的作用域与最小改动（P-231）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [entrypoint_contract.py#L106](../../researchclaw/pipeline/entrypoint_contract.py#L106) | 新增 `patch_entrypoint_guard`（D-1）：AST 找零参入口，追加 guard；缺 `METRIC_DEF` 时注入定义行，数值行只在返回 dict 含该指标时打印 |
| 同上 #L171 | `build_entrypoint_prompt` 增 `symbol_contract` 参数；有契约时改写规则 4（main.py 自己的符号不得外借） |
| [codegen_evidence.py#L307](../../researchclaw/pipeline/codegen_evidence.py#L307) | 新增 `symbol_contract_block`（D-2）：文件 → 声明符号 + defined/MISSING，2000 字符上限 |
| [\_code_generation.py#L237](../../researchclaw/pipeline/stage_impls/_code_generation.py#L237) | 新增 `_contract_issues`（D-4）：语法 + 入口 + 符号一次校验 |
| 同上 #L269 | 新增 `_smoke_modules`（D-5）：进程内 `compile()` + 子解释器 import；交付模块缺失为 failure，第三方缺包为 warning |
| 同上 #L327 | `_generate_entrypoint` 接 `blueprint`，候选缺声明符号即拒，并把缺失名回传给下一次 attempt |
| 同上 #L390 | `_ensure_entrypoint` 改为补丁优先（D-1），LLM 仅在补丁不可用时调用；写盘前过 `_contract_issues`（D-4） |
| 同上 #L450 | 新增 `_valid_single_file` + `_repair_one_file_for_symbols`（D-3/D-6）：一次一个文件、16k→32k、二次截断即放弃 |
| 同上 #L590 | `_ensure_symbol_contract` 改按文件循环（D-3），合并后先查符号再查入口契约（D-4） |
| 同上 #L2437 | 对齐重生成：写盘后依次 `_ensure_entrypoint` → `_ensure_symbol_contract` → `_contract_issues`，失败回滚整组（D-4） |
| 同上 #L2705 | 出口前插入 `_smoke_modules`，失败返回 StageResult FAILED（D-5） |
| [code_agent.py#L1666](../../researchclaw/pipeline/code_agent.py#L1666) | `_repair_critical_issues`：契约块替代 `arch_spec[:4000]`（D-2）、只列受影响文件（D-3）、二次截断转 `_repair_files_individually`（D-6）、preservation 规则（D-7） |
| 同上 #L1872 | 新增 `_repair_files_individually`：每文件一次请求，16k→32k |
| 同上 #L1958 | `_accept_repair_files` 增 `catastrophic_rewrite` 守卫（D-7）；trace 增 `edited_lines` / `split_per_file` |
| [\_helpers.py#L616](../../researchclaw/pipeline/_helpers.py#L616) | 新增 `_extract_named_block`：取回单文件回复时按请求名恢复（L-7） |
| [boundary_registry.yaml#L634](../../tests/boundary_registry.yaml#L634) | 新增 S-063（`_smoke_modules` 子进程，category A，inherit）、W-034（对齐重生成回滚写盘，`safe_join`） |

## 2. 测试

| 文件 | 覆盖 |
|---|---|
| [test_entrypoint_contract.py](../../tests/test_entrypoint_contract.py) | 新增 `TestPatchEntrypointGuard` 5 例、`TestSymbolContractPrompt`、`TestEntrypointSymbolAware`、`TestContractIssues` 2 例、`TestSmokeModules` 3 例；改写 2 例到补丁语义 |
| [test_symbol_recheck.py](../../tests/test_symbol_recheck.py) | 新增 `test_one_request_per_affected_file`（2 文件 → 2 次请求） |
| [test_generation_budget_contract.py](../../tests/test_generation_budget_contract.py) | 新增 `TestRepairSplitOnSecondTruncation`、`TestCatastrophicRewriteGuard` |
| [test_context_budget.py](../../tests/test_context_budget.py) | 截断用例改为新语义：组合 2 次 + 每文件 2 次 = 8 次，trace `split_per_file` |
| [test_codegen_evidence.py](../../tests/test_codegen_evidence.py) | 新增 `TestSymbolContractBlock` 5 例 |

## 3. 读数

```
pytest tests/test_boundary_coverage.py tests/test_entrypoint_contract.py \
       tests/test_symbol_recheck.py tests/test_codegen_evidence.py \
       tests/test_generation_budget_contract.py tests/test_context_budget.py -q
127 passed
```

红→绿记录：
- `test_patches_missing_guard_without_llm` 改动前红（会调用 LLM），补丁路径落地后绿；
- `test_split_repairs_one_file_per_request` 曾因单文件回复被改名为 `main.py` 而红，`_extract_named_block` 落地后绿；
- 边界守卫曾报 S-063 owner/category 与 W-034 未登记，登记后绿。

全量回归：

```
pytest tests -q
6 failed, 4257 passed, 108 skipped in 330.13s
```

6 项失败均为本机环境类（`test_hitl_advanced` 壳钩子 WinError 193、`test_memory_system` 4 项 Keras 3、`test_rc_sentinel` bash 路径），与 P-231 改动无交集。

## 4. 现场预期

下一个 Stage 10 运行应出现：

```
Stage 10: entrypoint guard patched in place (9xxx -> 9xxx chars) — main.py was not regenerated
Stage 10: symbol contract restored by targeted repair (main.py)
```

失败分支：`entrypoint candidate rejected before write (...)`、`symbol repair broke the entrypoint contract (...)`、`Repair still truncated at 32768 — splitting per affected file`、`regen attempt N rejected (...) — restoring the previous files`。

## 5. 未做

未部署、未重跑 B 站；未改 `_extract_multi_file_blocks` 的改名行为；未引入 diff 格式；未做会话摘要。
