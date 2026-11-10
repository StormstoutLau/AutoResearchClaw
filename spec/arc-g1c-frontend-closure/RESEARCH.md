---
id: arc-g1c-frontend-closure-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1c-event-protocol-DESIGN, arc-g1-residual-analysis-RESEARCH]
upstream: arc-g1-residual-analysis-RESEARCH
---

# 调研：P-031 前端联调闭环条件

> **Feature**：P-036，闭环 A1-2 的消费方（浏览器 `EventSource`）与 HTTP 适配器验证。
> **Spec 步骤**：Step 1-2（T1：改 `frontend-legacy/` 与 `tests/`）

## 1. 缺口

| 项 | 现状 |
|---|---|
| 服务端契约 | 已实现；但本机缺 `fastapi`，4 个 API 用例长期 skip |
| 消费方 | `frontend-legacy/src/services/api.js` 只有 fetch 封装，无 SSE |
| 负向验证 | 缺口（`stream.gap`）只在核心层测过，未在 HTTP 层测 |

## 2. 闭环条件核对

| 条件 | 结论 |
|---|---|
| 依赖可达 | ✅ `pip install fastapi httpx` 成功（0.162.2） |
| 前端落点存在 | ✅ `frontend-legacy/src/services/api.js`（无构建步骤） |
| 可证伪验证 | ✅ HTTP 层可测：游标、`Last-Event-ID`、缺口、终止关流 |
| 浏览器重连 | ⚠️ 需运行服务 + 浏览器，本批不做（见 §4） |

## 3. 方案

| 方案 | 评价 |
|---|---|
| **A 在 api.js 增加 `listEvents` / `streamEvents`** | 最小、无构建依赖；与服务端事件类型常量对齐 |
| B 新建独立 SDK 模块 | 过度设计，仅一个消费方 |
| C 只补服务端测试，不动前端 | 消费方仍缺，未闭环 |

**裁决 A**。

## 4. 边界

- 浏览器级 `EventSource` 自动重连**未在本批验证**：需要真实服务与人工观察；协议层已由「`Last-Event-ID` 优先 + 缺口显式」用例覆盖。
- 不引入前端构建链。

## 5. 未决

- **U-1 浏览器重连手工验证**：判据 = 断网/重启服务后 UI 从 `Last-Event-ID` 续；触发 = UI 接入；E2。

## 6. 引用

1. WHATWG HTML §9.2（`EventSource` 重连与 `Last-Event-ID`）。
2. 仓内：[P-031 DESIGN](../arc-g1c-event-protocol/DESIGN.md)、[P-035 §4](../arc-g1-residual-analysis/RESEARCH.md)。
