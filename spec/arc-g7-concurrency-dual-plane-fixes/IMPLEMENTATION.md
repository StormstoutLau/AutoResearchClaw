---
id: arc-g7-concurrency-dual-plane-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-fixes-DESIGN, arc-g7-concurrency-dual-plane-fixes-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 并发段修复（P-173）

## 1. 交付面与源码锚点

| 交付 | 文件 | 符号/行 | 行为 |
|---|---|---|---|
| 备份文件名 | [admission.py](../../researchclaw/runtime/admission.py) | `REGISTRY_BACKUP_NAME` [L27](../../researchclaw/runtime/admission.py#L27) | `registry.bak.json` |
| 损坏异常 | 同上 | `RegistryCorrupt` [L37](../../researchclaw/runtime/admission.py#L37) | 双损坏 fail-closed |
| 状态解析 | 同上 | `_read_state` [L158](../../researchclaw/runtime/admission.py#L158) | 非法 JSON/非对象 → `RegistryCorrupt` |
| 恢复选择 | 同上 | `_load` [L176](../../researchclaw/runtime/admission.py#L176) | 取 revision 更高的有效副本，缺失/损坏回写主 |
| 回写 | 同上 | `_restore` [L214](../../researchclaw/runtime/admission.py#L214) | `copyfile + os.replace` |
| 双副本保存 | 同上 | `_save` [L220](../../researchclaw/runtime/admission.py#L220) | revision+1；先备份后主 |
| supervisor 分支 | [supervisor.py](../../researchclaw/runtime/supervisor.py) | `_admit` [L122-L152](../../researchclaw/runtime/supervisor.py#L122-L152) | `admission_corrupt` → CONFIG，不 spawn |
| A7-4 用例 | [test_event_replay_rotation.py](../../tests/test_event_replay_rotation.py) | [L35](../../tests/test_event_replay_rotation.py#L35)/[L55](../../tests/test_event_replay_rotation.py#L55)/[L76](../../tests/test_event_replay_rotation.py#L76) | 轮转/gzip/缺口三态 |
| registry 用例 | [test_admission.py](../../tests/test_admission.py) | [L116](../../tests/test_admission.py#L116)/[L130](../../tests/test_admission.py#L130) | 恢复/缺失回退/双损坏 |
| supervisor 用例 | [test_supervisor.py](../../tests/test_supervisor.py) | [L237](../../tests/test_supervisor.py#L237) | 损坏不 spawn |
| A7-1 模板 | [config.g7-field.example.yaml](../../config.g7-field.example.yaml) | 全文 | 裸 API + loopback + 小规模真实实验 |
| A7-1 方案 | [arc-g7-field-run-decision-20261125.md](../../docs/arc-g7-field-run-decision-20261125.md) | §1/§4/§7 | 拓扑、配置、验收、待确认 |

## 2. TDD 红 → 绿

1. **红**：先改测试——`test_corrupt_primary_recovers_from_backup` 期望 `last_error=recovered_from_backup`、`fencing=2`；`test_both_copies_corrupt_fail_closed` 期望 `RegistryCorrupt`；新增 A7-4 三用例。初版实现对「双损坏」仍返回空状态、A7-4 段数期望少算一段（实现按 `seg_count >= 3` 预滚动），测试红。
2. **绿**：实现 `_read_state/_load/_restore/_save` + supervisor `except RegistryCorrupt`；按实际滚动顺序修正 A7-4 期望（`1-3/4-6/7-9`）。
3. **回归**：修复相关 84 passed；全量读数见 §4。

## 3. 关键实现点

- **revision 选新**：`_save` 每次 +1；`_load` 仅当备份 revision 严格更大才用备份，避免同 revision 时反复回写。
- **备份先写**：先替换 `registry.bak.json`，再替换 `registry.json`；崩溃窗口内最多丢一次「主替换」，下次加载从备份恢复。
- **双损坏 fail-closed**：只有两份都不存在才返回空状态；任一份存在但都不可读 → `RegistryCorrupt`。
- **supervisor 不 spawn**：`_admit` 捕获后返回 `"corrupt"`，`run()` 统一返回 CONFIG(78)，`queued=False`。
- **A7-4 负向**：删除 `events.1-3.jsonl.gz` 后 `verify_run` 的 `retention_limited=True`，`ok/converged=False`，`first_seq=4`。

## 4. 验收读数

| 项 | 命令 | 读数 |
|---|---|---|
| 修复面 | `pytest tests/test_admission.py tests/test_supervisor.py tests/test_event_replay_rotation.py -q` | **33 passed** |
| 相关回归 | `pytest tests/test_...（事件/soak/并发/ops） -q` | **84 passed** |
| 全量 | `pytest -q` | **3952 passed / 6 failed / 108 skipped**（6 = 本机环境态：Windows shell hook、Keras 3、bash 路径，同 P-172 基线） |

## 5. 边界

- **A7-1 仍未执行 72h**：本批只锁定接入方式、模板与验收判据；72h 需集群端点（模型名/端口/凭据）与独占主机。
- **A7-5 独立新人盲测**仍为 U-172-1；本批不改变。
- **A7-4** 已有机械验收；72h 现场 run 的真实目录需在 A7-1 完成后复跑一次 `soak verify`。
- 不新增 CLI/config 字段；不改 `verify_run` 默认值。
