---
id: arc-g1-hardening-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-08
depends: [arc-g1-hardening-IMPLEMENTATION]
upstream: arc-g1-hardening-IMPLEMENTATION
---

# 验收清单：G-1 急救项

## 1. H-1..H-8

- [x] H-1 `run-1.json` 主路径含 `returncode`，两个 writer 合并
- [x] H-2 `max_retries=0` 调 1 次、`=2` 最多 3 次
- [x] H-3 Stage 20/23 产出 `claim_verification.json`
- [x] H-4 检索降级写 `retrieval_status.json` 且 `retrieval_degraded=true`
- [x] H-5 失败 run 不进入聚合，`excluded_runs` 记录原因
- [x] H-6 子进程读不到 `OPENAI_API_KEY`
- [x] H-7 `..` / 绝对路径 / 嵌套遍历 / symlink 四类逃逸全拒
- [x] H-8 默认无 `*`；非回环无 token 启动失败

## 2. 裁决

- [x] Q18=A 语义登记（L1 清单 + Croissant 四字段）
- [x] Q19=A 代码落地（回环默认 + 强制 token）
- [x] Q20=A′ 语义登记（分层账本，代码归 G6）

## 3. 机检

- [x] 8 个测试文件 28 用例全绿
- [x] 既有回归子集 346 passed / 5 skipped
- [x] `roadmap_coverage_check --check` missing=0
- [x] dc-validator 四文档 0 违规
- [x] 106 验收计数不变
