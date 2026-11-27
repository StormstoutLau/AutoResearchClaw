---
id: arc-stage10-generation-budget-contract-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract-RESEARCH]
upstream: arc-stage10-generation-budget-contract-RESEARCH
---

# 设计：生成预算分档、文件预算与符号契约（B-34 M4）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | `LLMClient.chat` 增 **`extra_body: dict \| None`**，仅在 OpenAI-compatible 的 chat-completions 路径**最后合并**进请求体 | ① 为每个供应商加专用参数；② 在 `config` 里放全局 reasoning 字段 | ① 供应商字段长期发散；② 全局字段无法按模块分档。最后合并允许单次调用覆盖 `max_tokens` 等 |
| D-2 | 兼容性：`extra_body` 为空时**不传第 6 个实参、不写任何新键** | 始终传 `extra_body=None` | 既有测试/test double 以 6 位置参数定义；始终传会打破它们（实测 2 例红） |
| D-3 | `thinking_policy` **默认 `off`**；`tiered` 才发字段 | 默认开启 | 严格 provider 对未知字段回 400；默认关闭保证零行为变化 |
| D-4 | 机械模块判定 = 文件名子串命中 `config/settings/constants/schema/types/utils/util/cli/io/loader` | ① 蓝图 `role` 字段；② LLM 分类 | ① 当前蓝图无该字段；② 每次多一次调用。文件名是最便宜且可测的代理 |
| D-5 | 机械模块发 `reasoning_effort`（默认 `low`，可配），设计模块发 `reasoning.max_tokens`（配置 >0 时） | 设计模块也发 `low` | 设计模块需要推理（R-1）；只给上限，不降档 |
| D-6 | 文件预算：`file_max_lines`（默认 300）< 蓝图 `max_lines` 覆盖 < 下限 40；**只提示不硬门** | ① 硬门失败；② 不提示 | ① 行数不是质量判据，硬门会误杀合法长文件；② 无提示时模型无约束 |
| D-7 | 符号契约只校验**已交付文件**中声明的名字；缺文件交给 `check_declared_files` | 两处都报 | 避免同一根因重复报错（现场 `data.py` 缺失会同时触发两条） |
| D-8 | 符号来源支持 `symbols` / `required_symbols` / `classes` / `functions` 四种拼写，元素可为字符串或 `{name: ...}` | 只认一种拼写 | 蓝图由模型生成，拼写不稳定；四种都接受不增加歧义 |
| D-9 | 符号匹配集 = `ast.walk` 中所有 `ClassDef/FunctionDef/AsyncFunctionDef` 的名字（含嵌套与方法） | 只认顶层 | 蓝图常声明方法名；只认顶层会造成假失败 |
| D-10 | 文件不可解析（`SyntaxError`）时**判失败** | 跳过 | 语法坏的文件本就不可交付；跳过会让契约形同虚设 |

## 2. 接口

```python
# researchclaw/llm/client.py
LLMClient.chat(..., extra_body: dict[str, Any] | None = None)

# researchclaw/config.py
@dataclass(frozen=True)
class CodeAgentConfig:
    ...
    thinking_policy: str = "off"          # "off" | "tiered"
    thinking_mechanical_effort: str = "low"
    thinking_core_max_tokens: int = 0     # >0 时给设计模块发 reasoning.max_tokens
    file_max_lines: int = 300

# researchclaw/pipeline/code_agent.py
CodeAgent._is_mechanical_module(file_name) -> bool
CodeAgent._module_line_budget(file_spec) -> int
CodeAgent._thinking_extra(file_name) -> dict[str, Any]
CodeAgent._chat(system, user, max_tokens=8192, extra_body=None)

# researchclaw/pipeline/codegen_evidence.py
_declared_symbols(blueprint) -> list[tuple[str, str]]
_defined_names(code) -> set[str]
check_symbol_contract(blueprint, files) -> list[EvidenceFailure]
```

分档流程：

```text
for file_spec in blueprint.files:
    budget = file_spec.max_lines or cfg.file_max_lines  (>=40)
    prompt += "BUDGET: keep this file at or under N lines"
    extra  = cfg.thinking_policy == "tiered"
             ? (mechanical ? {"reasoning_effort": effort}
                           : {"reasoning": {"max_tokens": core}} if core>0 else {})
             : {}
    chat(8192, extra) ──truncated?──> chat(32768, extra)   # 沿用 B-34 M1-b
```

符号契约：

```text
declared = [(file, symbol) for ordered file entries]
for (file, symbol) in declared:
    code = delivered.get(file);  if code is None: continue   # 文件门负责
    if symbol not in ast_names(code): missing.append(f"{file}:{symbol}")
missing -> EvidenceFailure("blueprint_symbols_missing", detail=...)
```

## 3. 非目标

- 不做函数级分块生成（C++）。
- 不自动拆分超预算文件。
- 不改 `max_tokens` 的 8192→32768 升级链。
- 不改对齐门/B-32 既有四项门。
- 不为 `enable_thinking=false` 提供配置项（仅手工兜底）。

## 4. 边界

- **分档正确性依赖文件名**：`pipeline_utils.py` 会被判机械；蓝图若把算法写在 `utils.py` 会被降档。可用 `max_lines`/人工评审补偿。
- **符号契约只证明名字存在**：空实现、`pass`、错误签名都能通过；语义正确性仍由对齐门与 Stage 12 负责。
- **行数只提示**：模型可无视；本批只留 prompt 与日志，不做硬门。
- **字段下发风险**：`tiered` 只应对已知接受这些键的 endpoint 开启（halogen 已实测）；严格 provider 会 400，属于配置责任。
- **`extra_body` 可覆盖 `model`/`messages`**：这是有意留出的逃生口，调用方自担。
