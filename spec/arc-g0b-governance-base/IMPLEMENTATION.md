---
id: arc-g0b-governance-base-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g0b-governance-base-DESIGN]
upstream: arc-g0b-governance-base-DESIGN
---

# 实施记录：G0b 调研批次（docs-only）

> 本批只落调研/设计，不迁移文件、不改钩子、不改 CI。E-* 为文档落点，V-* 为文档门禁。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | 实测 G0b 当前状态（钩子、路径、引用、M7、CI） | [RESEARCH.md](RESEARCH.md) §2 |
| E-2 | 建立 A0-1..A0-6 缺口表 | RESEARCH §3 |
| E-3 | 对比 SPEC_PROCESS/脚本路径三方案 | RESEARCH §4 |
| E-4 | 对比钩子组成三方案，确定 6 必需 + 2 额外 | RESEARCH §5 |
| E-5 | 确定 Q3：新文档立即 + 空 grandfather | RESEARCH §6 |
| E-6 | 定义 m7/repo/blackbox/spec-gates 最小语义 | RESEARCH §7、[DESIGN.md](DESIGN.md) §6-§8 |
| E-7 | 给出外部锚点、风险与实施顺序 | RESEARCH §8-§10 |
| E-8 | 登记 U-1..U-6 | RESEARCH §11 |

## 2. 验证

```bash
python scripts/dc_validator.py spec/arc-g0b-governance-base/RESEARCH.md \
  spec/arc-g0b-governance-base/DESIGN.md spec/arc-g0b-governance-base/IMPLEMENTATION.md \
  spec/arc-g0b-governance-base/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python tools/spec_runner/spec_runner.py step-gate \
  --session specwf-p017-arc-g0b-governance-base --expect research design implement verify finalize
python scripts/console_gen.py --check
python scripts/private_config_check.py spec/arc-g0b-governance-base docs/PROGRESS.md docs/CONSOLE.md
python scripts/step_enforce.py --base HEAD \
  spec/arc-g0b-governance-base/RESEARCH.md spec/arc-g0b-governance-base/DESIGN.md \
  spec/arc-g0b-governance-base/IMPLEMENTATION.md spec/arc-g0b-governance-base/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p017-arc-g0b-governance-base.jsonl
```

## 3. 结果（2026-11-10）

- V1：`DC 契约校验通过：6 文件，2 结果，0 违规`。
- V2：`step-gate[specwf-p017-arc-g0b-governance-base]: 决策链一致 pass → exit 0`。
- V3：`CONSOLE.md 与源一致`。
- V4：`private_config_check` exit 0。
- V5：`step-enforce: mode=batch pid=P-017 sessions=specwf-p017-arc-g0b-governance-base ... exit 0`。

## 4. 未执行 / 边界

- 未迁移 `SPEC_PROCESS.md`，未创建 `spec/SPEC_PROCESS.md`。
- 未迁移 `scripts/spec/*`，未创建根兼容壳。
- 未新增 m7/repo/blackbox 钩子，未改 pre-commit 组成。
- 未创建 `spec/grandfather.yaml`，未实现 dc_validator 的 grandfather 读取。
- 未新增 CI `spec-gates` job。
- 未实现 m7_stats / repo_stats / blackbox_check。
- 未固化 A0-2..A0-4 负向用例。
- 未修改 `arc-master-roadmap.md`（G0b 仍标未就绪）。
