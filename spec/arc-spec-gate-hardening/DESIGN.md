---
id: arc-spec-gate-hardening-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-spec-gate-hardening-RESEARCH]
upstream: arc-spec-gate-hardening-RESEARCH
---

# 设计：Spec 门禁加固（P-081）

> 基于 [RESEARCH.md](RESEARCH.md)。两项加固：CI 范围兜底（F-1）、档位感知的四文档齐全检查（F-2 + F-3）。

## 1. 加固矩阵

| ID | 缺口 | 修法 | 生效面 | 验收 |
|---|---|---|---|---|
| FIX-1 | CI 对 step-enforce 空转 | `ci.yml` 新增 range 步骤：`--base` + 变更集 argv；merge commit 逐个 `--check-merge` | push / PR | 本地以 `--base HEAD~1` 实测不误报；CI 事件路径读码 |
| FIX-2 | 四文档齐全无判据 | `step_enforce` 按 P 行档位：T1 校验四份、T3 跳过、缺档位判红 | P ≥ 81 的声明 | 单测 4 项 + 本批自检 |
| FIX-3 | 档位不可读 | `spec_map.parse_progress_rows` 增 `basis`；新增 `row_tier()` | 所有调用方 | 单测 |

## 2. CI 步骤（FIX-1）

```yaml
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # 需要 before/base 的祖先可见
      ...
      - name: Batch binding on the pushed range (P-081)
        env:
          BASE_SHA: ${{ github.event.before || github.event.pull_request.base.sha }}
        run: |
          set -euo pipefail
          if [ -z "${BASE_SHA:-}" ] || [ "$BASE_SHA" = "000…0" ]; then
            echo "no base sha — skipping range check"; exit 0
          fi
          if ! git cat-file -e "${BASE_SHA}^{commit}" 2>/dev/null; then
            echo "base not in this clone — skipping range check"; exit 0
          fi
          mapfile -t CHANGED < <(git diff --name-only "${BASE_SHA}...HEAD")
          python scripts/spec/step_enforce.py --base "${BASE_SHA}" "${CHANGED[@]}"
          for sha in $(git rev-list --merges "${BASE_SHA}..HEAD"); do
            python scripts/spec/step_enforce.py --check-merge "${sha}"
          done
```

- `--base` 模式的 `new` 固定读 WORKTREE（= checkout 后的 HEAD），`old` 读 `BASE_SHA`，语义为「整个推送范围的最终态」。
- base 缺失 / 全 0 / 不在克隆内 → **打印跳过**（降级链），不静默当作检查通过。
- merge commit 用 `rev-list --merges` 识别（RESEARCH F-5），逐个跑 evil merge 检测。

## 3. 四文档齐全（FIX-2 / FIX-3）

### 3.1 数据面

`spec_map.parse_progress_rows` 增加 `basis`（P 行第 3 列文本）：

```python
rows[pid] = {"status": ..., "features": ..., "basis": m.group(3)}
```

新增：

```python
TIER_RE = re.compile(r"\bT([13])\b")
def row_tier(row: dict) -> str | None:
    m = TIER_RE.search(str(row.get("basis") or ""))
    return f"T{m.group(1)}" if m else None
```

### 3.2 判定（`step_enforce._resolve_declared`）

```text
阈值 DOC_COMPLETENESS_MIN_P = 81（本批起；历史 P 行不回溯）
对每个本次变更的 feature：
  owners = 声明该 feature 且 P ≥ 阈值的 P 行
  若无 owners → 跳过（覆盖检查已报错）
  tier = 最高编号 owner 的档位
  tier 缺失 → 错误「P 行缺批次档位」
  tier == T3 → 跳过（T3 合法无四文档）
  tier == T1 → 校验四份；缺任一 → 错误「T1 批次四文档不全」
```

- `CHECKLIST.md` 与历史变体 `CHECKLIST_FUNC.md` 任一存在即视为齐全（与 `FEATURE_RE` 同口径）。
- 检查位置在「feature 覆盖」之后、「session 完整性」之前：先给最直接的修复信号。

## 4. 关键决策与被拒绝方案

| # | 决策 | 被拒绝方案 | 拒绝理由 | 代价 |
|---|---|---|---|---|
| D-1 | CI 用**范围模式** `--base BASE` | 逐提交新增 `--commit <sha>` 接口 | `--base` 的 new 固定 WORKTREE，逐提交需扩展 `_read_doc_bytes`/digest 读取语义；中间态违规收益低于改动面（U-1） | 中间提交违规但末态合规时不判 |
| D-2 | 四文档检查**按档位** | 无条件四文档 | 违反 SPEC_PROCESS T3 定义（轻批无四文档），会把合法批次判红 | 依赖 P 行档位标注（U-2） |
| D-3 | 阈值 81 | 沿用 129/137 | 棘轮应从引入批次起生效；沿用旧阈值等于本批不加固（P-080 G-3 同型） | 81–128 的历史批次若再被改动会受新约束（合规成本） |
| D-4 | 缺档位判红 | 缺档位默认 T1 | 默认 T1 会让历史未标注行大面积误报；判红给出明确修复动作 | 需补标注 |
| D-5 | 四文档只查**本次变更的 feature** | 全仓扫描 | 全仓扫描会误伤历史 feature（如 readiness 仅 RESEARCH） | 历史 feature 的缺口不会被主动发现 |

## 5. 不变式

- I-1 既有判据不弱化：feature 覆盖、session 完整性、digest 校验顺序与语义不变。
- I-2 T3 轻批保持合法：只要档位标注正确。
- I-3 fail-closed：缺档位 / 四文档缺失 → 红；base 不可达 → 显式跳过（不是通过）。
- I-4 单一实现：档位解析只在 `spec_map`，`step_enforce` 不重复正则。
- I-5 无三方依赖；CI 只增加 bash 步骤。

## 6. 边界

- **职责外**：逐提交语义（U-1）、T3 裁剪理由的语义核验（U-2）、全仓历史 feature 补齐。
- **能力边界**：范围模式看不到中间提交；`before`/`base.sha` 语义若变化，代码的「不可达即跳过」会退化为不检查（有打印，不静默）。

## 7. 验收映射

| ID | 验收 |
|---|---|
| FIX-1 | 本地 `--base HEAD~1` 对 P-080 范围 exit 0；CI 步骤读码含 `fetch-depth: 0` / `--base` / `--check-merge` |
| FIX-2 | 单测：T1 缺一文档 → 红；T1 齐全 → 绿；T3 缺文档 → 绿；缺档位 → 红 |
| FIX-3 | 单测：`basis` 保真、`row_tier` 三态 |
