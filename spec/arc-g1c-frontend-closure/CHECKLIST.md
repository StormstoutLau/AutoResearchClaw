---
id: arc-g1c-frontend-closure-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1c-frontend-closure-IMPLEMENTATION]
upstream: arc-g1c-frontend-closure-IMPLEMENTATION
---

# 验收清单：P-031 闭环（P-036）

## 1. 交付

- [x] `api.js` 暴露 `listEvents` / `streamEvents`
- [x] 事件类型常量与服务端 17 类对齐
- [x] 终止事件后主动关闭流
- [x] `stream.gap` 独立回调
- [x] JSON 游标端点读取 `Last-Event-ID`

## 2. 验证

- [x] HTTP API 5 用例实跑（不再 skip）
- [x] 核心 7 用例
- [x] `node --check` 通过
- [x] 缺口负向用例在 HTTP 层可红

## 3. 未验证

- [ ] 浏览器 `EventSource` 自动重连（U-1，需真实服务人工观察）

## 4. 收口

- [x] PROGRESS P-036
- [x] session 5/5
- [x] CONSOLE 刷新
- [ ] 总纲 v1.3（P-031 前端闭环状态）
