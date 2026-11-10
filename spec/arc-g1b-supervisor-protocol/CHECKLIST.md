---
id: arc-g1b-supervisor-protocol-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-IMPLEMENTATION]
upstream: arc-g1b-supervisor-protocol-IMPLEMENTATION
---

# 验收清单：G1b 调研

## 1. 调研完整性

- [x] A1-2/3/7/9/10/11/12 七项全部映射到子问题
- [x] 现状事实 10 项，均给文件与行号
- [x] 四个子问题各 3 方案并给出推荐理由
- [x] 退出码表覆盖四类错误 + 保守默认
- [x] supervisor 循环含退避、上限、稳定期重置
- [x] attempt 与 `stage-NN_v{k}` 的语义差异写明
- [x] SSE 缺口语义（`stream.gap`）显式定义
- [x] outbox 幂等键定义

## 2. 锚点质量

- [x] 锚点 10 项：crash-only / microreboot / AWS 退避 / systemd / K8s / WHATWG SSE / Temporal / outbox / Stripe / SRE
- [x] T1 占 9 项，T1 论文 2 项
- [x] 每条给出可回源 URL
- [x] 未把二手博客当作唯一依据

## 3. 边界

- [x] 未改运行时代码
- [x] 未新增 CLI / 路由
- [x] 未改总纲与门禁

## 4. 机检

- [x] V1 `dc_validator` 四文档 → 0 违规
- [x] V2 `step-gate --expect` → 5/5
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → exit 0

## 5. 实施批（P-029）前置

- [ ] 退出码契约与 `classify_exit` 单测先行
- [ ] supervisor 用临时 run 做 kill/重启集成测试
- [ ] SSE 用 TestClient 做「断线 + Last-Event-ID」用例
- [ ] outbox 做「崩溃后不重复执行」用例
- [ ] 三层状态做「attempt 失败不写 Stage」负向用例
