---
id: arc-g0b-implementation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g0b-implementation-IMPLEMENTATION]
upstream: arc-g0b-implementation-IMPLEMENTATION
---

# 验收清单：G0b 完整治理基座

## 1. 交付物齐备

- [x] `spec/SPEC_PROCESS.md` 存在且内容 = 原根文件正文（v1.7.1）
- [x] 根 `SPEC_PROCESS.md` 为指针（无规则内容）
- [x] `spec/templates/` 六模板未动
- [x] `scripts/spec/` 含 6 迁移脚本 + 4 新脚本
- [x] 6 个根兼容壳存在且不含逻辑
- [x] `spec/grandfather.yaml` 存在，`entries: []`
- [x] `.pre-commit-config.yaml` 六必需 + 三额外守卫
- [x] `.github/workflows/ci.yml` 含 `spec-gates` job

## 2. A0-1..A0-6 验收

- [x] A0-1 `pre-commit run --all-files` 全绿（9/9，六必需全 Passed）
- [x] A0-2 新建 `.md` 缺 `status:` → 拒绝（T-1：selftest F1 exit 1）
- [x] A0-3 缺 `verify` → finalize 拒绝（T-2：隔离 repo step-gate exit 1）
- [x] A0-4 verify 后改正文 → digest 不匹配（T-3：隔离 repo exit 1）
- [x] A0-5 手改 `CONSOLE.md` → `--check` 非 0（T-4：exit 1，重生成后 0）
- [x] A0-6 `spec-gates` job 存在且与 3.11–3.13 矩阵并行（无 `needs`）

## 3. Q3 实施前提

- [x] F-1 `dc_validator` 检查逻辑零改动（仅 ROOT/注释/BOM），豁免在 `grandfather_gate.py`
- [x] F-2 豁免仅 dc1/dc2/dc3；`dc4` 登记即 exit 2（selftest F5）
- [x] F-3 `expires_days: 90` 标注「内部政策参数（E3）」并绑定 U-1
- [x] F-4 作用域外文件不消耗条目（selftest F4a）；域外 path 登记 exit 2（F4b）
- [x] F-5 `renewals` append-only、≤1 次（F8）、上限 `cutoff+180`（F6/F7）

## 4. 不变式

- [x] `dc_validator` 的 M2-M6 逻辑与迁移前一致（diff 仅 3 处非逻辑改动）
- [x] 根壳转发后 `python scripts/dc_validator.py` 与真身同结果
- [x] `step_enforce` / `console_gen` 迁移后判定不变（digest / CONSOLE 均 pass）
- [x] 未修改任何历史 IMPLEMENTATION / session 正文

## 5. 机检

- [x] V1 `pre-commit run --all-files` exit 0（9/9 Passed）
- [x] V2 `grandfather_gate --selftest` 11/11 PASS
- [x] V3 `step_enforce --base HEAD` exit 0
- [x] V4 `console_gen --check` 一致
- [x] V5 `m7_stats` exit 0（samples=0）
- [x] V6 `repo_stats --check` exit 0（280/84158/118/41789/21）
- [x] V7 `blackbox_check` exit 0（module=ok，console=skip）
- [x] V8 `roadmap_coverage_check --check` missing=0
- [x] V9 无测试引用被迁移脚本路径（Grep 0 命中）→ 零回归

## 6. 收口

- [x] `docs/PROGRESS.md` 增 P-021 行
- [x] `tools/spec_runner/sessions/specwf-p021-*.jsonl` 5/5
- [x] 总纲 v0.9：G0b 标完成、交付物与验收状态同步
- [x] `docs/CONSOLE.md` 派生刷新；`docs/REPO_STATS.md` 派生刷新

## 7. 残留（不阻塞关闭）

- [ ] U-2 根壳保留期（保留 2 个批次后复审）
- [ ] U-3 blackbox 控制台断言在本地安装后恢复
- [ ] U-4 `repo_stats --check` 是否纳入 CI（当前仅 pre-commit）
