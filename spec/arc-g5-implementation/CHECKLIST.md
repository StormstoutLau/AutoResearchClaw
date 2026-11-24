---
id: arc-g5-implementation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-g5-implementation-IMPLEMENTATION, arc-g5-implementation-DESIGN]
upstream: null
---

# 审查验收 Checklist：G5 知识接入与 Grounded QA（P-155）

> **Feature**：P-155。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.1 / verified）。
> **状态**：验收完成；功能/接口/不变式/错误处理/兼容性项通过，读数见 §10。
> **批次口径**：G5 单批；P-154 仅为决策前序。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-7 对应 RESEARCH §3/§6 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「8 模块 + `__init__`/config 接线 + 2 计数 + 1 钩子 + 7 测试」 |
| 读数在 checklist 有验收项 | ✅ | §10 与 IMPLEMENTATION §9.2 同源 |
| 术语一致 | ✅ | 15/17、500、`retrieval_degraded`、`fulltext`、citation 四字段四文档互查一致 |

## 2. 功能验收

> DoR：夹具与模块签名先于用例存在；DoD：通过条件成立且证据读数落到 T01-T28。
> 执行器：`python scripts/spec/g5_acceptance.py --phase <red|green> [--allow-missing]`。
> 外部证据与算法锚点：RESEARCH §5/§6、IMPLEMENTATION §4。

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| A5-1 空库查询 | 空目录 | `[]` + `empty=true`，无伪造条目 | ✅ | T11 passed；28/28 green |
| A5-2 Paper 500 | 600 条夹具 | 500 入选、重复 0、置信度 0–1 | ✅ | T01-T05 passed |
| A5-3 KG 15/17 | 夹具 KG | 15 实体、17 关系、非法边 0、3 查询 ≥3 实体带 page | ✅ | T07-T09 passed |
| A5-4 5 份 pack | manifest | 5 份可加载；单 run 注入 ≤5 | ✅ | T16 passed（shipped manifest） |
| A5-5 计数同源 | 索引重算 | 文档与重算一致 | ✅ | T27-T28 passed；两脚本 `--knowledge` 读数一致 |
| A5-6 降级显式 | 缺失索引/后端降级 | `retrieval_degraded=true` | ✅ | T12 passed |
| A5-7 全文未就绪 | 全文查询/引用 | `fulltext=false`，引用被拒 | ✅ | T15 passed |
| A5-8 pack 篡改 | 改 digest/签名 | 拒绝加载 | ✅ | T17-T19 passed |
| A5-9 read_position | 保存后重启 | 位置恢复、不重抓 | ✅ | T25-T26 passed |
| GQ-1 默认关闭 | 不启用 GQ | 零文件、与基线逐字节一致 | ✅ | T20 passed |
| GQ-2 citation 四字段 | 有证据回答 | source/locator/quote/digest 齐全且可复算 | ✅ | T21 passed |
| GQ-3 无证据 | 空检索 | `status=insufficient`，无「已证实」 | ✅ | T22 passed |
| GQ-4 依赖失败 | 后端超时/缺失 | `retrieval_degraded=true`，stage DONE | ✅ | T23 passed |
| GQ-5 矛盾策略 | 默认/`policy=block` | 默认 warn；block 时 Stage 20 阻断 | ✅ | T24 + 2 条 Stage 20 接线用例 passed |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `KnowledgeStore` | 查询/计数 | `QueryResult` 六字段齐全 | ✅ | T11-T15 passed |
| `paper_index` | 加载/选择 | 签名与 DESIGN 一致 | ✅ | T01-T06 passed |
| `textbook_kg` | 加载/查询 | 节点带 page | ✅ | T07-T10 passed |
| `skillpack` | 加载/校验 | 返回 `SkillPackInfo` | ✅ | T16-T19 passed |
| `grounded_qa` | 回答/关闭 | GQ 与 NullGQ 均符合契约 | ✅ | T20-T24 + 2 接线 passed |
| `read_position` | 保存/读取 | 按 kind/instance 恢复 | ✅ | T25-T26 passed |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 不伪造数据 | 空库/缺失索引 | 空结果 | ✅ | T11/T12 passed |
| J-2 置信度 0–1 | 混用量纲 | 落库全部 0–1 | ✅ | T04/T05 passed |
| J-3 非法关系不入库 | 非法边夹具 | 拒绝且计数 | ✅ | T08 passed |
| J-4 降级显式 | 缺失索引 | `retrieval_degraded=true` | ✅ | T12/T23 passed |
| J-5 计数单一来源 | 两脚本调用 | 同一函数 | ✅ | T27-T28；两脚本 `--knowledge` |
| J-6 查询只读 | 前后哈希 | 索引不变 | ✅ | T14 passed |
| J-7 SkillPack 拒绝 | 篡改 pack | 加载失败 | ✅ | T17-T19 passed |
| J-8 GQ 关闭零文件 | 关闭后目录扫描 | 无 `grounded_qa/` | ✅ | T20 passed |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 缺失索引 | 空目录 | 空 + 降级 | ✅ | T12 passed |
| Paper 索引损坏 | 非法 JSONL | `ValueError` | ✅ | T06 passed |
| KG JSON 损坏 | 非法 JSON | `ValueError` | ✅ | T10 passed |
| 非法关系 | 未登记 type | 拒绝并计数 | ✅ | T08 passed |
| SkillPack 篡改 | 改文件/签名 | 拒绝加载 | ✅ | T17/T18 passed |
| 未知查询 kind | 非法 kind | `ValueError` | ✅ | T13 passed |

## 6. 性能验收

索引为本地文件与线性查询；本批无性能门槛。一次读数（500 条索引、`limit=10`）：

```text
query_paper_500: 9.07 ms count=10
```

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 写入契约不变 | `knowledge/base.py` 回归 | 既有用例全绿 | ✅ | `test_rc_kb.py` + `test_knowledge_graph.py` + `test_k5_refs.py` 56 passed |
| 既有图查询不变 | `knowledge/graph` 回归 | 全绿 | ✅ | 同上 |
| GQ 默认关闭 | pipeline 基线 | 产物逐字节一致 | ✅ | T20 passed |

## 8. ADD 审计

本批无 ADD 新增或修订。

## 9. Review 记录（Step 8）

- RESEARCH §7 ↔ DESIGN §7 ↔ CHECKLIST §2 的 14 项映射一一对应。
- 外部证据按 SPEC_PROCESS 分层：E1/E2/E3/E5/E6/E7/E8/E9 为 T1，E4 为 T3 线索；引用核验表见 RESEARCH §6.1。
- 算法锚点见 IMPLEMENTATION §4；测试清单 T01-T28 见 IMPLEMENTATION §3。
- 实施期新增两处接线（DESIGN §2 已登记）：`KnowledgeBaseConfig.grounded_qa_policy`（默认 `warn`，非法值校验失败）与 `knowledge/__init__.py` 公共导出；GQ-5 另加 2 条 Stage 20 接线用例。
- 红→绿读数见 IMPLEMENTATION §8；门禁读数见 §10。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 6 | 6 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 6 | 6 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **41** | **41** | **0** | **0** |

算术自洽：41 = 4+14+6+8+6+0+3+0；通过 41 = 总数 41。

### 10.2 验收结论

- [x] 验收通过：28 条 T 用例 + 2 条 Stage 20 接线全绿；相关回归 261 passed。
- [ ] 验收不通过：无。

### 10.3 全量回归（本机环境说明）

```text
$ python -m pytest -q -x --tb=short
1 failed, 966 passed, 28 skipped
  tests/test_hitl_advanced.py::TestHookRegistry::test_shell_hooks
  [WinError 193] .sh hook cannot execute on Windows

$ python -m pytest -q -x --tb=line --ignore=tests/test_hitl_advanced.py
1 failed, 1298 passed, 85 skipped
  tests/test_memory_system.py::TestEmbeddings::test_tfidf_fallback
  Keras 3 + transformers requires tf-keras (environment, not this batch)
```

两处失败均为本机环境限制（Windows 不能直接执行 `.sh`；未安装 `tf-keras`），与本批 G5 改动无关；本批新增/修改路径的定向回归见 §2/§7 与 IMPLEMENTATION §9.2。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 代码实施 | 已完成 | 8 模块 + `__init__`/config 接线 + 2 计数脚本 + Stage 20 钩子 |
| 测试与验收 | 已完成 | T01-T28 28/28 green；+2 条 Stage 20 接线；相关回归 261 passed |
| 全量 pytest（本机） | 环境限制 | 见 §10.3；两处失败与本批无关 |
| P-154 口径 | 已定 | 仅为决策前序，不作为独立 feature 批次 |
| 全量 2,487 | 未做 | Q7 已裁决后续批次 |
| 非对称签名 | 未做 | 本批 HMAC；公钥签名后续 |
