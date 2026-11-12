---
id: arc-g4-m1-registry-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m0-design, arc-g4-m0-design-review]
upstream: arc-g4-m0-design-IMPLEMENTATION
---

# 调研：G4-M1 工具注册表与启动校验（P-101）

> **Feature**：P-101，G4-M1（A4-1：100% 已注册工具有 schema；缺 schema 启动即失败）。
> **Spec 步骤**：Step 1-2（T1 实施批）。
> **结论先行**：M0 冻结的注册表契约可直接落地，但 P-100 复核暴露的 **5 项裁决（Q-1..Q-5）必须在实现前定案**——其中 D-1（审批组合漏洞）落为校验规则 V-8，D-2（依赖矛盾）采纳「升核心依赖」，handler 解析拆为 V-5a/V-5b 两级以消除核心路径对 `mcp` extra 的隐性依赖。6 个既有工具 schema 等价搬迁（逐字复制，T-2 deep equality 拦截任何改写）。

## 1. 调研目标

1. 裁决 P-100 复核提出的 Q-1..Q-5 五项设计决策（各给证据与拒绝理由）。
2. 确认 6 个既有工具 schema 的搬迁源与等价性判定方式。
3. 确认 `handler` 指向与核心/extra 依赖边界的现状。
4. 产出 8 条校验规则 + 14 项测试矩阵的落点。

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 读码（E3） | `mcp/tools.py`、`mcp/server.py`、`pyproject.toml`、`config.py` | ✅ 搬迁源与依赖面确认 |
| 探针（E2） | `jsonschema` 的 `Draft202012Validator.check_schema` 可用性 | ✅ 本机 4.x 可用 |
| 复核报告回源（E1） | P-100 D-1..D-7 与 O 项 | ✅ 5 项裁决全部有依据 |
| 简报对照（E1） | P-101 简报 §2-§4 | ✅ 采纳全部建议（无偏离项） |

**降级链记录**：无跳过。P-101 简报 5 项建议全部采纳，无「拒绝建议的理由」需登记（简报 §2 要求偏离时登记，本批零偏离）。

## 3. 五项裁决（Q-1..Q-5）

### Q-1（P-100 D-2）：`jsonschema` 归属 → **升核心依赖**

- 证据 A：`researchclaw/tools/registry.py` 将位于核心包；A4-1 要求「缺 schema 启动即失败」= fail-closed，校验不可降级。
- 证据 B：`pyproject.toml` L43 `jsonschema>=4.20` 当前仅在 dev extras；若并入 `server`/`mcp` extras（M0 Q-1 原建议），不装 extras 的 CLI/pipeline 用户在核心启动路径触发 `ImportError`（P-100 D-2 的结构性矛盾）。
- 证据 C：`jsonschema` 核心依赖的体积代价 = `jsonschema` + `attrs` + `referencing` + `rpds-py`（4 个包，纯 Python/Rust wheel，无编译链）。
- **裁决**：`dependencies` 加 `jsonschema>=4.20`；dev extras 中原条目保留（冗余无害，避免意外破坏既有 `-e ".[dev]"` 用户）。
- **拒绝备选**：两级校验（手写结构 + jsonschema 可选）——弱化 fail-closed 且 `anyOf`/`$ref` 等 2020-12 语义无法手写覆盖；registry 移入 `mcp/` 子包——A4-10 要求 REST/MCP/invoker 三入口同源，注册表不能绑定 MCP extra。

### Q-2（P-100 D-1）：审批组合漏洞 → **双保险**

- 证据 A：P-100 X-1 推演——`approval=never` × `risk=high` 不落 DESIGN §5 任何拒绝分支，高危工具可配置为永久免审批，A4-5 负向用例不可达。
- **裁决**：① M1 落校验规则 **V-8**：`risk=high ⇒ approval ∈ {always, high_only}`，错误码 `E_REGISTRY_APPROVAL`（配置层关闭 fail-open）；② M3 审批门加保险分支「`risk=high ∧ 无有效审批 → 拒绝`」（运行时层，M1 仅在 DESIGN 登记，不实现）。
- **拒绝备选**：仅运行时保险——配置层不拦则 `registry.yaml` 可以写出非法组合，错误被推迟到调用期。

### Q-3（P-100 O-4）：fail-closed 启动范围 → **分级**

- 证据 A：DESIGN §2「应用启动路径最前调用」未定义入口集合；`researchclaw/cli.py` 的纯研究流程（23 阶段 pipeline）不消费工具注册表。
- **裁决**：`Registry.load()`/`load_registry()` 自身 fail-closed（任何非法即抛 `RegistryError`）；**进程退出由调用方决定**——M2 的 server/MCP 入口与 M3 的 invoker 在启动时调用并退出；纯 pipeline CLI **不**在启动路径加载。三入口行为在 DESIGN §4 声明。
- **拒绝备选**：全入口无条件加载——把工具子系统故障传导给与研究无关的流程，违反最小影响面。

### Q-4（P-100 O-7）：顶层 `version` 类型 → **int**

- 证据 A：M0 DESIGN §2 示例 `version: 1`（YAML int），但 V-1 未定义类型；YAML `"1"` 与 `1` 语义不同。
- **裁决**：`isinstance(version, int) and version == 1`；字符串 `"1"`、float `1.0` 均拒绝（fail-closed，不做隐式转换）。工具级 `version` 保持字符串（语义化版本，非枚举）。

### Q-5（P-100 V-5 修正）：`handler` 解析时机 → **拆 V-5a/V-5b**

- 证据 A：6 个工具的真实入口在 `researchclaw/mcp/server.py`（`ResearchClawMCPServer`），该模块顶部 `from mcp.server import MCPServer`（**依赖 mcp extra**）。
- 证据 B：若 V-5 在 `load_registry()` 内做 `importlib` 导入，核心路径（无 mcp extra）加载注册表即失败——与 Q-1 升核心依赖的目的（消除 optional 依赖绑架）自相矛盾。
- **裁决**：**V-5a** 格式校验必做（`^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$`，fail-closed）；**V-5b** `importlib` 解析仅在 `strict=True`（M2/M3 入口）执行。`resolve_handlers(strict=False)` 默认只做格式层。
- **拒绝备选**：M0 原 V-5「可解析」单级——启动期强制导入 handler 模块，把 mcp extra 依赖泄漏进核心。

## 4. 搬迁源确认（E3）

- 源：`researchclaw/mcp/tools.py` L8-87，6 个工具（`run_pipeline`/`get_pipeline_status`/`get_experiment_results`/`search_literature`/`review_paper`/`get_paper`）。
- 等价性判定：`registry.yaml` 的 `inputSchema` 与 `get_tool_schema(name)["inputSchema"]` **deep equality**（T-2，拦截任何「顺手优化」）。
- `handler` 统一指向 `researchclaw.mcp.server:ResearchClawMCPServer`（M2 adapter 经 `server.handle_tool_call` 分发；V-5b 延迟解析规避 extra 依赖）。
- `risk` 首版赋值：`run_pipeline=medium`（起长任务）、`review_paper=medium`（LLM 成本）、其余 `low`；`approval` 全部 `never`（无 high，V-8 自洽）。
- `scope`：`run_pipeline`/`search_literature` = `global`（不依赖 run）；其余 4 个（需 `run_id`）= `run`。
- `sandbox_profile: default` 对纯查询工具为占位（M4 才真正消费），在 DESIGN 声明。

## 5. 幻觉抑制审查（Step 2 Review）

| 引用/声明 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| 6 工具 schema 内容 | `mcp/tools.py` L8-87 | 读码 + T-2 deep equality | ✅ E3/E1 |
| `jsonschema` 在 dev extras L43 | `pyproject.toml` | 读码 | ✅ E3 |
| `Draft202012Validator.check_schema` 可用 | 本机 jsonschema 4.x | 探针 | ✅ E2 |
| handler 模块依赖 mcp extra | `mcp/server.py` L26-31 导入 | 读码 | ✅ E3 |
| P-100 D-1/D-2/O-4/O-7/V-5 依据 | 复核报告 §3/§4 | 回源 | ✅ E1 |

### 待修正项

- [x] M0 DESIGN V-5 单级「可解析」→ 本批拆 V-5a/V-5b（随受控回边落 M0 文档）。
- [x] M0 RESEARCH A4-3「无 `--memory`」→ 按 P-100 D-7 订正（随受控回边落 M0 文档）。

## 6. 参考文献

- P-101 简报（`p101-m1-brief.md`，工作区根目录、不入仓；裁决建议与测试矩阵）
- [P-100 复核](../../docs/arc-g4-m0-design-review-20261114.md)（D-1/D-2 依据）
- [M0 DESIGN §2](../arc-g4-m0-design/DESIGN.md)（注册表契约）
- [总纲 G4](../../arc-master-roadmap.md) L448-484
- CommonMark 无关；JSON Schema 2020-12 规范（经 P-093 T1 回源）

---
