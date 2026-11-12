---
id: arc-g3-p3-cleanup-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-p3-cleanup-DESIGN]
upstream: arc-g3-p3-cleanup-DESIGN
---

# 实施：G3 遗留 P3 清理批（P-094）

## 1. 改动边界

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_spine.py` | 修改 | F-1 `n` 缺省省略；F-2 写侧固定 live；F-3 回退顺序；F-4 casefold；F-5 缩进块状态机；F-6 未闭合行内码截断 |
| 2 | `tests/test_claim_spine.py` | 修改 | 新增 6 项（F-1..F-6 各一）；既有 18 项零改动 |
| 3 | `spec/arc-g3-m3-claim-spine/IMPLEMENTATION.md` | 修改 | F-7 计数 18→19 订正（P-094 注记） |
| 4 | `spec/arc-g3-m3-claim-spine/DESIGN.md` | 修改 | F-8 §8 回退顺序订正 + §4/§4.2 增补（P-094 注记） |
| 5 | `tools/spec_runner/sessions/specwf-p083-arc-g3-m3-claim-spine.jsonl` | 修改 | 受控回边 seq 8-9（verify + finalize rebind） |
| 6 | `.github/workflows/ci.yml` | 修改 | F-9 extras job mcp 版本断言 |
| 7 | `spec/arc-g3-p3-cleanup/` 四文档 | 新增 | 本批次 spec |
| 8 | `docs/PROGRESS.md` + `arc-master-roadmap.md` | 修改 | P-094 登记 + 总纲 v1.4f |

## 2. 接口影响

- `annotations_from_stage14` / `extract_claim_markers` / `export_claim_labels` / `verify_claim_trace` / `verify_claim_digests` **签名与返回结构不变**。
- 行为变化（单向）：annotation 可能无 `n`；marker 键恒小写；缩进块/未闭合行内码区域不产 marker；论文回退顺序 22→19→17。

## 3. 实施顺序（先红后绿）

1. 写 6 项新测试（红：F-1 伪 `n=1`、F-2 落盘 `stage-14_v2/`、F-3 取 `§Draft`、F-4 大写不提取、F-5 缩进块提取、F-6 行内码提取）。
2. 实现 `claim_spine.py` 六处修复 → 绿。
3. P-083 两文档订正 + session 回边（digest 在全部回填后最后生成）。
4. CI yml 断言 + 本地 importlib 探针验证。

## 4. 关键实现记录

- `_annotation_for`：`n` 仅当 `count` 为正整数时写入；`n_seeds` 覆盖分支不变。
- `annotations_from_stage14`：`target_dir = run_dir / "stage-14"`（固定 live）；`evidence_locator` 仍指向实际 summary。
- `_paper_text`：顺序 `(stage-22, stage-19, stage-17)`。
- `CLAIM_MARKER_RE` 加 `re.IGNORECASE`；`extract_claim_markers` 捕获组 `.lower()` 入键。
- 逐行扫描新增 `in_indent` 状态：空白行保持状态；围栏判定先行；`^ {4,}\S` 开块；其余非空行闭块。
- `_strip_inline_code`：成对剔除 + 奇数余反引号从末位截断至行尾。
- CI extras job 增 `Assert MCP SDK version` 步（`importlib.metadata` 元组比较 `>= (2,1)`）。

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | 6 项：`test_claim_spine.py` 19→25（P-089 增 1 项后的基线为 19） |
| 红→绿 | 红：6 failed / 19 passed（6 项新用例全红）；绿：**25 passed** |
| 双环境 | 3.13.5 四文件 **125 passed**（claim spine 25 + claim policy + stage claim hooks + offline audit）；3.11.15 **125 passed** |
| 相关回归 | M1-M5 十文件 **199 passed**；扩展组（rc_executor+hooks+policy+sidecar+verifier_wiring+artifact_node+pipeline_summary+stage_events+mandate+k5_wiring）**348 passed** |
| CI 断言探针 | 本机 `importlib.metadata.version("mcp")` = 2.3.0 → 元组 (2,3) ≥ (2,1) ✅；ci.yml YAML 解析通过，extras job 三步在位 |
| 门禁 | DC 0 违规；step-gate 5/5（P-094）+ P-083 回边后 legacy 一致；pre-commit 9/9 Passed；`digest_bound=1`（单声明 P-094，finalize 文件表覆盖双 feature 八文档） |

## 6. 验收边界（诚实口径）

- F-9 的最终有效性由 CI 实跑（GitHub Actions）确证，本批提供本地探针与 yml 读码证据。
- P-084 O-4（论文 live-or-latest）与 P-086 O-1（标题行内标记）保持登记遗留，不在本批。
- casefold 使 `[C-DEADBEEF]` 这类大写未知 id 进入 `unknown_claim_marker` 判红路径——比静默更严格，符合 fail-closed。

---
