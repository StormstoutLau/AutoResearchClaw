---
id: arc-g7-review-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-review-fixes-DESIGN, arc-g7-review-fixes-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 复审修复批（P-164）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **环境**：Python ≥3.11（本机 3.13.5）；仅标准库；pytest 8.3.4。

## 1. 文件清单

| 路径 | 类型 | 改动 |
|---|---|---|
| `researchclaw/runtime/event_log.py` | 修改 | `verify_chain(start_seq=1)` 偏移链 |
| `researchclaw/soak/verifier.py` | 修改 | 先算 `first_seq`，再按起点校验链 |
| `researchclaw/soak/driver.py` | 修改 | POSIX 新会话 + killpg 守卫；删死代码；`_progress() -> int` |
| `experiments/arc_bench/orchestration/adapters.py` | 修改 | `_write_budget_failure` + 异常分支调用 |
| `tests/test_soak_verifier_retention.py` | 新增 | 偏移链/逃生舱/篡改回归（T01..T03） |
| `tests/test_soak_driver_kill.py` | 新增 | spawn/kill 助手单测（T04） |
| `tests/test_orchestration_overflow.py` | 新增 | 真实 token/worker 溢出 + fixture 不覆盖（T06..T08） |
| `spec/arc-g7-review-fixes/*.md` | 新增 | 四文档 |

## 2. 接口签名

```python
# researchclaw/runtime/event_log.py
def verify_chain(self, start_seq: int = 1) -> tuple[bool, str]:
    """start_seq>1: offset chain after retention; first prev skipped, payload kept."""

# researchclaw/soak/verifier.py
chain_ok, chain_message = log.verify_chain(start_seq=first_seq or 1)

# researchclaw/soak/driver.py
def _spawn_kwargs(os_name: str | None = None) -> dict[str, bool]
def _posix_kill_tree(proc, *, getpgid=None, killpg=None, kill=None) -> str  # "group"|"process"
def _default_spawn(cmd, **kwargs)
def _default_kill(proc) -> None
def _progress(self) -> int

# experiments/arc_bench/orchestration/adapters.py
class OrchestrationAdapter(ABC):
    def _write_budget_failure(self, task, workdir: Path, exc: BudgetExceeded) -> None
```

**回退点**：R-1（verify_chain 参数）、R-2（spawn/kill）、R-3（mtime）、R-4（失败工件），见 DESIGN §5。

## 3. 关键实现约束

1. `_posix_kill_tree` 的 `getpgid/killpg/kill` 全部可注入，Windows 上也能单测；默认参数在调用时解析，避免 Windows 导入期访问 `os.getpgid`。
2. `_default_spawn` 合并 kwargs 时 `start_new_session` 可被调用方覆盖（显式传 False 时不强加）。
3. `_write_budget_failure` 只写缺失文件；已存在文件不读不写不覆盖。
4. usage 与 trace 自洽：`prompt_tokens == Σ span.attributes.tokens_in`；`charged_tokens` = 尝试 token（仅 `kind=="tokens"`）。
5. 非 token 类超限（workers/wall/depth）：`prompt_tokens=0`、trace tokens=0，`exceeded=true`、`status=budget_exceeded`。

## 4. 测试计划（红 → 绿）

| 测试 | 红断言（实现前） | 绿断言（实现后） |
|---|---|---|
| T01 `test_verify_chain_offset_after_prefix_deletion` | `verify_chain(start_seq=2)` 抛 TypeError / 默认 False | 偏移 True；默认 False（seq gap） |
| T02 `test_verify_run_retention_escape_hatch` | `allow_retention_gap=True` 仍 `converged=False` | 默认 `retention_limited` 且不 ok；allow=True 时 `ok/converged/chain_ok` 全 True |
| T03 `test_offset_chain_still_detects_tamper` | 无偏移实现 | 首条 payload 篡改 → chain False；中段 seq 缺口 → chain False |
| T04 `test_spawn_kwargs_and_killpg_guard` | 助手不存在 | POSIX `start_new_session=True`；组长 killpg；非组长/OSError 回退 proc.kill |
| T05 既有 soak 测试 | — | 27+ passed 不回归 |
| T06 `test_real_token_overflow_writes_ob4_artifacts` | workdir 0 文件、judge missing_files | 五件套齐全；`ob4_budget_state_ok=true`、`usage_matches_trace=true`、total=0 |
| T07 `test_real_worker_overflow_writes_ob4_artifacts` | 同上 | 同上（`kind=workers`） |
| T08 `test_budget_failure_writer_does_not_overwrite_fixture` | — | `over_budget` 的 `charged_tokens==budget+1` 保持不变 |
| T09 回归 | — | 编排 24 + soak 27 + event_log 全过 |

## 5. 低效操作排除

| 低效操作 | 排除 |
|---|---|
| 偏移模式重新扫描全日志 | 复用一次 `read_all()`；只改起点 |
| killpg 前额外 `ps` | 仅 `getpgid` 一次系统调用 |
| 预算失败写完整报告 | 只写五件套最小结构（<2 KB） |
| 新增依赖 | 零新增；只用 `signal/os/subprocess` |
| 改 gate/CLI | 零改动 |

## 6. 版本与 API 核验（Step 6）

| API | 下限 | 核验 |
|---|---|---|
| `subprocess.Popen(start_new_session=)` | 3.2+ | Python 官方文档；3.11 可用 |
| `os.getpgid` / `os.killpg` / `signal.SIGKILL` | POSIX only | 只在 POSIX 分支调用；Windows 不访问 |
| `Path` / `dataclasses` | 3.x | 既有用法 |
| pytest | ≥7.0 | 本机 8.3.4 |
| 三方依赖 | 无 | pyproject 不变 |

## 7. Review（Step 6，自查·单视角）

| 检查项 | 结论 |
|---|---|
| 版本真实存在 | 全部标准库；POSIX API 有平台守卫 |
| 签名可实现 | 四个助手均为纯函数/薄封装，可注入测试 |
| 无虚构 API | 未引用未安装包 |
| 兼容性 | 正常路径默认参数，不改调用方 |
| 低效操作已排除 | §5 |
| 与设计对齐 | D-1..D-5 均有落点；R-1..R-4 对应 |
