---
id: arc-spec-gate-hardening-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [SPEC-PROCESS, arc-spec-workflow-install-DESIGN]
upstream: SPEC-PROCESS
---

# 调研文档：Spec 门禁加固（P-081）

> **Feature**：把 P-080 后对 `spec/SPEC_PROCESS.md` v1.7.1 的强制力审计结论落为门禁——建议 1（CI 兜底 step-enforce）与建议 2（四文档齐全）。
> **Spec 步骤**：Step 1-2。

## 1. 调研目标

1. **CI 为何不强制**：`step_enforce` 在 CI 的 `pre-commit run --all-files` 中是否真正执行判定？
2. **四文档齐全缺口**：现有判据为何允许只交单份文档？
3. **加固形态**：如何在 CI 拿到正确的比较基线（push / PR），以及如何在不误伤 T3 轻批的前提下强制 T1 四文档？

## 2. 调研方法

| 通道 | 用途 | 结果 |
|---|---|---|
| 读码 `step_enforce.main` | 变更集来源 | ✅ 本地模式取 `_local_changed()`；`--base` 模式取 argv |
| 实测干净树 | 复现 CI 空转 | ✅ `git status` 0 行时 `step_enforce docs/PROGRESS.md` → **exit 0** |
| 读码 `FEATURE_RE` / `_digest_scope` | 四文档判定面 | ✅ 只匹配**已存在**的四文档；缺文件不报 |
| `WebSearch` + GitHub 事件实证 | `before` 语义 | ⚠️ 官方页只取到事件目录；社区实证：首次 push 为全 0（T3） |
| `WebSearch`（git-scm 官方） | 识别 merge commit | ✅ `--min-parents=2` ≡ `--merges`（T1） |
| 读码 `ci.yml` | 现有 job | ✅ `push`/`pull_request` 双触发；无 `--base`、无 `--check-merge` |

## 3. 调研发现

### 3.1 F-1：CI 对 step-enforce 空转（E2 实测）

`step_enforce` 本地模式：

```python
changed = _local_changed()          # diff --cached ∪ diff ∪ ls-files --others
files = [f for f in changed if FEATURE_RE.match(f) or SESSION_RE.match(f) or f == "docs/PROGRESS.md"]
if not docs and not sessions and not progress_changed:
    return 0
```

CI checkout 干净 → 三个集合皆空 → `files` 空 → `return 0`。`ci.yml` 只有 `pre-commit run --all-files`，没有 `--base` 调用，因此 **CI 不兜底**；唯一强制面是开发者本地的 commit 钩子。

### 3.2 F-2：四文档齐全无判据（E1 读码）

- `FEATURE_RE` 只匹配 `spec/<feature>/{RESEARCH,DESIGN,IMPLEMENTATION,CHECKLIST}.md` 中**存在的那几份**；
- `_digest_scope` 注释明说「非四文档不绑」；
- 因此「只交 RESEARCH」或「只交 DESIGN + CHECKLIST」都能通过，只要 P 行声明了该 feature。

### 3.3 F-3：区分 T1/T3 的唯一机械信号是 P 行依据列

`SPEC_PROCESS.md §批次档位` 规定 T3 轻批**无四文档**（1 条 session + PROGRESS 行）。若无条件强制四文档，会把合法的 T3 批次判红。现成可机械读取的信号只有 PROGRESS 行第 3 列（依据列）里的 `T1` / `T3` 词——`spec_map.parse_progress_rows` 目前只返回 `status/features`，未保留依据列。

### 3.4 F-4：push / PR 的比较基线

- push：`github.event.before` 是推送前的 SHA；首次推送/新分支为全 0（社区实证 T3，官方页未取到正文）；
- PR：`github.event.pull_request.base.sha`；
- 两者任一缺失/全 0/不在克隆内 → 必须**显式跳过并打印**，不得静默当作通过（降级链）。

### 3.5 F-5：merge commit 的识别

`git rev-list --min-parents=2` 等价 `--merges`（git-scm 官方文档，T1）。用它逐个跑 `step_enforce --check-merge <sha>`，补齐 P-144 设计但未接入 CI 的 evil merge 检测。

## 4. 综合分析

1. 加固 1：CI 增加一个 range 步骤——`BASE = before || pull_request.base.sha`，把 `git diff --name-only BASE...HEAD` 作为 argv 传给 `step_enforce --base BASE`；再对 `rev-list --merges BASE..HEAD` 逐个 `--check-merge`。
2. 加固 2：在 `step_enforce._resolve_declared` 中，对 P ≥ 新阈值（81，本批起）的声明按 feature 读取档位；T1 → 校验 `RESEARCH/DESIGN/IMPLEMENTATION/CHECKLIST` 四份存在；T3 → 跳过；缺档位 → 红。
3. 阈值取 81 而非沿用 129/137：棘轮从**引入批次**起生效，否则本批及近期批次仍不受约束（与 P-080 审计发现的 G-3 同型）。

## 5. 幻觉抑制审查（Step 2 Review）

| 引用 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| `--min-parents=2` ≡ `--merges` | git-scm docs | 原文片段 | ✅ T1 |
| `before` 首次 push 全 0 | 社区实证 | 搜索结果两处一致 | ⚠️ T3（代码做防御，不依赖断言） |
| `pull_request.base.sha` | GitHub 事件上下文 | 官方页目录 + 通行用法 | ⚠️ T3（代码对不可达 base 显式跳过） |

- 无 A 类断言依赖未验证来源；两处 T3 事实均配有**运行时防御**（全 0 / 不可达 → 打印跳过）。

## 6. 对设计的输入

### 6.1 方案

1. CI range 兜底（不新增 step_enforce 模式）。
2. 档位感知的四文档齐全检查（`DOC_COMPLETENESS_MIN_P = 81`）。
3. `spec_map` 扩展 `basis` 字段与 `row_tier()`（单一实现，I-10）。

### 6.2 约束

- 不弱化既有判据；T3 轻批保持合法。
- 不新增三方依赖；CI 只加 bash 步骤。
- 历史 P 行不回溯（阈值 81）。
- 失败必须 fail-closed：缺档位、四文档缺失、base 不可达（打印跳过）三种行为显式区分。

### 6.3 未决项登记（四元块）

- **U-1 逐提交 vs 范围**
  - **判据**：中间提交违规但末态合规的场景被 CI 拦截
  - **触发条件**：出现「中间提交漏 P 行、后续提交补齐」的真实事故
  - **当前倾向**：范围模式（`--base`）+ merge evil 检测；逐提交需新增 `--commit` 接口
  - **证据等级**：E1 读码（`--base` 的 new 固定 WORKTREE）

- **U-2 档位标注可信度**
  - **判据**：T3 行有可机械核验的裁剪理由（如「Layer-0」+ 路径集）
  - **触发条件**：出现首个 T3 降档滥用
  - **当前倾向**：只校验 T1/T3 词存在；理由文本不核
  - **证据等级**：SPEC_PROCESS §批次档位（自述不可机械拦截）

## 7. 参考文献

- Git. *git-rev-list(1)* — `--min-parents` / `--merges`. https://git-scm.com/docs/git-rev-list
- GitHub Docs. *Events that trigger workflows*.
- spec/SPEC_PROCESS.md v1.7.1 §批次档位与裁剪理由、§诚实边界。

---

**Review 签字**: 自查（单视角）+ 实测 日期: 2026-11-12
