# P-103 复核子批：G4-M2 动态注册 + listChanged 接缝 + `GET /api/tools`（2026-11-14）

> **性质**：Layer-0 独立异构复核（T3 轻批，零生产代码/零门禁写入）。**不采信** [P-103 实施](../spec/arc-g4-m2-dynamic-tools/IMPLEMENTATION.md) 与复核简报的任何结论，全部一手重验：HEAD `d0eea78` 读码、双环境测试复跑、CI 固定清单宽回归、wheel 实构建、session digest 逐文件复算、17 组对抗探针。
> **异构性**：实施会话为 **GLM-5.3-Flash**（`specwf-p103-arc-g4-m2-dynamic-tools.jsonl` model 字段），本复核为 **DeepSeek-V4.1-Flash**——RULE-5 交叉成立。
> **编号**：用户裁决（2026-11-12）复核批**并入 P-103，不占独立编号**；M3..M5 = P-104..P-106 不变，M0 DESIGN 无需第三次编号回边，P-103 session 既有行未改动。
> **单向权限**：只标记问题，不改实现；探针零残留（临时脚本与产物已清理，X-9 扰动文件已按 sha256 校验还原）。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | registry 24 + dynamic 12 = 76 | `--collect-only -q` | ⚠️ registry **24** ✅ / dynamic **10**（非 12）；总数 76 = 24+10+42 仍成立 |
| V-2 | 3.13.5 四套件 76 passed | 复跑同四文件 | ✅ 76 passed（2.91s） |
| V-3 | 3.11.15 74 passed / 2 skipped | `uv run --python 3.11 --with mcp --with fastapi …` | ✅ 条件口径：含 fastapi 时 **76 passed**；不含 fastapi 时 74/2skip |
| V-4 | 宽回归 295 passed / 5 skipped | 按 `ci.yml` 固定清单 40 文件复跑 | ❌ **1 failed / 600 passed / 13 skipped**；失败点见 D-1。295/5 口径无文件清单，且遗漏该失败 |
| V-5 | wheel 冒烟（D-1 关闭） | `uv build --wheel` 实构建 | ❌ **构建失败**（D-1） |
| V-6 | 21 文件 +1135/−116 | `git show --stat HEAD` | ✅ |
| V-7 | P-103 session 5 行 / 1 finalize / digest 8 文件 | 本地 sha256 逐文件复算 | ✅ 5 行、8 文件零 mismatch |
| V-8 | M0 受控回边 + 总纲 v1.4o | 读 P-099 session + `git show` | ✅ seq8/9 两次 rebind（`reason` 在位）、v1.4o 修订段在位 |
| V-9 | REST 白名单 | T-6 复跑 + 读码 | ✅ 无 `handler`/`sandbox_profile`，8 字段与 M0 §3.1 一致 |
| V-10 | 启动 fail-closed | 路由 seam 探针 X-15 + 读码 `app.py` L133 | ✅ `E_REGISTRY_HANDLER_UNRESOLVED` 冒出；app 工厂内直接调用（app 级直测受 `RCConfig` 构造阻塞，见 §5 限制） |
| V-11 | adapter 零硬编码 | T-4 复跑 + 读码 | ✅ 无工具名字面量 |

## 2. 对抗探针（X 表，17 组实测）

### 2.1 缺陷（3 项）

| # | 探针 | 实测 | 判定 |
|---|---|---|---|
| X-8 | **真实构建 wheel** | `ValueError: A second file is being added to the wheel archive at the same path: 'researchclaw/tools/registry.yaml'`——包内副本已存在，`force-include` 又把仓库根文件映射到同一路径 | **D-1 P1** |
| X-16 | 真实注册表最小参数调用，记录 dispatcher 实收 kwargs | `run_pipeline` 收到 `{"topic":"x","config_path":null,"auto_approve":null}`；`search_literature` 收到 `{"query":"q","max_results":null}`；`review_paper` 收到 `{"paper_path":"…","run_id":null}` | **D-2 P2**：可选参数一律以 `null` 注入；`auto_approve` 由默认 `True` 变 `bool(None)=False` |
| X-17 | `spec.resolve()` 返回对象类型 | 6 个 handler **全部**解析为 `ResearchClawMCPServer` **类**（`isclass=True`） | **D-3 P2**：V-5b 只证「可导入」，未证「可调用」；M3 invoker 直接调用会构造新 server |

### 2.2 通过项

| # | 探针 | 结果 |
|---|---|---|
| X-1 | `probe_a` 传 `{"topic":123}`（schema: string） | ⚠️ **通过**，dispatcher 收到 `123`——运行时类型不校验 → **H1 成立** |
| X-2 | 未声明键 `{"topic":"x","bogus":1}` | ⚠️ 静默丢弃（handler 只见 `topic`）→ H1 |
| X-3 | 缺必填 `{}` | ✅ `ToolError: Field required`（合成签名 required 生效） |
| X-4 | `anyOf` 二选一传 `{}` | ⚠️ **通过**，且收到 `{"a":null,"b":null}` → H1 + `null` 注入 |
| X-5 | refresh 后旧工具集合 | ✅ `['probe_a','probe_d']`，旧 `probe_b` 已移除 |
| X-6 | monkeypatch `remove_tool` 抛错 → refresh | ⚠️ 被 `except Exception: pass` 吞掉，refresh 仍返回 OK；SDK `add_tool` 以 WARNING 覆盖既有注册（无重复项）→ **O-3**，非 P 级 |
| X-7 | `RC_TOOL_REGISTRY` 指向坏注册表 → 路由 seam | ✅ `E_REGISTRY_HANDLER_UNRESOLVED` |
| X-9 | 仅改仓库根 yaml 语义（`cpu: 2→3`）→ T-R1 | ✅ 变红（`1 failed`），漂移防护有效；随后按备份 + sha256 还原 |
| X-10 | handler 模块不存在 | ✅ `E_REGISTRY_HANDLER_UNRESOLVED` |
| X-11 | stdio session 可达性 | ✅ 证据成立：`hasattr(connection/_session/request_context)` 全 `False`；`server.session_manager` 属性激活即抛 `RuntimeError: Session manager can only be accessed after calling streamable_http_app()` |
| X-12 | 同注册表重复注册 | ⚠️ WARNING `Tool already exists` + 覆盖，无重复项 → O-4 |
| X-13 | `risk=high + approval=never` 经 adapter 加载路径 | ✅ `E_REGISTRY_APPROVAL` |
| X-15 | `routes.tools.get_registry()` + 坏 env | ✅ `E_REGISTRY_HANDLER_UNRESOLVED`（lazy 但 fail-closed） |

## 3. 缺陷

### D-1（P1）wheel 构建失败：`force-include` 与包内副本同路径冲突，且违反既有打包契约测试

- **根因**：P-103 同时新增 `researchclaw/tools/registry.yaml`（包内 canonical）并在 `pyproject.toml` L58 加 `force-include = {"tools/registry.yaml" = "researchclaw/tools/registry.yaml"}`。hatchling 对同一归档路径写入两次 → `ValueError`，构建中止。
- **第二证据**：既有测试 `tests/test_packaging.py::test_wheel_does_not_force_include_package_data`（该文件在 CI 固定清单 L111，早于本批存在）显式断言 `"force-include" not in wheel`，P-103 使其变红。按 CI 固定清单复跑：**1 failed / 600 passed / 13 skipped**。
- **影响**：① CI `packaging` job 在 `python -m build --wheel`（ci.yml L24）即失败，后续 wheel 冒烟与 `researchclaw --help` 均不执行；② CI `contract` job 在 3.11/3.12/3.13 三档全红；③ `pip install .` 不可用；④ **D-1 未关闭**，总纲 v1.4o「packaging 冒烟」与 CHECKLIST「T-R1 + CI packaging 冒烟 ✅」不成立（该 job 从未真实跑过构建）。
- **修复建议**：**删除 `force-include` 整行**（保留包内副本；hatchling 对 `packages=["researchclaw"]` 默认包含包内非 .py 数据文件），符合既有契约测试；不采用「删包内副本、保留 force-include」——与既有测试语义冲突。修后须本地实跑 `python -m build --wheel` + `pip install dist/*.whl` + `load_registry()` 三重冒烟。
- **回归护栏**：`test_packaging.py` 保留（它已捕获本缺陷）；建议在 `test_packaging.py` 或 CI 增加「构建后 zip 内存在 `researchclaw/tools/registry.yaml` 且无重复路径」断言。

### D-2（P2）可选参数以 `null` 注入，`run_pipeline.auto_approve` 默认值由 `True` 静默翻转为 `False`

- **机制**：`_make_call` 对非 required 属性生成 `default=None` 的 KEYWORD_ONLY 参数；SDK `Tool.run` 经 `arg_model` 校验时把未传字段填成 `None` 并原样传给 dispatcher（X-4/X-16 实证，六个工具的可选参数全部呈现 `null`）。
- **回归事实**：`0648e2a` 的 legacy 签名 `async def _run_pipeline(topic, config_path=None, auto_approve: bool = True)`；handler `auto_approve = bool(args.get("auto_approve", True))`。旧路径省略该参数 → `True`；新路径收到 `None` → `bool(None)=False`。
- **影响**：MCP 客户端只传 `topic` 时，pipeline 从「自动过 gate」变成「停在 gate 等审批」，行为静默改变，且现有 42 项 MCP 测试只锁 schema 等价、未覆盖参数语义，测试无法捕获。
- **修复建议（择一）**：① 从注册表 schema 的 `default` 生成签名默认值，无 `default` 的可选参数不设 `None`（需解决「kw-only 无默认必须排在最后」——可全部 optional 置后，或改用 `**kwargs` + 仅被 SDK 采信的 `__signature__`）；② 在 `_dispatch_tool` 过滤「值为 `None` 且 schema 无 default」的键（不下发 None），并在 DESIGN 登记语义。无论哪种，须补回归用例：`run_pipeline` 最小参数 → handler 收到 `auto_approve=True`。

### D-3（P2）注册表 `handler` 全部指向类对象，V-5b「可解析」≠「可调用」

- **实证**：`tools/registry.yaml` 6 条均为 `handler: "researchclaw.mcp.server:ResearchClawMCPServer"`；`ToolSpec.resolve()` 返回类（`inspect.isclass=True`）。`load_registry(strict_handlers=True)` 仅 `importlib` + `getattr`，故全部通过。
- **影响**：M3 invoker 若按契约调用 `spec.resolve()(name, kwargs)`，会以参数构造一个新的 `ResearchClawMCPServer`（`TypeError` 或构造副作用）。当前 M2 因 dispatcher 旁路而未爆炸，属「M3 前置缺陷」。
- **修复建议**：handler 改指向真实调用点（例如 `researchclaw.mcp.server:ResearchClawMCPServer._dispatch_tool` 或模块级 `dispatch_tool` 函数并同步注释语义）；至少在加载期加 `callable(obj) and not inspect.isclass(obj)` 校验（复用 `E_REGISTRY_HANDLER` 或新增码），并在 M0 §9 登记为 M3 前置。

### D-4（P3）DESIGN 与实现三处漂移

| # | DESIGN 声明 | 实现事实 |
|---|---|---|
| 1 | §3.1 `register_from_registry(server, registry, dispatcher, *, notifier=None)` | 无 `notifier` 参数（仅 `refresh_from_registry` 有） |
| 2 | §5 `_dispatch_tool` 返回 `self._as_result(...)` | 返回裸 dict（IMPL §2 已记录，DESIGN 未回填） |
| 3 | §4「启动时模块级 `load_registry(strict_handlers=True)`」 | lazy `REGISTRY=None` + `app.py` L133 调用 |

### D-5（P3）自报读数与取证口径失准

- dynamic「12 项」实为 **10** 个测试函数（无参数化展开）。
- 「宽回归 295 passed / 5 skipped」无文件清单、不可复现；按 CI 固定清单复跑为 **1 failed / 600 passed / 13 skipped**，且失败点正是本批引入。
- 「packaging 冒烟绿」未经真实构建（V-5 实测失败）。
- 属 E1 取证范围选择问题：宽回归疑似未包含 `tests/test_packaging.py`，恰好漏掉唯一能捕获 D-1 的既有测试。

## 4. 观察项（O 表）

| # | 内容 | 处置 |
|---|---|---|
| O-1 | `inputSchema` 的显示真值（`Tool.parameters`）与运行时校验真值（`fn_metadata.arg_model`，SDK `base.py` L152）分离：类型/`anyOf`/多余键不受注册表约束 | 建议在 M2 DESIGN 增一节说明 A4-10「一致」仅指 `list_tools()` 输出；若 M3 invoker 承担运行时校验则自然收敛 |
| O-2 | 未知键静默丢弃（X-2）与未知注册表键静默忽略（P-102 O-1 沿袭） | 记录 |
| O-3 | `refresh_from_registry` 的 `except Exception: pass` 吞 `remove_tool` 失败（X-6）；当前因 SDK 覆盖式 `add_tool` 未致重复 | 建议改为记录 warning 或仅在确知 SDK 语义时收窄异常 |
| O-4 | 重复注册同名工具：WARNING + 覆盖，无重复项（X-12） | 记录 |
| O-5 | T-R1 为语义相等（`yaml.safe_load`），空白/注释级漂移不触发（X-9 首轮实测通过） | 记录；若需字节级一致性另立断言 |
| O-6 | `__registry_handler__` 只写不读（全仓 1 处 `setattr`，0 处读取） | 删除或由 M3 invoker 启用 |
| O-7 | M0 DESIGN §9 M2 行仍写「实施中」（L164）；§3 L91 假设的 `server.connection` 路径经 X-11 证否（属性不存在） | 收敛时一并回填：M2 状态、`session_manager` 懒加载即抛的事实 |
| O-8 | `outputSchema` 6 工具均为 `{type: object}`，无返回体抽样支撑（P-102 O-2 沿袭） | 记录 |

## 5. 取证矩阵（RULE-6）

| 手段（等级） | 覆盖 | 结果 |
|---|---|---|
| pytest 双环境（E1） | V-1..V-4 | 24/10 collected；3.13.5 76 passed；3.11.15 76 或 74+2skip（依 fastapi）；CI 清单 1F/600P/13S |
| digest 复算 + git show（E1） | V-6/V-7/V-8、旧版签名 | ✅ 8 文件零 mismatch；21 文件边界吻合；legacy `auto_approve: bool = True` 取证 |
| wheel 实构建（E2） | V-5 / X-8 / D-1 | ❌ duplicate path，构建中止 |
| 运行时探针（E2，17 组） | X-1..X-17 | **1 P1 + 2 P2**，另有 O-1..O-6 |
| 读码（E3） | SDK `tools/base.py` L152、`utilities/func_metadata.py` L112；`registry_adapter.py`；`routes/tools.py`；`app.py` L130-133；M0 §3 L90-92 / §3.1 L96 | ✅ H1/H4/H6 机制定位 |
| 盲区扫描（E4） | 工具名字面量、`__registry_handler__` 引用、handler 类型、CI 清单覆盖、`test_packaging.py` 归属 | ✅ 发现 D-3/D-5/O-6 |

**E2 限制（诚实声明）**：app 级 fail-closed 未做直接构造探针——`RCConfig` 需 7 个必填段，未在零残留约束下最小化构造；以路由 seam 实测（X-15）+ `app.py` L133 读码为证，等级记为 E2+E3 组合而非纯 E2。

## 6. 结论与处置

- **主线部分成立**：A4-10 前半（`list_tools()` 与注册表 deep equality）、后半（追加条目无需改代码）、REST 白名单、启动 fail-closed、listChanged 阻塞点（X-11 证据成立）、D-2/D-3（P-102）关闭，均经一手复验为真。
- **D-1 未关闭（P1）**：wheel 构建失败 + 既有打包契约测试红 + CI 两 job 红。这是构建阻断级缺陷，**P-103 暂不能验收关闭**，且 D-1 的「已关闭」结论不成立。
- **P2 ×2**：D-2 可选参数 `null` 注入导致 `auto_approve` 默认翻转（真实行为回归，测试未覆盖）；D-3 handler 指向类对象（M3 前置缺陷）。
- **建议处置顺序**：① 删 `force-include` → 本地 `python -m build --wheel` + 装 wheel + `load_registry()` 三连冒烟；② 修 `_make_call` 默认值语义 + 补「最小参数」回归用例；③ handler 指向真实调用点或加载期拒绝类对象；④ 回填 DESIGN 三处漂移与 M0 状态/§3 L91 事实；⑤ 复跑 CI 全清单 + 双环境 + digest 重绑。
- 按 RULE-5 单向权限，本复核未改任何实现文件；X-9 扰动已还原（sha256 `8c9e34bb` 一致）；探针脚本与构建产物全部清理。

## 7. 收敛复验（2026-11-13，同一复核子批）

> **范围**：仅复验 D-1/D-2/D-3/D-4/D-5/O-6 的关闭主张（实施方 GLM 的 v1.1 修复），不重开主线验收。**基线**：`d0eea78` + 20 文件暂存（+345/−70），未提交。**方式**：一手复跑 + 独立探针（新临时目录，零仓内写入）。

### 7.1 一手复验（V2 表）

| # | 主张 | 方式 | 结果 |
|---|---|---|---|
| V2-1 | 修复边界 20 文件 | `git status --short` / `diff --cached --stat` | ✅ 与 IMPL §1 十三项吻合 |
| V2-2 | 四套件 79 passed；collect 25+12 | 复跑 + `--collect-only` | ✅ 79 passed；37 collected（registry 25 + dynamic 12，MCP 42 → 合计 79） |
| V2-3 | CI 固定清单 0 failed | 40 文件全量复跑 | ✅ **604 passed / 13 skipped，0 failed**（复核时为 1 failed） |
| V2-4 | 3.11 含 extras 79 passed | `uv run --python 3.11 --with …` | ✅ 79 passed |
| V2-5 | wheel 三连（D-1 关闭） | 独立 `uv build --wheel` + zip 检查 + 装 target | ✅ 428 entries、零重复路径、恰一份 `researchclaw/tools/registry.yaml`；装后 `load_registry()` 6 tools，handler 全为 `dispatch_tool` |
| V2-6 | session 追加 + digest 绑定 | `git diff --cached --numstat` + `step_enforce.py` | ✅ **2 插入 / 0 删除**（seq1-5 未被改写）；`digest_bound=1` |
| V2-7 | force-include 已移除 | 读 `pyproject.toml` + grep | ✅ 无配置项（仅两行说明注释）；`test_packaging.py` 在 V2-3 中复绿 |

### 7.2 独立探针（X2 表）

| # | 探针 | 实测 | 判定 |
|---|---|---|---|
| X2-1 | 6 条 handler 解析类型 | 全部 `function`、`callable=True`、`isclass=False`、`iscoroutinefunction=True` | D-3 关闭 |
| X2-2 | 类 handler 经 strict load | `E_REGISTRY_HANDLER`；非 strict（格式级）仍放行 | D-3 关闭（分层正确） |
| X2-3 | `dispatch_tool` 端到端 | `get_pipeline_status` 返回 `{"success": false, "error_code": "RUN_NOT_FOUND", …}` | 调用点真实可执行 |
| X2-4 | 真实注册表最小参数（4 工具） | 实收 `{"topic":"x"}` / `{"query":"q"}` / `{"run_id":…}` / `{"paper_path":…}`，**无任何 null 可选键** | D-2 关闭 |
| X2-5 | 显式 `null` 可选参数 | 被丢弃（`{"topic":"x"}`） | 语义边界：显式 null 与省略不可区分（记录） |
| X2-6 | 必填参数显式 `null` | 透传 `{"topic": null}` → handler `str(None)` = `"None"` | **O-10**（既有 O-1 家族：运行时不做类型校验；M3 关闭） |
| X2-7 | 全仓 `__registry_handler__` | 代码 0 引用（仅文档留痕） | O-6 关闭 |
| X2-8 | DESIGN 残留 | §1 表第 3 行、§2.1 仍以 `force-include` 描述 D-1 修复，未标注被 §10 取代 | **O-9**（P3 级文档清晰度） |
| X2-9 | DESIGN §10 拒绝理由 | 「无 default 的可选参数会变成 required」不成立（默认仍为 `None`，不会变 required） | **O-12**（理由需订正；决策本身可保留） |

### 7.3 结论

- **D-1（P1）关闭**、**D-2/D-3（P2）关闭**、**D-4 基本关闭**（仅 O-9 两处残留描述）、**D-5 读数已订正**（79 / 604+13 / 428 与实测一致）、**O-6 关闭**。
- 新增 O 级（不阻塞）：**O-9** DESIGN 残留 force-include 表述；**O-10** 必填参数显式 null 穿透（`topic:null → "None"`，M3 invoker 校验面关闭）；**O-11** `dispatch_tool` 首次调用会构造完整默认 server 实例（含二次注册），M3 应改为复用/注入；**O-12** DESIGN §10 拒绝理由技术表述不成立。
- **复核意见：v1.1 修复验收通过，可提交**；O-9/O-12 建议随下次文档触碰顺带订正，O-10/O-11 登记为 M3（P-104）前置输入。
- 单向权限：本次复验未改任何实现或 spec 文件，仅追加本节；探针与 wheel 构建产物已清理，工作树仅保留实施方已暂存的修复集。
