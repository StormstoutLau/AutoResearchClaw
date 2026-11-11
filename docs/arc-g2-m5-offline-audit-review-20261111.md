# P-064 M5 独立异构复审报告（2026-11-11）

> **性质**：Layer-0 独立异构复审（T3，零代码/零门禁）。纪律同 P-053/P-055/P-062——不采信 [四文档](../spec/arc-g2-m5-offline-audit/IMPLEMENTATION.md) 结论，全部一手复验；「异构」体现在**实现者未覆盖的角度**（删除向量、门禁上下文、CLI 组合语义）与**开源社区先例映射**（S 表，全部联网回源）。
> **对象**：P-064 G2 M5（离线审查模式，[spec/arc-g2-m5-offline-audit/](../spec/arc-g2-m5-offline-audit/)）。工作树状态：已暂存未提交。
> **探针**：`%TEMP%\m5_review_probe.py`（R-A..R-H）+ 内联探针 R-I/R-J（临时目录，零仓库变异）。

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | M5 套件 29 项 | `--collect-only` 计数 29 + 全跑 29 passed（3.13.5） | ✅ 与 IMPLEMENTATION §3 一致 |
| T-2 | M4+M5 合计 88 passed | 3.13.5 与 3.11.15 双环境复跑均 88 passed | ✅ |
| T-3 | 相关回归 108 passed（含 test_cli） | 复跑 108 passed（3.55s） | ✅ |
| T-4 | CLI 退出码 0/1/2 | 一致→0、`--policy-version 1` 漂移→1（DRIFT + diff 明细）、目录缺失→2、annotations 损坏→2（R-F） | ✅ 三态成立 |
| T-5 | 只读性 | `test_offline_audit_is_read_only`（全树字节快照）复跑通过 | ✅ |
| T-6 | 确定性 | `test_offline_audit_is_deterministic` 复跑通过 | ✅ |
| T-7 | 「共享比对、无双实现」声明 | grep 实证 `run_stage23_consistency` 与 `run_offline_audit` 均调 `compare_claims`；探针 **R-G** 同一 run 上 Stage 23 payload 与离线报告 diffs/audit 逐值相等，差异仅 `expected_policy_version` | ✅ |
| T-8 | 文档计数 | 改动清单 8 项与暂存集一致（另 4 spec 文档 + session + 2 派生视图）；测试 29 = collect 计数 | ✅ 零幻觉 |
| T-9 | RESEARCH F-1..F-8 回源抽查 | F-1（R-03 §5.1 离线批次模式裁定）、F-4（C4 含 `policy_version` 必填）、F-5（gate decisions 无版本，探针 **R-H** 列出 decision 键证实）、F-6（CLI 派发形态）逐条属实 | ✅ |
| T-10 | D-1..D-6 决策与实现一致性 | 逐条对照代码：共享比对、claims 版本锚点、只读、退出码、跳过语义、`CURRENT_POLICY_VERSION` 真值源全部落地 | ✅ |
| T-11 | 机检 | pre-commit 9/9；step_enforce P-064 5/5；coverage missing=0 | ✅ 复跑通过 |

## 2. 复审发现

### 缺陷（D 表）

| # | 级 | 缺陷 | 证据 | 修法 |
|---|---|---|---|---|
| **D-1** | P2 | **孤儿生产决定不可见（删除型绕过）**：`compare_claims` 只检查 claim→decision 方向；删掉 `stage-20/claims.jsonl` 的行后，gate decisions 中残留条目成为孤儿，审计不产生任何 diff | 探针 **R-C**：双 claim re-gate 后删第二行 → `checked=1, consistent=True`，c-22222222 的 decision 无 diff；**R-A/R-B**（清空/删除整个 stage-20 claims）→ 回退 stage-09 后同样空转通过 | `compare_claims` 增对称检查：`production keys − claim keys` 非空 → 逐条 `orphan_production_decision` diff（社区先例：Argo CD Orphaned Resources Monitoring，S-3） |
| **D-2** | P3 | **`--policy-version 0` 被静默吞掉**：`cmd_audit` 用 `args.policy_version or CURRENT_POLICY_VERSION`，`0` 为 falsy 回退当前版本 2 | 探针 **R-E**：`--policy-version 0` → `expected_policy_version=2`、rc=0 | `if args.policy_version is not None` 显式判空；argparse 校验 `>= 1`（C4 约束） |
| **D-3** | P3 | **`--json --output` 并用时 stdout 被污染**：`--output` 的提示行 `audit: report written to ...` 打在 stdout 且先于 JSON | 探针 **R-I**：stdout 首行为提示行，`json.loads(stdout)` 失败（`Expecting value`） | `--json` 时提示行改写 stderr（或 `--output` 提示恒走 stderr） |

### 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | 报告不透传生产门禁总体 verdict（`pass/downgraded/block`）：被阻断 run 审计同样 `consistent=True`（探针 **R-D**），审计者无法区分「通过且一致」与「阻断但一致」 | 报告增强 |
| O-2 | 报告无 claims **来源溯源**：`R-A/R-B` 中 stage-20 claims 缺失/清空时静默回退 stage-09，报告 `checked=1` 不标注来源文件与优先级路径 | 报告增强 |
| O-3 | `write_audit_report` 用 `write_text` 非原子写，与 P-063 原子写纪律不一致（低风险：报告落在 run 外） | 实现注记 |
| O-4 | `offline_audit` 引 stage_hooks 三个私有名（`_annotations`/`_claim_key`/`_load_production_gate`）——包内可接受，长期应转公开 API | 代码卫生 |
| O-5 | 状态矩阵测试的 7 statuses 硬编码，与 C4 schema/`STATUS_ORDER` 无机械绑定——词表变更不会让矩阵自动跟上 | 测试注记 |
| O-6 | 退出码语义需文档化：本实现取 **pytest 约定**（1=断言失败、2=错误）；Terraform `-detailed-exitcode` 恰好相反（2=有变更、1=错误，S-2）——两者皆主流，DESIGN 应注明防 CI 误读 | 文档 |
| O-7 | session ts 单调性仍受 P-060 未来时间戳影响（CONSOLE「最近会话」显示 P-060）；继承问题非本批引入 | 数据卫生 |

## 3. 开源社区锚点（S 表，全部联网回源）

| # | 案例 | 锚点内容 | 等级 | 映射 |
|---|---|---|---|---|
| S-1 | **OPA Decision Logs**（openpolicyagent.org） | 决策日志记录「被查询的 policy、input、bundle 元数据」，明确用于 *auditing and offline debugging of policy decisions*，事件含 `decision_id` | T1 官方文档 | D-1 共享比对 + 离线重放：生产记录决策、审计平面用**同一评估器**重放——与 `claim_gate.json` + `compare_claims` 同构 |
| S-2 | **Terraform plan `-detailed-exitcode`**（developer.hashicorp.com） | 0=空 diff（无变化）/ 1=错误 / 2=非空 diff（有变更）——录制状态 vs 重算期望状态的三态退出码 | T1 官方文档 | D-4 退出码三态（注意顺序与 pytest 相反 → O-6） |
| S-3 | **Argo CD Orphaned Resources Monitoring**（argo-cd.readthedocs.io） | GitOps 双平面比对中，**不属于任何 Application 的孤儿资源**必须可检测、可告警 | T1 官方文档 | **D-1 修法直接同构**：孤儿生产决定（decision 有而 claim 无）必须可见 |
| S-4 | **pt-table-checksum**（Percona Toolkit 官方文档） | 主/备双平面在线一致性校验：在主库执行校验查询，「与主库不一致的副本会产生不同结果」；明确 *read-only tool* | T1 官方文档 | D-3 只读审计 + 双平面一致性（数据库领域先例） |
| S-5 | **`git fsck`**（git-scm.com） | 只读校验对象库连通性与有效性；`hash mismatch` 即严重完整性问题；interrogate 类命令「不触碰工作树」 | T1 官方文档 | D-3 只读 + 失败封闭；审计不修改被审计对象 |
| S-6 | **Flyway Validate**（Redgate 官方文档） | 比对源迁移脚本与已应用记录，检测「事后增删改」，版本/校验和不符即报 `TYPE_MISMATCH` 等错误码拒绝 | T1 官方文档 | D-2 版本锚点（`policy_version_mismatch`）；D-2 修法：不符即拒，不给默认值 |
| S-7 | **OPA bundle `revision`**（openpolicyagent.org CLI/management 文档） | bundle 携带 `revision` 字段标识版本；`--revision` 显式设定；capabilities 按特定 OPA 版本校验策略 | T1 官方文档 | D-2/D-6 版本真值源（`CURRENT_POLICY_VERSION`） |
| S-8 | **Nix `nix-store --verify-path` / `nix-build --check`**（nixos.org manual + arXiv 2501.15919） | 前者：比对存储路径内容与数据库中记录的密码学哈希，无变化 exit 0 否则 1；后者：重跑构建验证位级可复现 | T1 官方文档 + T2 论文 | D-1 记录 vs 重算的双平面原型；确定性测试（T-6）的先例 |
| S-9 | **pytest 退出码约定**（docs.pytest.org） | 0=全部通过 / 1=收集并执行但有失败 / 2=执行被中断（错误） | T2 官方文档 | D-4：本实现 1=漂移（断言失败）、2=输入错误与 pytest 同序 |

**映射结论**：P-064 六项决策（D-1..D-6）在开源社区均有成熟先例，方案形态无异议；三项新发现缺陷中，D-1 的修法（孤儿可见）有 Argo CD 直接先例，D-2 的修法（不符即拒）有 Flyway 先例。

## 4. 结论

- **M5 主线成立**：T-1..T-11 全过，四文档计数零幻觉，「共享比对」与「只读」两项核心承诺一手证实（R-G/R-I 与快照测试）。
- **三项缺陷登记**：D-1（P2，删除型绕过——孤儿生产决定不可见）、D-2/D-3（P3，CLI 语义边角）。D-1 是 P-062 D-2「静默跳过」家族的新向量（删除而非损坏），修法机械（对称检查），建议 **P-068 修复批**（P-066 由[缺陷复核报告](arc-g2-m5-defect-reverification-20261111.md)占用、P-067 由其报告复核占用）与 O-1/O-2（报告透传 verdict + claims 溯源）一并落实。
- **社区先例**：九条锚点全部回源，P-064 方案形态与 OPA/Terraform/Argo CD/Percona/Git/Nix 的成熟实践一致；退出码顺序与 Terraform 相反而与 pytest 一致，建议在 DESIGN 注明（O-6）。
