---
id: arc-reuse-plan-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-reuse-plan-DESIGN]
upstream: null
---

# 实施：配置快照与复用计划（P-148）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：1 新模块 + 2 既有文件扩展 + 1 测试文件。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/skills/config_sanitizer.py` | 新增 | `sanitize_config`、`write_sanitized_snapshot` |
| `researchclaw/skills/pipeline_manifest.py` | 修改 | v2 支持、`config_path` 导出、快照校验 |
| `researchclaw/cli.py` | 修改 | `pipeline-skill plan` 子命令 |
| `tests/test_reuse_plan.py` | 新增 | 11 条用例 |

## 2. 读数

```text
$ python -m pytest tests/test_reuse_plan.py -q
...........                                                              [100%]
11 passed in 0.58s

$ python -m pytest tests/test_pipeline_skill.py tests/test_reuse_verify.py tests/test_action_ledger.py -q
32 passed in 1.12s
```

诚实记录：本批测试与实现交替推进，**不是严格 TDD**。首轮 10 passed / 1 failed，失败原因是 `~/.ssh/id_rsa` 未被识别为绝对路径；扩展 `ABS_PATH_RE` 后 11 passed。该缺陷由测试暴露，实现未迁就测试。

## 3. 实现要点

### 3.1 脱敏

- 递归遍历 dict/list；键名匹配凭据正则且值非空 → `***REDACTED***`。
- `*_env` 后缀保留（环境变量名不是密钥）。
- 绝对路径（盘符、`/`、`~/`、UNC）→ `<REDACTED_PATH>`。
- 返回脱敏副本与被替换键路径，不修改入参。

### 3.2 manifest v2

- `export_manifest(..., config_path=...)` 写 `config.sanitized.yaml`，把指针/哈希/键路径写入 `config` 块，版本置 2。
- 无 `config_path` 时版本保持 1，行为与 P-146 一致。

### 3.3 加载校验

`validate_manifest` 接受 1/2；v2 额外要求：config 块存在、指针相对且位于技能目录、文件名固定、快照存在、sha256 一致。

### 3.4 plan

只读命令：加载 → 校验 → 输出 `researchclaw run --config "<snapshot>" --topic "<your topic>"`、阶段、工具、待补键。v1 返回 exit 2 并提示重新导出。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-148 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 8/8 success |

## 5. 未做与边界

- 未自动执行；`plan` 只输出命令。
- 未存 prompt；P-145 D-7 未被推翻。
- 未验证重跑结果与原始 run 等价。
- 脱敏为命名启发式，已知边界见 RESEARCH §6。
