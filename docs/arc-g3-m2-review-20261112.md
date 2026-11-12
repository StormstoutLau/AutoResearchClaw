# P-079 对 P-078 G3 M2 的独立异构复核（2026-11-12）

> **性质**：Layer-0 独立异构复核（T3，零生产代码）。不采信 [P-078 实施](../spec/arc-g3-m2-stage-events/IMPLEMENTATION.md) 结论，全部一手重验：读码、双环境测试复跑、11 组异构探针（伪锚两形态/并发追加/空签名/无 id 结果集/双行坏尾/豁免穿插/大小写/seq 接续/窗口退化/写读集成）。**异构性**：复核会话与实施会话为不同模型基座（RULE-5）。
> **编号说明**：本批占用 **P-079**；M3/M4/M5 由 v1.3p 的 P-079/P-080/P-081 顺延为 **P-080/P-081/P-082**（沿 P-077 让位先例）。

## 1. 一手复验（V 表）

| # | 声明 | 方式 | 结果 |
|---|---|---|---|
| V-1 | M2 套件 30 passed（3.13.5） | 复跑 `test_stage_events + test_pipeline_summary_check` | ✅ 30 passed |
| V-2 | 3.11.15 同读数 | uv 临时 venv（3.11.15）复跑 | ✅ 30 passed |
| V-3 | 相关回归 99 passed | 复跑六文件组合 | ✅ 99 passed |
| V-4 | 接线顺序：护栏在 checkpoint 前、锚点在 summary 写后 | 偏移量静态核对 + 集成测试断言（checkpoint 停在 stage 5） | ✅ |
| V-5 | 锚点只由顶层执行写（`owns=True`） | 读码 `_emit_summary_anchor` + `test_emit_summary_anchor_skips_nested_execution` + `test_events_disabled_skips_anchor` | ✅ |
| V-6 | `EVENT_TYPES` 前后端同步 | 读码两端 + 既有对齐测试在回归套件内通过 | ✅ |
| V-7 | FC-1..3 断言非恒真 | 逐条核对：`action=pause` 且 `code` 精确匹配、`consecutive` 精确值、checkpoint/sidecar 副作用断言 | ✅ |
| V-8 | D-2 三回归真实 | `test_second_anchor_in_same_segment_is_rejected`（field=duplicate_anchor）/ payload 篡改 / 跨段放行 | ✅ |
| V-9 | PROGRESS P-078 行、总纲 v1.3p、CI 清单含 `test_stage_events.py` | 比对 | ✅ |
| V-10 | DC 四文档 0 违规 | dc_validator 复跑 | ✅ |
| V-11 | session 5/5 | step-gate --expect 全链 | ✅ exit 0 |
| V-12 | IMPLEMENTATION 读数与实测一致 | §5 表逐项比对 | ✅ |

## 2. 异构探针（X 表）

| # | 探针 | 结果 | 定性 |
|---|---|---|---|
| X-1 | 伪锚追加（digest ≠ 当前 digest） | 末锚检查判红 | 无缺陷（探针初版构造错误，撤回） |
| X-1b | **同域一致重写**：summary + 侧车 + 新段伪锚（digest = 被篡改 summary 的 digest） | 三向全过，`ok=True` | **边界声明属实**——DESIGN §4.2 诚实声明的绕过面真实存在，无夸大 |
| X-2 | 8 线程并发 `record_stage_progress` | 8 行全落盘、seq 有序、零丢失零重复 | 无缺陷（依赖 GIL/IO 原子性实现细节，见 O-3） |
| X-3 | `queries.json` 存在但 queries 为空列表 | `plan_payload` 返回 payload（queries=[]），`plan_sig` 正常产出 | 无缺陷（空计划 ≠ 缺计划，签名可区分） |
| X-4 | 两轮结果集均无 id/paper_id/doi/title（仅 abstract），内容完全不同 | 第 3 轮 `action=pause` | **P3-2 独立确认**：无 id 行跨内容同 digest，存在误暂停风险 |
| X-5 | 末尾**连续两行**损坏 | 倒数第二行抛 `StageEventError` | 与设计一致（「仅末行容忍」），探针构造了设计外场景，撤回；登记 O-1 |
| X-6 | 同签名轮中间穿插 `network_error=true` 轮 | 豁免轮不重置不计数，consecutive 跨它累计至 3 → pause | 无缺陷（语义符合 DESIGN §3.3） |
| X-7 | 锚点 digest 大写 | `E_SUMMARY_TAMPERED` | 无缺陷（与 M1 侧车严格口径一致） |
| X-8 | 手写 seq=99 后追加 | 新 seq=100 | 无缺陷 |
| X-9 | `window=0` / `-5` / `10` | 0/负数立即 pause；10 不 pause | 无缺陷（window 仅内部常量调用；登记 O-2） |
| X-10 | 真实 `EventLog` 写入 → `verify_summary` 读取 | 集成通过 | 无缺陷（写读编码一致） |

## 3. 缺陷

**零 D 级缺陷。** 两个初判 FAIL 经复判均为探针构造与文档语义的偏差（X-1 撤回见上表；X-5 按设计语义正确），沿 P-077 X-7 先例记「探针缺陷，撤回」。

## 4. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | `load_stage_events` 仅容忍**单行** torn tail；`EventLog.read_all` 对 active segment 容忍任意尾坏行——两套读侧语义不一致，崩溃后多行半写会 fail-closed | 一致性；M3/P-080 统一 |
| O-2 | `evaluate_loop` 的 `window` 参数无下界校验（≤0 恒 pause）；当前仅 `LOOP_WINDOW=3` 内部调用，外部误用风险低 | 加固 |
| O-3 | X-2 并发零丢失依赖 CPython GIL 与单行 append 的实现细节，非契约保证；U-3 单写者假设仍需 P-080（D-1 修复批）裁决文件锁方案 | 设计输入 |
| O-4 | X-4 确认的 P3-2（无 id 结果集同构）在真实文献场景依赖上游 id 稳定性；U-2（Stage 5 元数据产物）落地时应一并补 id 缺失兜底 | 设计输入 |

## 5. 结论与处置

- **P-078 主线成立**：V-1..V-12 全过；30 passed 双环境读数、接线顺序、边界诚实登记全部属实。
- **D-2 修复有效**：X-1/X-7 证伪锚追加路径全部判红；X-1b 证实能力边界声明准确（不承诺抗一致重写）。
- **零 D 级缺陷**；O-1..O-4 登记为 P-080（修复批）与 M3（claim 脊柱）输入。
- 探针脚本与临时 venv 已按零残留原则删除；登记 P-079（T3，零代码/零门禁，同型先例 P-077/P-072/P-067）。
- 编号顺延：M3/M4/M5 = **P-080/P-081/P-082**。
