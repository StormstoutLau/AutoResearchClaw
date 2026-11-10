---
id: arc-roadmap-v07-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-roadmap-v07-DESIGN]
upstream: arc-roadmap-v07-DESIGN
---

# 实施记录：总纲 v0.7

> 本批只改总纲与 P-018 文档；不改代码、不改 106 计数。

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-01 | 版本 0.6→0.7、标题、v0.7 修订块 | `arc-master-roadmap.md:4-29` |
| E-02 | G0b 标题“未就绪（调研完成，待实施）” | `arc-master-roadmap.md:191` |
| E-03 | G0b 状态注（P-017 实测 + S-1/T-1/H-1） | `arc-master-roadmap.md:193` |
| E-04 | 交付物补 `spec_map` / `blackbox` / 根壳 / 空 grandfather | `arc-master-roadmap.md:197-203` |
| E-05 | A0-1 六必需 + 两额外；表后机制注 | `arc-master-roadmap.md:209-216` |
| E-06 | Q3 建议 + 外锚扩展 | `arc-master-roadmap.md:218-220` |
| E-07 | Q3/Q11 状态 | `arc-master-roadmap.md:632,640` |
| E-08 | §11 增 P-017 行 | `arc-master-roadmap.md:747` |

## 2. 验证

```bash
python scripts/roadmap_coverage_check.py --check
python scripts/dc_validator.py spec/arc-roadmap-v07/RESEARCH.md \
  spec/arc-roadmap-v07/DESIGN.md spec/arc-roadmap-v07/IMPLEMENTATION.md \
  spec/arc-roadmap-v07/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python tools/spec_runner/spec_runner.py step-gate \
  --session specwf-p018-arc-roadmap-v07 --expect research design implement verify finalize
python scripts/console_gen.py --check
python scripts/private_config_check.py spec/arc-roadmap-v07 docs/PROGRESS.md docs/CONSOLE.md
python scripts/step_enforce.py --base HEAD \
  spec/arc-roadmap-v07/RESEARCH.md spec/arc-roadmap-v07/DESIGN.md \
  spec/arc-roadmap-v07/IMPLEMENTATION.md spec/arc-roadmap-v07/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p018-arc-roadmap-v07.jsonl
```

## 3. 结果（2026-11-10）

- V1：`roadmap-coverage: accept=106 suite=70 declared=37 missing=0`。
- V2：`DC 契约校验通过：6 文件，2 结果，0 违规`。
- V3：`step-gate[specwf-p018-arc-roadmap-v07]: 决策链一致 pass → exit 0`。
- V4：`CONSOLE.md 与源一致`。
- V5：`private_config_check` exit 0。
- V6：`step-enforce: mode=batch pid=P-017,P-018 ... exit 0`。

## 4. 未执行 / 边界

- 未改 G0b 验收 ID 数量（106 不变）。
- 未改路线顺序、C 套件、G1/G2/G3 验收。
- 未裁决 Q3/Q11；只写 P-017 建议。
- 未实施 G0b 迁移、钩子、grandfather、spec-gates。
- 未改 `researchclaw/` 代码。
