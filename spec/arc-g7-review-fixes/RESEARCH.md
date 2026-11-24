---
id: arc-g7-review-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-soak-review-20261125, arc-g7-orchestration-review-20261125, arc-g7-soak-DESIGN, arc-g7-orchestration-DESIGN]
upstream: arc-master-roadmap
---

# 调研：G7 复审修复批（P-164）

> **批次定位**：把 P-161 登记的 D-1..D-3（soak）与 P-163 登记的 D-1（编排）合并为一个独立修复批；只修缺陷、补回归测试，不新增能力、不改门禁。
> **不做**：A7-2/A7-3/A7-5..7、FA、OB 新能力；P-161/P-163 的 O 表观察项不强制承接。

## 1. 修复对象（一手证据）

| 编号 | 来源 | 缺陷 | 代码锚点 @4e9e853 |
|---|---|---|---|
| D-1 | P-161 | retention 逃生舱不可达：删除最旧归档段后，`allow_retention_gap=True` 仍因 `verify_chain` 固定从 seq=1 起校验而 `chain_ok=False` | [event_log.py L409-L438](../../researchclaw/runtime/event_log.py#L409-L438)、[verifier.py L216-L229](../../researchclaw/soak/verifier.py#L216-L229)、[L256-L260](../../researchclaw/soak/verifier.py#L256-L260) |
| D-2 | P-161 | POSIX 注入仅 `proc.kill()`，不杀进程树，与 DESIGN J-9「硬杀进程树」矛盾 | [driver.py L73-L81](../../researchclaw/soak/driver.py#L73-L81) |
| D-3 | P-161 | 死代码三处：重复 `run_dir.is_dir()`、`killed=False`、`_progress()` 的 mtime 全被丢弃 | [driver.py L184-L204](../../researchclaw/soak/driver.py#L184-L204)、[L250](../../researchclaw/soak/driver.py#L250)、[L116-L129](../../researchclaw/soak/driver.py#L116-L129) |
| D-4 | P-163 | 真实预算溢出零工件：`ThreadedAdapter.start` 的 `BudgetExceeded` 分支只改状态，五件套全缺，judge 报 missing_files 而非 `usage.exceeded` | [adapters.py L127-L130](../../experiments/arc_bench/orchestration/adapters.py#L127-L130) |

## 2. 复现探针（E2/E3）

| 探针 | 结论 |
|---|---|
| PR-2v2（P-161） | 删最旧归档段后：默认 `retention_limited` ✅；`allow_retention_gap=True` 仍 `chain:seq gap at 2 (expected 1)`、`converged=False` |
| PR-1（P-163） | gold × D1 × `Budget(tokens=300)`：`status=budget_exceeded`，workdir **0 文件**，judge `missing_files=5` |
| PR-2（P-163） | `max_workers=2`（层宽 3）：同样零工件 |
| PR-10（P-163） | `over_budget` fixture 先写五件套再抛 → judge 可读；证明缺口在通用异常路径，不在 fixture |
| 本批复核 | `runner` 的 `BudgetExceeded` 分支与 `_execute` 写入顺序逐行确认；`_progress` 两处调用均丢弃第二返回值 |

## 3. 外部依据（T1/T2）

| 来源 | 机制 | 借用 |
|---|---|---|
| POSIX `setsid`/进程组语义（POSIX.1；Python `subprocess.Popen(start_new_session=True)` 文档） | 子进程成为新会话/进程组组长，`killpg(pgid, SIGKILL)` 可终止整组 | D-2 的进程树硬杀 |
| 哈希链偏移校验（本仓 `EventLog` 既有语义 + P-040 O-1） | 删除前缀后，首可读事件的 `prev_sha256` 不可验；其后每条 `prev/payload` 仍可验 | D-1 只跳过首条 prev 指针，不跳过 payload 与后续链 |
| P-161/P-163 复审报告（T1 内部） | 缺陷、探针、修法建议 | 修复范围与验收判据 |

## 4. 未决项（四元块）

- **U-1 偏移链是否削弱篡改检测**
  - 判据：偏移模式下首条 payload 篡改、后续 prev 篡改、中段 seq 缺口三类仍判红
  - 触发条件：Step 3 设计时
  - 当前倾向：只跳过首条 `prev_sha256` 指针；payload 与后续链全验；首条 `prev` 为 `ZERO_HASH` 视为伪造
  - 证据等级：E3

- **U-2 POSIX killpg 的误杀边界**
  - 判据：只有 `getpgid(pid)==pid`（本批 spawn 起的新会话组长）才 killpg；否则回退 `proc.kill()`
  - 触发条件：Step 3 设计时
  - 当前倾向：`start_new_session=True` + 组长守卫；注入自定义 spawn 时安全回退
  - 证据等级：E1（Python 文档 + 本仓测试注入面）

- **U-3 预算失败工件的最小形态**
  - 判据：五件套可解析、`usage.exceeded=true/truncated=false/status=budget_exceeded`、usage 与 trace token 自洽、aggregation=0 仍门控
  - 触发条件：Step 3 设计时
  - 当前倾向：只在文件缺失时合成；fixture 已写工件不覆盖
  - 证据等级：E2（PR-1/PR-10）

## 5. Review（Step 2，自查·单视角）

- [x] 四条缺陷均有代码锚点 + 探针；无“听说”级断言。
- [x] 外部依据为 POSIX/Python 官方文档，非社区转述。
- [x] 未把 O 表观察项混入修复范围。
- [x] U-1..U-3 已转 DESIGN 决策，未写成已实现。

## 6. 参考文献

1. Python Software Foundation. *subprocess — Popen `start_new_session`*. https://docs.python.org/3/library/subprocess.html
2. IEEE Std 1003.1 (POSIX.1), `setsid()`, `killpg()`, process group semantics.
3. P-161 复审报告：[docs/arc-g7-soak-review-20261125.md](../../docs/arc-g7-soak-review-20261125.md)
4. P-163 复审报告：[docs/arc-g7-orchestration-review-20261125.md](../../docs/arc-g7-orchestration-review-20261125.md)
