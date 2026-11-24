---
id: arc-g7-drift-guard-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-drift-guard-RESEARCH, failure-guards-design, arc-g7-review-fixes-DESIGN]
upstream: arc-master-roadmap
---

# 设计：G7 漂移护栏（P-167）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **范围**：护栏 A（相关性漂移）在 Stage 15 决策点的实现 + FA-1..FA-3；不含护栏 B/C、A7 其他段、FA 之外的漂移曲线。
> **前置**：观察项已先登记至 [docs/observations-registry.md](../../docs/observations-registry.md)（Layer-0，不承接）。

## 1. 决策

| 编号 | 决策 | 被拒绝的替代方案 | 拒绝理由 / 代价 |
|---|---|---|---|
| D-1 | 新建纯模块 `researchclaw/guards/drift.py`；Stage 15 只调用 `assess_drift` / `write_drift_report`，判定逻辑不写进 `_analysis.py` | 全部内联在 `_analysis.py` | 内联不可单测、与 1300+ 行 stage 实现耦合；纯模块可用合成 fixture 精确覆盖 FA-1..FA-3。代价：多一个包 |
| D-2 | 默认后端 = 确定性词面 TF-IDF 余弦（unigram+bigram，去停用词）；`embed_fn` 可注入语义后端。词面后端只在 `rq_cos < 0.20` 且 `unsupported > 0.40` 时 PAUSE，中等低相似只 WARN | ① 默认调外部 embedding API；② 词面后端永远只 WARN | ① 离线不可复现、引入网络依赖；② FA-1 无法在默认运行中触发。代价：词面后端语义分辨力有限，极端门槛只抓"明显跑题" |
| D-3 | claim 信号复用 `ClaimVerifier`：`unsupported_ratio = ungrounded/(grounded+ungrounded)`，排除 `unchecked`；分母 0 时该信号为 `None`，不参与 PAUSE | 自写 claim 抽取 / 把 unchecked 计入分母 | 自写会与 H-3 现有实现漂移；计入 unchecked 会把"无法验证"误判为"不支持"。代价：依赖 stage-06 cards/短名单的存在 |
| D-4 | `p_only_ratio` = 含 p 值/显著性词但无效应量的句子 / 含显著性词的句子；只作 WARN | 用 LLM 判"是否只报 p 值" | LLM 判据不稳定且需网络；正则可复现、可单测。代价：对非英文/复杂句式覆盖有限 |
| D-5 | 动作四值：`pass` / `warn` / `pause` / `exempt`。首次 `pause` 即返回 `StageStatus.PAUSED`（不自动 REFINE、不重采样） | 设计草案的"首次强制 REFINE，第二次 PAUSED" | E2/E9 表明重采样不改变目标函数且会掩盖漂移；PAUSE 让人复核更安全。代价：比草案更严格，可能增加人工介入 |
| D-6 | 合法 PIVOT 豁免契约 = `stage-15/scope_change_approval.json`（`approved=true`）；无文件/未批准不豁免 | 从 `decision.md` 文本里找 "approved" | 文本匹配可伪造、不可审计；机器可读文件才有明确 producer/consumer。代价：HITL UI 接线留给后续（U-2） |
| D-7 | 在 `_execute_research_decision` 的 `_parse_decision` 之后、写 `decision_structured.json` 之前调用护栏；报告写 `stage-15/drift_report.json`，`decision_structured.json` 增加 `drift` 块；PAUSE 时向 `decision.md` 追加"RQ 重锚定"段 | 在 executor/runner 层做后置检查 | runner 层拿不到 decision 文本与 analysis 结论段；Stage 15 已有 PAUSED 先例，改动面最小。代价：护栏只在 Stage 15 生效 |
| D-8 | 阈值放 `DriftThresholds`（默认 0.45/0.35/0.40/0.50/0.20），支持 `ARC_DRIFT_*` 环境变量覆盖；不改 `RCConfig` schema | 新增 config.yaml 字段 | config schema 变更会扩散到 wizard/校验/文档；环境变量足够本批。代价：配置不如 YAML 显式 |

## 2. 指标定义（算法）

### 2.1 文本与相似度

```
tokenize(text):
  lower → regex [a-z][a-z0-9-]{2,} → 去停用词
  tokens + 相邻 bigram（"a_b"）→ 词项序列

tfidf_cosine(a, b):
  docs = [tokens(a), tokens(b)]
  df(t) = 出现在几个 doc
  idf(t) = ln((1 + 2) / (1 + df(t))) + 1
  tf(t, d) = count(t, d) / len(d)
  v_d(t) = tf * idf
  return dot(v_a, v_b) / (||v_a|| * ||v_b||)   # 0 if norm 0
```

- `goal_text = stage-01/goal.md + "\n" + stage-08/hypotheses.md`
- `outcome_text = extract_conclusion(stage-14/analysis.md) + "\n" + decision.md`
- `extract_conclusion`：按 Markdown 标题切段，优先标题含 `conclusion|discussion|results|findings|结论|讨论|结果|发现` 的段；无匹配取全文末 40%（至少 400 字符）。
- `rq_cos = tfidf_cosine(goal_text, outcome_text)`；若注入 `embed_fn`，则 `cos(embed_fn(goal), embed_fn(outcome))`，`backend="injected"`。

### 2.2 claim 支持率

```
report = ClaimVerifier(run_dir).verify_text(outcome_text)
checked = report.grounded_claims + report.ungrounded_claims
unsupported_ratio = report.ungrounded_claims / checked if checked > 0 else None
```

### 2.3 只看 p 值比例

```
sentences = split(outcome_text)
candidates = [s for s in sentences if re.search(p-value|significant|显著性, s)]
p_only = [s for s in candidates if not re.search(effect size|cohen|odds ratio|hazard ratio|CI|%|β|r², s)]
p_only_ratio = len(p_only) / len(candidates) if candidates else 0.0
```

### 2.4 判定

```
if decision == "PIVOT" and scope_approval.approved:
    action = "exempt"
elif goal_len < 40 or outcome_len < 40:
    action = "warn"; reasons += ["insufficient_inputs"]
else:
    if backend == "injected":
        pause = rq_cos < 0.35 and unsupported_ratio is not None and unsupported_ratio > 0.40
    else:
        pause = rq_cos < 0.20 and unsupported_ratio is not None and unsupported_ratio > 0.40
    if pause:
        action = "pause"
    elif rq_cos < 0.45 or (p_only_ratio or 0) > 0.50:
        action = "warn"
    else:
        action = "pass"
```

## 3. 数据结构

```python
@dataclass(frozen=True)
class DriftThresholds:
    rq_warn: float = 0.45
    rq_pause: float = 0.35
    unsupported_pause: float = 0.40
    p_only_warn: float = 0.50
    lexical_pause: float = 0.20
    @classmethod
    def from_env(cls) -> "DriftThresholds": ...

@dataclass(frozen=True)
class DriftReport:
    schema: str = "arc-drift-report/1"
    run_id: str = ""
    decision: str = ""
    action: str = "pass"          # pass|warn|pause|exempt
    rq_cos: float | None = None
    unsupported_ratio: float | None = None
    p_only_ratio: float | None = None
    backend: str = "lexical_tfidf"
    thresholds: dict = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    signals: dict = field(default_factory=dict)  # goal_chars/outcome_chars/claims_checked/scope_approved
    generated: str = ""
    def to_dict(self) -> dict: ...
```

报告落盘：`stage-15/drift_report.json`；`decision_structured.json` 增加 `drift` 块（同一 `to_dict`）。

## 4. API

```python
# researchclaw/guards/drift.py
def lexical_cosine(a: str, b: str) -> float
def extract_conclusion(text: str) -> str
def p_only_ratio(text: str) -> float
def claim_support(run_dir: Path, text: str) -> tuple[float | None, int]
def read_scope_change_approval(stage_dir: Path) -> dict | None
def write_scope_change_approval(stage_dir: Path, *, approved: bool, reason: str,
                                 approved_by: str = "hitl") -> Path
def assess_drift(run_dir: Path, stage_dir: Path, decision: str, decision_md: str,
                 analysis: str, *, embed_fn: Callable[[str], list[float]] | None = None,
                 thresholds: DriftThresholds | None = None) -> DriftReport
def write_drift_report(stage_dir: Path, report: DriftReport) -> Path
def format_reanchor_section(report: DriftReport) -> str

# researchclaw/pipeline/stage_impls/_analysis.py
def _apply_drift_guard(stage_dir: Path, run_dir: Path, decision: str,
                       decision_md: str, analysis: str) -> tuple[DriftReport, StageResult | None]
```

`_apply_drift_guard` 返回 `(report, pause_result|None)`；PAUSE 时 `pause_result.status=StageStatus.PAUSED`、`error="E_DRIFT_DETECTED"`、`decision="refine"`、`artifacts=("decision.md","decision_structured.json","drift_report.json")`。

## 5. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | 护栏只写 `stage-15/drift_report.json`、追加 `decision.md` 的重锚段、更新 `decision_structured.json`；不碰其他 stage 产物 |
| J-2 | `unsupported_ratio is None` 时绝不 PAUSE；`claims_checked==0` 视为信号缺失 |
| J-3 | `PIVOT` + `scope_change_approval.json.approved=true` → `exempt`，不 WARN/PAUSE |
| J-4 | 报告中必须记录 `backend` 与完整 `thresholds`；不得只写动作 |
| J-5 | 词面后端在 `rq_cos >= 0.20` 时绝不 PAUSE；注入后端在 `rq_cos >= 0.35` 时绝不 PAUSE |
| J-6 | 不改 gate/CLI/schema/StageStatus；PAUSE 复用既有 `StageStatus.PAUSED` |
| J-7 | 同一输入 + 同一阈值 → 同一 `action`/`rq_cos`/`unsupported_ratio`/`p_only_ratio`（`generated` 时间戳除外） |
| J-8 | PAUSE 不推进 checkpoint；runner 既有 PAUSED 分支负责停机 |

## 6. 验收映射

| ID | 断言 | 落点 |
|---|---|---|
| FA-1 | 无关主题的 analysis → `PAUSED` | T03 + `_apply_drift_guard` 返回 PAUSED |
| FA-2 | `rq_cos` 高、`unsupported` 低 → 正常 DONE | T04（action pass）；DONE 路径不改 |
| FA-3 | 已批准 `scope_change` 的 PIVOT → 不触发 | T05（action exempt） |
| — | 中等低相似 → WARN；p_only 高 → WARN | T06/T07 |
| — | 无足够输入 → WARN 不 PAUSE | T08 |

## 7. 回退点

| 编号 | 回退动作 | 影响 |
|---|---|---|
| R-1 | 删除 `_apply_drift_guard` 调用与 `researchclaw/guards/` | Stage 15 回到无护栏；其余不变 |
| R-2 | 只保留 WARN，删除 PAUSE 分支 | FA-1 失效，FA-2/3 仍可 |
| R-3 | 删除 scope approval 读取 | FA-3 失效（PIVOT 会被当普通决策） |
| R-4 | 词面后端换成 injected 默认 | 需外部 embedding；离线不可复现 |

## 8. 非目标 / 边界

- **职责外**：护栏 B（伪造执行）、C（循环不收敛）、A7-2/3/5/6/7、真实 LLM 语义 judge。
- **能力边界**：词面后端不能判断"语义相关但用词不同"；它只抓明显跑题。真正语义后端需 `embed_fn` 注入（本批不接线）。
- **流程边界**：`scope_change_approval.json` 的 producer（HITL UI/CLI）不在本批；本批只定义契约 + helper，FA-3 测试直接写文件。
- **校准边界**：阈值是经验初值，未做 ≥30 条人工校准（U-5）。

## 9. Review（Step 4，自查·单视角）

| 检查项 | 结论 |
|---|---|
| 基于已验证调研 | D-2 ← E1/E2/E9；D-3 ← E3/E5/E11；D-5 ← E2/E9；D-6 ← E9/E10 |
| 无未经验证假设 | 阈值明确为初值；scope producer 未接线已登记 U-2 |
| 无归因扭曲 | 未把 Kosmos 的 79.4% 当作本仓精度；仅借用"引用可追溯" |
| 替代方案 ≥2 | D-1/D-2/D-3/D-5/D-6/D-8 均列否决方案与代价 |
| 职责边界 | §8 区分职责外/能力边界/流程边界/校准边界 |
