---
id: arc-g1-review-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1-review-fixes-IMPLEMENTATION]
upstream: arc-g1-review-fixes-IMPLEMENTATION
---

# 验收清单：P-040（G1 复审缺陷修复）

## 1. 交付

- [x] `verify_chain` 校验 `payload_sha256`（末行 payload 篡改可检）
- [x] summary 当前时做 `chain_tail` 尾闭合；落后时跳过
- [x] `effect.started` 登记进 `EVENT_TYPES` 与前端常量（18 类）
- [x] SSE/WS 预检缺失日志 → 404 / close 1008，且不创建目录
- [x] 流循环复查日志存在性

## 2. 验证

- [x] 新增 8 个用例；协议三文件 30 passed
- [x] G1 范围回归 84 passed
- [x] 末行 payload 篡改：修复前假通过 → 修复后红
- [x] 前端常量 18/18 机械对齐用例

## 3. 未验证

- [ ] `verify_chain` 接入 resume 热路径（U-1，需部分校验语义）
- [ ] 归档删段后的链校验（O-1，既有行为）

## 4. 收口

- [x] PROGRESS P-040
- [x] session 5/5
- [x] CONSOLE 刷新
- [x] 总纲 v1.3a 修订行
