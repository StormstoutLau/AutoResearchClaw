---
id: arc-roadmap-v06-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-roadmap-v06-DESIGN]
upstream: arc-roadmap-v06-DESIGN
---

# 实施记录：总纲 v0.6 状态同步

> 本批只改总纲与文档，不改代码、不改 106 计数。E-* 为实际落点，V-* 为验证。

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-01 | 版本 0.5→0.6、日期、v0.6 修订块 | `arc-master-roadmap.md:4-27` |
| E-02 | G-1 标记完成 + 状态注 | `arc-master-roadmap.md:164-166` |
| E-03 | G0b 标记未就绪 + 缺口注 | `arc-master-roadmap.md:189-191` |
| E-04 | Q17 改“已裁决” | `arc-master-roadmap.md:640` |
| E-05 | §11 新增 P-011..P-015 依据行 | `arc-master-roadmap.md:738-740` |
| E-06 | G3 候选增量注（P-014/P-015） | `arc-master-roadmap.md:326` |

## 2. 验证

```bash
python scripts/roadmap_coverage_check.py --check
python scripts/dc_validator.py spec/arc-roadmap-v06/RESEARCH.md \
  spec/arc-roadmap-v06/DESIGN.md spec/arc-roadmap-v06/IMPLEMENTATION.md \
  spec/arc-roadmap-v06/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python tools/spec_runner/spec_runner.py step-gate \
  --session specwf-p016-arc-roadmap-v06 --expect research design implement verify finalize
python scripts/console_gen.py --check
python scripts/private_config_check.py spec/arc-roadmap-v06 docs/PROGRESS.md docs/CONSOLE.md
python scripts/step_enforce.py --base HEAD \
  spec/arc-roadmap-v06/RESEARCH.md spec/arc-roadmap-v06/DESIGN.md \
  spec/arc-roadmap-v06/IMPLEMENTATION.md spec/arc-roadmap-v06/CHECKLIST.md \
  docs/PROGRESS.md tools/spec_runner/sessions/specwf-p016-arc-roadmap-v06.jsonl
```

## 3. 结果（2026-11-10）

- V1：`roadmap-coverage: accept=106 suite=70 declared=37 missing=0`。
- V2：`DC 契约校验通过：6 文件，2 结果，0 违规`。
- V3：`step-gate[specwf-p016-arc-roadmap-v06]: 决策链一致 pass → exit 0`。
- V4：`CONSOLE.md 与源一致`。
- V5：`private_config_check` exit 0。
- V6：`step-enforce: mode=batch pid=P-014,P-015,P-016 ... exit 0`。

## 4. 未执行 / 边界

- 未新增/删除验收 ID，106 计数不变。
- 未改变阶段顺序、C 套件成员或 G0b 验收标准。
- 未修改 `researchclaw/` 代码。
- G0b 的交付物补齐与 Q3 裁决仍待后续批次。
- R-3a/b/c 的实现仍待 P-015 触发条件满足后另开批次。
