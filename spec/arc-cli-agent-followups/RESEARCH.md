---
id: arc-cli-agent-followups-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-wiring-RESEARCH, arc-cli-agent-seam-DESIGN]
upstream: arc-cli-agent-seam-DESIGN
---

# 调研：CLI 代理未决项收口与前移

> **Feature**: P-011/P-012 遗留的 U-1..U-5 收口、前移与再登记。
> **状态**: verified（基于 P-011/P-012 已归档事实，无新增外部检索）
> **Spec 步骤**: Step 1-2

## 1. 调研目标

1. U-1..U-5 中哪些触发条件已经命中？命中后是否有裁决记录？
2. 哪些项在 P-012 的“未纳入本批”中掉队？
3. P-011 §5.3 的待修正项是否仍然有效？

## 2. 调研方法

| 工具 | 用途 | 查询 |
|---|---|---|
| Grep | 全仓 U-项引用与四元块 | `U-[1-5]` |
| Read | 触发条件与实现状态 | P-011 §6.4、P-011 DESIGN §8、P-012 §5-§7 |
| Read | Stage 13 CLI 调用点 | `_execution.py` refine/repair |
| Read | 返工图登记形态 | `docs/rework-graph.json` |

## 3. 调研发现

### 3.1 触发状态

| 项 | 触发条件 | 是否命中 | 证据 |
|---|---|---|---|
| U-1 质量收益 A/B | 真实 run 连续两轮 LLM 失败且为跨文件结构 | 否 | 尚无该 run |
| U-2 Windows 矩阵 | CI 增加 Windows job 或第二例编码问题 | 否 | CI 仍为 ubuntu |
| U-3 传输选型 | R-3 进入设计阶段 | **是** | P-012 DESIGN E-6、IMPLEMENTATION E-3 |
| U-4 审计口径 | 高审计 run 选择非 API 后端 | 否 | 尚无该 run |
| U-5 Stage 13 边界 | R-3 进入 Stage 13 接线 | **是** | P-012 E-5 已接线 |

### 3.2 收口缺口

- **F-1 U-3 未记录裁决**：P-012 实际选择 CLI-stdin（Claude/Codex），但 U-3 的“当前倾向”仍写“优先 ACP”，二者未对齐。
- **F-2 U-5 未落地**：P-012 的 Stage 13 CLI refine 直接复用现有 prompt，未限制“重写实验设计”；与 U-5 倾向“只修复与参数级改进”不一致。
- **F-3 U-4 掉队**：P-011 登记了 U-4，但 P-012 IMPLEMENTATION §5 与 CHECKLIST §6 的“未纳入本批”均未列 U-4。
- **F-4 P-011 §5.3 过期**：前两条（P-007 表述、示例配置标注）已被 P-012 的实际接线取代；第三条（X-4/X-5/X-11 正文未抓）仍有效但不阻塞功能。
- **F-5 返工图为空**：`docs/rework-graph.json` 的 `forks` 为 `[]`，未登记未决项；按规范这是允许的，未决项以四元块登记即可。

### 3.3 处置建议

| 项 | 处置 | 理由 |
|---|---|---|
| U-3 | **关闭**：Stage 10/13 采用 CLI-stdin；ACP 保持 LLM 层；SDK 暂缓 | 与 P-012 实现一致，避免“倾向”与代码相反 |
| U-5 | **关闭并落地**：Stage 13 CLI refine 加“只修复/调参、不改实验设计”边界提示 + 审计字段 | 可在不改变默认 LLM 路径的前提下约束 CLI 路径 |
| U-4 | **前移到本批**：在 P-013 重新登记，保留原触发条件 | 修复 P-012 的掉队 |
| U-1/U-2 | **保持 pending**：触发条件未命中，不提前实现 | 避免无证据的复杂度 |
| 新开 U-6 | **硬门（可选）**：若首次观察到 Stage 13 CLI 改动条件集，则增加静态/差异门 | 先观察再建门，避免过度设计 |

## 4. 综合分析

1. U-3/U-5 属于“触发已命中但未收口”，是本批必须解决的登记缺陷。[置信度: ★★★★★]
2. U-5 的边界适合做成“提示 + 审计字段”，而不是立即引入条件集差异检测；后者误报成本高。[置信度: ★★★★☆]
3. U-1/U-2/U-4 不应在本批实现，只需保持可检索的登记。[置信度: ★★★★★]
4. P-011 §5.3 的过期项不应改归档文档，应在 P-013 IMPLEMENTATION 记录处置。[置信度: ★★★★☆]

## 5. 幻觉抑制审查

| 声明 | 验证方式 | 状态 |
|---|---|---|
| U-3/U-5 触发条件命中 | 对照 P-012 DESIGN/IMPLEMENTATION | ✅ |
| Stage 13 CLI refine 复用现有 prompt | 读 `_execution.py` 调用点 | ✅ |
| P-012 未列 U-4 | 读 IMPLEMENTATION §5、CHECKLIST §6 | ✅ |
| 返工图为空 | 读 `docs/rework-graph.json` | ✅ |

## 6. 对设计的输入

### 6.1 约束

1. 不改变默认 `provider="llm"` 的 Stage 13 prompt 与行为。
2. 不修改 P-011/P-012 归档文档；处置记录写在本批 IMPLEMENTATION。
3. U-5 先做提示级约束，不做条件集静态门。
4. U-4 必须在本批文档中可检索。

### 6.2 未决项登记（四元块）

- **U-1 CLI 代理的边际质量收益**（沿用 P-011）
  - **判据**：同一任务集（≥10 个）上，CLI 后端的成功率/耗时/成本相对 LLM 多阶段有统计意义提升。
  - **触发条件**：真实 run 连续两轮 LLM 失败且失败原因为跨文件结构。
  - **当前倾向**：暂不实现 A/B；先保持 CLI 为 opt-in。
  - **证据等级**：E1。

- **U-2 Windows 支持基线**（沿用 P-011）
  - **判据**：Windows 10/11 + PowerShell 5/7 上 `.CMD`、含空格路径、UTF-8 中文 prompt 三类用例全绿。
  - **触发条件**：CI 增加 Windows job，或第二例 argv/编码问题。
  - **当前倾向**：stdin + `taskkill /T` 为最低基线。
  - **证据等级**：E2。

- **U-4 审计口径**（本批前移）
  - **判据**：CLI/ACP 后端能输出归一化的工具调用与文件变更记录，满足 Q17 对高审计 run 的要求。
  - **触发条件**：任何需要“推理链可审计”的 run 选择非 API 后端。
  - **当前倾向**：高审计 run 禁用 CLI/ACP，仅用 API-first。
  - **证据等级**：E1。

- **U-6 Stage 13 CLI 边界的硬门**
  - **判据**：出现“CLI refine 改动条件集/实验设计”的可复现案例后，静态或差异门能拒绝该产物。
  - **触发条件**：首次观察到 Stage 13 CLI 改动 `condition=` 集合或实验设计字段；或用户第二次报告。
  - **当前倾向**：先使用提示级边界 + `refinement_log.cli_agent.boundary` 审计；暂不建硬门。
  - **证据等级**：E1。

## 7. 参考文献

1. [arc-cli-agent-wiring/RESEARCH.md](../arc-cli-agent-wiring/RESEARCH.md) §6.4（U-1..U-4）。
2. [arc-cli-agent-wiring/DESIGN.md](../arc-cli-agent-wiring/DESIGN.md) §8（U-5）。
3. [arc-cli-agent-seam/DESIGN.md](../arc-cli-agent-seam/DESIGN.md) §7（U-5 现状）。
4. [arc-cli-agent-seam/IMPLEMENTATION.md](../arc-cli-agent-seam/IMPLEMENTATION.md) §5（未执行项）。
