---
id: arc-g1b-implementation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1b-implementation-IMPLEMENTATION]
upstream: arc-g1b-implementation-IMPLEMENTATION
---

# 验收清单：G1b 实施（P-029）

## 1. 三缺口

- [x] R-1 `85` 暂停码生效；暂停不重启、不写失败
- [x] R-2 supervisor 不持租约；仅清理已过期残留
- [x] R-3 续期线程生效；租约丢失后拒绝写事件

## 2. 验收

- [x] A1-7 六类退出码 + `is_retryable` 仅 75
- [x] A1-11 attempt 记录不迁移 Stage 状态
- [x] A1-12 resume_note ≤500 字且含产物/恢复要求
- [x] A1-10 outbox 去重与失败终态
- [x] A1-3 supervisor 循环（单测覆盖退避/预算/暂停）
- [ ] A1-3 真实 kill -9 集成（本机未执行，登记 U-1）
- [ ] A1-9 backend 会话续接（仅记录字段，U-2）
- [ ] A1-2 SSE/WS（切分到 P-031）

## 3. 机检

- [x] V1 G1b 单测 21 passed
- [x] V2 runner/CLI 回归 99 passed
- [x] V3 `pre-commit run --all-files` 9/9
- [x] V4 `step_enforce --base HEAD` exit 0
- [x] V5 packaging/docs 子集无回归

## 4. 收口

- [x] PROGRESS P-029
- [x] session 5/5
- [x] CONSOLE 派生刷新
- [ ] 总纲 G1 状态更新（待 P-031 完成后一并标记）

## 5. 遗留

- [ ] U-1 kill -9 集成测试（需真实子进程）
- [ ] U-2 backend 会话续接能力探测
- [ ] U-3 残留租约按 pid 存活的精细判定
