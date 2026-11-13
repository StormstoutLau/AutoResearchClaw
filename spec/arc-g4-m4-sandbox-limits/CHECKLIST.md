# 审查验收清单：G4-M4 沙箱配额 / TTL / 137 / 四类逃逸

---
id: arc-g4-m4-sandbox-limits-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-13
depends: [arc-g4-m4-sandbox-limits-IMPLEMENTATION, arc-g4-m4-sandbox-limits-DESIGN]
upstream: arc-g4-m4-sandbox-limits-IMPLEMENTATION
---

> **Feature**: arc-g4-m4-sandbox-limits（P-105，G4-M4）
> **创建日期**: 2026-11-13
> **状态**: verified
> **Spec 步骤**: Step 7-8 + Step 10 取证矩阵

---

## 1. 验收原则

- 每项可测试、有明确通过条件；禁止无证据的 ✅（Step 10 取证矩阵 §8 绑定 E1-E5）。
- 测试通过 ≠ 设计落地（ADD Iron Law）：除测试外核对冻结语义逐条落地。

## 2. 验收清单（DoR / DoD）

| # | 验收项 | DoR | DoD | 结果 |
|---|--------|-----|-----|------|
| C-1 | T-1..T-16 全绿 | test_sandbox_boundary.py 存在 | 先红记录 + 全绿输出 | ✅ 先红 5 failed+12 errors → **19 passed**（收敛批后；原 17 + T-15/T-16） |
| C-2 | 既有 36 项零回退 | test_rc_docker_sandbox.py 可跑 | 36/36 + 新断言通过 | ✅ 既有 **36 全绿** + 新增 **9** 断言 → **45 passed**（审计订正：`git show` 计新增 `def test_` = 9） |
| C-3 | 配额默认生效 | 代码落盘 | 命令含 --cpus/--pids-limit/--memory + rc.run 标签；无 --rm | ✅ T-1/T-2/T-3/T-4 + test_rc 新 5 断言 |
| C-4 | 137 归因诚实 | _inspect_container 落盘 | OOMKilled→resource_limit；不可解析→None；137 为兜底（自愿 `exit(137)` 亦归 resource_limit，D-4 登记） | ✅ T-5/T-6/T-11/T-14 + inspect 解析 3 用例 + `_attribute_limit` 优先级 6 断言；措辞已按复核 D-4 降级 |
| C-5 | TTL TERM→grace→KILL | _TtlWatcher 落盘 | TERM→SIGKILL 双断言 + limit_reason=ttl_timeout | ✅ T-10（真线程，首条 TERM、次条 SIGKILL）+ T-8（ttl_timeout + 显式 TTL 被子预算抬升的反向断言 `_ttl == 0.3`）；恒真断言已删 |
| C-6 | TTL 线程生命周期 | run()/run_project() 落盘 | 返回后 stop+join、无残留线程 | ✅ T-9（is_alive False + stop 置位）+ T-10（仅本容器名） |
| C-7 | harness 信号兜底 | harness_template 落盘 | SIGTERM→finalize→exit 143；atexit 注册；幂等 | ✅ T-13 源码断言 + e2e Test 9 行为取证（results.json 宽限期内落盘） |
| C-8 | run_id 传递 | stage-14 调用点 | 主执行/两处重跑/ExperimentRunner 传 run_id；repair/agent 4 点显式登记 | ✅ **5/9 live 调用点**传 run_id（IMPLEMENTATION §5.4 全枚举；收敛批补 `:1770` 与 `runner.py:131`） |
| C-9 | config 解析 | _parse_experiment_config | 5 字段 + 坏值回退默认 | ✅ T-12 正反两用例 |
| C-10 | CI 固定清单 | ci.yml | test_sandbox_boundary.py + test_rc_docker_sandbox.py 入清单 | ✅ ci.yml contract tests 清单 +2 |
| C-11 | 五套件回归 | 全仓测试可跑 | 全绿（3.13.5；3.11.15 兼容面跑单测子集） | ✅ 五套件 **130 passed**；CI 全清单 43 文件 **687 passed / 13 skipped 零失败**（3.13.5；3.11 兼容面为既有纪律，本批语法面无新特性依赖） |
| C-12 | wheel 三连 | build 后端可用 | build/wheel/install 三连成功 | ✅ python -m build wheel+sdist → 新 venv 装 wheel 探针 `DockerSandboxConfig` 新字段与 `_attribute_limit` 可用 |
| C-13 | e2e 证据层 | 本地 Docker daemon | 四类逃逸/OOM/TTL 场景取证（quarantine 登记，见 §4） | ✅ **22 passed / 0 failed**（slim 证据镜像 python3.11-slim+numpy，非生产镜像如实登记；OOM 137→resource_limit、TTL→results.json 落盘、fork bomb 受限、symlink 双分支、network none、零容器残留） |
| C-14 | 冻结语义回边 | M0 §6/§9 | DESIGN 回边 + P-099 session 记录 rebind | ✅ M0 DESIGN §6 M4 落地状态块 + §9 M4 行（本批受控回边；P-099 session 不动——M0 批次 session 归 M0 批，状态以 DESIGN 回边为准） |
| C-15 | 文档链 | PROGRESS/roadmap | P-105 行 + v1.4r + 9 门禁全绿 | ✅ PROGRESS P-105 + roadmap v1.4r；9 门禁见提交时 pre-commit 输出 |
| C-16 | 不变式核对 | DESIGN §8 | I-M4-1..7 逐条有证据 | ✅ I-M4-1（`_attribute_limit` 唯一实现，映射 6 断言）；I-M4-2（T-4）；I-M4-3（T-10）；I-M4-4（T-11/T-16）；I-M4-5（e2e Test 9 + finalize 覆盖写）；I-M4-6（36 项零回退）；I-M4-7（network 默认未动 + T-6 CI 清单无回退） |
| C-17 | ttl_timeout 不可伪造（D-2） | `_TtlWatcher._fire` 落盘 | TERM 投递成功才置 `_fired`；deadline 锚定容器创建 | ✅ T-16（kill 抛 `FileNotFoundError` → `fired is False` 且 `limit_reason is None`） |
| C-18 | 长跑不被 TTL 截断（D-3） | `_effective_ttl` 落盘 | `ttl_sec=0（auto）, timeout_sec=7200` → 有效 TTL ≥ 7200；显式 `ttl_sec>0` 仍为硬上限 | ✅ T-15（默认跟随预算）+ T-8（显式 0.3 不被抬升）；DESIGN §4.3 有效 TTL 定义 |

## 3. 一致性 Review（Step 8）

- [x] RESEARCH F-1..F-13 ↔ DESIGN D-1..D-6：每条决策有发现支撑
- [x] DESIGN §4 接口 ↔ IMPLEMENTATION §5：签名一致（run_id/ttl 字段/映射）
- [x] IMPLEMENTATION §6 测试计划 ↔ CHECKLIST §2：T-1..T-16 ↔ C-1..C-18 对齐
- [x] 术语一致：limit_reason 三值 + None；「验收层/证据层」与 D-Q4 拆分同义

## 4. RULE-3 quarantine 登记（e2e 证据层）

| 要素 | 登记 |
|------|------|
| 事项 | 四类逃逸/OOM/TTL 的本地 Docker e2e 取证（tests/e2e_docker_sandbox.py 扩展场景） |
| Owner | P-105 实施方（GLM-5.3-Flash） |
| Deadline | G4 收尾批（P-10x 里程碑末）前完成复跑并更新证据 |
| 降权 | 每次实施批运行一次并记录输出（不阻塞 CI 结论；CI 无 Docker） |
| Re-qualification | CI runner 具备 Docker 后：场景转 pytest 化入 CI 固定清单并解除 quarantine |
| 单测替代（验收层） | T-1..T-16 全 mock 覆盖命令/解析/状态机/时序，本项不构成 skip（测试真实运行） |

## 5. 风险确认

- [x] 默认 --cpus=2.0/--pids-limit=512 行为变更已在 DESIGN §4.3 登记
- [x] SIGKILL 分支不宣称产物落盘（P-100 D-4）
- [x] cpus throttling 不误判 137（P-100 D-3）
- [x] 不伪造 tool.call/tool.result 事件（M3 orphan 扫描边界）

## 6. 退出判据

全部 ⬜ → ✅（带证据指针）+ §3 一致性全勾 + §5 风险确认全勾 + 9 门禁全绿 ⇒ P-105 可提交。

**状态（2026-11-13，收敛批后）**：C-1..C-18 全 ✅、§3/§5 全勾；收敛批对应复核 D-1/D-2/D-3/D-5 与审计 F-1..F-4 订正，复跑 `test_sandbox_boundary.py` 19 + `test_rc_docker_sandbox.py` 45 = **64 passed**，e2e **22 passed / 0 failed**（TTL 8s→TERM→results.json 落盘→`ttl_timeout`），9 门禁见提交时 pre-commit 输出。

---

**Review 签字**: GLM-5.3-Flash（实施会话自审） 日期: 2026-11-13
