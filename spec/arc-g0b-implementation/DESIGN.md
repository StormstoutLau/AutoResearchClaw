---
id: arc-g0b-implementation-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g0b-implementation-RESEARCH]
upstream: arc-g0b-implementation-RESEARCH
---

# 设计：G0b 完整治理基座

> 输入：[RESEARCH.md](RESEARCH.md)。本文件把 S-1 + T-1 + H-1 + 独立策略层落成可实施规格。

## 1. 总体结构

```
根
├── SPEC_PROCESS.md            # 薄指针（≤5 行，指向 spec/SPEC_PROCESS.md）
├── scripts/
│   ├── dc_validator.py        # 兼容壳（runpy 转发）
│   ├── step_enforce.py        # 兼容壳
│   ├── console_gen.py         # 兼容壳
│   ├── rework_graph_check.py  # 兼容壳
│   ├── roadmap_coverage_check.py  # 兼容壳
│   ├── spec_map.py            # 兼容壳
│   └── spec/                  # 真身
│       ├── dc_validator.py
│       ├── step_enforce.py
│       ├── console_gen.py
│       ├── rework_graph_check.py
│       ├── roadmap_coverage_check.py
│       ├── spec_map.py
│       ├── grandfather_gate.py   # 策略层（新增）
│       ├── m7_stats.py           # 新增
│       ├── repo_stats.py         # 新增
│       └── blackbox_check.py     # 新增
└── spec/
    ├── SPEC_PROCESS.md        # 规范正文（由根迁移）
    └── grandfather.yaml       # 空清单 + cutoff + 过期策略
```

**单一真值源**：每个治理脚本只有 `scripts/spec/` 一份真身；根文件只做 `runpy` 转发，不含逻辑（T-1）。壳与真身不会漂移，因为壳里没有可漂移的内容。

## 2. 兼容壳规格

```python
# scripts/<name>.py —— 仅转发
import os, runpy, sys
_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec", "<name>.py")
sys.path.insert(0, os.path.dirname(_TARGET))   # 同目录 import（spec_map）可解析
sys.argv[0] = _TARGET
runpy.run_path(_TARGET, run_name="__main__")
```

- `sys.argv[0]` 重写后，真身内的 `argparse(prog=...)` 与错误信息仍指向真身路径，不误导。
- 不打印弃用提示：pre-commit 输出需稳定，且 88 处历史文档引用会频繁命中。

## 3. ROOT 上移

迁到 `scripts/spec/` 后，仓库根由「上两级」变「上三级」：

| 脚本 | 原 | 现 |
|---|---|---|
| `dc_validator` | `dirname(dirname(abspath(__file__)))` | 再套一层 `dirname` |
| `roadmap_coverage_check` | 同上 | 同上 |
| `step_enforce` | `Path(__file__).resolve().parents[1]` | `parents[2]` |
| `console_gen` | 同上 | 同上 |
| `rework_graph_check` | `Path(__file__).resolve().parent.parent` | `parents[2]` |
| `spec_map` | 无 ROOT（纯函数） | 不变 |

`sys.path.insert(0, str(Path(__file__).resolve().parent))` 保持不变——同目录 import 仍然成立。

## 4. grandfather 策略层（F-1 方案 b）

### 4.1 调用关系

```
pre-commit hook: dc-validator
  entry: python scripts/spec/grandfather_gate.py
        └─ import dc_validator（同目录）
        ├─ files = argv 或 gather_md_files()
        ├─ results = dc_validator.run_checks(files, ALL_CHECKS)
        ├─ policy = load_policy("spec/grandfather.yaml")
        ├─ results' = filter(results, policy)
        └─ exit 0/1/2
```

`dc_validator.py` **零改动**（I-1..I-6 保持）。直接调 `python scripts/dc_validator.py` 仍是严格模式（无豁免），可用于自测与独立核验。

### 4.2 `spec/grandfather.yaml` schema

```yaml
version: 1
cutoff: 2026-11-10
expires_days: 90          # 内部政策参数（E3），见 U-1
entries: []
```

条目（当前为空，仅约定形态）：

```yaml
entries:
  - path: spec/<feature>/RESEARCH.md   # 必填，仓库相对路径，须存在且在全仓 .md 集内
    check_ids: [dc1, dc2, dc3]         # 必填，非空；只接受 dc1/dc2/dc3
    reason: pre-DC2 legacy import       # 必填，非空
    owner: <name>                       # 必填，非空
    expires: 2027-02-08                 # 必填，ISO 日期
    renewals: []                        # 可选，追加式续期记录
    approved_by: <name>                 # 可选
    issue: <link or P-id>               # 可选
```

字段规则：

| 规则 | 违反处理 |
|---|---|
| `version` 必须为 `1` | exit 2 |
| `cutoff` / `expires` 必须为 ISO 日期 | exit 2 |
| `path` 必须存在、不得重复、不得落在 DC 作用域外 | exit 2 |
| `check_ids` ⊆ `{dc1,dc2,dc3}` 且非空 | exit 2（dc4/dc5/r7 拒绝登记） |
| `reason` / `owner` 非空 | exit 2 |
| `expires ≤ cutoff + 2*expires_days` | exit 2 |
| `renewals` 每项含 `{from, to, reason}`；`len(renewals) ≤ 1`；`to = from + expires_days`；且 `to ≤ cutoff + 2*expires_days` | exit 2 |
| 未知字段 | exit 2（fail-closed） |

### 4.3 过滤算法

```
for r in results:
    if r.severity == "":            keep
    if r.check_id not in {dc1,dc2,dc3}:  keep      # dc4/dc5/r7 全仓语义，不豁免
    e = entry_by_path.get(r.file)
    if e is None:                   keep
    if e.check_id 不含 r.check_id:  keep
    if today > e.expires:           keep 并计入 expired
    else:                           丢弃 并计入 grandfathered
```

输出：`[grandfathered] <path> (check_ids=..., expires=...)`；汇总 `grandfathered=N expired=M`。

### 4.4 语义触碰

策略层**不判定** touch：它只认文件级豁免。touch = migrate 由流程约束承载（P-019 §4 矩阵 + PROGRESS 行 + Review）。豁免在**语义触碰后**若仍存在，Review 必须要求迁移或续期——这是本设计的诚实边界，写入 §8。

## 5. 三道新门禁

### 5.1 `m7_stats.py`

- 解析 `docs/M7_EVIDENCE_LOG.md`：`## 1. 样本` / `## 2. 统计` 两节。
- 若两节均只含「（暂无）」→ `samples=0`，exit 0。
- 若 §1 为 markdown 表：表头必须含 `样本` 列；行数 = 样本数；§2 若声明 `合计` 必须等于样本数，否则 exit 1。
- 文件缺失 → exit 2。

### 5.2 `repo_stats.py`

- 统计：`researchclaw/**.py` 文件数与总行数、`tests/**.py` 文件数与总行数、`docs/PROGRESS.md` 的 P 行数。
- 默认打印；`--check` 与 `docs/REPO_STATS.md` 的三行声明比对，漂移 exit 1；文件缺失 exit 2。
- 真值源 = 文件系统；`docs/REPO_STATS.md` 是派生视图（与 CONSOLE 同构）。

### 5.3 `blackbox_check.py`

- 强制：`[sys.executable, "-m", "researchclaw", "--help"]`，`timeout=30`，`returncode != 0` → exit 1。
- 条件：`shutil.which("researchclaw")` 命中才跑 `researchclaw --help`；未命中打印 `[skip] console script not installed`。
- 输出：`blackbox: module=ok console=ok|skip elapsed=..s`。

## 6. 钩子组成（H-1）

| # | id | entry | 类别 |
|---|---|---|---|
| 1 | `dc-validator` | `python scripts/spec/grandfather_gate.py` | **必需** |
| 2 | `m7-stats` | `python scripts/spec/m7_stats.py` | **必需** |
| 3 | `repo-stats` | `python scripts/spec/repo_stats.py --check` | **必需** |
| 4 | `step-enforce` | `python scripts/spec/step_enforce.py` | **必需** |
| 5 | `console-gen` | `python scripts/spec/console_gen.py --stage` | **必需** |
| 6 | `blackbox-check` | `python scripts/spec/blackbox_check.py` | **必需** |
| 7 | `private-config` | `python scripts/private_config_check.py` | 额外守卫 |
| 8 | `code-agent-wiring` | `python scripts/code_agent_wiring_check.py` | 额外守卫 |
| 9 | `rework-graph` | `python scripts/spec/rework_graph_check.py` | 额外守卫 |

## 7. SPEC_PROCESS 迁移（S-1）

- 正文 → `spec/SPEC_PROCESS.md`，保留原 front-matter，`version` 保持 `1.7.1`（内容未变，只换位置）；在 front-matter 下加一行 `> **位置迁移**：2026-11-10（P-021）自仓库根迁入 `spec/`，内容与版本不变`。
- 根 `SPEC_PROCESS.md` → 指针（标题 + 一行说明 + 链接），不含规则。
- 链接重写三类：
  1. `docs/...` → `../docs/...`（目标存在）；
  2. `spec/templates/...` → `templates/...`（同目录）；
  3. **跨仓/不存在目标**（`adr/`、`spec/academic-writing-workflow/`、`spec/stage-tooling-contract/`、`spec/project-console/`、`docs/discoveries/`）→ 链接文本加 `源项目·` 前缀，由 DC3 档 2 语义排除解析。

## 8. 诚实边界

- 策略层**不判断**语义触碰；touch=migrate 仍是流程约束，不可机械拦截。
- `m7_stats` 在零样本期只证明「结构有效」，不能证明审计质量。
- `repo_stats` 是派生视图，不是代码质量指标。
- `blackbox` 在控制台脚本未安装时尚跳过，覆盖由 CI packaging job 兜底（U-3）。
- 迁移不改任何历史 IMPLEMENTATION/会话正文（追加式证据）。

## 9. 验收映射

| 验收 | 落点 |
|---|---|
| A0-1 | §6 八道钩子 + 额外守卫，`pre-commit run --all-files` 全绿 |
| A0-2 | `grandfather_gate` 空清单下透传 dc1 → 缺字段必红（负向用例 T-1） |
| A0-3 | `step_enforce` 未改逻辑，负向用例 T-2 固化 |
| A0-4 | digest 校验未改逻辑，负向用例 T-3 固化 |
| A0-5 | `console_gen --check`，负向用例 T-4 固化 |
| A0-6 | CI `spec-gates` job |
| Q3-F2 | §4.3 过滤只含 dc1/dc2/dc3 |
| Q3-F3 | §4.2 注释 E3 + U-1 |
| Q3-F4 | 负向用例 T-5（作用域外不消耗条目） |
| Q3-F5 | §4.2 `renewals` 规则 |

## 10. 回滚

| 变更 | 回滚 |
|---|---|
| 钩子 entry 改路径 | 单行改回 `python scripts/<name>.py` |
| grandfather 策略层 | hook entry 改回 `python scripts/spec/dc_validator.py`；`spec/grandfather.yaml` 可保留（无消费者） |
| 脚本迁移 | `git mv` 反向 + 删壳；ROOT 改回 |
| SPEC_PROCESS 迁移 | `git mv spec/SPEC_PROCESS.md SPEC_PROCESS.md` + 删指针 |
