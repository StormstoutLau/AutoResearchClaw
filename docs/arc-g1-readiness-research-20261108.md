---
id: arc-g1-readiness-research-20261108
type: design
version: 0.1
status: draft
date: 2026-11-08
depends: [arc-master-roadmap, arc-roadmap-verdict-IMPLEMENTATION]
upstream: arc-master-roadmap
---

# G-1 开工前补充调研：H-1..H-8 测试方案与 Q18/Q19/Q20 裁决建议

> **范围**：总纲 §7 的 Q18/Q19/Q20，以及 §4 G-1 的 H-1..H-8（绑定 v0.4 / `a7427ec`）。
> **方法**：逐项静态读码复核 + 外部锚点核验；**不改代码、不改总纲**。
> **结论**：H-1..H-8 全部成立，但其中 3 项的落点需要修正；Q18/Q19 可直接按建议裁决，Q20 的默认建议需要**修正**（不是合并字段）。

## 0. 取证矩阵

| 手段 | 覆盖项 | 结果 |
|---|---|---|
| 静态读码（E3） | 8 个 H 项的当前实现 | 8/8 复核；H-1/H-3/H-5 的落点与总纲表述有偏差 |
| `rg` 全仓检索（E1） | `safe_join` / `retrieval_degraded` / `StageAttempt` / `max_retries` 消费点 | 前三者零命中；`max_retries` 仅 LLM/CLI 层有消费 |
| 配置与入口（E2） | `config.py`、`server/app.py`、`runner.py`、`code_agent.py` | Q19/Q20 的字段语义已定 |
| 官方锚点（E4） | 12 项标准/文档 | 全部命中（§5） |

## 1. H-1..H-8 现状复核

| ID | 总纲断言 | 代码实测 | 判定 | 落点修正 |
|---|---|---|---|---|
| **H-1** | Stage 12 的 `run-1.json` 含 `returncode` | Stage 12 主路径在 `_execution.py:575-588` 内联写 payload，**无** `returncode`；agent 路径的 `_write_agent_run_payload()`（L151）**有** | 成立 | 缺的是**主路径**；两个 writer 应合并为一个纯函数 |
| **H-2** | 配置为 0 不重试、为 2 最多 3 次 | `contracts.py:25` 定义 `max_retries`，但 `executor.py`/`runner.py` 均无消费点；仅 LLM 客户端与 CLI bridge 有重试 | 成立 | 重试应包在 `execute_stage` 外层（stage 级），不是 LLM 级 |
| **H-3** | `ClaimVerifier` 在 Stage 20/23 被调用 | 类定义在 `hitl/claim_verifier.py:68`，全仓仅 `tests/test_hitl_verifier.py` 使用 | 成立 | 门禁报告需新增 `claim_verification` 段 |
| **H-4** | 降级时 `retrieval_degraded=true` | 全仓零命中；`_literature.py:203` 的 `except Exception` 静默跳过来源；L352 的 `silent_fallback` 只针对**模型计划**回退 | 成立 | 插入点在 `_literature.py` 的来源失败分支，不是模型计划分支 |
| **H-5** | `completed + rc≠0 → FAILED` | Stage 12 的 `run_status` 已用 `returncode`（L269/L550）；但 `_helpers.py:938 _collect_experiment_results` **不读** `status`/`returncode`，任何含 `metrics` 的 run 都被聚合 | 成立（更精确） | 真正缺口在**聚合层过滤**，不是 Stage 12 状态判定 |
| **H-6** | 子进程看不到密钥 | `sandbox.py:324`、`sandbox.py:425` 均为 `{**os.environ, ...}`；`mcp/client.py:69` 为 `env=dict(os.environ)` | 成立 | 需新增 allowlist builder，覆盖全部 3 处 |
| **H-7** | `safe_join()` 四类逃逸全拒 | 全仓无 `safe_join`；`_execution.py:1141-1144` 仍是裸 `target_dir / fname` | 成立 | 是**新增函数** + 全量替换写入点，不是修一个函数 |
| **H-8** | 非白名单 Origin 被拒、默认非 `*` | `config.py:748` 默认 `("*",)`；`server/app.py:84-87` 同时 `allow_credentials=True` | 成立 | 默认值 + 启动校验（`*` + credentials 直接拒绝） |

## 2. H-1..H-8 pytest 实施设计

### 2.1 统一约定

- 复用 `tests/conftest.py`；临时目录用 `tmp_path`，环境变量用 `monkeypatch.setenv/delenv`（pytest 官方语义）。
- 文件名沿用总纲 §5.1 已登记的名称；新测试全部走 `pytest -q`，不引入新依赖。
- 每项至少 1 正 1 反；负向用例必须是"去掉实现就变红"，与 A2-2 的变异测试精神一致。
- 平台标注：H-6 用 `python -c` 跨平台；H-7 的 symlink 用例在 Windows 需 `skipif`（无权限时）。

### 2.2 逐项测试矩阵

| ID | 测试文件 | 核心用例 | 负向用例 | 依赖的改动 |
|---|---|---|---|---|
| H-1 | `tests/test_stage12_returncode.py` | 抽出 `build_run_payload(...)` 后，`rc=1` → payload 含 `returncode=1` 与 `mode` | 删掉字段 → 断言失败 | 抽纯函数 + 主路径改用 |
| H-2 | `tests/test_stage_retries.py` | 桩 executor 连续失败 2 次后成功，`max_retries=2` → 调用 3 次；`=0` → 1 次 | 不消费配置 → 调用次数恒为 1 | `execute_stage` 外层重试循环 |
| H-3 | `tests/test_claim_verifier_wiring.py` | 构造含 claim 的 run_dir，Stage 20 的 `decision.json` 含 `claim_verification` 段 | 删调用 → 段缺失 | Stage 20/23 显式实例化 |
| H-4 | `tests/test_retrieval_degraded.py` | 桩来源抛异常 → `sources.json` 的 `retrieval_degraded=true` + `degraded_reason` | 静默跳过 → 字段缺失 | `_literature.py` 失败分支写标记 |
| H-5 | `tests/test_forged_execution_guards.py`（扩展现有 `test_fabrication_guards.py` 亦可） | 两个 run：`rc=0` 有 metrics、`rc=1` 有 metrics → 只聚合前者，后者进 `excluded_runs` | 聚合层不过滤 → 后者被计入 | `_collect_experiment_results` 增加过滤 |
| H-6 | `tests/test_env_allowlist.py` | `monkeypatch.setenv("OPENAI_API_KEY", "sk-x")` → 子进程 `python -c` 读不到 | 透传 `os.environ` → 读到 | allowlist builder + 3 处替换 |
| H-7 | `tests/test_safe_join.py` | `safe_join(base, "a/b.txt")` 允许；`../x`、绝对路径、symlink、`a/../../x` 全拒 | 裸 `base / name` → 逃逸成功 | 新增 `safe_join` + 替换写入点 |
| H-8 | `tests/test_cors_default.py` | 默认配置的 `allow_origins` 不含 `*`；非白名单 Origin 无 ACAO | 默认 `*` → 断言失败 | 默认值 + 启动校验 |

### 2.3 实施顺序（依赖关系）

```
H-1（payload 纯函数）
  └→ H-5（聚合层过滤，复用同一 payload 字段）
H-7（safe_join 工具）
  └→ H-6（allowlist builder 可复用路径校验风格）
H-2（stage 重试）→ 独立
H-3（ClaimVerifier 接线）→ 独立
H-4（检索降级）→ 独立
H-8（CORS 默认）→ 独立
```

- 先做 **H-1 + H-5**：两者共享 `returncode` 字段，且共同构成"伪造执行"证据链。
- 再做 **H-7 + H-6**：同属边界防护，可共用测试夹具。
- **H-2/H-3/H-4/H-8** 互不依赖，可并行。
- 全部完成后，C-9（H-1..H-5）与 C-4（H-6..H-8）的对应成员转绿。

### 2.4 验收

```bash
python -m pytest tests/test_stage12_returncode.py tests/test_stage_retries.py \
  tests/test_claim_verifier_wiring.py tests/test_retrieval_degraded.py \
  tests/test_forged_execution_guards.py tests/test_env_allowlist.py \
  tests/test_safe_join.py tests/test_cors_default.py -q
```

- 期望：8 个文件全部通过；每个文件至少 1 个负向用例；无网络依赖。
- 变异检查：逐项删除实现（或注释调用）后对应测试必须变红（人工抽查 2 项）。

## 3. Q18：vendor 供应链与语料 pin

### 3.1 三个方案

| 方案 | 做法 | 成本 | 收益 | 兼容 | 维护 | 升级 | 短期 | 长期 |
|---|---|---|---|---|---|---|---|---|
| **A. L1 清单** | 每个 vendor 记录 `repo/commit/license/sha256`；语料记录 `name/version/hash/license`（Croissant 四字段） | 低 | 高：可复现、可审计 | 零侵入 | 低 | 好 | 立即可做 | 稳定 |
| B. 全量 SBOM | 生成 SPDX/CycloneDX，接 CI | 中 | 中：多一层机器可读 | 需新工具链 | 中 | 好 | 慢 | 好但过重 |
| C. lockfile only | 只 pin 版本 | 极低 | 低：无 license/来源 | 零 | 低 | 差 | 快 | 不足 |

### 3.2 建议

> **Q18 = A**：`vendor/MANIFEST.yaml`（repo/commit/license/sha256）+ `corpus/MANIFEST.yaml`（四字段）；CI 用 `--check` 校验清单与实际文件哈希一致。**不引入完整 SBOM**（B 的收益抵不过工具链成本；C 缺 license/来源，无法支撑洁净室审查）。

### 3.3 锚点

- SLSA v1.0 Build L1：只需"存在可验证的 provenance"，与 A 的粒度一致。
- SPDX ISO/IEC 5962:2021：若未来需要升级到 SBOM，SPDX 是标准出口，当前不必落地。
- Croissant 1.1：语料元数据的四字段是它的最小子集。
- NIST SSDF PS.3：要求保留 provenance，A 满足。

## 4. Q19：API 默认认证收紧

### 4.1 三个方案

| 方案 | 做法 | 成本 | 收益 | 兼容 | 维护 | 升级 | 短期 | 长期 |
|---|---|---|---|---|---|---|---|---|
| **A. 回环默认 + 非回环强制 token** | `host` 默认 `127.0.0.1`；绑定非回环且 `auth_token==""` → 启动失败 | 低 | 高：默认安全、无需改本地工作流 | 本地零感知；部署需设 token | 低 | 好 | 快 | 稳定 |
| B. 始终要求 token | 任何绑定都强制 token | 中 | 高 | 破坏本地一键启动 | 低 | 好 | 慢 | 稳定 |
| C. 现状 + 文档 | 保持 `0.0.0.0` + 空 token | 零 | 无 | 零 | 低 | 差 | 快 | 风险累积 |

### 4.2 建议

> **Q19 = A**：`server.host` 默认 `127.0.0.1`；启动时若 `host` 非回环且 `auth_token` 为空 → fail-closed（拒绝启动并打印生成命令）。CORS 的 `*` + `allow_credentials=True` 组合同时改为启动校验失败（见 H-8）。

### 4.3 锚点

- OWASP API2:2023：认证缺失/实现不当是 API 首要风险。
- CWE-306：关键功能缺少认证。
- OWASP ASVS V2：认证验证要求。
- OWASP WSTG CORS：`*` 与反射 Origin 均属不安全配置。

## 5. Q20：预算字段统一（建议修正总纲默认）

### 5.1 关键事实

- `hitl.cost_budget_usd` 默认 **0 = 不限**（`hitl/config.py:92`），由 `CostGuard` 在 executor 使用。
- `experiment.cli_agent.max_budget_usd` 默认 **5.0**（`config.py:588`），被 **runner 当作整条流水线预算**（`runner.py:482`），同时被 **传给 Claude Code CLI 的 `--max-budget-usd`**（`code_agent.py:579-580`）。
- 预算检查发生在 **每个 stage 之前**（`runner.py:513`），单 stage 内的多次 LLM 调用不受约束；`LLMClient.chat()` 发送前无检查。

**结论**：这不是"同一个概念的两个名字"，而是**两个不同作用域**（run 级 vs 单次 CLI 子进程）被混用。直接合并会删除 CLI 子进程的上限。

### 5.2 三个方案

| 方案 | 做法 | 成本 | 收益 | 兼容 | 维护 | 升级 | 短期 | 长期 |
|---|---|---|---|---|---|---|---|---|
| **A. 分层账本** | `run_budget_usd`（run 级，唯一账本）+ `cli_agent.max_budget_usd`（派生上限 = min(配置, 剩余 run 预算)）；`LLMClient.chat` 前置检查 | 中 | 高：不误伤 CLI 语义，逐调用可拦 | 需改配置名/兼容别名 | 中 | 好 | 中 | 优 |
| B. 合并为单字段 | 只留 `cost_budget_usd` | 低 | 中 | 破坏 CLI 上限 | 低 | 差 | 快 | 差 |
| C. 保持现状 + 文档 | 两字段各自为政 | 零 | 低 | 零 | 低 | 差 | 快 | 风险累积 |

### 5.3 建议

> **Q20 = A（修正总纲默认建议）**：不合并字段，而是**明确作用域**——`run_budget_usd` 为唯一 run 账本（默认 0 不限，但启动打印 `budget_unset` 警告；CI 设 `ARC_REQUIRE_BUDGET=1` 时缺失即失败），`cli_agent.max_budget_usd` 降为**单次 CLI 调用的派生上限**；`LLMClient.chat()` 在发送前检查剩余预算，超限返回 `budget_exhausted` 而非先调用后拒绝。

### 5.4 锚点

- FrugalGPT：成本约束应在调用前决定（级联/预算），与本方案的前置检查一致。
- AWS REL05-BP03：限制重试次数与退避，避免预算被重试放大。
- 内部事实：`runner.py:513` 为阶段级检查、`client.py:320` 仅记账，二者共同证明前置检查缺失。

## 6. 外部锚点清单（12 项）

| # | 锚点 | 用途 | 来源 |
|---|---|---|---|
| E-1 | SLSA v1.0 Build L1（provenance） | Q18 粒度 | <https://slsa.dev/spec/v1.0/levels> |
| E-2 | SPDX / ISO IEC 5962:2021 | Q18 升级出口 | <https://spdx.dev/faq/> |
| E-3 | Croissant 1.1 | 语料四字段 | <https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html> |
| E-4 | OWASP API2:2023 Broken Authentication | Q19 | <https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/> |
| E-5 | CWE-306 Missing Authentication | Q19 负向判据 | <https://cwe.mitre.org/data/definitions/306.html> |
| E-6 | OWASP ASVS V2 Authentication | Q19 验收 | <https://wiki.owasp.org/index.php/OWASP_Application_Security_Verification_Standard> |
| E-7 | OWASP WSTG CORS | H-8 | <https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/11-Client-side_Testing/07-Testing_Cross_Origin_Resource_Sharing> |
| E-8 | CWE-526 环境变量中的敏感信息 | H-6 | <https://cwe.mitre.org/data/definitions/526.html> |
| E-9 | CWE-22 路径遍历 | H-7 | <https://cwe.mitre.org/data/definitions/22.html> |
| E-10 | AWS REL05-BP03（限重试+退避） | H-2 | <https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html> |
| E-11 | FrugalGPT | Q20 | <https://arxiv.org/abs/2305.05176> |
| E-12 | pytest（monkeypatch/tmp_path） | H 测试写法 | <https://docs.pytest.org/en/stable/how-to/monkeypatch.html> |

## 7. 总结建议

| 项 | 建议 | 需修正总纲默认 |
|---|---|---|
| Q18 | A：L1 清单 + Croissant 四字段 | 否（与默认一致） |
| Q19 | A：回环默认 + 非回环强制 token | 否（与默认一致） |
| Q20 | **A′：分层账本（run 级 + CLI 派生上限）** | **是**（默认建议"合并为单字段"会误删 CLI 上限） |
| H-1..H-8 | 按 §2 顺序，先 H-1/H-5，再 H-7/H-6 | 否 |

**下一步**：Q18/Q19 可直接裁决；Q20 需按 A′ 修正 §7 的建议文本；H-1..H-8 的 pytest 与实现应在同一批次落地（测试先行，避免"测试绿但实现缺"的假象）。
