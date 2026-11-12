---
id: arc-g4-mcp-alignment-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-recheck-d1]
upstream: arc-g3-recheck-d1
---

# 调研文档：G4 开工前 MCP 版本对齐验证（P-093）

> **Feature**：P-093，总纲 §G4 风险项（L461）的开工前置验证。
> **Spec 步骤**：Step 1-2（T3 调研批，零生产代码）。
> **结论先行**：**版本对齐验证通过，G4 的 MCP 依赖基础安全**——代码按 SDK 2.x API 编写、pin `>=2.1,<3` 有效（PyPI 2.0.0..2.3.0 实存）、CI 按 pin 安装、mcp 2.3.0 实跑仓内 MCP 测试 **42 passed**。唯一风险是**本机环境漂移**（Anaconda 全局装了旧 SDK 1.27.2，不满足 pin，本机 MCP 测试无法收集），属用户环境操作，不影响 CI 与 G4。

## 1. 调研目标

1. **pin 真实性**：`mcp>=2.1,<3` 指向的版本在 PyPI 是否实存？
2. **代码-SDK 匹配**：`server.py`/`client.py` 使用的 API 在 SDK 2.x 下是否存在？
3. **协议侧**：总纲 "MCP 2026-07-28 = MCP v2（stateless，移除 initialize/session）" 的说法是否准确？
4. **本机风险**：开发机环境是否满足 pin？

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | pyproject pin、server/client API、CI 安装方式 | ✅ |
| 本机探针（E2） | 已装版本、import 验证、测试收集 | ✅ 发现 1.27.2 漂移 |
| 临时 venv 实跑（E2） | mcp 2.3.0 下 API 存在性 + 仓内 MCP 测试 | ✅ 42 passed |
| PyPI JSON API（T1） | 版本清单与 latest | ✅ 2.0.0..2.3.0 |
| WebFetch 官方 spec（T1） | 2026-07-28 lifecycle/versioning 原文 | ✅ Modern/Legacy 术语 |

**降级链记录**：pypi.org 网页抓取返回空内容 → 降级到 PyPI JSON API（`pypi.org/pypi/mcp/json`）成功；无静默跳过。

## 3. 调研发现

### 3.1 pin 真实性（T1，PyPI JSON API）

- `mcp` 包 2.x 系列实存：`2.0.0 / 2.0.1 / 2.1.0 / 2.1.1 / 2.2.0 / 2.3.0`（latest **2.3.0**）。
- pin `mcp>=2.1,<3`（[pyproject.toml](../../pyproject.toml) L18/L28）有效；code_wiki/14 "CI 锁定 mcp==2.3.*" 与 latest 一致。

### 3.2 代码-SDK 匹配（E2，mcp 2.3.0 临时 venv）

| API | 2.3.0 下 |
|---|---|
| `from mcp.server import MCPServer` | ✅ 存在 |
| `from mcp import Client, StdioServerParameters` | ✅ 存在 |
| `CallToolResult(content=…, structured_content=…, is_error=…)` | ✅ 签名匹配 |
| `MCPServer.run_stdio_async / run / tool` | ✅ 全部存在 |
| **仓内 MCP 测试实跑** | ✅ **42 passed**（test_mcp.py + test_mcp_protocol.py） |

### 3.3 协议侧回源（T1，modelcontextprotocol.io spec 2026-07-28）

- 官方术语是 **Modern vs Legacy**，不是 "v1/v2"：`2026-07-28` 及以后 = Modern（**无协商握手**，每请求以 `_meta` 携带版本，stateless）；`2025-11-25` 及更早 = Legacy（`initialize` 握手建立会话）。
- 总纲 L461 的实质正确（"stateless、移除 initialize/session" 对 Modern 服务器成立），但 "MCP v2" 非官方用语 → 订正建议见 §5。
- SDK 2.x 是配套 Modern era 的 SDK 大版本（PyPI 2.0.0 起跳），与协议版本解耦。

### 3.4 本机环境漂移（E2，非仓风险）

- 本机 Anaconda 全局：`mcp==1.27.2`（**不满足 pin**）。
- 后果：`from mcp.server import MCPServer` → ImportError；`CallToolResult` 签名为 `(self, data)`（1.x 形态）；`tests/test_mcp*.py` 收集即 ERROR（`server.py` L28-31 的 fail-closed 导入设计按预期工作）。
- **CI 不受影响**：ci.yml extras job 用 `pip install -e ".[server,mcp,voice]"` 按 pin 装 2.x，并用 `python -c "import ... mcp"` 冒烟。
- **修复动作（用户环境操作，本批不执行）**：`pip install -U "mcp>=2.1,<3"`（升级全局环境），或为本仓使用独立 venv。

## 4. 综合分析

1. **不存在总纲担心的 "按 v2 文档写、按旧 SDK 跑"**（仓内代码与 CI 均按 SDK 2.x）——风险方向相反：是**个别开发机按旧 SDK 装环境**。[★★★★★]
2. **G4 依赖基础安全**：`tools/list`、inputSchema（SDK 生成）、`listChanged` 由 SDK 2.x 提供，A4-1/A4-10 的 MCP 侧地基已在。[★★★★☆]
3. **G4 剩余关注点**（非 MCP 版本问题）：沙箱后端选型（A4-2/A4-3）、`tool.call`/`tool.result` 事件（A4-4，可复用 G1 事件链）、registry.yaml schema（A4-1）。[★★★★☆]

## 5. 幻觉抑制审查（Step 2 Review）

| 引用/声明 | ID/来源 | 验证方式 | 状态 |
|---|---|---|---|
| mcp 2.x 版本清单与 latest | PyPI JSON API | 实查 | ✅ T1 |
| Modern/Legacy 术语与无握手语义 | spec 2026-07-28 basic/versioning | WebFetch 原文 | ✅ T1 |
| `MCPServer`/`Client`/`CallToolResult` API | mcp 2.3.0 本地导入 | 临时 venv 实测 | ✅ E2 |
| 仓内 MCP 测试 42 passed | 临时 venv 实跑 | pytest | ✅ E2 |
| 本机 1.27.2 漂移 | importlib.metadata | 实查 | ✅ E2 |

### 待修正项

- [x] 总纲 L461 "MCP v2" 措辞 → 官方为 Modern/Legacy；本报告 §3.3 订正，总纲在 P-093 登记时同步一句（见 PROGRESS 行依据）。
- [x] "ARC 依赖 mcp>=2.1,<3" 的风险方向订正：仓内/CI 对齐 ✓，风险在本机环境漂移。

## 6. 对 G4 的输入

1. **可开工**：MCP 版本风险解除，无需改 pin 或代码。
2. **G4 建议用例**：A4-1（registry schema + SDK 生成 inputSchema）、A4-4（tool.call/result 事件接入既有 events.jsonl）、A4-10（SDK `listChanged`）。
3. **环境纪律建议**：G4 施工批要求贡献者按 pin 安装 `[mcp]` extra；可在 extras job 的冒烟命令中加版本断言 `python -c "import mcp; assert mcp.__version__ >= '2.1'"`（留 G4 实施批）。

## 7. 参考文献

- PyPI mcp：https://pypi.org/pypi/mcp/json（版本清单，实查 2026-11-13）
- MCP spec 2026-07-28 Versioning：https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
- 总纲 §G4 风险：`arc-master-roadmap.md` L461
- 仓内实现：`researchclaw/mcp/server.py`、`researchclaw/mcp/client.py`、`.github/workflows/ci.yml`

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-13
