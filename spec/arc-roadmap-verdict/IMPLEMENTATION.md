---
id: arc-roadmap-verdict-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-roadmap-verdict-DESIGN]
upstream: arc-roadmap-verdict-DESIGN
---

# 实施记录：总纲 v0.4 落地

> E-01..E-16 已按 [DESIGN §2](DESIGN.md) 全部执行；本文件记录验证与勘误。

## 1. 执行对账

| 落点 | 状态 | 证据 |
|---|---|---|
| E-01..E-02 | ✅ | 总纲头部 version: 0.4；§1 L94 最小集 |
| E-03（G1 +7） | ✅ | §4 G1 交付物 15 条（原 8 + 7） |
| E-04（G2 谓词化） | ✅ | A2-4/5/6 谓词断言；交付物 7 条 |
| E-05（G3 +4 / A3-1） | ✅ | 交付物 12 条；A3-1 含 Stage 22 |
| E-06/E-07 | ✅ | G5 +2；G7 归档措辞 |
| E-08..E-11（§5） | ✅ | C-9=H-1..H-5；声明 35 条；§5.1 矩阵 12 行 |
| E-12..E-14 | ✅ | §6/§7/§11 |
| E-15/E-16 | ✅ | scripts/roadmap_coverage_check.py；ci.yml `roadmap-coverage` job |

## 2. 验证

```bash
# V1 覆盖率门禁（D-6 核心；期望 accept=106 missing=0）
python scripts/roadmap_coverage_check.py --check

# V2 DC 契约（本批四文档 + PROGRESS/CONSOLE）
python scripts/dc_validator.py spec/arc-roadmap-verdict/RESEARCH.md spec/arc-roadmap-verdict/DESIGN.md \
  spec/arc-roadmap-verdict/IMPLEMENTATION.md spec/arc-roadmap-verdict/CHECKLIST.md \
  docs/PROGRESS.md docs/CONSOLE.md

# V3 决策流五步
python tools/spec_runner/spec_runner.py step-gate --session specwf-p005-arc-roadmap-verdict \
  --expect research design implement verify finalize

# V4 派生视图
python scripts/console_gen.py --check

# V5 计数不变（106）
python -c "import io,re;t=io.open('arc-master-roadmap.md',encoding='utf-8').read();s4=t.split('## 4.')[1].split('## 5.')[0];print(len(set(re.findall(r'\b(?:A0a|A0|A1|A2|A3|A4|A5|A6|A7|A8a|A8b|AN|FC|FA|GQ|OB|H)-\d+',s4))))"

# V6 C-9 归属（H-5 在 C-9、不在 C-7）
rg -n "C-9.*H-1\.\.H-5|C-7.*FC-1" arc-master-roadmap.md
```

## 3. 勘误登记（复核 F-1..F-8 的 disposition；不改 P-004 归档件）

| # | 处置 |
|---|---|
| F-1（D-3 计数 18→12） | ✅ 已落地：§5.1 标题即"共 12 条" |
| F-2（P0-1 歧义读法） | ✅ 已消歧：D-1A 使 H-5 ∈ C-9（生效 G-1），箭头注记全部移除 |
| F-3（A3-5 有意 N/A） | ✅ 已标注：声明段单列 |
| F-4（ISO 链接 /fr/） | 📋 勘误：正确英文页为 `iso.org/obp/ui/en/#!iso:std:72089:en`；引用时以本条为准 |
| F-5（Temporal "必须"） | 📋 勘误：官方口径 "strongly recommended"（at-least-once 下） |
| F-6（OTel semconv 迁移） | 📋 勘误：GenAI semconv 在独立仓 `open-telemetry/semantic-conventions-genai` 且未稳定；实现时须 pin repo+版本 |
| F-7（B-8 调用点） | 📋 已佐证：runner.py:513（阶段级）、executor.py:296（CostGuard）、client.py:320（仅记账）；Q20 承接 |
| F-8（4 条未枚举） | ✅ 已落地：§5.1 矩阵含平台列（A1-3 类 POSIX 约束在 G1 RESEARCH 定死） |

## 4. 未执行项

- Q18/Q19/Q20 的实际裁决（登记后按总纲规则以默认建议先行时须记 `provisional`）。
- H-1..H-8 的 pytest 文件（§5.1 为计划路径，G-1 开工时冻结）。
- `researchclaw/` 预算字段统一（Q20 裁决后另开代码批次）。
