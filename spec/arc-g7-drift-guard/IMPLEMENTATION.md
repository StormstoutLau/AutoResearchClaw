---
id: arc-g7-drift-guard-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-drift-guard-DESIGN, arc-g7-drift-guard-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 漂移护栏（P-167）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **环境**：Python ≥3.11（本机 3.13.5）；仅标准库；pytest 8.3.4；无新增三方依赖。

## 1. 文件清单与源码锚点

| 路径 | 类型 | 改动 |
|---|---|---|
| `researchclaw/guards/__init__.py` | 新增 | 导出 `assess_drift` / `DriftReport` / `DriftThresholds` |
| `researchclaw/guards/drift.py` | 新增 | 指标、阈值、判定、报告、scope 批准契约 |
| `researchclaw/pipeline/stage_impls/_analysis.py` | 修改 | `_apply_drift_guard` + Stage 15 接线 |
| `tests/test_drift_guard.py` | 新增 | 指标/FA-1..FA-3/边界/接线 |
| `docs/observations-registry.md` | 新增 | O 表集中登记（先行） |
| `spec/arc-g7-drift-guard/*.md` | 新增 | 四文档 |

**插入点（@4e9e853 + P-167 前）**：

| 位置 | 现状 | 改动 |
|---|---|---|
| [_analysis.py L1326](../../researchclaw/pipeline/stage_impls/_analysis.py#L1326) | `decision = _parse_decision(decision_md)` | 之后调用 `_apply_drift_guard` |
| [_analysis.py L1352-L1359](../../researchclaw/pipeline/stage_impls/_analysis.py#L1352-L1359) | 无法解析 → `StageStatus.PAUSED` 先例 | 复用同一状态返回 PAUSE |
| [_analysis.py L1373-L1381](../../researchclaw/pipeline/stage_impls/_analysis.py#L1373-L1381) | 写 `decision_structured.json` | payload 增加 `drift` 块 |
| [_analysis.py L1399-L1404](../../researchclaw/pipeline/stage_impls/_analysis.py#L1399-L1404) | DONE 返回 | WARN/PASS 走原路径；PAUSE 提前返回 |
| [_helpers.py L399-L423](../../researchclaw/pipeline/_helpers.py#L399-L423) | `_read_prior_artifact` | 读取 goal/hypotheses/analysis |
| [claim_verifier.py L68-L109](../../researchclaw/hitl/claim_verifier.py#L68-L109) | `verify_text` 返回报告 | 复用 |
| [claim_verifier.py L210-L299](../../researchclaw/hitl/claim_verifier.py#L210-L299) | grounded/ungrounded/unchecked | 计算分母 |
| [stages.py L65-L75](../../researchclaw/pipeline/stages.py#L65-L75) | `StageStatus.PAUSED` | 复用 |
| [runner.py L833-L870](../../researchclaw/pipeline/runner.py#L833-L870) | PAUSED 不推进 | 复用 |

## 2. 接口签名

```python
# researchclaw/guards/drift.py
SCHEMA_DRIFT = "arc-drift-report/1"
SCHEMA_SCOPE_APPROVAL = "arc-scope-change-approval/1"

@dataclass(frozen=True)
class DriftThresholds:
    rq_warn: float = 0.45
    rq_pause: float = 0.35
    unsupported_pause: float = 0.40
    p_only_warn: float = 0.50
    lexical_pause: float = 0.20
    @classmethod
    def from_env(cls) -> "DriftThresholds"
    def to_dict(self) -> dict[str, float]

@dataclass(frozen=True)
class DriftReport:
    schema: str
    run_id: str
    decision: str
    action: str
    rq_cos: float | None
    unsupported_ratio: float | None
    p_only_ratio: float | None
    backend: str
    thresholds: dict[str, float]
    reasons: tuple[str, ...]
    signals: dict[str, Any]
    generated: str
    def to_dict(self) -> dict[str, Any]

def tokenize(text: str) -> list[str]
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

# _analysis.py
def _apply_drift_guard(stage_dir: Path, run_dir: Path, decision: str,
                       decision_md: str, analysis: str) -> tuple[DriftReport, StageResult | None]
```

**回退点 R-1..R-4**：见 DESIGN §7。

## 3. 算法实现细节

### 3.1 词面 TF-IDF 余弦

```python
_STOP = frozenset("the a an and or of to in on for with by is are was were be been this that these those it its as at from into than then we our their there here can may might will would should could not no".split())
_TOKEN = re.compile(r"[a-z][a-z0-9\-]{2,}")

def tokenize(text: str) -> list[str]:
    words = [w for w in _TOKEN.findall(text.lower()) if w not in _STOP]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]

def lexical_cosine(a: str, b: str) -> float:
    docs = [tokenize(a), tokenize(b)]
    if not docs[0] or not docs[1]:
        return 0.0
    df = Counter()
    for doc in docs:
        df.update(set(doc))
    vecs = []
    for doc in docs:
        tf = Counter(doc)
        vec = {t: (n / len(doc)) * (math.log(3 / (1 + df[t])) + 1) for t, n in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        vecs.append((vec, norm))
    (va, na), (vb, nb) = vecs
    if na == 0 or nb == 0:
        return 0.0
    dot = sum(v * vb.get(t, 0.0) for t, v in va.items())
    return round(max(0.0, min(1.0, dot / (na * nb))), 6)
```

### 3.2 结论段抽取

```
SECTIONS = ("conclusion", "discussion", "results", "findings", "结论", "讨论", "结果", "发现")
按 ^#{1,6}\s+ 切段；保留标题命中 SECTIONS 的段；无命中 → text[-max(400, int(len*0.4)):]
```

### 3.3 p_only 比例

```
candidates = [s for s in re.split(r"(?<=[.!?。！？])\s+", text) if P_RE.search(s)]
p_only = [s for s in candidates if not EFFECT_RE.search(s)]
ratio = len(p_only)/len(candidates) if candidates else 0.0
```

### 3.4 claim 支持率

```python
from researchclaw.hitl.claim_verifier import ClaimVerifier
report = ClaimVerifier(Path(run_dir)).verify_text(text)
checked = report.grounded_claims + report.ungrounded_claims
ratio = report.ungrounded_claims / checked if checked else None
return ratio, checked
```

- `ClaimVerifier` 构造会读 `stage-06*/cards` 与 `stage-05*/shortlist.jsonl`；失败/缺失时 knowledge base 为空，citation claim 会判 `grounded=False`（见 L220-L242）。

### 3.5 判定顺序（不可交换）

1. `scope_approved = read_scope_change_approval(stage_dir)`；`decision.upper()=="PIVOT" and approved` → `exempt`。
2. 文本长度 <40 → `warn`（`insufficient_inputs`），不再做 PAUSE。
3. 计算 `rq_cos` / `unsupported` / `p_only`。
4. PAUSE：
   - `backend=="injected"`：`rq_cos < rq_pause` 且 `unsupported is not None` 且 `unsupported > unsupported_pause`
   - `backend=="lexical_tfidf"`：`rq_cos < lexical_pause` 且同上
5. WARN：`rq_cos < rq_warn` 或 `p_only > p_only_warn`。
6. 否则 PASS。
7. 所有分支都写 `drift_report.json`；PAUSE 追加 `decision.md` 的 `## Drift Guard — RQ Re-anchoring Required` 段。

### 3.6 Stage 15 接线

```python
decision = _parse_decision(decision_md)
...
quality_warnings = ...
drift_report, drift_pause = _apply_drift_guard(
    stage_dir, run_dir, decision, decision_md, analysis
)
decision_payload = {
    "decision": decision,
    "raw_text_excerpt": decision_md[:500],
    "quality_warnings": quality_warnings,
    "drift": drift_report.to_dict(),
    "generated": _utcnow_iso(),
}
(stage_dir / "decision_structured.json").write_text(json.dumps(decision_payload, indent=2), encoding="utf-8")
if drift_pause is not None:
    return drift_pause
_ledger = _update_plan_ledger(run_dir, decision)
...
```

- PAUSE 返回：`StageStatus.PAUSED`、`error="E_DRIFT_DETECTED"`、`decision="refine"`、`artifacts=("decision.md","decision_structured.json","drift_report.json")`。
- `_apply_drift_guard` 负责写报告/追加段；`_execute_research_decision` 不再重复写。

## 4. 测试计划（红 → 绿）

| 测试 | 红断言（实现前） | 绿断言（实现后） |
|---|---|---|
| T01 `test_tokenize_and_lexical_cosine` | `researchclaw.guards.drift` 不存在 | 相关文本 cos 高、无关文本 cos 低、空文本 0 |
| T02 `test_extract_conclusion_and_p_only` | 函数不存在 | 标题段抽取正确；p_only 比例符合构造 |
| T03 `test_fa1_unrelated_analysis_pauses` | `_apply_drift_guard` 不存在 | action=pause；StageResult.status=PAUSED；drift_report.json 存在；decision.md 含重锚段 |
| T04 `test_fa2_related_analysis_proceeds` | — | action=pass（或 warn 不含 pause）；stage 仍 DONE |
| T05 `test_fa3_approved_scope_change_exempts` | — | PIVOT + approved → action=exempt、无 pause |
| T06 `test_pivot_without_approval_is_judged` | — | 无 approval 的 PIVOT 仍按信号判 |
| T07 `test_insufficient_inputs_warn_only` | — | 短文本 → warn，绝不 pause |
| T08 `test_p_only_warn` | — | 高 p_only、高 cos → warn |
| T09 `test_thresholds_env_override` | — | `ARC_DRIFT_RQ_WARN` 等生效；报告记录阈值 |
| T10 `test_report_schema_and_decision_payload` | — | schema/字段齐全；decision_structured 含 drift |

## 5. 低效操作排除

| 低效操作 | 排除 |
|---|---|
| 每次判定重新读全部 stage 产物 | 只读 goal/hypotheses/analysis/decision 四个文件 |
| 引入 embedding 服务 | 默认词面；`embed_fn` 仅注入 |
| 重复 claim 抽取 | 每次 Stage 15 一次，文本仅 conclusion+decision |
| 大文本全量 TF-IDF | 结论段截断到末 40%，词项上限天然受文本长度约束 |
| 改 config schema | 环境变量覆盖，零 schema 变更 |

## 6. 版本与 API 核验（Step 6）

| API | 下限 | 核验 |
|---|---|---|
| `re` / `math` / `json` / `Counter` | 3.x | 标准库 |
| `dataclasses` / `Path` | 3.x | 既有用法 |
| `ClaimVerifier` | 本仓 | [claim_verifier.py L68](../../researchclaw/hitl/claim_verifier.py#L68) |
| `StageStatus.PAUSED` | 本仓 | [stages.py L65-L75](../../researchclaw/pipeline/stages.py#L65-L75) |
| pytest | ≥7.0 | 本机 8.3.4 |
| 三方依赖 | 无 | pyproject 不变 |

## 7. Review（Step 6，自查·单视角）

| 检查项 | 结论 |
|---|---|
| 版本真实存在 | 全部标准库/本仓 API |
| 签名可实现 | 纯函数 + 一个 stage helper |
| 无虚构 API | 未引用未安装包 |
| 兼容性 | 不改既有公开签名；PAUSE 复用状态机 |
| 低效操作已排除 | §5 |
| 与设计对齐 | D-1..D-8 均有落点；R-1..R-4 对应 |
