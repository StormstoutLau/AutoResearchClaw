---
id: arc-g4-m1-registry-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m1-registry-DESIGN]
upstream: arc-g4-m1-registry-DESIGN
---

# 实施：G4-M1 工具注册表与启动校验（P-101）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `tools/registry.yaml` | 新增 | 6 工具等价搬迁（schema 逐字）+ `default` profile |
| 2 | `researchclaw/tools/__init__.py` | 新增 | 导出 Registry/ToolSpec/RegistryError/load_registry + 10 错误码 |
| 3 | `researchclaw/tools/registry.py` | 新增 | 加载器 + 9 条校验规则（V-1..V-8，V-5 拆 a/b） |
| 4 | `tests/test_tool_registry.py` | 新增 | 14 函数（3 参数化展开 → 19 collected） |
| 5 | `pyproject.toml` | 修改 | `dependencies` 加 `jsonschema>=4.20`（Q-1，带注释） |
| 6 | `.github/workflows/ci.yml` | 修改 | 固定清单加 `tests/test_tool_registry.py` |
| 7 | `spec/arc-g4-m0-design/{RESEARCH,DESIGN}.md` | 修改 | 受控回边（D-7 订正 + 编号顺延 + V-5a/b + V-8 + Q-1 裁决） |
| 8 | `tools/spec_runner/sessions/specwf-p099-*.jsonl` | 修改 | seq 6-7 受控回边 |
| 9 | `spec/arc-g4-m1-registry/` 四文档 | 新增 | 本批 spec |

## 2. 关键实现记录

- `_check_json_schema`：`Draft202012Validator.check_schema` + `type == "object"`；`outputSchema` 可空、有则同校验（V-3b）。
- `ToolSpec.resolve()`：`importlib.import_module` + `getattr`，失败抛 `E_REGISTRY_HANDLER_UNRESOLVED`。
- `load_registry(strict_handlers=False)`：V-5b 延迟（Q-5）；`strict=True` 仅 server/invoker 入口调用。
- 首错即抛（D-4）；`Registry.reload()` 重读重校验、旧实例不变（T-13）。
- `risk` 首版：`run_pipeline/review_paper=medium`，其余 `low`；approval 全 `never`（V-8 自洽）。
- **测试 helper 修正一次**：`_payload` 最初忽略 `tools` override、`_write_registry` 不建父目录——红态后修正（诚实记录，非实现缺陷）。

## 3. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | 14 函数 → 19 collected（3 enum 参数化展开） |
| 红→绿 | 红：`ModuleNotFoundError: researchclaw.tools`（collection error）；辅助修正后 **1 failed/32→**（实现首轮 **6 failed/13 passed**：T-2 等 4 项 schema 用例 + risk 断言 + strict 解析 FileNotFoundError——根因是测试 helper 两处 bug，非实现缺陷；修正 helper 后全绿）；绿：**19 passed** |
| 双环境 | 3.13.5 registry+MCP+claim 套件 **194 passed**；3.11.15 **18 passed / 3 skipped**（T-2 `importorskip("mcp")`：mcp 包 fail-closed 导入，轻量环境诚实 skip；CI tests job 装含 mcp extras 实跑） |
| 相关回归 | 十五文件宽回归（registry+MCP+M1-M5+K5）**278 passed**；扩展组 **348 passed** |
| pyproject | 核心依赖 +1（jsonschema>=4.20）；dev 原条目保留 |
| 门禁 | 待回填 |

## 4. 验收边界（诚实口径）

- T-2 的等价搬迁断言在无 mcp extra 的轻量环境 skip（3 skipped 的 1 项）；CI tests job 与主环境实跑覆盖。
- `mcp/tools.py` 本批**保留**（双源 + T-2 锁定一致）；M2 迁移 adapter 后移除。
- `sandbox_profiles.default` 为占位，M4 才消费（DESIGN §2 声明）。

---
