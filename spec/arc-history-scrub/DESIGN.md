---
id: arc-history-scrub-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-history-scrub-RESEARCH]
upstream: arc-history-scrub-RESEARCH
---

# 设计：替换规则与回滚

## 1. 替换规则（按最长优先）

| 原值 | 占位符 |
|---|---|
| `127.0.0.1:<主端口>:127.0.0.1:<API端口>`（SSH -L 组合） | `127.0.0.1:<TUNNEL_PORT>:127.0.0.1:<API_PORT>` |
| `127.0.0.1:<主端口>` | `127.0.0.1:<TUNNEL_PORT>` |
| `<私网IP>` | `<B_STATION_HOST>` |
| `<SSH用户名>` | `<user>` |
| 独立数字 `<备用端口>` | `<ALT_TUNNEL_PORT>`（单词边界正则） |

## 2. 流程

1. `git bundle create <backup> --all`；`git diff > code_wiki.patch`；
2. 清理工作区（保留 patch）；
3. `git filter-repo --force --replace-text <rules>`；
4. 恢复 `origin`、恢复 `code_wiki` patch；
5. 全历史与当前树双向验证。

## 3. 回滚

- 备份 bundle 可 `git clone <bundle>` 恢复旧历史；
- 未强推前，远端仍保留旧历史，可作为第二副本。

## 4. 远端策略

本地重写已完成；`origin/main` 仍指向旧历史。**强推需用户再次明确授权**，本批不执行。
