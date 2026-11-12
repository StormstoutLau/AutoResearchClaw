---
id: arc-g3-p3-cleanup-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-m3-claim-spine, arc-g3-m3-claim-fixes, arc-g4-mcp-alignment]
upstream: arc-g3-recheck-d1
---

# 调研文档：G3 遗留 P3 清理批（P-094）

> **Feature**：P-094，G3 收口后遗留 P3 一次性清理（用户裁决「清理全部遗留 P3」）。
> **Spec 步骤**：Step 1-2（T1 修复批：六项 claim spine 静默面 + 一项登记面订正 + 一项 CI 断言）。
> **结论先行**：全部 8 项遗留均有可落地的最小修复，零阻断依赖；唯一前置是 P-083 四文档订正须走 digest 受控回边（门禁机制已验证，P-085/P-089 有先例）。

## 1. 调研目标

清点并验证 G3 全部登记遗留的修复落点：

1. P-083 O-3：`IMPLEMENTATION.md` §5 测试计数偏差（写 18 实 19）——登记面订正。
2. P-084 D-3/D-4/D-5/D-6：annotation `n` 伪造、版本化 stage-14 落盘目录、论文回退顺序、大写标记静默面。
3. P-086 O-2/O-3：缩进代码块、未闭合行内码两处提取器形态缺口。
4. P-093 §6.3：CI extras job 缺 mcp 版本断言。

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 复核报告回源（E1） | [P-084 复核](../../docs/arc-g3-m3-review-20261112.md)、[P-086 复审](../../docs/arc-g3-m3-claim-fixes-review-20261112.md) 的 X/D/O 表 | ✅ 8 项全部定位 |
| 读码（E3） | `claim_spine.py` 五接口现状 | ✅ 六处落点逐行确认 |
| 读码（E3） | `.github/workflows/ci.yml` extras job | ✅ 冒烟只 `import mcp`，无版本断言 |
| 本机探针（E2） | `mcp` 2.3.0 是否暴露 `__version__` | ❌ **无该属性** → P-093 §6.3 建议形式须订正 |
| 门禁机制读码（E3） | `step_enforce.py` `verify_digests` + P-083 session | ✅ 受控回边路径可复用（7 行含回边先例） |

**降级链记录**：无跳过；mcp 属性探针为唯一反证发现（见 R-7）。

## 3. 现状取证

### 3.1 六项静默面（claim spine）

| # | 来源 | 现状读码（`claim_spine.py`） | 触发面 |
|---|---|---|---|
| D-3 | P-084 X-5 | L187：`"n": int(count) if isinstance(count, int) and count > 0 else 1`——`count` 缺失时伪造 `n=1` | `metrics_summary` 条目缺 `count`（如 mean-only 条目） |
| D-4 | P-084 X-7 | L258：`target_dir = summary_path.parent`——仅版本化 `stage-14_v2/` 存在时 annotation 写入版本化目录，Stage 20/23 读 live `stage-14/` 静默缺席 | 重跑版本化场景（P-083 DESIGN §5.6 本就要求写 `stage-14/`，属实现偏离） |
| D-5 | P-084 X-8 | L316-325：`_paper_text` 顺序 `stage-22 → stage-17 → stage-19`——final 缺失时取**较旧草稿**而非修订稿 | final 缺失且 17/19 并存（P-083 DESIGN §8 本身即缺口，属设计订正 + 一行实现） |
| D-6 | P-084 X-2 | L23：`CLAIM_MARKER_RE` 区分大小写，`[C-11111111]` 静默忽略 | LLM 大写复述 claim id（与 `CLAIM_ID_RE` 小写口径同族） |
| O-2 | P-086 X-3 | 提取器无缩进块状态，4 空格缩进块内 marker 被当正文提取 | 示例以缩进块呈现（D-1 误阻断路径残留面） |
| O-3 | P-086 X-5 | L293：`_INLINE_CODE_RE.sub` 只剔成对行内码，未闭合单反引号内 marker 被提取 | 未闭合行内码形态（U-2 同族） |

### 3.2 登记面与 CI 面

- **P-083 O-3**：[IMPLEMENTATION §5](../arc-g3-m3-claim-spine/IMPLEMENTATION.md) L65 写「新增 18 项（…`test_stage_claim_hooks.py` 2）」，P-084 V-5 复计实为 19（`stage_claim_hooks` 写 2 实 3）。订正即改 P-083 四文档 → digest 失配 → 走受控回边（verify step_seq=4 + finalize step_seq=5 带 `rebind_reason` + 新 digest；P-085 session 行 6-7、P-089 均有先例）。
- **D-5 设计面**：[P-083 DESIGN §8](../arc-g3-m3-claim-spine/DESIGN.md) L165 顺序 `22 → 17 → 19` 本身即缺口（P-084 判「实现忠实设计，属设计缺口」）→ 与实现一并订正，同一受控回边覆盖。
- **P-093 §6.3**：CI extras job「Verify imports」仅 `import fastapi, uvicorn, httpx, mcp`；建议加版本断言。**订正**：`mcp` 2.3.0 无 `__version__` 模块属性（本机探针），须用 `importlib.metadata.version("mcp")` + 元组比较。

## 4. 修复选项分析

| # | 选项 | 权衡 | 判定 |
|---|---|---|---|
| R-1（D-3） | ① `n` 省略；② 置 `null` | 省略与 `ci` 的「仅当有值写入」口径一致（DESIGN §4 L87），下游不须判空 | **① 省略** |
| R-2（D-4） | annotation 固定写 live `stage-14/`；读取侧回退 | 写侧一行即闭环（P-083 DESIGN §5.6 原文如此）；读取侧已有 live-or-latest（`_live_or_latest`） | **只改写侧** |
| R-3（D-5） | 顺序改 `22 → 19 → 17` | 修订稿必新于草稿；P-084 O-4 的 live-or-latest 论文回退**不在本批范围**（登记遗留） | **一行顺序订正** |
| R-4（D-6） | ① 提取侧 casefold；② 文档声明静默 | ① 真实修复 LLM 大写复述面，键归一小写与 claim id 口径一致；② 只是把静默写成文档。fail-closed 方向：casefold 后未知大写 id 仍判红 | **① casefold** |
| R-5（O-2） | 缩进块状态机（≥4 空格 + 非空行开块，空行不断块，低缩进非空行闭块） | 与围栏状态互不干扰（围栏判定先行）；单向减少 marker（不新增） | **状态机** |
| R-6（O-3） | 成对剔除后若余反引号为奇数，从最后一个反引号截断至行尾 | 未闭合跨度内全部内容按行内码处理（fail-closed 方向：只减 marker） | **奇数截断** |
| R-7（CI） | `importlib.metadata.version("mcp")` 元组比较 `>= (2,1)` | P-093 原建议 `mcp.__version__` 不存在；元组比较避免字典序陷阱 | **订正后采纳** |

## 5. 幻觉抑制审查（Step 2 Review）

| 引用/声明 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| D-3..D-6 六处落点行号 | P-084 X-2/X-5/X-7/X-8、P-086 X-3/X-5 | 读码复核 L23/L187/L258/L316 | ✅ E3 |
| P-083 计数 18 vs 19 | P-084 V-5 | git diff 计数（复核报告一手） | ✅ E1（沿用） |
| P-083 DESIGN §5.6 要求写 stage-14 | P-083 DESIGN L134 | 读码 | ✅ E3 |
| mcp 无 `__version__` | 本机 2.3.0 探针 | `getattr(mcp, '__version__', None)` → None | ✅ E2 |
| 受控回边先例 | P-085/P-083 session 行 6-7 | 读 session 文件 | ✅ E1 |

### 待修正项

- [x] P-093 §6.3 的断言形式（`mcp.__version__`）→ 本报告 R-7 订正为 `importlib.metadata`，DESIGN/IMPLEMENTATION 采用订正形式。

## 6. 对上文的输入

1. **六项静默面**全部为单向 fail-closed 方向修复（只减 marker / 只省字段），不弱化任何既有判红路径。
2. **P-083 订正**合并为一个受控回边（IMPLEMENTATION 计数 + DESIGN §8 顺序），P-083 session 追加 2 行（verify + finalize rebind）。
3. CI 断言订正 P-093 原建议形式，登记于本 feature IMPLEMENTATION。

## 7. 参考文献

- [P-084 复核报告](../../docs/arc-g3-m3-review-20261112.md)（D-1..D-6、O-1..O-6）
- [P-086 复审报告](../../docs/arc-g3-m3-claim-fixes-review-20261112.md)（O-1..O-5）
- [P-093 RESEARCH §6.3](../arc-g4-mcp-alignment/RESEARCH.md)（CI 版本断言建议）
- [P-083 DESIGN/IMPLEMENTATION](../arc-g3-m3-claim-spine/)（订正对象）
- [SPEC_PROCESS 受控回边](../SPEC_PROCESS.md)（U-1 约定）

---
