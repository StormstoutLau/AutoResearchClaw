---
id: arc-q3-grandfather-policy-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-g0b-governance-base-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：Q3“touch = migrate”与存量 grandfather 策略

> **Feature**：裁决 Q3——Spec 文档的迁移是“触碰即强制”，还是“新文档立即、存量豁免”。
> **状态**：verified（实测 + 社区/学术锚点 + 方案对比；未改代码）
> **Spec 步骤**：Step 1-2

## 1. 问题定义

Q3 的原始表述是：

> Spec "touch = migrate" 是否立即生效；存量豁免范围。

拆成三个可判定的子问题：

1. **新文档**：是否从创建起就必须满足 DC1-DC5 与 Step 链？
2. **存量文档**：未被触碰时是否继续豁免？被触碰时是否必须迁移？
3. **豁免边界**：grandfather 是否永久、是否有期限、是否可续期、哪些检查可豁免？

## 2. 当前事实（2026-11-10）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `pre-commit run --all-files` **exit 0**，六钩子全绿 | 实际运行 |
| F-2 | `dc_validator` 在 pre-commit 语义下对全部 spec 文档 **0 违规** | 实际运行 |
| F-3 | `spec/templates/` 六模板在 pre-commit 下通过 | 实际运行 |
| F-4 | `spec/grandfather.yaml` **不存在** | `Test-Path` |
| F-5 | 当前没有已知的存量 DC 违规，**grandfather 清单应为空** | F-2 + F-3 |
| F-6 | `step_enforce` 已实现 finalize digest 绑定；grandfather 不应豁免 digest | `step_enforce.py:52-59`、`:204-253` |
| F-7 | 106 条验收计数与 Q3 无直接关系 | 总纲 §4/§5 |

**关键含义**：当前执行“严格立即迁移”的迁移成本为 **0**；grandfather 不是为现有债务准备，而是为未来导入/历史例外准备的安全阀。

## 3. 方案对比

### 方案 A：严格立即

所有文档（新/存量）一接触就必须完全合规；无 grandfather。

- 优点：规则最简单；无豁免账本；无“永久债务”。
- 缺点：无应急通道；导入旧文档、紧急修复、第三方文档会被卡死；大 diff 可能淹没实质变更。
- 适用：仓库完全干净且永不导入旧文档。

### 方案 B：基线 + 棘轮（推荐）

新文档立即合规；存量在 `cutoff` 日做一次基线；未被触碰的存量按基线豁免；**语义触碰**时必须迁移或显式续期；豁免有 owner、reason、expires。

- 优点：新代码立即干净；存量不被一次性大 migration 阻塞；豁免可见、可过期、可收敛；与主流静态分析 baseline 一致。
- 缺点：需要 `grandfather.yaml` 与 validator 读取逻辑；需要定义“touch”。
- 适用：当前仓库（基线为空，机制成本低、未来收益高）。

### 方案 C：永久 grandfather

新文档立即；所有存量永久豁免，不要求触碰迁移。

- 优点： friction 最低。
- 缺点：债务永久化；无收敛；与 Q3 的“migrate”语义矛盾。
- 适用：不再维护的归档仓，不适用于活跃规范。

### 方案 D：宽限期 + 警告

先警告 N 天，再转红。

- 优点：给迁移窗口。
- 缺点：警告容易被忽略；宽限期结束仍要一次性处理；没有棘轮。
- 适用：一次性大规模迁移，不是持续治理。

## 4. “touch”的精确定义

建议把“触碰”分成两类，避免 typo/空白修复触发大迁移：

| 类型 | 判定 | 处理 |
|---|---|---|
| **语义触碰** | 改 front matter（id/type/version/status/depends/upstream）、断言/决策/契约、链接目标、代码锚点、章节结构 | 必须迁移；否则拒绝提交 |
| **非语义维护** | 纯空白、换行、拼写、标点、格式，不改变断言/链接/契约 | 不触发迁移；按 maintenance 处理 |
| **不确定** | 无法判断是否语义 | 按语义触碰处理（fail-closed） |

补充规则：

1. 新文档从第一次提交起必须合规。
2. 被语义触碰的 grandfathered 文档：迁移，或续期（需 owner/reason，最长 90 天，最多一次）。
3. 过期未迁移：按正常违规报红。
4. grandfather 只豁免 DC1/DC2/DC3；**不豁免** DC4/DC5、Step 链、digest、CONSOLE 派生一致性。
5. 不允许“新建文档即入 grandfather”；只有导入/历史文档可申请。

## 5. 外部锚点

| # | 锚点 | 机制 | 对本决策的启示 | 验证 |
|---|---|---|---|---|
| X-1 | Android Lint baseline | 首次生成 `lint-baseline.xml`，只报告新问题 | 基线快照 + 新问题失败 | ✅ 官方文档 |
| X-2 | PHPStan baseline | 记录现有错误，只关注新/变更代码 | “new and changed code” 语义 | ✅ 官方文档 |
| X-3 | ESLint bulk suppressions | 规则设为 error，现有违规入抑制文件，新违规失败 | 新代码立即、存量按节奏清理 | ✅ 官方博客 |
| X-4 | Detekt baseline | 基线文件 + 新问题门禁 | Kotlin 生态同构 | ✅ 官方迁移文档 |
| X-5 | SonarQube Clean as You Code | 新代码定义 + 质量门禁 | “新代码必须干净” | ✅ 官方文档 |
| X-6 | Kubernetes deprecation policy | 弃用后至少一年/三版本再移除 | 豁免应有时间边界 | ✅ 官方文档 |
| X-7 | Kruchten/Nord/Ozkaya, *Technical Debt* (IEEE Software 2012) | 技术债的可见化与偿还 | 豁免必须可见、可计量 | ✅ 元数据 |
| X-8 | 增量静态分析（ACM CSUR 2025） | 只重算受影响部分 | “触碰才迁移”有工程合理性 | ✅ 摘要 |
| X-9 | `pylint-grandfather`（PyPI） | 旧代码豁免、新/变更代码强制 | 社区已有同构工具 | ✅ PyPI 页面 |
| X-10 | Boy Scout Rule / Broken Windows | 每次触碰都改善 | 反方观点：应更严格 | ⚠️ 二手 |

## 6. 方案评分

| 维度 | A 严格 | B 基线+棘轮 | C 永久豁免 | D 宽限 |
|---|---|---|---|---|
| 新代码立即干净 | 5 | 5 | 5 | 3 |
| 存量收敛 | 5 | 4 | 1 | 3 |
| 应急/导入可用 | 1 | 4 | 5 | 4 |
| 规则复杂度 | 5 | 3 | 4 | 3 |
| 可审计性 | 4 | 5 | 1 | 2 |
| 当前迁移成本 | 5 | 4 | 5 | 4 |
| 长期债务风险 | 1 | 2 | 5 | 3 |

**B 在“收敛、应急、可审计”之间最平衡；A 可作为 B 的一个退化配置（grandfather 为空时等价）。**

## 7. 明确裁决建议

**建议 Q3 = B（基线 + 棘轮），参数如下：**

1. `cutoff: 2026-11-10`。
2. `entries: []`（当前零存量违规）。
3. 新文档立即合规。
4. 存量**语义触碰**必须迁移；非语义维护不触发。
5. 豁免字段：`path / reason / owner / expires`；默认 90 天，最多续期一次。
6. 只豁免 DC1/DC2/DC3；不豁免 DC4/DC5、Step 链、digest、CONSOLE。
7. 过期自动红；新增豁免需在 PROGRESS 或提交说明中说明理由。

**不选 A 的理由**：当前虽可零成本执行，但没有导入旧文档/紧急修复的合法通道，容易逼出“绕过门禁”的坏习惯。
**不选 C 的理由**：与“migrate”目标相反，债务永久化。
**不选 D 的理由**：警告不是门禁，无法形成棘轮。

## 8. 实施影响

- `spec/grandfather.yaml`：空清单 + cutoff + expires_days。
- `dc_validator`：读取豁免；只跳过 DC1/DC2/DC3；输出 `grandfathered`；过期/未知字段 fail-closed。
- `step_enforce`：不读取 grandfather，保持 digest/step 链独立。
- 文档：总纲 Q3 状态改为“已裁决（B）”；G0b 决策闸门关闭。
- 批次：属于门禁变更，按 T1 完整管线实施（另开批次）。

## 9. 未决项

- **U-1 豁免上限**：是否需要“全局最多 N 条”？判据=豁免数量趋势；触发=>10 条；倾向=不设硬上限，按过期收敛；E1。
- **U-2 续期次数**：是否允许第二次续期？判据=实际续期请求；触发=首个二次请求；倾向=不允许，需升级裁决；E1。
- **U-3 非语义维护的判定**：是否引入 diff 白名单？判据=实际误判；触发=首次争议；倾向=人工判断 + fail-closed；E2。
- **U-4 导入文档流程**：是否需要单独标签？判据=导入频率；触发=首个导入；倾向=先人工登记；E1。

## 10. 参考文献

1. Android Developers. *Improve your code with lint checks*（baseline）.
2. PHPStan. *The Baseline*. https://phpstan.org/user-guide/baseline
3. ESLint. *Introducing bulk suppressions* (2025). https://eslint.org/blog/2025/04/introducing-bulk-suppressions/
4. detekt. *Migration guide / baseline*.
5. SonarQube. *Clean as You Code*.
6. Kubernetes. *Deprecation Policy*. https://kubernetes.io/docs/reference/deprecation-policy/
7. Kruchten, Nord, Ozkaya. *Technical Debt: From Metaphor to Theory and Practice*. IEEE Software, 2012.
8. ACM Computing Surveys. *Common Threads in Incremental Data Flow Analysis* (2025).
9. `pylint-grandfather`. https://pypi.org/project/pylint-grandfather/
10. 仓内：`SPEC_PROCESS.md`、`scripts/dc_validator.py`、`scripts/step_enforce.py`。
