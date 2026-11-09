---
id: arc-cli-agent-wiring-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-wiring-DESIGN]
upstream: arc-cli-agent-wiring-DESIGN
---

# 实施记录：接线断裂调研落档

> 本批只做调研与设计，不改代码、不改总纲正文。E-* 为实际落点，V-* 为可重放验证。

## 1. 落点

| # | 动作 | 落点 |
|---|---|---|
| E-1 | 记录三条代理路径、配置面与调用链事实（F-1..F-9） | [RESEARCH.md](RESEARCH.md) §3.1 |
| E-2 | 追溯 `experiment/code_agent.py` 的引入与零调用历史 | RESEARCH.md §3.1.3 |
| E-3 | 建立 13 项外部锚点（官方文档 6、论文 3、工程实践 4） | RESEARCH.md §3.2 |
| E-4 | 对比 6 种社区接法，给出 4 条路线与推荐 | RESEARCH.md §3.3、§4.4 |
| E-5 | 设计收口/接线/回退/测试方案（D-1..D-9） | [DESIGN.md](DESIGN.md) §2-§6 |
| E-6 | 登记 U-1..U-5 未决项 | RESEARCH.md §6.4、DESIGN.md §8 |
| E-7 | 登记 P-011 决策流（5 步） | `tools/spec_runner/sessions/specwf-p011-arc-cli-agent-wiring.jsonl` |

## 2. 验证

```bash
# V1 契约（仅 spec 作用域；裸跑 dc_validator 会带出全仓既有噪声）
python scripts/dc_validator.py spec/arc-cli-agent-wiring/RESEARCH.md \
  spec/arc-cli-agent-wiring/DESIGN.md spec/arc-cli-agent-wiring/IMPLEMENTATION.md \
  spec/arc-cli-agent-wiring/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md

# V2 决策流五步
python tools/spec_runner/spec_runner.py step-gate specwf-p011-arc-cli-agent-wiring \
  --expect research design implement verify finalize

# V3 派生视图
python scripts/console_gen.py --check

# V4 无生产调用方（期望仅命中定义与文档字符串）
python -c "import subprocess,pathlib; \
hits=[(str(p),i+1,l.strip()) for p in pathlib.Path('researchclaw').rglob('*.py') \
for i,l in enumerate(p.read_text(encoding='utf-8').splitlines()) \
if 'create_code_agent' in l]; print(hits)"

# V5 本批改动边界
git status --short spec/arc-cli-agent-wiring docs/PROGRESS.md docs/CONSOLE.md
```

## 3. 结果（2026-11-10）

- V1：`DC 契约校验通过：6 文件，2 结果，0 违规`（PROGRESS/CONSOLE 无 front-matter，按规则 skip）。
- V2：`step-gate[specwf-p011-arc-cli-agent-wiring]: 决策链一致 pass → exit 0`。
- V3：`CONSOLE.md 与源一致`（exit 0）。
- V4：`create_code_agent` 仅出现在 `researchclaw/experiment/code_agent.py` 的 docstring（L10/L12）与定义（L771），无阶段调用点。
- V5：新增 `spec/arc-cli-agent-wiring/` 与 session 文件；修改 `docs/PROGRESS.md`、`docs/CONSOLE.md`；本批无代码改动。
- 附加：`private_config_check.py` 对本批文档 exit 0（无私网地址/密钥）。

## 4. 未执行 / 边界

- **R-4 最小真相修正未执行**：`validate_config`/`doctor` 的 fail-fast 需另开批次。
- **R-3 统一接缝未执行**：配置去重、Stage 10/13 接线、适应度函数均未写代码。
- **R-2 删除未执行**：需 U-1 的 A/B 证据后裁决。
- **未修改 P-007 文档**：其“Claude Code 接入”表述的订正登记在 RESEARCH §5.3，待后续批次处理。
- **未做 A/B**：三种后端在成功率/耗时/成本上的对比仍是 U-1。
- **工作树提示**：`researchclaw/experiment/code_agent.py` 与 `tests/test_b_station_provider.py` 的未提交改动来自上一轮 prompt 修复（stdin + 进程树清理），不计入本批。
