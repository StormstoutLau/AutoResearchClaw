---
id: arc-cli-agent-seam-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-wiring-RESEARCH]
upstream: arc-cli-agent-wiring-RESEARCH
---

# 调研：R-3 统一接缝的实施输入

> **Feature**: 按 P-011 的 R-3 路线，把 CLI 代码代理接入 Stage 10/13，并收口配置与验证面。
> **状态**: verified（沿用 P-011 已验证锚点，本批不新增外部检索）
> **Spec 步骤**: Step 1-2

## 1. 调研目标

1. R-3 的四个落点（配置、工厂、Stage 10、Stage 13）在当前代码中的精确插入位置是什么？
2. 哪些现有行为必须保持不变（默认 llm、阶段产物、评审/回退链）？
3. 最小可验证实现边界是什么，哪些留给 U-1/U-5？

## 2. 调研方法

| 工具 | 用途 | 查询 |
|---|---|---|
| SearchCodebase | 定位插入点与现有分支 | `_execute_code_generation`、`_execute_iterative_refine`、`create_code_agent` |
| Read | 读取上下文与变量生命周期 | `_code_generation.py:640-960`、`_execution.py:1013-1590` |
| git log | 确认改动历史 | `create_code_agent`、`CodeAgentConfig` |
| P-011 归档 | 外部锚点与路线 | [arc-cli-agent-wiring/RESEARCH.md](../arc-cli-agent-wiring/RESEARCH.md) |

## 3. 调研发现

### 3.1 插入点事实

| # | 事实 | 位置 |
|---|---|---|
| G-1 | Stage 10 在 `extra_guidance` 组装完成后、Beast Mode 之前是唯一无副作用的插入点 | `_code_generation.py:627-645` |
| G-2 | Beast/CodeAgent/Legacy 是三条互斥分支，通过 `_beast_mode_used`/`_code_agent_active` 控制 | `_code_generation.py:640-930` |
| G-3 | `files` 在所有分支后必有值，且后续统一进入校验/修复循环 | `_code_generation.py:926-960` |
| G-4 | Stage 13 在 `llm is None` 时提前返回；CLI 路径应在该早退之后接入 | `_execution.py:1216-1248` |
| G-5 | Stage 13 每轮先 LLM 改进（`:1366`），再校验/修复（`:1441`），最后运行沙箱 | `_execution.py:1325-1590` |
| G-6 | `candidate_files` 由 `best_files` 与抽取文件合并，保留未重写的支撑模块 | `_execution.py:1390-1395` |
| G-7 | `refinement_log` 是 Stage 13 的唯一结构化日志 | `_execution.py:1154-1184` |
| G-8 | `pipeline/code_agent.py` 的 `CodeAgentConfig` 与 `config.py` 的同名字段完全一致，且无继承关系 | 两处定义 |

### 3.2 必须保持的不变量

1. 默认 `cli_agent.provider="llm"` 时，Stage 10/13 的调用序列与产物不变。
2. CLI 失败必须回退到现有 LLM 路径，不改变阶段状态。
3. `refinement_log.json` 的既有字段不删除；新增字段只增不改。
4. Stage 13 的早退（`llm is None`）保留，避免无 LLM 环境下行为突变。
5. 不改变 `experiment.code_agent` 的阶段开关语义。

### 3.3 外部依据

本批不新增外部检索，沿用 P-011 已验证锚点：

- X-1/X-2/X-3：Claude Code `-p` 管道、Agent SDK、ACP 均为结构化/stdio 通道。
- X-6/X-7：Windows `.cmd` 经 cmd.exe 二次解析，长 prompt 不得走 argv。
- X-9/X-13：简单优先，接线必须带来可测收益。
- X-11：用可执行检查固化架构约束。

## 4. 综合分析

### 4.1 关键发现

1. Stage 10 可在 Beast Mode 前插入“显式 provider”分支，失败后自然落回既有链路。[置信度: ★★★★★]
2. Stage 13 可用两个局部 helper 替换主改进与修复调用，其余循环逻辑不动。[置信度: ★★★★☆]
3. 配置去重可通过“config.py 为规范定义、pipeline 导入”完成，无循环依赖。[置信度: ★★★★★]
4. Codex 目前仍把 prompt 放 argv，存在与 Claude 相同的 Windows 截断风险。[置信度: ★★★★★]

### 4.2 技术 landscape

- 传输：Claude/Codex 均支持 stdin；ACP 已在 LLM 层独立存在。
- 接线：Stage 10/13 都是同步函数，适合在函数内创建一次代理实例。
- 验证：pytest 可覆盖工厂/传输；Stage 接线用 helper 单测，避免启动整条管线。

### 4.3 研究空白

- CLI 后端的质量收益（U-1）仍未测；本批只做接线与可回退，不宣称质量提升。
- Stage 13 的“允许改什么”边界（U-5）未定；本批沿用现有 refine 语义。

## 5. 幻觉抑制审查

| 引用/声明 | 验证方式 | 状态 |
|---|---|---|
| Stage 10 插入点无副作用 | 读码 `:627-645` | ✅ |
| Stage 13 早退在 `:1216` | 读码 | ✅ |
| 两个 `CodeAgentConfig` 字段一致 | 逐字段对照 | ✅ |
| Windows prompt 截断 | 本会话实测 + P-011 X-6 | ✅ |
| CLI 质量收益 | 未测 | ⚠️ 不在本批结论内 |

## 6. 对设计的输入

### 6.1 约束

1. 默认路径零行为变化。
2. CLI 失败必须可回退，并写入结构化日志。
3. prompt 不得进 argv；Codex 同步改为 stdin。
4. 配置类只保留一份定义。
5. 新增检查必须零依赖、可在 CI 与 pre-commit 运行。

### 6.2 未决项

沿用 P-011 的 U-1（质量收益）、U-2（Windows 矩阵）、U-3（传输选型）、U-4（审计口径）、U-5（Stage 13 边界），不重复定义。

## 7. 参考文献

1. [arc-cli-agent-wiring/RESEARCH.md](../arc-cli-agent-wiring/RESEARCH.md) §3-§4（问题链、13 项锚点、路线）。
2. [arc-cli-agent-wiring/DESIGN.md](../arc-cli-agent-wiring/DESIGN.md) §2（D-1..D-9）。
