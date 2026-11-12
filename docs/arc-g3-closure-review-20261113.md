# P-088 G3 收口独立异构复核（2026-11-13）

> **性质**：Layer-0 独立异构复核（T3，零生产代码/零门禁）。不采信 P-083..P-087 的结论，按 G3 的 17 项验收（A3-1..8、AN-1..6、FC-1..3）逐项一手取证：测试复跑、读码、运行时探针。**异构性**：复审会话（GLM-5.3-Flash）与实施会话（DeepSeek-V4.1-Flash）为不同模型基座（RULE-5）；单向权限，只标记问题。
> **基线**：`4efc901`（P-086/P-087 已提交）。**编号**：本批占用 **P-088**；若需修复，建议 **P-089**（T1），修复后重新收口。

## 1. 一手复验（V 表）

| # | 验收 | 取证方式 | 结果 |
|---|---|---|---|
| V-1 | A3-1 三出口一致 | P-083 套件 + E2 探针（Stage 20→22→23） | ✅ 三出口状态/export/trace 一致 |
| V-2 | A3-2 summary 篡改判红 | 探针：写侧车后改 `pipeline_summary.json` | ✅ `E_SUMMARY_TAMPERED` |
| V-3 | A3-3 断网 digest 复算 | `verify_claim_digests` + `verify_tree` 单测/探针 | ✅ 篡改 blob/pointer 均判 `E_ARTIFACT_HASH` |
| V-4 | A3-4 K5 未解析阻断 | P-087 wiring 测试 + 读码 | ✅ Stage 22/23 均 `E_K5_UNRESOLVED_REF` |
| V-5 | A3-5 retrieval 降级显式 | P-087 wiring 测试 + summary 读码 | ✅ 论文注记 + 报告 + summary 布尔 |
| V-6 | A3-6 RunMandate 记录/不可变 | `test_mandate_is_written_once_and_immutable` 等 | ⚠️ 记录/不可变 ✅；「改配置不撤销在跑 run」无执行点/测试 → O-2 |
| V-7 | A3-7 每次 LLM 请求记录 prompt_version；claim 可追溯 | 读码 `manager.for_stage`、`_chat_with_prompt`、C4 schema | ❌ 仅渲染点日志；直连请求不记；claim 无版本字段 → **D-1 P2** |
| V-8 | A3-8 越界 StageHandback 交回路由 | 读码 `write_handback` 全仓引用 | ❌ 仅定义+测试，无阶段生产者/路由 → **D-2 P2** |
| V-9 | AN-1 节点哈希可复算 | `test_artifact_node.py` + 探针 | ✅ 篡改 blob/pointer 判红；materialized 原始产物漂移不检测 → O-1 |
| V-10 | AN-2 父节点可解析/无环 | 单测 + 缺失父探针 | ✅ `E_ARTIFACT_PARENT` |
| V-11 | AN-3 inputs_digest 重算 | 单测 | ✅ |
| V-12 | AN-4 project(node) 与旧 evidence 等值 | `test_project_to_evidence_uses_content_hash` | ✅ |
| V-13 | AN-5 pointer/snapshot 边界 | pointer/sensitive 单测 | ✅（`locator+content_hash`，`materialized` 表达 pointer/snapshot） |
| V-14 | AN-6 sensitive 只存指针 | `test_build_node_pointer_for_sensitive` | ✅ |
| V-15 | FC-1 3 轮同签名零新增 → PAUSE | `test_stage_events.py` | ✅ |
| V-16 | FC-2 有新增 → 放行 | `test_loop_does_not_pause_when_rows_change` | ✅ |
| V-17 | FC-3 网络错误豁免 | `test_network_error_round_is_exempt` | ✅ |

**测试读数（E1）**：G3 相关 11 文件 **185 passed**（15.35s）。

## 2. 缺口专项（X 表）

| # | 缺口 | 证据 | 定级 |
|---|---|---|---|
| X-1 | **A3-7 仅渲染点记录**：`prompt_version` 只在 `PromptManager.for_stage` 计算并 `logger.info`；`_chat_with_prompt` 直连调用（debate/code agent/repair 等）不携带版本；C4 schema 无 `prompt_version`，claim 无法追溯 | `manager.py` L244-L252；全仓 `prompt_version` 仅 3 处；`c4_claim_record.schema.json` 只有 `policy_version` | **D-1 P2** |
| X-2 | **A3-8 无 handback 生产者**：`write_handback` 仅定义（`mandate.py` L165），production 代码零调用；runner 只在文件存在时校验，端到端「交回路由」未成立 | 全仓 grep `write_handback` 仅 1 处定义 | **D-2 P2** |
| X-3 | **A3-6 缺「配置变更不撤销在跑 run」执行点**：mandate 只写不读（除 handback scope）；配置对象在 `execute_pipeline` 入参后不再重读，效果上满足，但无测试/显式对照 | 读码 `execute_pipeline` + `ensure_run_mandate` 调用点 | O-2 P3 |
| X-4 | **A3-7/A3-8 编号映射互换**：总纲 L419-L420 定义 A3-7=prompt_version、A3-8=StageHandback；P-087 DESIGN/CHECKLIST 写成 A3-7=StageHandback、A3-8=prompt_version | 总纲 vs P-087 文档 | **D-3 P3** |
| X-5 | **AN-1 materialized 原始产物漂移**：`verify_tree` 对 `materialized=true` 只校验 blob；注册后修改 stage 产物文件不判红（M0 §3.3 以 blob 为 canonical，属设计边界） | `artifact_node.py` L313-L328；探针 AN_1_hash=false / blob 篡改=true | O-1 P3 |
| X-6 | **A3-7 直连请求面**：`_chat_with_prompt` 无 `prompt_version` 参数；即使补日志，仍需覆盖直接 `llm.chat` 调用 | 读码 `_helpers.py` L755-L813 | D-1 子项 |

## 3. 结论

- **G3 主线成立**：17 项中 15 项可判绿；A3-1..A3-5、AN-1..6、FC-1..3 的机制与读数均一手复现（185 passed）。
- **不可直接收口**：A3-7（P2）与 A3-8（P2）按验收原文未成立；A3-6 缺执行点/测试（O），A3-7/A3-8 编号映射互换（D-3 P3）。
- **建议 P-089 修复批（T1）**，范围最小化：
  1. **A3-7**：为每次 LLM 请求记录 `prompt_version`（至少 `_chat_with_prompt` 全量 + 直接 `llm.chat` 调用点），并在 claim 导出/标注中持久化生成版本（或独立 `claim_prompt_versions.json`）。
  2. **A3-8**：选一个真实暂停场景（如 Stage 17 无指标阻断 / Stage 20 gate blocked）产出 `handback.json`，走 `write_handback` + runner 路由，补端到端测试。
  3. **A3-6**：补「配置变更不影响已接受 run mandate」的对照测试（或显式把 mandate 读入 runner 作为 scope 判定源）。
  4. **D-3**：总纲与 P-087 文档统一 A3-7/A3-8 编号；修订 P-087 四文档需走 digest 受控回边。
  5. 顺带 P-083 O-3（测试计数）与 P-084 D-3..D-6 可并入或另排。
- 修复后建议 **P-090 复评**（T3，核 2 项 P2 + 1 项 P3），再决定 G4/G5/G8a。

## 4. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 复跑（E1） | V-1、V-9..V-17 | ✅ 185 passed |
| 运行时探针（E2，含篡改/缺失父/边界） | V-2、V-3、V-9、X-5 | ✅ 判红路径生效；X-5 边界确认 |
| 静态读码（E3） | V-4..V-8、X-1..X-4、X-6 | ✅ 缺口定位 |
| 登记链核对（E1） | 基线 `4efc901`、G3 17 项映射 | ✅ |
| 盲区扫描（E4，扫描范围：17 项验收 × 正/负向） | 全部 | **发现 2 项 P2 + 2 项 P3/O** |

## 5. 处置

- 本批零代码/零门禁；未改任何实现。
- 登记 P-088（T3）；若用户批准，P-089 按上述 4 项修复，P-090 复评后收口 G3。
