---
id: arc-roadmap-review-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-06
depends: [arc-roadmap-review-DESIGN]
upstream: arc-roadmap-review-DESIGN
---

# 实施：可重放取证命令与产出清单

## 1. 取证命令

```bash
# H-1..H-8 代码事实（E1）
rg --no-ignore -n "returncode" researchclaw/pipeline/stage_impls/_execution.py
rg --no-ignore -n "max_retries" researchclaw
rg --no-ignore -n "ClaimVerifier|claim_verifier" researchclaw tests
rg --no-ignore -n "retrieval_degraded" .
rg --no-ignore -n "os.environ" researchclaw/experiment/sandbox.py researchclaw/mcp/client.py
rg --no-ignore -n "def _write_project" researchclaw/pipeline/stage_impls/_execution.py
rg --no-ignore -n "cors_origins" researchclaw/config.py

# G5 源数据（E2）
python -c "import json;print(len(json.load(open(r'D:\Paper\Paper_Organized_v2_report.json',encoding='utf-8'))))"
python -c "import json;d=json.load(open(r'D:\Textbook\output\pilot\knowledge_graph.json',encoding='utf-8'));print(len(d['nodes']),len(d['edges']))"

# 前端依赖闭合（E2）
python -c "import re,glob;..."   # 解析 id/depends/upstream，输出 UNRESOLVED

# 外部引用（E4）
# 逐条 WebFetch arxiv.org/abs/<id> 与官方规范页
```

## 2. 产出

| 文件 | 内容 |
|---|---|
| [docs/arc-roadmap-review-20261106.md](../../docs/arc-roadmap-review-20261106.md) | 完整审查报告（取证矩阵、P1/P2/P3、可行性、修复顺序） |
| `spec/arc-roadmap-review/` | 四文档（本批次） |
| `tools/spec_runner/sessions/specwf-p002-arc-roadmap-review-20261106.jsonl` | 五步决策流 |

## 3. 未执行项

- 未修改 `arc-master-roadmap.md` 及 14 份关联文档（审查只标记，不修复）。
- 未做异构基座复审（RULE-5）。
- 未逐篇读论文全文验证因果结论。
