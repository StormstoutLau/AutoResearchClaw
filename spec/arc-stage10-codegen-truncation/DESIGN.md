---
id: arc-stage10-codegen-truncation-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-stage10-codegen-truncation-RESEARCH]
upstream: arc-master-roadmap
---

# 设计：Stage 10 截断容错与出口门（P-178）

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由与代价 |
|---|---|---|---|
| D-1 | **容错围栏**：抽取前按 ` ``` ` 奇偶补一个闭合围栏；blueprint 正则允许 `\Z` 作为结尾 | 提高 `max_tokens` 后假设一定闭合 | 截断是常态；提高上限只是降低概率。代价：极少数代码字符串内含三个反引号时会误判奇偶 |
| D-2 | **截断感知重试**：`resp.truncated`/`finish_reason=length` 时对 blueprint、单文件、single-shot 各重试一次 32768 | 只按「内容为空」重试 | 截断响应非空但不可解析，旧条件漏掉（RESEARCH R4） |
| D-3 | **评审守卫**：文件为空时跳过 Review；Review 改写文件后强制重跑 hard validation + exec-fix | 关闭 Review；或只在 Review 后记录警告 | 空文件进评审会让模型「凭空造项目」（R3）；关闭 Review 会丢真实的改进能力 |
| D-4 | **出口门**：`main.py` 必须有 `__main__` guard 且出现 `METRIC_DEF`，否则 Stage 10 `FAILED` | 让 Stage 12 兜底 | 失败前移一个 stage，错误信息直接指向入口；代价是某些「合法但不打印指标」的实验设计会被拒（本仓契约要求打印） |
| D-5 | **不改默认 `max_tokens` 与逐文件策略** | 把 8192 全局提到 32768 | 提上限会增加单次延迟与成本，且不解决解析健壮性；逐文件生成已由 D-1 恢复 |

## 2. 算法

### 2.1 围栏闭合（D-1）

```
_close_unterminated_fence(text):
    if text.count("```") % 2 == 1: return text + "\n```"
    return text
```

`_extract_code_block` 与 `_extract_multi_file_blocks` 入口先调用；`_parse_blueprint`
额外剥掉首行 ` ```yaml ` 与结尾 ` ``` `（双保险）。

### 2.2 截断重试（D-2）

```
blueprint: resp ← chat(8192); if resp.truncated: resp ← chat(32768)
单文件:     resp ← chat(8192); if resp.truncated: resp ← chat(32768)
single-shot: files ← extract(resp); if not files and (content or truncated):
                 resp ← chat(32768); files ← extract(resp)
```

### 2.3 评审守卫（D-3）

```
if review_max_rounds > 0 and files:
    before ← copy(files)
    files, rounds ← review(files)
    if files != before:
        if hard_validation: files ← hard_validate(files)
        files ← exec_fix(files)
```

### 2.4 出口门（D-4）

```
_entrypoint_issues(main):
    empty → ["main.py is empty or missing"]
    SyntaxError → ["syntax error ..."]
    无 `if __name__ == "__main__"` → issue
    源码不含 "METRIC_DEF" → issue
```

Stage 10 在最终 `DONE` 之前调用；`files["main.py"]` 为空时回退读取 `stage-10/experiment/main.py`（覆盖外部 CLI agent 直接落盘的路径）。

## 3. 不变式

| ID | 不变式 |
|---|---|
| J-1 | 截断响应（无闭合围栏）也能被单文件/多文件抽取器解析 |
| J-2 | blueprint 在首行 ` ```yaml ` 未闭合时仍可解析 |
| J-3 | 文件为空时 Review 不被调用（`review_rounds=0`） |
| J-4 | Review 改动文件后，最终文件必经过 hard validation 与 exec-fix |
| J-5 | Stage 10 返回 `DONE` 时，`main.py` 一定能执行并打印 `METRIC_DEF` |

## 4. 错误语义

| 场景 | 行为 |
|---|---|
| 截断且重试仍截断 | 交给抽取器（可能得到部分文件）→ 出口门兜底 |
| 抽取为空 | Stage 10 不再静默 DONE：`main.py` 缺失 → FAILED |
| `main.py` 仅常量 | FAILED，错误列出缺失的 guard / `METRIC_DEF` |
| Review 返回相同文件 | 不重复校验（避免额外 LLM 调用） |
| 外部 CLI agent 直接写盘 | 出口门从 `experiment/main.py` 读取校验 |

## 5. 职责边界

- **职责外**：模型输出质量（是否真的实现了算法）；服务端实际 `max_output_tokens`；`max_tokens` 全局调参。
- **能力边界**：围栏奇偶启发式对「代码内包含奇数个三反引号」会误判；此类输入极罕见，出口门仍会拦截不可执行结果。

## 6. 拒绝方案

| 方案 | 拒绝理由 |
|---|---|
| 只提高 `max_tokens` | 截断概率下降但解析器仍脆弱；R1/R2 不解决 |
| 直接关闭 Review | 丢失真实修复能力，且不解决 R3 的根因（空文件） |
| 让 Stage 12 兜底 | 已经发生（R5），但代价是 20+ 分钟浪费在错误产物上 |
| 对截断响应静默接受 | 会把半截代码当成完整文件，风险更高 |
