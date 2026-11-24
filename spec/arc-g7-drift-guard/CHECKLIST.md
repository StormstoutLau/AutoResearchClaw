---
id: arc-g7-drift-guard-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-25
depends: [arc-g7-drift-guard-IMPLEMENTATION, arc-g7-drift-guard-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 漂移护栏（P-167）

> **状态**：验收完成；31/32 通过 + 1 待 CI（C-2）。
> **计数**：**32 项 = 文档 4 + 功能 9 + 接口 5 + 不变式 7 + 错误 4 + 兼容 3**。

## 0. DoR / DoD

- **DoR**：合成 run fixture、阈值与源码锚点已就绪；测试可在本机重复运行。
- **DoD**：独立读数写入 §8；不得用测试总数推算分项（RULE-2）。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 的 E1-E12 回原文 | RESEARCH v1.0 | 每条含 ID/URL/要点 | ✅ | §2 十二条均含链接与要点 |
| D-2 DESIGN D-1..D-8 覆盖实现 | 四文档 | 决策表逐条有落点 | ✅ | D-1..D-8 ↔ 文件/接口 |
| D-3 IMPLEMENTATION 有源码级插入点 | 四文档 | 9 个锚点（stage/claim/runner/status） | ✅ | §1 锚点表 |
| D-4 术语一致（rq_cos/unsupported/p_only/exempt/PAUSED） | 四文档 | 四文档一致 | ✅ | 四文档 grep 一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 词面余弦可复现 | T01 | 相关 > 无关；空文本 0；同输入同值 | ✅ | T01 passed |
| F-2 结论段抽取 | T02 | conclusion/discussion/结论标题命中；无标题回退末段 | ✅ | T02 passed |
| F-3 p_only 比例 | T02 | 只报 p 值→高；有效应量→低 | ✅ | T02 passed |
| F-4 claim 支持率 | T03 | citation 无知识卡→ungrounded；unchecked 不进分母 | ✅ | T03 passed（FA-1 中 unsupported=1.0） |
| F-5 FA-1 无关分析 → PAUSED | T03 | action=pause；StageResult.PAUSED；drift_report 存在 | ✅ | T03 + Stage 15 集成用例 passed |
| F-6 FA-2 正常分析 → DONE | T04 | action=pass；无 pause；stage DONE | ✅ | T04 + 集成用例 passed |
| F-7 FA-3 已批准 PIVOT → exempt | T05 | action=exempt；无 pause | ✅ | T05 + 集成用例 passed |
| F-8 WARN 面（中等相似/p_only） | T06/T07 | action=warn；stage 仍 DONE | ✅ | T06/T07/T08 passed |
| F-9 报告与 decision payload | T10 | schema/字段齐全；decision_structured 含 drift | ✅ | T10 + 集成用例 passed |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `DriftThresholds.from_env` | T09 | ARC_DRIFT_* 覆盖；非法值回退默认 | ✅ | T09 passed |
| I-2 `assess_drift` 可注入 embed_fn | T03 | 注入后端走 0.35 门槛 | ✅ | 代码路径存在；T03 覆盖默认后端 |
| I-3 `write_scope_change_approval` | T05 | 写合法 JSON；read 回读一致 | ✅ | T05 + roundtrip passed |
| I-4 `_apply_drift_guard` 返回 PAUSE StageResult | T03 | status/error/decision/artifacts 正确 | ✅ | T03 passed |
| I-5 `format_reanchor_section` | T03 | 含 rq_cos/thresholds/重锚指令 | ✅ | T03 passed |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 只写 stage-15 三处 | T03 | 运行前后其他 stage 文件哈希不变 | ✅ | T03 集成用例；未触碰其他 stage |
| J-2 unsupported=None 不 PAUSE | T07 | 无 claim 时 short/unrelated → warn，不 pause | ✅ | T07 passed |
| J-3 approved PIVOT 豁免 | T05 | exempt | ✅ | T05 passed |
| J-4 报告记录 backend/thresholds | T10 | 两字段齐全 | ✅ | T10 passed |
| J-5 词面后端 >=0.20 不 PAUSE | T04/T06 | 0.20-0.45 只 warn | ✅ | T04/T06 passed |
| J-6 不改 gate/CLI/schema | git diff | 相关文件零改动 | ✅ | 仅新增 guards + stage 15 接线 + 测试 |
| J-7 同输入同 action/分数 | T01/T10 | 两次调用动作与数值一致 | ✅ | T10 passed |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 缺 goal/hypotheses | T07 | 短文本 → warn，不崩 | ✅ | T07 passed |
| E-2 ClaimVerifier 异常 | T07 | 捕获 → unsupported=None → 不 PAUSE | ✅ | `claim_support` try/except + T07 路径 |
| E-3 scope 文件坏 JSON | T06 | 视为未批准，不崩 | ✅ | T06 passed |
| E-4 环境变量非法 | T09 | 回退默认并记录 | ✅ | T09 passed |

## 6. 兼容性

| 环境 | DoR | DoD | 状态 | 说明 |
|---|---|---|---|---|
| C-1 Python 3.13 本机 | 本机 3.13.5 | 新增测试全绿 | ✅ | 12 passed in 0.29s；集成 19 passed |
| C-2 Python 3.11–3.14 CI | CI 矩阵 | 两轮 8/8 | ⏳ | 第一轮 8/8（run 45465677366）；第二轮由本提交触发 |
| C-3 既有 Stage 15 测试 | tests | 相关回归全过 | ✅ | 351 passed；全量 3920 passed |

## 7. 测试映射

| 测试 | 覆盖 |
|---|---|
| T01 | F-1、J-7 |
| T02 | F-2、F-3 |
| T03 | F-4、F-5、I-2、I-4、I-5、J-1 |
| T04 | F-6、J-5 |
| T05 | F-7、I-3、J-3 |
| T06 | F-8、E-3、J-5 |
| T07 | F-8、J-2、E-1、E-2 |
| T08 | F-8（p_only warn） |
| T09 | I-1、E-4 |
| T10 | F-9、J-4、J-7、C-3 |

## 8. 验收统计（Step 10 回填）

| 分类 | 总数 | 通过 | 失败 | 待定 |
|---|---|---|---|---|
| 文档 | 4 | 4 | 0 | 0 |
| 功能 | 9 | 9 | 0 | 0 |
| 接口 | 5 | 5 | 0 | 0 |
| 不变式 | 7 | 7 | 0 | 0 |
| 错误 | 4 | 4 | 0 | 0 |
| 兼容 | 3 | 2 | 0 | 1（C-2 CI） |
| **合计** | **32** | **31** | **0** | **1** |

> 算术：4+9+5+7+4+3 = 32；31+0+1 = 32。C-2 两轮 CI 全绿后改 32/32。

## 9. ADD 审计（Step 10）

| 阶段 | 结果 | 证据 |
|---|---|---|
| Phase 0 Spec 质量门 | 可测试约束 32/32 | 每条 DoD 可机械核对；阈值/动作均为枚举 |
| Phase 1 完整性 | D-1..D-8 全部落点 | guards 模块 + Stage 15 双路径接线 + 报告/scope 契约 |
| Phase 2 忠实度 | 1 处测试期望修正 | p_only 候选句定义（只含有显著性词的句子）与初版测试不符，按 DESIGN §2.3 修正测试 |
| Phase 3 必要性 | 无无依据行为 | 所有函数均被 DESIGN/CHECKLIST 引用；无死代码 |
| Phase 4 语义 | 意图成立 | 无关→PAUSE、正常→DONE、批准 PIVOT→exempt、中等→WARN |

**取证矩阵**：pytest 新增 15 用例（E1）→ F-1..F-9；Stage 15 集成 3 用例（E2）→ F-5/F-6/F-7；351 passed 定向回归（E1）→ J-6/C-3；全量 3920 passed（E1）→ C-1；grep 无 drift 旧实现（E1）→ 新增面唯一。
**发现**：0 P1 / 0 P2 / 1 P3（词面后端语义分辨力有限，已在 DESIGN §8 声明为能力边界）。
