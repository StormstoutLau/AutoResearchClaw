# P-160 G7 soak 工具链 异构复审报告（2026-11-25）

> **性质**：Layer-0 独立异构复审（T3，零代码/零门禁变更）。纪律同 P-020/P-023/P-030/P-062——不采信 [IMPLEMENTATION](../spec/arc-g7-soak/IMPLEMENTATION.md)/[CHECKLIST](../spec/arc-g7-soak/CHECKLIST.md) 结论，全部以探针、读码、机检一手重验。
> **异构声明（RULE-5）**：本复审由 GLM-5.3-Flash 独立会话执行，实施批 P-160 由 DeepSeek-V4.1-Flash 完成——模型家族异构；reviewer 只标记问题、不改写实现（单向权限）。
> **对象**：P-160 G7 第一段 soak 工具链（[spec/arc-g7-soak/](../spec/arc-g7-soak/)，merge commit `c4e673e`，PR #42）。工作树状态：干净（main @ `c4e673e`）。
> **探针**：`%TEMP%\p161_review_probe.py`、`%TEMP%\p161_review_probe2.py`（全部临时目录，零仓库变异；首轮探针自身预期算错两处，已用 v2 修正版复核，见 T-3 注记）。

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | 测试读数：soak 27 + 边界 17 + event_log（含 roll_recovery 3）= 58 passed（11.63s） | 本轮实跑 | ✅ 与 P-160 记载一致 |
| T-2 | F-1：轮转边界后 active 缺失，重开从归档段末行恢复 `last_seq/last_hash`；gz 归档同样可恢复且续写不断链 | 探针 P-5（gz + active 双层，append seq 续接、`verify_chain` ok） | ✅ |
| T-3 | F-1b：torn tail 截断与轮转**组合**边界——active 有效行保留、坏尾丢弃、`events.jsonl.tmp` 无残留、append 续 seq、全链可验 | 探针 P-1v2（该组合场景 P-160 测试未覆盖，本探针补证成立；首轮探针 FAIL 为探针自身预期错误，非产品缺陷） | ✅ |
| T-4 | F-2：归档-only checkpoint 恢复（`recovered=true`、下一阶段正确） | 测试 T09 复跑 | ✅ |
| T-5 | F-4：checkpoint 原子替换对瞬时 `PermissionError` 重试、无 `.tmp` 残留 | 测试 T19 复跑 | ✅ |
| T-6 | 驱动行为：3 次硬杀收敛且与 baseline 终态签名相等（T10）、预算硬上限 `capped`（T11）、rc=65 不重启（T12）、活租约不被抢（T22）、超时不伪收敛（T21） | 测试复跑 | ✅ |
| T-7 | P-160 session finalize `evidence_digest` 四文件 sha256 与合并后内容逐字节一致（CRLF 规范化） | 探针 P-4 | ✅ |
| T-8 | CHECKLIST §10.1 算术：8 行 `4+9+8+10+7+3+3+4=48`，通过列和 47，`48=47+0+1` 成立；逐项状态与 §2–§7 标记一致 | 逐项核对（RULE-2） | ✅ |
| T-9 | IMPLEMENTATION 文件清单与 merge commit `c4e673e` stat 一致（4 soak 模块 + 3 修改 + 4 测试 + 边界登记 + 派生视图） | `git show --stat` | ✅ 计数零幻觉 |
| T-10 | 全门禁重跑：pre-commit 10/10（dc/grandfather/stats/console/blackbox/private/wiring/rework/coverage/step_enforce） | 本轮实跑 | ✅ |
| T-11 | CI 两轮 8/8（runs 45438699406 / 45439585673，Tests 3.11–3.14 + Spec gates + Roadmap + Packaging + Extras） | `gh pr checks 42` | ✅ 与 PROGRESS 记载一致 |
| T-12 | P-160 session 决策链 step-gate 5/5 pass | 本批复跑 | ✅ |

## 2. 缺陷（D 表）

### D-1（P2）retention 逃生舱结构性不可达：`allow_retention_gap=True` 仍不可能收敛

- **证据**：探针 **P-2v2**——构造含 checkpoint + summary 的 run，删除最旧归档段（模拟 365 天删除）后：`verify_run` 默认判 `retention_limited` ✅；但 `allow_retention_gap=True` 时 `problems` 仍含 `chain:seq gap at 2 (expected 1)`，`chain_ok=False`，`converged=False`。根因：[event_log.py](../researchclaw/runtime/event_log.py) `verify_chain` 固定从 `expect_seq=1` 起校验（`L336-344`），保留删除后首个可读事件 seq>1 ⇒ `chain_ok` **结构性恒 False**；而 [verifier.py](../researchclaw/soak/verifier.py) `integrity_ok` 要求 `chain_ok`（`L292-296`）——逃生舱是**必要非充分**。旁证：EventLog docstring（P-040 O-1）早已声明「归档删除后链仅部分可验」。
- **影响**：[DESIGN §4.4](../spec/arc-g7-soak/DESIGN.md)「保留删除」行声明 `retention_limited=true（72h 默认视为失败，除非显式 allow_retention_gap=True）`——隐含逃生舱可产生可用验证，实现达不到。72h soak 本身不受影响（<30 天保留期），但 A7-4 的「归档后缺口」负向面与**跨 30 天的历史 run 复核**（如 72h 现场报告留证 30 天后复核）会永久误红。
- **附带**：该整行检查零测试覆盖（`allow_retention_gap`/`retention_limited` 在 `tests/test_soak_*.py` grep 0 命中）——设计元素无测试（ADD Phase-1）。
- **修法**：`verify_chain` 增加起点偏移（`expect_seq` 从 `read_all()` 首事件 seq 起，逐行仍校验 prev/payload 连续），或 verifier 在 `first_seq>1` 时以「起点偏移链 + `payload_sha256` 逐行」替代整链断言；补 2 用例（默认红 + 逃生舱绿）。

### D-2（P2）POSIX 注入不杀进程树，与 DESIGN「硬杀进程树」自相矛盾

- **证据**：[driver.py](../researchclaw/soak/driver.py) `_default_kill`（`L69-78`）POSIX 分支 `proc.kill()` 仅杀直接子进程；[DESIGN §4.1](../spec/arc-g7-soak/DESIGN.md) 步 2 自称「硬杀进程树（Windows taskkill /F /T /PID，POSIX proc.kill()）」——「进程树」与「proc.kill()」在 POSIX 上矛盾（E3 @`c4e673e`）。
- **影响**：72h 现场若在 POSIX 主机执行，真实 worker（`python -m researchclaw run`）派生的孙进程（LLM CLI、沙箱子进程）被孤儿化后可继续运行，并在 driver 重启新 worker 拿到租约后**继续写 stage 产物**——事件日志单写者不受影响（租约随死进程可回收），但产物双写正是 A7-2 要隔离的面。CI（Linux）fake worker 无孙进程，测试不暴露。
- **修法**：POSIX spawn 加 `start_new_session=True` + `os.killpg(os.getpgid(pid), SIGKILL)`；或 DESIGN 明示 field run 仅限 Windows 并把 POSIX 进程树隔离登记为 A7-2（多 run 并发段）的前置输入。

### D-3（P3）死代码/死变量三处（Phase-3 必要性：无设计依据的行为）

- **证据**（E3 读码 @`c4e673e`）：① [driver.py](../researchclaw/soak/driver.py) `run()` 对 `cfg.run_dir.is_dir()` 做了**两次相同早退**（`L184-187` 与 `L201-204`，中间夹 `driver_started` 记录）——第二次不可达；② `killed = False`（`L250`）为 refactor 至 `action` 后的死变量；③ `_progress()` 返回的 mtime 在所有调用点被 `_mtime` 丢弃，若为恢复耗时口径预留，DESIGN §4.2 未声明。
- **影响**：仅可读性与审计噪声，无行为错误。
- **修法**：删除重复检查与死变量；mtime 或删或补设计声明。

## 3. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | `cursor_mismatch` 探针在静态日志上按构造恒等（cursor 与 expected 同源 `read_all`），真实价值仅是**检出验证期间的并发追加/改写**；DESIGN §4.4 未声明此弱点，测试断言因此偏弱但非恒真（并发下可红） | 实现注记 |
| O-2 | `EventLog.count` 语义由「active 可读行数」变为「历史最高 seq」（P-160 改动，源码注释声明动机=重启后配额不重置）；生产代码零消费点（grep 0 命中，E1），行为安全；但语义变化未在四文档登记 | 语义注记 |
| O-3 | 对已完成 run（checkpoint=total）指定小于终态的 `inject_at_stages` 时，注入发生在驱动首个 poll——实际杀点=终态阶段而非目标阶段，「阶段 X 注入」语义在已完成 run 上漂移；`stage_after`/`recovery_seconds` 记录仍自洽 | 语义注记 |
| O-4 | specwf-p160 session 的 ts 为补写时的估计值（非逐事件实时落盘），CONSOLE 时间线排序可能失真；finalize digest 与合并内容一致（T-7 已验），影响仅限显示 | 数据卫生 |
| O-5 | CLI `soak run --inject-at-stages` 默认 `"3,7,11"` 是破坏性默认（默认即注入硬杀）；RESEARCH/DESIGN 声明了注入计划但 CLI 默认值未在文档明示 | 文档 |

## 4. 结论

- **P-160 三条主线成立**：soak 工具链（driver/verifier/report/CLI）、四项写入边界修复（F-1/F-1b/F-2/F-4）、A7-4 轮转后回放——T-1..T-12 全部一手复现，文档计数零幻觉，session digest 绑定一致。
- **三项缺陷登记**：D-1（P2，retention 逃生舱不可达 + 零测试）、D-2（P2，POSIX 进程树与设计表述矛盾）、D-3（P3，死代码）。均有机械修法、无需改架构。
- **处置建议**：**P-162 修复批**落实 D-1..D-3（作为 G7 第二段「并发/编排评测」开工前置或并行均可）；O-1..O-5 随修或存档。
- **边界维持**：A7-4 交付状态维持「轮转后回放 ✅」；**「保留删除后回放」在 D-1 修复前不得宣称可用**；72h 现场运行（U-1）与 A7-2/A7-3/A7-5..7、FA、OB 仍不在本批范围。
