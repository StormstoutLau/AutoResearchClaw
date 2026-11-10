---
id: arc-g0b-governance-base-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g0b-governance-base-IMPLEMENTATION]
upstream: arc-g0b-governance-base-IMPLEMENTATION
---

# 验收清单：G0b 调研批次

## 1. 调研完整性

- [x] A0-1..A0-6 逐项核对现状与缺口
- [x] 实测 `pre-commit run --all-files` 当前 exit 0
- [x] 实测当前六钩子组成与 A0-1 要求不一致
- [x] 核对 `spec/SPEC_PROCESS.md` 缺失、根文件存在、23 处引用
- [x] 核对 `scripts/spec/` 缺失、88 处引用、5 个 ROOT 计算点
- [x] 核对 `spec/grandfather.yaml` 缺失、M7 账本为空、根 CODE_WIKI 缺失
- [x] 核对 CI 无 `spec-gates`
- [x] 路径方案 3 种、钩子方案 3 种均有取舍
- [x] Q3 给出“新文档立即 + 空 grandfather”的可执行结论
- [x] m7/repo/blackbox/spec-gates 有最小语义与失败条件
- [x] 外部锚点 ≥8 项并标验证状态

## 2. 设计输入

- [x] 迁移目录图与根壳模板明确
- [x] SPEC_PROCESS 28 个相对链接重写规则明确
- [x] 钩子 YAML 片段与 entry 路径明确
- [x] grandfather schema 与 dc_validator 读取规则明确
- [x] spec-gates job 片段明确
- [x] A0-1..A0-6 与实施落点一一映射
- [x] U-1..U-6 四元块完整

## 3. 边界

- [x] 未迁移 `SPEC_PROCESS.md`
- [x] 未迁移 `scripts/spec/*`
- [x] 未改 `.pre-commit-config.yaml`
- [x] 未改 `.github/workflows/ci.yml`
- [x] 未创建 `spec/grandfather.yaml`
- [x] 未实现 m7/repo/blackbox
- [x] 未改 `researchclaw/` 代码
- [x] 未改总纲

## 4. 机检

- [x] V1 `dc_validator` → 0 违规
- [x] V2 `step-gate` → 5/5 pass
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → mode=batch, exit 0

## 5. 下一批（实施）

- [ ] 迁移 SPEC_PROCESS + 根指针 + 28 链接
- [ ] 迁移 6 脚本 + 根壳 + ROOT/import 修正
- [ ] 新增 m7/repo/blackbox 钩子
- [ ] 空 `grandfather.yaml` + dc_validator 读取
- [ ] 新增 `spec-gates` CI job
- [ ] 固化 A0-2..A0-4 负向用例
- [ ] 全量 pre-commit 与 CI 验证
