---
id: arc-history-scrub-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-private-endpoint-hygiene-IMPLEMENTATION]
upstream: arc-private-endpoint-hygiene-IMPLEMENTATION
---

# 调研：历史提交脱敏

> **授权**：用户明确要求执行 `git filter-repo`，彻底清除历史中的私网 IP。
> **前序**：P-009 已清当前树并加门禁；历史仍有地址，需重写。P-009 §4/§5 中「历史未重写」的表述由本批取代。

## 1. 命中范围

| token 类别 | 命中提交 |
|---|---|
| 私网 IP + SSH 用户名 | `98518fd`（引入）、`9aa1d38`（当前树移除） |
| 主隧道端口 | 同上 |
| 备用隧道端口 | 同上 |

SSRF 测试中的 `192.0.2.1`（RFC 5737 文档网段）与旧提交中的 `127.0.0.1:8080` 属合法夹具，**不在替换范围**——按具体字符串而非网段替换。

## 2. 约束

1. 只替换本批泄漏的具体 token，不误伤测试夹具与通用端口。
2. 改写前必须备份全量 refs。
3. 远端 `origin` 会被 filter-repo 移除，需手工恢复；是否强推由用户决定。
4. 工作区有 3 个未提交的 `code_wiki/*` 改动，需先备份再恢复。

## 3. 验收

- `git log --all -S` 对四个 token 均 0 命中；
- 旧 HEAD 对象不可达、reflog 为空；
- 当前树扫描 0 违规、测试与门禁全绿。
