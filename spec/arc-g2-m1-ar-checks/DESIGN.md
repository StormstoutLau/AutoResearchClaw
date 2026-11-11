---
id: arc-g2-m1-ar-checks-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m1-ar-checks-RESEARCH]
upstream: arc-g2-m1-ar-checks-RESEARCH
---

# 设计：G2 M1 学术八条判据

> 基于 [RESEARCH.md](RESEARCH.md)。8 条纯函数 + 统一 `Finding` + 16 fixture + 8 条变异。

## 1. 模块与 API

| 文件 | 职责 |
|---|---|
| `researchclaw/evidence/__init__.py` | 导出 `Finding`、`SEVERITIES`、`CHECKS`、`check_claim` |
| `researchclaw/evidence/ar_checks.py` | AR-01..08 八个纯函数 + 注册表 + `check_claim` |
| `tests/fixtures/g2/ar/arNN_{positive,negative}.json` | 16 个 ClaimRecord fixture |
| `tests/test_g2_ar_checks.py` | fixture 分类、变异自检、正例回验 C4 schema |

```python
@dataclass(frozen=True)
class Finding:
    code: str        # "AR-01".."AR-08"
    severity: str    # "fail" | "warn" | "downgrade"
    message: str
    field: str       # 失败字段的 JSON 路径（"evidence[1].digest"）
    cap: str | None = None   # 状态封顶（仅 AR-05/06）

CHECKS: dict[str, Callable[[Mapping[str, Any]], list[Finding]]]

def check_claim(claim: Mapping[str, Any]) -> list[Finding]:
    """按 CHECKS 顺序执行；返回按 code 排序的 findings。无 IO、无异常。"""
```

- 输入是 M0 的 C4 映射（`dict`），**不依赖 jsonschema**；检查对缺失字段容错（视为未提供）。
- 检查层**不写回** `status`；`cap` 供 A2-4..A2-6 的谓词层消费。

## 2. 严重度语义（R-03 §3.4）

| 值 | 含义 | 出口 |
|---|---|---|
| `downgrade` | 移入 `assumptions`、正文不渲染、状态降 `speculation` | 检查层只报告；改写由后续谓词/Stage 执行 |
| `warn` | 形态可接受但有债（形式化欠账、共识仅过滤、封顶） | 记 `quality_warning`，不阻断 |
| `fail` | 完整性问题（无引用、顺序颠倒、digest 不符、跨仓复制真值） | Stage 20 阻断 |

不新增第四档；AR-05/06 的「封顶」用 `warn + cap` 表达。

## 3. 判据算法

| ID | 触发 | 判定 | 严重度 |
|---|---|---|---|
| **AR-01** | `claim_class=A` | `evidence[]` 至少 1 条同时有 `source_id`、`locator`、`quote` | 不满足 → `downgrade` |
| **AR-01** | `claim_class=B` | `reasoning_chain` 非空，且每步 `source_refs` 非空 | 不满足 → `downgrade` |
| **AR-02** | 任意 | `claim_type` 缺失 → 按 `exploratory`；`confirmatory` 时 `stats_protocol` 五字段齐全 | 缺失 → `downgrade` |
| **AR-03** | 声明含禁用短语 | 句内出现 `[e-xxxx]` 且能解析到 `evidence[]`；命中证据必须有 `locator` | 无可解析引用 → `fail`；有引用无定位 → `downgrade` |
| **AR-04** | `stats_protocol` 与 `results` 均为对象 | 四字段非空；`stats_protocol.section_index <= results.section_index` | 不满足 → `fail` |
| **AR-05** | `claim_class ∈ {A,B}` | `falsifier.condition` 非空且 `test_ref` 解析到 E1/E2 证据 | 缺失/未解析 → `warn` + `cap=latex_verified` |
| **AR-06** | `consensus` 为对象 | `used_as == "filter"`；`evidence` 为空时不得 `status ∈ {formally_verified, partially_formalized, numerically_verified}` | 违反 → `warn` + `cap=latex_verified` |
| **AR-07** | `claim_class ∈ {A,B}` | `formal_statement` 非空；否则 `formality.status=debt` 且 `reason` 非空 | 未声明 → `fail`；已声明 → `warn` |
| **AR-08** | 每条 `evidence` | `pointer` 必须有 `source_id`+`digest`；`snapshot` 必须有 `digest` 且 `readonly=true`；`inline_copy` ≤500 字符 | 违反 → `fail` |

**AR-05 解释**：`claim_type ∈ {model, method}` 不进入 v1（见 [RESEARCH](RESEARCH.md) §3）；以 A/B 类触发。

**AR-03 词法**：禁用短语冻结为 `研究表明/研究显示/已有研究表明/studies show/research shows/it is well known`（英文大小写不敏感）；引用标记冻结为 `[e-<id>]`。词法扩展走 U-1。

**AR-06 的「共识不得提升 tier」**：属比较性语义（需要前态），不可从单条记录机械判定；本批不实现，登记为不可机械化。

## 4. fixture 矩阵（16）

| AR | 正例 | 反例 | 反例预期 |
|---|---|---|---|
| AR-01 | A 类，证据三要素齐全 | A 类，缺 `locator`/`quote` | `downgrade` |
| AR-02 | confirmatory + 完整统计口径 | confirmatory + `stats_protocol=null` | `downgrade` |
| AR-03 | 「研究表明 [e-001] …」且 e-001 有 locator | 「研究表明 …」无引用 | `fail` |
| AR-04 | 统计口径 §3 ≤ 结果 §5 | 统计口径 §5 > 结果 §3 | `fail` |
| AR-05 | A 类，falsifier 指向 E1 证据 | A 类，falsifier 为空 | `warn` + cap |
| AR-06 | consensus `used_as=filter` 且有证据 | evidence 空 + `numerically_verified` | `warn` + cap |
| AR-07 | A 类，`formal_statement` 非空 | A 类，未声明 debt | `fail` |
| AR-08 | pointer 带 `source_id`+`digest` | snapshot `readonly=false` | `fail` |

- fixture 均为完整的 C4 映射；**正例**必须通过 M0 的 C4 schema（测试回验），反例允许结构性违规（如 AR-08）。
- 反例只针对目标判据；其他判据的 findings 不参与断言。

## 5. 变异自检（pre-red）

对每条 AR：

1. 载入对应反例，`check_claim` 必须产出该 code 的 finding；
2. `monkeypatch.setitem(CHECKS, code, lambda _claim: [])` 后重跑，该 code 的 finding 必须消失；
3. 断言「反例在本判据存在时红、判据被移除后不再红」——即判据是承重的。

同时：正例不得产出本判据的 finding（防止判据恒红）。

## 6. 失败定位与确定性

- `Finding.field` 使用 `evidence[1].digest` 这类可读路径；同一 claim 的 findings 按 `code` 排序，保证跨次运行一致。
- 检查函数不抛异常；输入字段类型错误按「未提供」处理（fail-closed 由 schema 层负责）。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 判据与 schema 双写不一致 | 正例回验 C4 schema；负例只测语义面 |
| 禁用短语词表过窄/过宽 | U-1 触发条件量化（真实片段命中率 <80%） |
| 变异测试误伤其他判据 | 只替换目标表项，断言只针对目标 code |
| 状态改写提前混入检查层 | API 只读；`cap` 留给谓词层 |
