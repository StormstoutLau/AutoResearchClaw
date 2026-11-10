---
id: arc-a1-9-session-resume-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-a1-9-session-resume-IMPLEMENTATION]
upstream: arc-a1-9-session-resume-IMPLEMENTATION
---

# 验收清单：P-037（A1-9 接线）

## 1. 交付

- [x] `SESSION_RESUME_BACKENDS` 登记 `claude_code`
- [x] 首跑 `--session-id`、重试 `--resume`
- [x] 会话不存在时显式新建并记 `resumed=false`
- [x] Stage 10/13 传入 `(run_dir, stage)` 会话上下文
- [x] attempt 记录写真实 `session_id` 与 `context_replayed`
- [x] 旧日志不冒充本次尝试

## 2. 验证

- [x] 新增 6 用例 + 白名单改写，22 passed
- [x] 相关回归 91 passed
- [x] 全量 3106 passed（7 项环境性失败与本批无关）
- [x] bogus session 实测 exit 1（T1）

## 3. 未验证

- [ ] 「静默新建」的 provider 侧机械识别（U-1，需 JSON 输出）
- [ ] PIVOT 重跑是否改用新会话（U-2，待 G2）
- [ ] C 站 seaviv（用户要求不动）

## 4. 收口

- [x] PROGRESS P-037
- [x] session 5/5
- [x] CONSOLE 刷新
- [ ] 总纲 v1.3（A1-9 状态）
