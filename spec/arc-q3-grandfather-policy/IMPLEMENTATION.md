---
id: arc-q3-grandfather-policy-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-q3-grandfather-policy-DESIGN]
upstream: arc-q3-grandfather-policy-DESIGN
---

# 实施记录：Q3 裁决调研（docs-only）

> 本批只做调研与设计；Q3 仍待用户确认，未创建 `grandfather.yaml`、未改 `dc_validator`。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | 定义 Q3 三个子问题与当前事实 | [RESEARCH.md](RESEARCH.md) §1-§2 |
| E-2 | 对比 A 严格 / B 基线+棘轮 / C 永久 / D 宽限 | RESEARCH §3 |
| E-3 | 定义语义触碰 vs 非语义维护 | RESEARCH §4 |
| E-4 | 收集 10 项社区/学术锚点 | RESEARCH §5 |
| E-5 | 给出明确裁决建议 B 与参数 | RESEARCH §7 |
| E-6 | 落 grandfather schema、validator 规则、续期、验收 | [DESIGN.md](DESIGN.md) §3-§9 |
| E-7 | 登记 U-1..U-4 | RESEARCH §9 |

## 2. 验证

```bash
python scripts/dc_validator.py spec/arc-q3-grandfather-policy/RESEARCH.md \
  spec/arc-q3-grandfather-policy/DESIGN.md spec/arc-q3-grandfather-policy/IMPLEMENTATION.md \
  spec/arc-q3-grandfather-policy/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python tools/spec_runner/spec_runner.py step-gate \
  --session specwf-p019-arc-q3-grandfather-policy --expect research design implement verify finalize
python scripts/console_gen.py --check
python scripts/private_config_check.py spec/arc-q3-grandfather-policy docs/PROGRESS.md docs/CONSOLE.md
python scripts/step_enforce.py --base HEAD \
  spec/arc-q3-grandfather-policy/RESEARCH.md spec/arc-q3-grandfather-policy/DESIGN.md \
  spec/arc-q3-grandfather-policy/IMPLEMENTATION.md spec/arc-q3-grandfather-policy/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p019-arc-q3-grandfather-policy.jsonl
```

## 3. 结果（2026-11-10）

- V1：`DC 契约校验通过：6 文件，2 结果，0 违规`。
- V2：`step-gate[specwf-p019-arc-q3-grandfather-policy]: 决策链一致 pass → exit 0`。
- V3：`CONSOLE.md 与源一致`。
- V4：`private_config_check` exit 0。
- V5：`step-enforce: mode=batch pid=P-019 ... exit 0`。

## 4. 未执行 / 边界

- 未创建 `spec/grandfather.yaml`。
- 未修改 `scripts/dc_validator.py`。
- 未修改总纲 Q3 状态（仍为“待确认（P-017 建议）”，本批补充 P-019 建议）。
- 未实施 G0b 迁移/钩子/CI。
- 未改 `researchclaw/` 代码。
