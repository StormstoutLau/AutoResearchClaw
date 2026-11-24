---
id: arc-heavy-followups-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-17
depends: [arc-heavy-followups-RESEARCH, arc-heavy-followups-DESIGN]
upstream: null
---

# 调研：U-3/U-2 修复范围与验收（P-139）

> **Feature**：P-139。承接 P-136 的 U-3/U-2 方案 A，做实施前的范围确认。
> **Spec 步骤**：Step 1-2（实施批的调研步）。
> **结论先行**：三项改动都是最小、可逆、无外部契约变更的：① `write_waiting` 改用 `atomic_write_text`；② `read_feedback_response` 去掉 `exists()` 预检并捕获 `FileNotFoundError`；③ `renew` 在锁内拒绝 `current.released`。四项回归覆盖 J-1..J-4。

## 1. 范围

| 编号 | 缺陷 | 文件 | 改法 |
|---|---|---|---|
| U-3a | `waiting.json` 非原子写 | `researchclaw/hitl/file_wait.py` | `path.write_text` → `atomic_write_text` |
| U-3b | feedback 读方 TOCTOU | `researchclaw/copilot/feedback.py` | 去掉 `exists()` 预检；捕获 `FileNotFoundError` 返回 `None` |
| U-2 | `released` 可被续约复活 | `researchclaw/runtime/lease.py` | `renew` 的锁内条件加 `current.released` |

**非目标**

- 不改外部 UI/CLI 对 `copilot_feedback_response.json` 的写入。
- 不改 `response.json`（P-134 已修）。
- 不改 `heavy` marker、`tests/ci_exclusions.yaml`、workflow。
- 不做全部 IPC 加锁或大范围重构。

## 2. 证据（E1）

| 编号 | 读数 | 来源 |
|---|---|---|
| E1-1 | `write_waiting` 原用 `path.write_text`（truncate 后写） | `file_wait.py` L54-L60（改前） |
| E1-2 | `ws_adapter._read_json` 解析失败返回 `None` 且不删文件，风险为一次 UI 状态闪烁 | `ws_adapter.py` L425-L436 |
| E1-3 | `read_feedback_response` 先 `exists()` 再 `read_text`，中间缺失会抛未捕获 `FileNotFoundError` | `feedback.py` L69-L95（改前） |
| E1-4 | `renew` 只校验 `owner + fencing`，不校验 `released` | `lease.py` L193-L217（改前） |
| E1-5 | 确定性复现：`release()` 后 `renew()` 成功且 `released=False` | P-136 RESEARCH §3 |
| E1-6 | 正常路径 `_runtime_end` 先停 keeper 再 release；`atexit` 只 release | `runner.py` L267 / L285-L296 |

## 3. 方案确认

| 方案 | 做法 | 判断 |
|---|---|---|
| **U-3 A（采纳）** | waiting 原子写 + feedback 读方容错 | 最小、覆盖两个具体缺口 |
| U-3 B | 只改 waiting | TOCTOU 仍在 |
| U-3 C | 全部 IPC 加锁 | 过度设计 |
| **U-2 A（采纳）** | `renew` 锁内校验 `released` | 让释放成为不可逆终态 |
| U-2 B | `release` 停 keeper | 跨模块耦合 |
| U-2 C | 只改 atexit 顺序 | supervisor 路径仍漏 |

## 4. 外部锚点

| 来源 | 结论 | 等级 |
|---|---|---|
| P-134 原子发布先例 | 同目录 tmp + `os.replace` 是本仓已验证写法 | E1 |
| CWE-367 TOCTOU | `exists()` 后 `read` 的检查-使用竞态应按「直接读 + 捕获缺失」处理 | T2 |
| 状态机终态原则 | `released` 是单向终态，普通续约不应逆转 | T2 |
| P-136 U-3/U-2 | 两项均由调研批显式登记 | E1 |

## 5. 验收口径

| 编号 | 不变式 | 测法 |
|---|---|---|
| J-1 | `waiting.json` 走 `atomic_write_text` | spy 断言写方调用 |
| J-2 | feedback 读方在文件消失时返回 `None` | `read_text` 抛 `FileNotFoundError` |
| J-3 | `released` 不可复活 | `release` 后 `renew` 抛 `LeaseLost`，磁盘仍 `released=True` |
| J-4 | 正常续约不受影响 | 未释放时 `renew` 成功、fencing 不变 |

## 6. 未决项

| ID | 内容 | 判据 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | 外部 UI 写 response 是否原子 | 外部实现是否可控 | 不在本仓，读方容错即可 | E1 |
| U-2 | waiting 读方是否需签名重试 | 是否出现持续半截 | 现有 `_read_json` 返回 `None` 已可自愈 | E1 |
| U-3 | 本批合并时机 | 观察窗口 2 | 分支完成、合并押后 | E1 |

## 7. 诚实边界

- 本批是实施批，但按用户裁决，代码只推分支、不合并 main。
- U-3 的原子性通过 spy 与既有 `atomic_write_text` 行为验证，未做故障注入。
- U-2 的复活路径已由 P-136 确定性复现，本批补回归。
