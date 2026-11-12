---
id: arc-g4-m1-registry-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g4-m1-registry-RESEARCH]
upstream: arc-g4-m1-registry-RESEARCH
---

# 设计：G4-M1 工具注册表与启动校验（P-101）

> 基于 [RESEARCH.md](RESEARCH.md) 的 Q-1..Q-5 裁决。交付 = `tools/registry.yaml` + `researchclaw/tools/registry.py` + 测试 + `pyproject.toml` 依赖变更 + M0 受控回边。A4-1。

## 1. 交付范围

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `tools/registry.yaml` | 新增 | 6 工具等价搬迁 + `default` profile |
| 2 | `researchclaw/tools/__init__.py` | 新增 | 导出 `Registry`/`ToolSpec`/`RegistryError`/`load_registry` |
| 3 | `researchclaw/tools/registry.py` | 新增 | 加载器 + 8 条校验 |
| 4 | `tests/test_tool_registry.py` | 新增 | 14 项 |
| 5 | `pyproject.toml` | 修改 | `dependencies` 加 `jsonschema>=4.20`（Q-1） |
| 6 | `spec/arc-g4-m0-design/{RESEARCH,DESIGN}.md` | 修改 | 受控回边（D-7 订正 + 编号 + V-5a/b + V-8） |

## 2. `tools/registry.yaml`

6 个工具逐字搬迁（schema 不改写）；字段见 RESEARCH §4（risk/scope/approval 首版赋值）。`sandbox_profiles.default`：`network: none, cpu: 2, memory: 4g, pids: 512, disk: 10g, ttl_sec: 1800`——纯查询工具的 profile 为**占位**，M4 才真正消费（诚实声明：本批不建立 profile 与执行的连接）。

## 3. `researchclaw/tools/registry.py`

### 3.1 数据结构

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str; version: str; description: str
    input_schema: dict; output_schema: dict | None
    scope: str; risk: str; approval: str
    sandbox_profile: str; handler: str
    def resolve(self) -> object          # V-5b：importlib，失败抛 E_REGISTRY_HANDLER_UNRESOLVED

@dataclass(frozen=True)
class Registry:
    version: int
    tools: tuple[ToolSpec, ...]
    sandbox_profiles: dict[str, dict]
    source_path: Path
    def get(self, name: str) -> ToolSpec | None: ...
    def resolve_handlers(self, *, strict: bool = False) -> None
    def reload(self) -> "Registry"       # 重读 source_path；失败抛错且旧实例不变

def load_registry(path=None, *, strict_handlers: bool = False) -> Registry
```

### 3.2 校验规则（8 条 + V-5 拆分，顺序执行、首错即抛）

| # | 规则 | 错误码 |
|---|---|---|
| V-1 | 顶层 `version` 为 int 且 == 1（Q-4：字符串/float 拒绝） | `E_REGISTRY_VERSION` |
| V-2 | `tools` 非空 list of dict；`name` 唯一且匹配 `^[a-z][a-z0-9_]{2,63}$` | `E_REGISTRY_NAME` |
| V-3 | `inputSchema` 存在且为 dict、`Draft202012Validator.check_schema` 通过、`type == "object"` | `E_REGISTRY_SCHEMA_MISSING` / `E_REGISTRY_SCHEMA_INVALID` |
| V-3b | `outputSchema` 若存在须通过 `check_schema` | `E_REGISTRY_SCHEMA_INVALID` |
| V-4 | `risk`/`approval`/`scope` 三枚举 | `E_REGISTRY_ENUM` |
| V-5a | `handler` 匹配 `^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$` | `E_REGISTRY_HANDLER` |
| V-5b | `strict_handlers=True` 时 `importlib` 可解析（Q-5：默认 False） | `E_REGISTRY_HANDLER_UNRESOLVED` |
| V-6 | `sandbox_profile` 在 `sandbox_profiles` 中 | `E_REGISTRY_PROFILE` |
| V-7 | profile：`network ∈ {none,setup_only,full}`（str）、`cpu/pids/ttl_sec`（int > 0）、`memory/disk` 匹配 `^\d+[gm]$` | `E_REGISTRY_PROFILE_INVALID` |
| **V-8** | **`risk == "high"` ⇒ `approval != "never"`**（Q-2/D-1） | `E_REGISTRY_APPROVAL` |

- 校验顺序：顶层结构 → 逐工具（V-2..V-8）→ profiles（V-6/V-7 交叉）。**首错即抛**（不收集多错，fail-closed）。
- `RegistryError(ValueError)`：字段 `code`/`message`/`tool`/`path`（可空）。

### 3.3 入口行为矩阵（Q-3）

| 入口 | 行为 |
|---|---|
| M2 server / MCP stdio | 启动时 `load_registry(strict_handlers=True)`；异常 → 进程退出（M2 落地） |
| M3 invoker | 启动时 `load_registry()`；异常 → 该入口不可用（M3 落地） |
| 纯 pipeline CLI | **不加载**注册表（本批不加任何调用点） |

## 4. pyproject 变更（Q-1）

`dependencies` 加 `"jsonschema>=4.20"`；dev extras 原条目保留（冗余无害）。不加 `$schema` 字段要求——`check_schema` 按 2020-12 默认草案执行。

## 5. 迁移表（P-096 式逐行对照）

| 行为 | M0 设计 | M1 实现 | 差异方向 |
|---|---|---|---|
| 缺 `inputSchema` | fail-closed | `E_REGISTRY_SCHEMA_MISSING` | 一致 |
| `approval=never`+`risk=high` | **未拦截（P-100 D-1）** | **`E_REGISTRY_APPROVAL`** | 收紧 |
| `handler` 可解析 | 单级、启动期导入 | V-5a 格式必做 + V-5b 延迟 | 收窄依赖面 |
| 顶层 `version` 类型 | 未定义 | int 严格 | 收紧 |
| 6 工具名称/参数 | 不变 | deep equality 断言 | 不变（INV-4） |

## 6. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | `jsonschema` 升核心依赖 | RESEARCH Q-1 证据 B/C | 拒绝 extras 并入（ImportError 绑架）、两级校验（弱化 fail-closed） |
| D-2 | V-8 双保险之配置层 | P-100 D-1 | 拒绝仅运行时保险（错误推迟到调用期） |
| D-3 | V-5a/V-5b 拆分 | RESEARCH Q-5 证据 A/B | 拒绝 M0 单级（mcp extra 泄漏进核心） |
| D-4 | 首错即抛 | fail-closed 纪律 | 拒绝收集多错（掩盖首个根因） |
| D-5 | profile 占位声明 | M4 才消费 | 拒绝本批建立 profile→执行连接（越批） |

## 7. 验收映射

| 验收 ID | 落点 |
|---|---|
| A4-1 正向 | T-1/T-2（6 工具装载 + deep equality） |
| A4-1 负向 | T-3（缺 schema）/ T-4（非法 schema）→ `RegistryError` 且无 fallback |
| D-1 关闭 | T-6（`E_REGISTRY_APPROVAL`） |
| D-2 落地 | pyproject diff + T-1 在无 extras 干净环境可跑（uv 隔离） |
| INV-4 | T-2 |
| M0 回边 | RESEARCH/DESIGN diff + P-099 session rebind + `digest_bound` 覆盖 |

## 8. 不变式

- I-1 注册表为唯一真值源；本批**不删** `mcp/tools.py`（M2 迁移后移除，本批保留双源并以 T-2 锁定一致性）。
- I-2 校验 fail-closed，无 fallback、无「跳过坏条目」。
- I-3 首错即抛，错误码固定 9 个。
- I-4 6 工具名称与参数不变（MCP 行为零变化）。
- I-5 核心路径不 import `mcp.*`（Q-5）。
- I-6 `Registry` 不可变；`reload()` 失败不影响旧实例。

## 9. 非目标

- MCP 动态注册/listChanged、`GET /api/tools`（M2）。
- tool 事件、审批运行时（M3）。
- 沙箱 profile 消费（M4）。
- `mcp/tools.py` 的删除（M2 迁移后）。

---
