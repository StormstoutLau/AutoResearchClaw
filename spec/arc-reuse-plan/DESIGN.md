---
id: arc-reuse-plan-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-reuse-plan-RESEARCH]
upstream: null
---

# 设计：配置快照与复用计划（P-148）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：1 个新模块、`pipeline_manifest.py` 扩展、`cli.py` 增一个子命令、1 个测试文件。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 新模块 `researchclaw/skills/config_sanitizer.py`，只做脱敏与快照 |
| D-2 | manifest v2 增 `config` 块：`pointer` / `sha256` / `source_format` / `redacted_keys` |
| D-3 | 有 `config_path` 导出为 v2；无则保持 v1（向后兼容） |
| D-4 | 加载时校验快照存在、路径在技能目录内、sha256 一致 |
| D-5 | `pipeline-skill plan` 输出命令与待补键，不执行 |
| D-6 | `*_env` 不脱敏；`~`/UNC 与盘符/绝对路径一律脱敏 |

## 2. Manifest v2 增量

```json
"manifest_version": 2,
"config": {
  "pointer": "config.sanitized.yaml",
  "sha256": "sha256:...",
  "source_format": "yaml",
  "redacted_keys": ["llm.api_key", "project.output_dir"]
}
```

约束：`pointer` 必须相对且位于技能目录内；文件必须存在；`sha256` 必须匹配。

## 3. API

```python
sanitize_config(data) -> tuple[dict, list[str]]
write_sanitized_snapshot(config_path, skill_dir) -> dict
export_manifest(..., config_path=None) -> dict      # 有 config 则 v2
validate_manifest(..., skill_dir=None)               # v2 校验快照
```

## 4. CLI

```
researchclaw pipeline-skill plan --skill-dir <d> [--json]
```

输出：`command`、`config_snapshot`、`stages`、`tools`、`redacted_keys`、`needs_manual_fill`。

退出码：0 有计划 / 2 输入不可用或 v1。

## 5. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 快照不含凭据值 | `test_snapshot_has_no_secret_bytes` |
| J-2 | `*_env` 保留、凭据键脱敏 | `test_redacts_secrets_and_paths` |
| J-3 | 快照 sha256 不匹配即拒绝 | `test_loader_rejects_tampered_snapshot` |
| J-4 | v1 仍可加载，v1 不能生成计划 | `test_export_without_config_stays_v1`、`test_plan_v1_rejected` |
| J-5 | v2 缺 config 块即拒绝 | `test_v2_requires_config_block` |
| J-6 | 脱敏不修改输入对象 | `test_does_not_mutate_input` |

## 6. Review 记录（Step 6）

- 脱敏器与 manifest 模块职责分离，避免 `pipeline_manifest.py` 继续膨胀。
- `plan` 只读：不写文件、不调用 runner。
- 退出码与 P-147 对齐（0/2；本命令无「差异」态，故不用 1）。
- 修正：`ABS_PATH_RE` 由「盘符 + `/`」扩展为含 `~/` 与 UNC。

## 7. 非目标

自动重跑、prompt 存储、配置合并、密钥托管、跨 run 快照。
