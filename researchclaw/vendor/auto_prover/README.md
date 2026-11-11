# Vendored Auto_Prover kernel (Apache-2.0)

> 上游：[Auto_Prover](https://github.com/StormstoutLau/Auto_Prover) @ `bd95f02`（v3.7.0）
> 冻结日期：2026-11-11（P-049 / G2 M2）｜许可：**本目录按文件保持 Apache-2.0**；`researchclaw` 其余部分仍为 MIT。

## 1. 边界

本目录只包含 **G2 判定内核 65 项测试的依赖闭包**，不是完整 Auto_Prover：

| 子路径 | 文件数 | 上游路径 | 说明 |
|---|---|---|---|
| `datatypes/` | 9 | `proof_pipeline/datatypes/` | 数据类型 |
| `verdict/` | 3 | `proof_pipeline/verdict/` | 判定策略唯一出口 |
| `sandbox/` | 4 | `proof_pipeline/sandbox/` | AST 白名单 + Job Object 沙箱（含 D173 启动器修复） |
| `semantic_verdict.py` | 1 | `proof_pipeline/semantic_verdict.py` | 语义判定（Tier1/2） |
| `model_gateway.py` | 1 | `proof_pipeline/model_gateway.py` | 网关类型（测试以 mock 使用） |
| `kg/` | 3 | `proof_pipeline/kg/` | `i2_extractor` / `verdict_writer` / `unified_cases` |
| `stages/` | 5 | `proof_pipeline/stages/` | `stage2_numerical` + 4 个数值辅助模块 |
| `scripts/verdict_recheck.py` | 1 | `scripts/verdict_recheck.py` | 旧 verdict 只读复核（stdlib） |

**不 vendor**：`stages/` 的 Lean/ATLAS 部分、`kg` 的导入/写回、`mcp_servers`、`atlas_bridge`、`lean4_cases`、AP 的 `spec/`/`docs/`（P-043 §8.3、V-5）。

## 2. 许可与合规

- `LICENSE` 与 `NOTICE` 为 AP 原文逐字节复制，不得删改。
- 修改过的文件在文件头带 `# Modified by AutoResearchClaw on YYYY-MM-DD: ...`（V-3）。
- 新增的打包文件（`__init__.py` ×4）为 Apache-2.0；`kg/__init__.py` 与 `stages/__init__.py` 替换了上游的重导入版本，避免拉入 sidecar/Lean。
- 第三方清单见 `THIRD_PARTY_NOTICES.md`；逐文件来源与 sha256 见 `SOURCE.json`。
- 仓库根 `.gitattributes` 对本目录设 `-text`，禁止 EOL 转换，保证 sha256 在 Windows/Linux 检出后一致。

## 3. 升级与校验

1. 更新 `SOURCE.json` 的 commit、文件清单与 sha256；
2. 重跑 65 项判定测试（`test_vendor_*`）与 `tests/test_vendor_auto_prover.py`；
3. 复核 `THIRD_PARTY_NOTICES.md`；
4. 若上游修改了被 vendor 的文件，在文件头追加修改声明。

```powershell
python -m pytest tests/test_vendor_d110_verdict_policy.py tests/test_vendor_d110_verdict_recheck.py tests/test_vendor_semantic_verdict.py -q
python -m pytest tests/test_vendor_auto_prover.py -q
```

## 4. 版本

| 项 | 值 |
|---|---|
| 上游版本 | 3.7.0 |
| 上游 commit | `bd95f02` |
| 内核文件 | 27（不含 `LICENSE`/`NOTICE`/新增 `__init__.py`） |
| 冻结用例 | 65（23 + 3 + 39） |
