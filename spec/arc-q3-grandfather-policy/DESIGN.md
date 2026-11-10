---
id: arc-q3-grandfather-policy-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-q3-grandfather-policy-RESEARCH]
upstream: arc-q3-grandfather-policy-RESEARCH
---

# 设计：Q3 = 基线 + 棘轮

> 输入：[RESEARCH.md](RESEARCH.md) §7 的建议。本文件把建议落成可执行规则；裁决确认前不写代码。

## 1. 决策

**Q3 = B（基线 + 棘轮）**：

- 新文档立即合规；
- 存量在 `cutoff` 做一次基线，当前 `entries: []`；
- 存量**语义触碰**必须迁移或续期；
- 豁免有期限、有 owner、有原因、可过期；
- 只豁免 DC1/DC2/DC3，不豁免 DC4/DC5、Step 链、digest、CONSOLE。

## 2. 不变量

1. **新文档零豁免**：第一次提交必须过 DC1-DC5。
2. **基线可空**：当前无存量违规，空清单是合法状态。
3. **过期即红**：grandfather 不是永久许可证。
4. **门禁不降级**：grandfather 不得跳过 digest、Step 链、DC4/DC5。
5. **fail-closed**：未知字段、重复 path、过期、无 owner/reason → exit 2。
6. **T1 实施**：改 `scripts/dc_validator.py` 与门禁，按 T1 完整管线另开批次。

## 3. grandfather.yaml

```yaml
version: 1
cutoff: 2026-11-10
expires_days: 90
entries: []
# - path: spec/<feature>/RESEARCH.md
#   reason: pre-DC2 legacy import
#   owner: <name>
#   expires: 2027-02-08
#   approved_by: <name>
#   issue: <link or id>
```

字段规则：

| 字段 | 必填 | 规则 |
|---|---|---|
| `version` | 是 | 必须为 `1` |
| `cutoff` | 是 | ISO 日期；新文档不得早于/等于 cutoff 入豁免 |
| `expires_days` | 是 | 默认 90；单条 `expires` 不得晚于 `cutoff + 2*expires_days` |
| `entries[].path` | 是 | 仓库相对路径，必须存在；不得重复 |
| `reason` | 是 | 说明为何不能立即迁移 |
| `owner` | 是 | 责任人 |
| `expires` | 是 | ISO 日期；过期即不豁免 |
| `approved_by` | 否 | 维护者/裁决人 |
| `issue` | 否 | 关联 issue/P 批次 |

## 4. “touch”判定

### 4.1 语义触碰（触发迁移）

- front matter 任一字段变化；
- 断言、决策、接口、契约、验收条件变化；
- 链接目标或代码锚点变化；
- 章节增删/重排导致契约结构变化；
- 任何无法确定是否语义的改动（fail-closed）。

### 4.2 非语义维护（不触发）

- 纯空白/换行；
- 拼写/标点/格式；
- 不改变断言、链接目标、契约的措辞微调。

### 4.3 处理矩阵

| 文档状态 | 非语义维护 | 语义触碰 |
|---|---|---|
| 合规文档 | 允许 | 保持合规 |
| grandfathered 未过期 | 允许 | 迁移，或续期（一次） |
| grandfathered 已过期 | 允许（仅维护） | 必须先迁移，不能续期 |
| 新文档 | 允许 | 必须合规 |

## 5. dc_validator 读取规则

1. 读取 `spec/grandfather.yaml`；不存在 → 视为空清单（兼容）。
2. 对每个待检文件：
   - 若命中未过期 entry：跳过 **DC1/DC2/DC3** 错误，输出 `[grandfathered] path (expires=...)`；
   - DC4/DC5 仍执行；
   - 若过期：不跳过，按正常违规报红。
3. 校验 schema：
   - 未知字段 / 重复 path / 缺 owner/reason/expires → exit 2；
   - `expires` 超过上限 → exit 2。
4. 汇总输出：`grandfathered=N expired=M`。
5. 不读取 grandfather 的检查：`step_enforce`、`console_gen`、digest 校验。

## 6. 续期规则

- 默认 90 天；
- 最多续期一次；
- 续期需在提交说明或 PROGRESS 写理由；
- 第二次续期必须升级为显式裁决（新批次），不得静默改日期。

## 7. 与 G0b 的关系

| G0b 项 | Q3 决策后的变化 |
|---|---|
| A0-1 | 六钩子不变；dc-validator 增加 grandfather 读取 |
| A0-2 | 新文档立即；不豁免 |
| A0-3 | Step 链不豁免 |
| A0-4 | digest 不豁免 |
| A0-5 | CONSOLE 不豁免 |
| A0-6 | spec-gates 仍跑全量 |
| 交付物 | `spec/grandfather.yaml` 从“待创建”变为“空清单 + 规则” |

## 8. 影响与回滚

- 影响：`dc_validator.py` 新增读取/校验；`spec/grandfather.yaml` 新增；文档 Q3 状态更新。
- 不影响：`step_enforce`、`console_gen`、运行时、CI 矩阵。
- 回滚：删除 `grandfather.yaml` 读取分支与文件；回到“全量严格”。
- 风险：豁免滥用 → 用 owner/expiry/审批/数量趋势约束。

## 9. 验收（实施批）

1. 空清单：全量 pre-commit 通过，输出 `grandfathered=0`。
2. 合法豁免：临时文档缺 `status` + 命中 entry → 仅 DC1 被跳过，DC4/DC5 仍执行。
3. 过期豁免：`expires` 设为昨天 → 缺 `status` 必须红。
4. 非法 schema：未知字段/重复 path/缺 owner → exit 2。
5. digest 不豁免：grandfathered 文档 verify 后改正文 → 仍红。
6. Step 链不豁免：grandfathered 文档缺 verify → finalize 仍红。

## 10. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §9 的 U-1..U-4。
