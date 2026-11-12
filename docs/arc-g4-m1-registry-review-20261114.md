# P-102 对 P-101「G4-M1 工具注册表」的独立异构复核（2026-11-14）

> **性质**：Layer-0 独立异构复核（T3，零生产代码/零门禁）。不采信 [P-101 实施](../spec/arc-g4-m1-registry/IMPLEMENTATION.md) 的任何结论，全部一手重验：HEAD `fbe27d3` 读码、双环境测试复跑、宽回归、session digest 逐文件复算、**H 组打包路径推演 + 21 组加载器对抗探针**。**异构性**：实施会话为 **GLM-5.3-Flash**（`specwf-p101-arc-g4-m1-registry.jsonl` model 字段），本复核为 **DeepSeek-V4.1-Flash**——与 P-100（GLM 复核 DeepSeek 实施）形成 RULE-5 双向交叉。**单向权限**：只标记问题，不改实现；探针零残留。
> **编号说明**：本批占用 **P-102**；G4-M2..M5 **顺延为 P-103..P-106**（M0 文档的 `P-102..P-105` 以本报告为准，M2 落地时随受控回边订正）。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | 19 用例（14 函数 + 3 参数化展开） | `--collect-only` | ✅ 19 collected |
| V-2 | 3.13.5 七文件 194 passed | 复跑 registry+MCP+claim 四文件组合 | ✅ 194 passed（4.52s） |
| V-3 | 3.11.15 18 passed / 3 skipped | `uv run --python 3.11 --with …` | ✅ 18 passed, 3 skipped（mcp 缺席） |
| V-4 | 扩展组 348 passed | rc_executor 等十文件 | ✅ 348 passed（202.47s） |
| V-5 | `jsonschema` 升核心依赖 | `pyproject.toml` L13（dependencies）+ L46（dev 保留） | ✅ 与 Q-1 裁决一致 |
| V-6 | CI 固定清单含 `test_tool_registry.py` | `ci.yml` L133 | ✅ |
| V-7 | 改动边界 18 文件 +1147/−26 | `git show --stat HEAD` | ✅ 与 IMPL §1 九项吻合（含派生视图/CI） |
| V-8 | P-101 session 5 行、1 finalize、digest 8 文件零 mismatch | 本地 sha256 逐文件复算 | ✅ |
| V-9 | A4-1 负向真实：缺 schema 即抛、无 fallback | 探针 + 读码 `_check_json_schema` | ✅ 无 fallback 分支 |
| V-10 | INV-4 等价搬迁（6 工具 schema deep equality） | T-2 复跑（主环境实跑） | ✅ 逐字段相等 |
| V-11 | 核心路径不 import `mcp.*` | 读码 registry.py imports（yaml/jsonschema/importlib/os/re/dataclasses/pathlib/typing） | ✅ |
| V-12 | M0 受控回边（D-7/编号/V-5a-b/V-8/Q-1）与 P-099 seq6-7 | 读码 + `step-gate --legacy` 复跑 | ✅ exit 0 |

## 2. 对抗探针（X 表，21 组）

### 2.1 缺陷

| # | 探针 | 实测 | 判定 |
|---|---|---|---|
| X-1 | **wheel 安装下的默认注册表路径** | `[tool.hatch.build.targets.wheel] packages = ["researchclaw"]` → `tools/registry.yaml` **不入包**；模拟 site-packages 布局后 `_default_registry_path()` 解析为 `site-packages/tools/registry.yaml`（**不存在**） | **D-1 P2**：pip 安装的用户在 M2/M3 启动加载时必然 `E_REGISTRY_VERSION`（文件不可读），A4-1 的 fail-closed 变成「谁都起不来」 |
| X-2 | `INV-6 Registry 不可变` | `registry.sandbox_profiles["default"]["cpu"] = 99` **成功**；`spec.input_schema["type"] = "array"` **成功**（frozen dataclass 只冻结字段引用，不冻结嵌套 dict） | **D-2 P3**：不变式表述超出实现，且真值源可被调用方改坏 |
| X-3 | 错误码语义 | 文件不存在 / 路径是目录（Permission denied）/ 空文件 → 全部报 **`E_REGISTRY_VERSION`** | **D-3 P3**：A4-1 的「启动即失败」可诊断性受损；运维会误判为版本问题 |

### 2.2 通过项（关键负向全部真实）

| # | 探针 | 结果 |
|---|---|---|
| C1-C4 | V-8 绕过尝试：`risk='HIGH'` / `approval='Never'` / `approval` 缺失 / `risk=' high'` | ✅ 全部 `E_REGISTRY_ENUM` 拒绝 |
| C5 | `risk=high + approval=high_only` | ✅ 放行（与 V-8 语义一致） |
| B1 | YAML 重复键（`risk` 两次，后者 `high`） | ✅ PyYAML 后者生效 → 被 V-8 拦下（`E_REGISTRY_APPROVAL`）——**无绕过** |
| E1/E2 | `strict_handlers` 边界 | ✅ 不存在模块 → `E_REGISTRY_HANDLER_UNRESOLVED`；`researchclaw.mcp.server:ResearchClawMCPServer` 在含 extra 环境解析成功 |
| F1/F2 | `cpu: true`（bool）、`memory: "4G"` | ✅ 均 `E_REGISTRY_PROFILE_INVALID`（bool 显式排除） |
| F4/F5 | `tools: []` / `tools: {}` | ✅ `E_REGISTRY_NAME` |
| A3 | 空文件 | ✅ 报错（码见 D-3） |
| G1 | 文件删除后 `reload()` | ✅ 抛错（旧实例未受影响，T-13 已覆盖） |
| B2/F3 | 未知键（tool 级/top 级/profile 级） | ⚠️ 静默忽略 → **O-1** |

## 3. 缺陷

### D-1（P2）wheel 安装缺注册表文件：默认路径解析出包外

- **根因**：`_default_registry_path()` 用 `Path(__file__).resolve().parents[2] / "tools/registry.yaml"`——editable 安装指向仓库根（正确），wheel 安装指向 `site-packages/`（错误）；而 hatch 配置 `packages = ["researchclaw"]` 不包含仓库根的 `tools/`。
- **影响**：M2（server/MCP 启动加载）与 M3（invoker）在**任何 pip 安装场景**都会启动失败。M1 自身未接线，故当前 CI 不红（packaging job 只跑 `--help`）。
- **修复建议（供 M2 吸收）**：① 将注册表作为包数据随包分发——`researchclaw/tools/registry.yaml`（canonical 副本）+ `[tool.hatch.build.targets.wheel] force-include = {"tools/registry.yaml" = "researchclaw/tools/registry.yaml"}`，`_default_registry_path()` 改为 `importlib.resources.files("researchclaw.tools") / "registry.yaml"`；或 ② 保留仓库根路径但 wheel 强制包含 `tools/` 目录并改用 `sys.prefix`/包相对双候选。**建议 ①**（包内资源是标准做法，且 `RC_TOOL_REGISTRY` 仍可覆盖）。
- **回归护栏**：packaging job 增加 `python -c "from researchclaw.tools.registry import load_registry; load_registry()"`（装 wheel 后必须成功）。

### D-2（P3）INV-6 不可变告破：嵌套 dict 可被调用方修改

`Registry`/`ToolSpec` 是 frozen dataclass，但 `sandbox_profiles`、`input_schema`、`output_schema` 是可变 dict。探针 X-2 实证两处均可改。影响：真值源在运行期被污染后无从发现（无校验、无指纹）。修复建议：`MappingProxyType` 深包装或加载后计算指纹并在 `reload` 前校验；或把 INV-6 改写为「字段不可重绑定、嵌套容器约定只读」并登记为已知边界。M2 前建议至少做浅层只读包装。

### D-3（P3）错误码错配：文件不可读/空文件报 `E_REGISTRY_VERSION`

`_load_payload` 把所有 OSError/YAMLError/非映射统一抛 `E_REGISTRY_VERSION`。A4-1 的负向用例只要求失败，但错误码是运维可见契约。修复建议：新增 `E_REGISTRY_UNREADABLE` / `E_REGISTRY_PARSE`（或复用 `E_REGISTRY_SCHEMA_INVALID` 不适用），并在 DESIGN §2 规则表登记。与 P-101 DESIGN §3.2「V-1 = version 类型」语义解耦。

## 4. 观察项（O 表）

| # | 内容 | 处置 |
|---|---|---|
| O-1 | 未知键静默忽略（tool 级/top 级/profile 级）——拼写错误的可选字段不报错 | 记录；M2 可加 `additionalProperties: false` 等价校验 |
| O-2 | `outputSchema: {type: object}` 对 6 工具均为**新增声明**（legacy 无此字段），未经返回体证据支撑 | 记录；M2 用真实返回做 schema 抽样验证或移除该字段 |
| O-3 | YAML 重复键静默后者生效（B1）——本次被 V-8 兜住，但机制本身不报错 | 记录；可选：`yaml.compose` 检测重复键 |
| O-4 | `RC_TOOL_REGISTRY` 环境变量可指向任意路径（含仓外），无来源校验 | 记录；属运维覆盖口，M2 可加 warning 日志 |
| O-5 | M1 保留 `mcp/tools.py` 双源，仅 T-2 锁定一致性；任何一方漂移只有在测试时暴露 | 已声明（U-2），M2 迁移后移除 |
| O-6 | 编号再次顺延：M2..M5 = **P-103..P-106** | 总纲 v1.4n 声明；M2 设计受控回边订正 |
| O-7 | `tools/registry.yaml` 在仓库根而非包内（D-1 的另一面）；`tools/` 目录名与 `tools/spec_runner/` 共存 | 与 D-1 同批处理 |

## 5. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境（E1） | V-1..V-4 | ✅ 19 / 194 / 18+3skip / 348 |
| digest 复算 + git show（E1） | V-7/V-8 | ✅ 8 文件零 mismatch、18 文件边界吻合 |
| 读码（E3） | V-5/V-6/V-11/V-12、D-1 根因、D-2/D-3 定位 | ✅ |
| 运行时探针（E2，21 组：V-8 绕过 5 / 加载器健壮性 6 / 不可变 2 / handler 2 / profile 4 / 重载 1 / 打包 1） | X 全表 | **1 P2 + 2 P3** |
| 打包路径推演（E2，模拟 site-packages 布局 + 读 hatch 配置） | X-1/D-1 | ✅ 结论确定 |

## 6. 结论与处置

- **P-101 主线成立**：A4-1 正向（6 工具全有 schema、等价搬迁逐字段相等）与负向（缺/非法 schema 即抛、无 fallback）均真实；P-100 的 D-1 确认关闭（V-8 五组绕过尝试全拒）；D-2 落地正确（核心依赖 + 核心路径不 import mcp）；双环境/宽回归/登记链与自报读数一致。
- **1 项 P2（D-1）不阻塞 M1 验收，但阻塞 M2 开工**：wheel 安装下注册表不在包内 → M2/M3 启动必然失败。**建议 M2（P-103）批内先修 D-1**（包内资源 + packaging job 冒烟），再实现动态注册；否则 M2 的「启动加载」用例在 wheel 场景不成立。
- **2 项 P3**：D-2（不可变告破）、D-3（错误码错配）随 M2 一并收敛（改动面小）。
- **O-1..O-7** 登记；M2..M5 编号顺延 P-103..P-106。
- 按 RULE-5 单向权限，复核未改实现；探针零残留；登记 P-102（T3，同型先例 P-100/P-097/P-095/P-090）。
