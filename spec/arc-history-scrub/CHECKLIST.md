---
id: arc-history-scrub-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-history-scrub-IMPLEMENTATION]
upstream: arc-history-scrub-IMPLEMENTATION
---

# 验收清单：历史脱敏

## 1. 改写

- [x] 全量 refs 已备份（bundle）
- [x] 未提交工作区已备份并恢复
- [x] `git filter-repo` 执行成功（323 提交）
- [x] `origin` 已恢复

## 2. 验证

- [x] 私网 IP 全历史 0 命中
- [x] SSH 用户名全历史 0 命中
- [x] 主隧道端口全历史 0 命中
- [x] 备用隧道端口全历史 0 命中
- [x] 旧 HEAD 对象不可达、reflog 为空
- [x] 当前树扫描 0 违规
- [x] B 站测试 21 passed / 9 skipped
- [x] pre-commit 全绿

## 3. 未执行

- [x] 强推远端（需单独授权）
- [x] 删除旧历史备份（确认后）
