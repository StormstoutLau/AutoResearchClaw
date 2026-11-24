---
id: arc-g7-review-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-review-fixes-RESEARCH, arc-g7-soak-DESIGN, arc-g7-orchestration-DESIGN]
upstream: arc-master-roadmap
---

# 设计：G7 复审修复批（P-164）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **范围**：P-161 D-1/D-2/D-3 + P-163 D-1 四项缺陷；不新增能力、不改门禁/CLI/schema。
> **原则**：最小修法；正常路径行为不变；负向面必须由测试锁定。

## 1. 决策

| 编号 | 决策 | 被拒绝的替代方案 | 拒绝理由 / 代价 |
|---|---|---|---|
| D-1 | `EventLog.verify_chain(start_seq: int = 1)` 增加偏移起点；`start_seq>1` 时只跳过**首条** `prev_sha256` 指针，仍校验 seq 连续、首条 payload、后续 prev/payload；首条 `prev_sha256==ZERO_HASH` 判伪造 | ① verifier 内重写一套哈希校验；② 直接以 `min(seq)` 起校验且不检查零 prev | ① 哈希逻辑双实现会漂移，违反单一真值源；② 会接受「伪造 seq>1 + 零 prev」的坏日志。代价：偏移模式首条 prev 不可验，需在 `chain_message` 明示 |
| D-2 | POSIX spawn 加 `start_new_session=True`；kill 时仅当 `os.getpgid(pid)==pid` 才 `os.killpg(pgid, SIGKILL)`，否则回退 `proc.kill()` | ① 无条件 `killpg`；② 只改文档把 field run 限制在 Windows | ① 自定义 spawn（测试/嵌入方）未建新会话时可能杀掉 driver 自身进程组；② 孤儿孙进程风险仍在，A7-2 前不能留。代价：需要两个可注入小助手以便在 Windows 上做单测 |
| D-3 | 删除重复 `run_dir.is_dir()` 早退、`killed=False`；`_progress()` 只返回 stage | 保留 mtime 作“恢复耗时预留” | DESIGN §4.2 未声明该口径，保留即无依据行为（ADD Phase-3）。代价：若未来需要 mtime，需重新引入并补设计 |
| D-4 | `ThreadedAdapter.start` 捕获 `BudgetExceeded` 后调用 `_write_budget_failure`：**仅在文件缺失时**合成五件套；trace 一条 `budget.rejected` span 与 usage token 自洽；`status=budget_exceeded`、`exceeded=true`、`truncated=false` | ① 由 runner 合成；② judge 把 missing 直接当 OB-4 失败；③ 只修 `over_budget` fixture | ① 工件契约属适配器，runner 不应知道内部；② 会把“缺工件”与“超预算未截断”混为一谈，削弱判据；③ fixture 已能读，真实路径仍坏。代价：多一个 60 行助手 |
| D-5 | 先写红测试再改实现；不新增依赖、不改 gate/CLI/schema | 先改实现后补测 | 违反 TDD 双要素（无失败记录）。代价：一次红→绿往返 |

## 2. 修法细节

### 2.1 D-1：偏移链

```python
def verify_chain(self, start_seq: int = 1) -> tuple[bool, str]:
    start = max(1, int(start_seq))
    offset = start > 1
    prev: str | None = None
    expect = start
    events = self.read_all()
    for index, event in enumerate(events):
        if int(event.get("seq", -1)) != expect:
            return False, "seq gap at %r (expected %d)" % (event.get("seq"), expect)
        if offset and index == 0:
            if event.get("prev_sha256") == ZERO_HASH:
                return False, "offset chain starts with zero prev_sha256"
        elif event.get("prev_sha256") != prev:
            return False, "prev_sha256 mismatch at seq %d" % expect
        if event.get("payload_sha256") != _sha256(canonical_json(event.get("payload", {}))):
            return False, "payload_sha256 mismatch at seq %d" % expect
        prev = _sha256(canonical_json(event))
        expect += 1
    ok, msg = self._verify_summary_tail(events, prev or ZERO_HASH)
    if not ok:
        return False, msg
    label = "ok (%d events%s)" % (
        len(events), ", offset from seq %d" % start if offset else "")
    return True, label
```

`verify_run` 调整顺序：先 `read_all` 与 `first_seq`，再 `verify_chain(start_seq=first_seq or 1)`；异常仍落 `archive_unreadable`。`retention_limited` 与 `integrity_ok` 逻辑不变。

### 2.2 D-2：进程树

```python
def _spawn_kwargs(os_name: str | None = None) -> dict:
    return {} if (os_name or os.name) == "nt" else {"start_new_session": True}

def _posix_kill_tree(proc, *, getpgid=None, killpg=None, kill=None) -> str:
    getpgid = getpgid or os.getpgid
    killpg = killpg or os.killpg
    kill = kill or proc.kill
    try:
        pgid = getpgid(proc.pid)
    except OSError:
        kill(); return "process"
    if pgid == proc.pid:
        try:
            killpg(pgid, signal.SIGKILL); return "group"
        except OSError:
            pass
    kill(); return "process"

def _default_spawn(cmd, **kwargs):
    return subprocess.Popen(cmd, **{**_spawn_kwargs(), **kwargs})

def _default_kill(proc) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], ...)
    else:
        _posix_kill_tree(proc)
```

### 2.3 D-3：死代码

- 删除 `run()` 中第二段 `if not cfg.run_dir.is_dir():` 早退。
- 删除 `killed = False`。
- `_progress() -> int`；两处调用改为 `stage = self._progress()`；删除 mtime 读取。

### 2.4 D-4：预算失败工件

`_write_budget_failure(task, workdir, exc)`：
- 若五件套已全存在 → 直接返回（fixture 不被覆盖）。
- `tokens = int(exc.observed) if exc.kind == "tokens" else 0`。
- 缺失项写最小合法结构：plan（nodes=[]）、delegations（[]）、aggregate（rows/invalid/conflicts/summary 空）、trace（一条 `budget.rejected` span，`tokens_in=tokens`）、usage（`prompt_tokens=tokens`、`charged_tokens=tokens`、`exceeded=true`、`truncated=false`、`status="budget_exceeded"`、budget 快照）。
- 只写缺失文件；已存在文件一律不动。

judge 路径预期：五件套可读 → `checks.ob4_budget_state_ok=true`、`usage_matches_trace=true`、`aggregation=0` → `total=0`（既有门控）。

## 3. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | `start_seq==1` 时 `verify_chain` 行为与修复前逐字节等价（正常路径零变化） |
| J-2 | 偏移模式只跳过首条 prev 指针；首条 payload、后续 prev/payload、seq 连续全验；零 prev 判伪造 |
| J-3 | 仅当子进程是自身进程组组长时 killpg；否则回退单进程 kill |
| J-4 | 预算失败工件只在文件缺失时合成，绝不覆盖已有工件 |
| J-5 | `verify_run` 保持只读；不修改 run 目录任何文件 |
| J-6 | 不改 gate/CLI/schema/公开结果字段；失败工件走既有 judge 判据 |

## 4. 验收映射

| 来源缺陷 | 落点 | 验收 |
|---|---|---|
| P-161 D-1 | D-1 + verifier 起点偏移 | 默认红 / 逃生舱绿 / 篡改仍红（T01/T02/T03） |
| P-161 D-2 | D-2 | spawn kwargs + killpg 守卫 + 回退（T04） |
| P-161 D-3 | D-3 | 读码零死代码 + 既有 driver 测试全过（T05） |
| P-163 D-1 | D-4 | 真实 token/worker 溢出五件套可读、OB-4 判据成立（T06/T07/T08） |

## 5. 回退点

| 编号 | 回退动作 | 影响 |
|---|---|---|
| R-1 | 去掉 `verify_chain(start_seq)` 参数与 verifier 调用，恢复固定 seq=1 | retention 逃生舱回到不可达；其余不变 |
| R-2 | 去掉 POSIX `start_new_session` 与 killpg 守卫 | 回到单进程 kill；测试助手可留 |
| R-3 | 恢复 `_progress` 的 mtime 返回值 | 无行为变化，仅回退可读性修复 |
| R-4 | 删除 `_write_budget_failure` | 真实溢出回到 missing_files；fixture 路径不变 |

## 6. 非目标

- **职责外**：A7-2 并发隔离、A7-3 双平面、FA、OB 新能力、O 表观察项。
- **能力边界**：本批只保证「可读工件的预算失败状态可判」「偏移链可验」；不保证 POSIX 上所有自定义 spawn 都能杀净孙进程（未建新会话者按单进程处理）。

## 7. Review（Step 4，自查·单视角）

| 检查项 | 结论 |
|---|---|
| 基于已验证调研 | 四条缺陷均有代码锚点 + 探针；D-1..D-4 逐条对应 RESEARCH §1 |
| 无未经验证假设 | POSIX 进程组依据 Python/POSIX 文档；未假设 CI 有孙进程 |
| 无归因扭曲 | 未把 fixture 通过当作真实路径通过（P-163 D-1 的核心） |
| 替代方案 ≥2 | D-1/D-2/D-4 均列 2 个否决方案与代价 |
| 职责边界 | §6 区分职责外与能力边界 |
