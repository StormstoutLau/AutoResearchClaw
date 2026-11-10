---
id: arc-g0b-governance-base-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g0b-governance-base-RESEARCH]
upstream: arc-g0b-governance-base-RESEARCH
---

# 设计：G0b 完整治理基座

> 输入：[RESEARCH.md](RESEARCH.md) §4-§10。目标：给出可实施、可回滚、可验收的 G0b 方案；本批只设计，不写代码。

## 1. 设计不变量

1. **历史证据不改**：历史 IMPLEMENTATION/会话正文不改，用根壳/根指针保持引用可用。
2. **单一真值源**：迁移后的 `scripts/spec/*` 是唯一实现；根壳只转发，不含逻辑。
3. **A0-1 是必需集**：dc/m7/repo/step/console/blackbox 六道必须存在；private-config/code-agent-wiring 作为额外守卫保留。
4. **Q3 新文档立即**：存量 grandfather 空清单，只留机制与过期策略。
5. **零新依赖**：m7/repo/blackbox 仅 stdlib + 现有 CLI；不引入新包。
6. **本批不写代码**：实施另开批次，避免研究/实施混在同一决策流。

## 2. 决策表

| # | 决策 | 选择 | 被拒绝的替代 | 理由 |
|---|---|---|---|---|
| D-1 | SPEC_PROCESS 路径 | 迁 `spec/SPEC_PROCESS.md` + 根指针 | 双份 / 全量改引用 | 满足交付物且不破坏历史 |
| D-2 | 相对链接 | 机械重写 28 处（adr/docs/spec） | 手工逐条 | 可复现、可校验 |
| D-3 | 治理脚本路径 | 迁 `scripts/spec/` + 根兼容壳 | 仅门面 / 全量改引用 | 单一真值源 + 历史引用可用 |
| D-4 | ROOT 计算 | 统一 `parents[2]` / 三级 dirname | 依赖 cwd | 与 cwd 无关，保持 I-2 |
| D-5 | `spec_map` | 随脚本迁入 `scripts/spec/` | 留根 + sys.path 补丁 | 同目录 import 最稳 |
| D-6 | 钩子组成 | 6 必需 + 2 额外 | 只留 6 / 合并 | 不丢安全与接线守卫 |
| D-7 | grandfather | 空清单 + cutoff + 过期 | 预造豁免 | 当前无存量违规 |
| D-8 | m7_stats | 结构校验 + 零样本可见 | 永久 no-op | 门禁应能判红 |
| D-9 | repo_stats | `code_wiki/` + PROGRESS 统计 | 根 CODE_WIKI | 根文件不存在 |
| D-10 | blackbox | CLI `--help` 双入口烟雾 | 全量 pytest | 快、稳定、与单测分层 |
| D-11 | spec-gates | 独立 job + `pre-commit run --all-files` | 并入 tests | 并行、职责单一 |

## 3. 目录与迁移

```text
spec/
  SPEC_PROCESS.md          # 新正文（相对链接已重写）
  grandfather.yaml         # 空清单 + cutoff
scripts/
  spec/
    dc_validator.py
    step_enforce.py
    console_gen.py
    rework_graph_check.py
    roadmap_coverage_check.py
    spec_map.py
    m7_stats.py
    repo_stats.py
    blackbox_check.py
  dc_validator.py          # 根壳：弃用提示 + runpy 转发
  ...
SPEC_PROCESS.md            # 根指针：Moved to spec/SPEC_PROCESS.md
```

**根壳模板**（只转发，不含逻辑）：

```python
#!/usr/bin/env python3
"""Deprecated shim: use scripts/spec/dc_validator.py."""
import runpy, sys
print("deprecated: use scripts/spec/dc_validator.py", file=sys.stderr)
runpy.run_path("scripts/spec/dc_validator.py", run_name="__main__")
```

## 4. SPEC_PROCESS 链接重写

| 原前缀 | 新前缀 | 数量 |
|---|---|---|
| `](adr/` | `](../adr/` | 9 |
| `](docs/` | `](../docs/` | 6 |
| `](spec/` | `](./` | 13 |

迁移后必须：
1. `python scripts/spec/dc_validator.py spec/SPEC_PROCESS.md` 通过；
2. 根指针中的相对链接仍指向 `spec/SPEC_PROCESS.md`；
3. 不改历史文档中的根路径引用。

## 5. 钩子配置

```yaml
- id: m7-stats
  entry: python scripts/spec/m7_stats.py
  language: system
  pass_filenames: false
  files: ^docs/M7_EVIDENCE_LOG\.md$

- id: repo-stats
  entry: python scripts/spec/repo_stats.py
  language: system
  pass_filenames: false
  files: ^(code_wiki/.*\.md|docs/PROGRESS\.md)$

- id: blackbox
  entry: python scripts/spec/blackbox_check.py
  language: system
  pass_filenames: false
  always_run: true
```

保留 `private-config` 与 `code-agent-wiring`；`dc/step/console/rework` entry 改为 `scripts/spec/`。

## 6. 统计与黑盒语义

### 6.1 `m7_stats.py`

- 解析 `docs/M7_EVIDENCE_LOG.md` 的 `## 1. 样本` 表与 `## 2. 统计` 表。
- 无样本：输出 `m7_stats: samples=0 (ledger empty)`，exit 0。
- 表头缺失/列数不一致/统计声明与行数不符：exit 1。
- `--check` 为门禁模式；无参数默认打印。

### 6.2 `repo_stats.py`

- 输入 `code_wiki/*.md` 与 `docs/PROGRESS.md`。
- 统计：代码文件/行（`researchclaw/**/*.py`）、测试文件/行（`tests/**/*.py`）、P 批次数。
- 输出 `repo_stats: code_files=... code_lines=... test_files=... test_lines=... batches=...`。
- 源目录缺失/解析失败：exit 1。
- 不写盘；需要快照时由 `--write docs/REPO_STATS.md` 显式触发（可选）。

### 6.3 `blackbox_check.py`

- 运行 `python -m researchclaw --help` 与 `researchclaw --help`，超时 30s。
- 两者任一非 0/超时/输出不含 `usage: researchclaw`：exit 1。
- 不运行 `run`/`doctor`，避免配置与网络依赖。

## 7. grandfather.yaml

```yaml
version: 1
cutoff: 2026-11-10
expires_days: 90
entries: []
# - path: spec/<feature>/RESEARCH.md
#   reason: pre-DC2
#   owner: <name>
#   expires: 2027-02-08
```

`dc_validator` 读取规则：
1. `entries=[]` → 零豁免，所有 spec 文档照常校验。
2. 命中 `path` 且在 `expires` 前 → 跳过该文件的 DC 错误，但输出 `grandfathered`。
3. 过期 → 不跳过，按正常违规报红。
4. 未知字段/重复 path → exit 2（fail-closed）。

## 8. CI `spec-gates`

```yaml
spec-gates:
  name: Spec governance gates
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: python -m pip install pre-commit
    - run: pre-commit run --all-files
```

- 与 `tests` 并行，不 `needs: tests`。
- 不使用 matrix；治理门禁只需一个 Python 版本。
- 若时长 >2 min，退回逐脚本步骤并保留 `pre-commit run --files` 分片。

## 9. A0 映射与负向用例

| ID | 实施落点 | 负向用例 |
|---|---|---|
| A0-1 | 8 钩子（6 必需 + 2 额外） | 删除 m7/repo/blackbox 任一 → 失败 |
| A0-2 | dc_validator SEVEN_FIELDS | 临时文档删 `status:` → 必须失败 |
| A0-3 | step_enforce 五步链 | 删 `verify` 事件 → finalize 必须失败 |
| A0-4 | step_enforce digest | verify 后改 1 字符 → 必须失败 |
| A0-5 | console_gen --check | 手改 CONSOLE 一行 → 必须失败 |
| A0-6 | spec-gates job | 删除 job → 分支保护/CI 检查失败 |

## 10. 影响与回滚

- 迁移提交可整体 `git revert`；根壳/根指针删除即回到旧路径。
- 钩子新增可逐条移除；不影响现有六钩子。
- `grandfather.yaml` 空清单零行为；删除即停用豁免。
- CI job 独立；删除不影响 tests/packaging。
- 不触碰 `researchclaw/` 运行时代码。

## 11. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §11 的 U-1..U-6。
