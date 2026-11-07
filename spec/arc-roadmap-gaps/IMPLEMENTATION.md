---
id: arc-roadmap-gaps-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-07
depends: [arc-roadmap-gaps-DESIGN]
upstream: arc-roadmap-gaps-DESIGN
---

# 实施记录：盲区调研落档与锚点核验

> 本批只写文档，不改代码、不改总纲正文。以下 E-* 为实际落点，V-* 为可重放验证。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | 把 2026-11-07 的完备度审计落档（8 维评分 / 6 结构缺口 / 8 执行盲区） | [RESEARCH.md](RESEARCH.md) §2 |
| E-2 | 建立“缺口 → 验收 ID → 可机判性 → 处置类型”映射 | RESEARCH.md §3 |
| E-3 | 核验并写入 12 项外部锚点（标准 6、论文 4、工程文档 2） | RESEARCH.md §4 |
| E-4 | 给出采用矩阵（采用 / 只借语义 / 拒绝）与理由 | RESEARCH.md §5 |
| E-5 | 把 7 项补全方案定义为 D-1..D-7，明确“未执行” | [DESIGN.md](DESIGN.md) §3 |
| E-6 | 用脚本复算 C 套件差集，得到 15 条未声明项 | RESEARCH.md §6 |
| E-7 | 检索测试映射，确认 106 条验收无 harness | RESEARCH.md §6 |
| E-8 | 静态核对预算字段与状态模型（两套预算、无 StageAttempt） | RESEARCH.md §2.3 B-4/B-8 |

## 2. 锚点核验记录

| 锚点 | 核验方式 | 结果 |
|---|---|---|
| X-1 OWASP API2:2023 | 官方域名命中 | ✅ 页面存在，含 Broken Authentication 定义 |
| X-2 SLSA v1.0 | 官方 `slsa.dev/spec/v1.0/levels` | ✅ Build L0–L3 + provenance |
| X-3 OTel GenAI | 官方 `opentelemetry.io` 属性注册表 | ✅ `gen_ai.*` 属性存在 |
| X-4 ACM Badging | 官方 `acm.org` v1.1 | ✅ 2020-08-24 版政策 |
| X-5 ISO 29148:2018 | ISO OBP 条目 | ✅ 含 requirements traceability 定义 |
| X-6 METR | arXiv 命中标题 | ✅ 2503.14499 |
| X-7 MLE-bench | arXiv 命中标题与摘要 | ✅ 2410.07095 |
| X-8 AgentChaos | arXiv 命中摘要 | ✅ 2608.06790 |
| X-9 Temporal | 官方文档 | ✅ Activity 幂等与 at-least-once |
| X-10 Croissant 1.1 | 官方规范页 | ✅ 1.1 规范存在 |
| X-11 FrugalGPT | arXiv 命中标题 | ✅ 2305.05176 |
| X-12 Actions limits | GitHub 官方 cheat sheet | ✅ `timeout-minutes` 默认 360 |

## 3. 验证

```bash
# V1 契约（仅 spec 作用域；裸跑 dc_validator 会带出全仓既有噪声）
python scripts/dc_validator.py spec/arc-roadmap-gaps/RESEARCH.md spec/arc-roadmap-gaps/DESIGN.md \
  spec/arc-roadmap-gaps/IMPLEMENTATION.md spec/arc-roadmap-gaps/CHECKLIST.md \
  docs/PROGRESS.md docs/CONSOLE.md

# V2 决策流五步
python tools/spec_runner/spec_runner.py step-gate specwf-p004-arc-roadmap-gaps \
  --expect research design implement verify finalize

# V3 派生视图
python scripts/console_gen.py --check

# V4 总纲未被本批改动
git diff --stat HEAD -- arc-master-roadmap.md

# V5 差集复算（期望输出 15 条）
python -c "import io,re;t=io.open('arc-master-roadmap.md',encoding='utf-8').read();s4=t.split('## 4.')[1].split('## 5.')[0];s5=t.split('## 5.')[1].split('## 6.')[0];p=r'\b((?:A0a|A0|A1|A2|A3|A4|A5|A6|A7|A8a|A8b|AN|FC|FA|GQ|OB|H))-(\d+)(?:\s*\.\.\s*(?:[A-Za-z0-9]+-)?(\d+))?'
def ex(s):
 o=set()
 for m in re.finditer(p,s):
  a=int(m.group(2));b=m.group(3);o.update('%s-%d'%(m.group(1),i) for i in range(a,int(b)+1)) if b else o.add('%s-%d'%(m.group(1),a))
 return o
print(sorted(ex(s4)-ex(s5)))"

## 4. 未执行项

- **D-1..D-7 全部未执行**：涉及 G-1/G2 出口判据与总纲正文，需用户裁决后另开批次。
- 未修改 `arc-master-roadmap.md`：本批只提供依据，不落在路线上。
- 未修改任何代码与配置（B-3 的默认 `auth_token` 仍为空）。
- 未实测 72h soak、kill -9、多 run 并发（B-1/B-2 仍为设计期风险）。
- 未访问 Paper/Textbook 语料仓，A5-2/A5-3 的来源盘点留待 G5 的 RESEARCH。
