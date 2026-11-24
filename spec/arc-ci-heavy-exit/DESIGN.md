---
id: arc-ci-heavy-exit-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-ci-heavy-exit-RESEARCH]
upstream: null
---

# 设计：heavy 用例回归默认 CI（P-141）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：7 个文件（5 处移出 + 2 处入链修复）；不改 `ci.yml` 测试命令与覆盖守卫逻辑。

---

## 1. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 去掉两条用例的 `@pytest.mark.heavy`，保留用例本体与全部断言 | RESEARCH §2 接缝 1/2 |
| D-2 | `tests/ci_exclusions.yaml` 清空为 `exclusions: []`，保留五字段契约注释 | RESEARCH §2 接缝 3 |
| D-3 | 删除 `.github/workflows/heavy.yml` | RESEARCH §4 方案 B/D 否决 |
| D-4 | 删除 `pyproject.toml` 的 `heavy` marker 定义 | RESEARCH §2 接缝 5；无标记即无引用 |
| D-5 | 保留 `ci.yml` 的 `-m "not heavy"` 与 `ci_coverage_check.py` 的守卫逻辑 | 无标记时等价全量；守卫的「未登记必须被收集」契约继续有效 |
| D-6 | 接受回归风险；30 天内出现原始签名即单提交回退 | 用户裁决 |
| D-7 | 本批只推分支与 PR，合并需单独授权 | 仓库工作流约束 |
| D-8 | 修复 `spec/arc-ci-heavy-schedule/IMPLEMENTATION.md` 中两条指向 `heavy.yml` 的相对链接，改为行内代码；同步重绑该批 session digest | 删除文件后入链必然悬空，dc/grandfather 会红 |

## 2. 目标形态

### 2.1 测试文件

```python
# tests/test_hitl_advanced.py
    def test_poll_with_delayed_response(self, tmp_path: Path) -> None:

# tests/test_supervisor.py
def test_lease_keeper_reports_loss(tmp_path):
```

用例体、断言、sleep 参数全部不变；仅移除装饰器行。

### 2.2 排除登记表

```yaml
version: 1
exclusions: []
# 契约（ci_coverage_check.py 校验）：
#   - 五字段 path / reason / marker / owner / since 均必填；marker 固定为 heavy
#   - 文件内含 pytest.mark.heavy ⇔ 必须在此登记
#   - P-141 起默认 CI 收集全部测试，本表为空；若未来重新隔离，需同时恢复
#     pyproject 的 heavy marker 定义与独立 workflow。
```

### 2.3 项目配置

```toml
# 删除整个 [tool.pytest.ini_options] 段（其唯一内容为 heavy marker）
```

### 2.4 workflow

`heavy.yml` 整体删除；`ci.yml` 不动。

## 3. 不变式

| 编号 | 不变式 | 验证 |
|---|---|---|
| J-1 | 两条用例被默认 CI 收集 | `pytest tests --collect-only -q -m "not heavy"` 命中两个 node id |
| J-2 | 两条用例仍可运行 | 聚焦执行 `2 passed` |
| J-3 | 覆盖闭合仍成立 | `ci_coverage_check.py --check` 输出 `L=149，R=0，C=149` |
| J-4 | 无残留 heavy 引用 | 测试文件 `pytest.mark.heavy` 命中 0；workflow 无 `-m heavy` |
| J-5 | 回退路径单提交可逆 | `git revert <squash>` 恢复 5 个文件 |

## 4. 风险接受

- 移出后两条用例随每个 PR 在 3.11/3.12/3.13/3.14 上运行；原误红四次集中在时序竞争。
- 已用两窗口 + 各 1000 次零失败降低概率；残余风险由用户裁决接受。
- 若出现原始签名（`Invalid response file`、`HITL poll timeout`、`keeper 必须在租约丢失时回调`），按 §5 回退，不在本批热修。

## 5. 回退

1. `git revert <P-141 squash commit>`：恢复两条 marker、登记表两条、`heavy.yml`、marker 定义。
2. 若 workflow 已被分支保护引用（当前无），先补回必需检查再合并。
3. 回退后重新进入「隔离观察」流程，不直接再次移出。

## 6. 兼容性

| 维度 | 影响 |
|---|---|
| 外部契约 | 无：测试文件名、用例名、断言不变 |
| CI 必需检查 | 无：7 个上下文均来自 `ci.yml` |
| 覆盖守卫 | 无：表空时闭包成立，`--selftest` 4/4 |
| 入链 | `arc-ci-heavy-schedule` 两条 `heavy.yml` 链接已改行内代码，P-129 session digest 已重绑 |
| 开发者命令 | `pytest -m "not heavy"` 仍可用；`pytest -m heavy` 收集 0 条，不再被任何 workflow 调用 |
