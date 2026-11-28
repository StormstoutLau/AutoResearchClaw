---
id: arc-stage10-repair-minimal-edit-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-minimal-edit-RESEARCH]
upstream: arc-stage10-repair-minimal-edit-RESEARCH
---

# 设计：Stage 10 修复的作用域与最小改动（P-231）

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| D-1 | 入口缺 `__main__` 守卫时**确定性补丁**：在符号完整的原文件末尾追加 guard，调用已有的零参入口函数；仅当源码无 `METRIC_DEF` 时注入定义行，**指标数值行只在入口返回的 dict 真正含该指标时输出**，否则不打印（不造假数） | L-1/L-2；Codex/Claude Code 的最小编辑实践 |
| D-2 | 结构化**符号契约块**（每文件一行，标注 defined/MISSING）注入入口生成、critical 修复、符号修复三处，替换 `arch_spec[:4000]` | L-2/L-4；aider repo map |
| D-3 | 修复作用域收敛：只针对受影响文件，**每次请求只返回一个文件**；符号修复按文件循环 | L-3；aider whole 格式的成本特征 |
| D-4 | 三个晚写入点（入口重生成、对齐重生成、符号修复）写盘前统一过 `_contract_issues`（语法 + 入口 + 符号），失败则保留旧文件；对齐重生成失败时回滚整组文件 | L-6；Agentless 的 patch validation |
| D-5 | 出口前做「编译 + 隔离导入」冒烟：`compile()` 在进程内逐文件编译，子解释器 `import` 全部模块；交付模块缺失算失败，第三方缺包只告警 | 编译/导入是 Agentless/EviACT 的独立阶段 |
| D-6 | 截断三出口：同一 prompt 最多升级一次；二次截断不再重发，改按文件拆分（每文件 16k→32k 各一次），仍失败即以 `truncated_after_escalation` 交 P-226 止损 | L-5；Claude Code 的「升级→续写→报错」 |
| D-7 | 最小改动约束：修复 prompt 加 preservation 规则；`_accept_repair_files` 拒绝「保留不足一半非空行」的改写；trace 记 `edited_lines` | arXiv 2609.04061；MSR 2026 回滚首因 |

## 2. 被拒绝的替代方案

| 方案 | 拒绝理由 | 代价 |
|---|---|---|
| 继续用 LLM 重生成 main.py，只把符号清单塞进 prompt | 重生成仍会重排、删改既有实现；run O 的 7227 字符产物正是这样丢符号的 | 一次 3–5 分钟调用，且仍有概率失败 |
| 引入 diff / SEARCH-REPLACE 编辑格式 | 需要精确匹配的 pre-image，失败率是另一类高发错误；当前只需单文件整文件返回 | 新增解析器与失败面 |
| 符号缺失时自动插入 stub 定义 | 会伪造实现，让实验「看起来完整」 | 违反不伪造原则 |
| 让 `_extract_multi_file_blocks` 不再把单文件改名为 main.py | 该行为被 Stage 10 生成路径依赖（单发回退） | 影响面大，改为在取回时按请求名恢复（L-7） |
| 用 in-process import 做冒烟 | 生成代码在管线进程内执行，会污染 `sys.modules` 并可能触发实验逻辑 | 必须子进程 |

## 3. 接口与数据流

```
_ensure_entrypoint
  ├─ patch_entrypoint_guard(main, metric)      # D-1：零 token
  │    └─ 无零参入口 / 已有 guard / 语法坏 → None
  ├─ 否则 LLM 重生成（带 D-2 契约块，候选丢符号即拒）
  └─ _contract_issues(candidate, blueprint)     # D-4：写前校验

_ensure_symbol_contract
  └─ for name in sorted(affected):              # D-3：一次一个文件
       _repair_one_file_for_symbols(...)        # D-6：16k → 32k → 放弃
  └─ _contract_issues(merged)                   # D-4

对齐重生成
  └─ _ensure_entrypoint → _ensure_symbol_contract → _contract_issues
       └─ 失败：恢复 _before 并与磁盘同步      # D-4 回滚

CodeAgent._repair_critical_issues
  └─ 组合 prompt（只列受影响文件 + 契约块）
       ├─ 二次截断 → _repair_files_individually  # D-6
       └─ _accept_repair_files（P-222 + D-7 半数守卫）
```

`symbol_contract_block(blueprint, files, limit_files=..., max_chars=2000)` 输出形如：

```
- main.py: ExperimentRunner (MISSING), compute_detection_metrics (MISSING), main (defined)
```

## 4. 验收

- 符号完整但缺 guard → **零 LLM 调用**，两契约同时满足，原文件内容保留；
- 无零参入口 → 走 LLM 路径；
- 声明符号被候选丢弃 → 候选被拒，继续下一 attempt；
- 两个文件缺符号 → 两次独立请求，每次只贴/只要一个文件；
- 二次截断 → 不再出现第三个同尺寸请求；
- 对齐重生成破坏契约 → 磁盘与内存都回到旧版本；
- 保留不足一半非空行的修复 → `catastrophic_rewrite` 拒收；
- 交付模块编译失败 → Stage 10 显式 FAILED；第三方缺包只告警。

## 5. 非目标

- 不改 P-222 的三道静态闸门与 P-226 的止损计数口径；
- 不改 `_extract_multi_file_blocks` 的既有改名行为；
- 不引入 diff 编辑格式、不做会话摘要；
- 不在本批部署或重跑 B 站。
