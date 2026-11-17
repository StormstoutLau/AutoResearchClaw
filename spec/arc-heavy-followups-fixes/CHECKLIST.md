---
id: arc-heavy-followups-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-17
depends: [arc-heavy-followups-fixes-IMPLEMENTATION, arc-heavy-followups-fixes-DESIGN]
upstream: null
---

# 审查验收 Checklist：U-3/U-2 最小修复（P-139）

> **Feature**：P-139。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：3 产品文件 + 3 测试文件；不涉及 workflow、heavy marker 或 `ci_exclusions.yaml`。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 决策可追溯到 RESEARCH | ✅ | D-1..D-5 逐条指向 RESEARCH §1/§5 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 两文档均为「3 产品 + 3 测试」 |
| IMPLEMENTATION 读数在 checklist 有验收项 | ✅ | TDD/回归读数 ↔ §2/§4 |
| 术语一致（J 编号、文件、函数名） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| waiting 走原子发布 | spy `atomic_write_text` | 被调用一次且参数为 waiting 路径 | ✅ | J-1 用例 |
| waiting 内容仍合法 | 读回 JSON | `stage` 等字段正确 | ✅ | `test_write_waiting` |
| feedback 文件消失返回 None | 注入 `FileNotFoundError` | 不抛异常、返回 `None` | ✅ | J-2 用例 |
| feedback 正常响应仍解析 | 写合法 JSON | 返回 Feedback 且字段正确 | ✅ | `test_read_feedback_response_valid` |
| release 后续约抛 LeaseLost | 先 release 再 renew | `pytest.raises(LeaseLost)` | ✅ | J-3 用例 |
| released 保持 True | 读回 lease | `released is True` | ✅ | J-3 用例 |
| 正常续约不受影响 | 未释放时 renew | 成功、fencing 不变 | ✅ | J-4 用例 |
| 4 条新用例全绿 | `pytest` 聚焦 | `4 passed` | ✅ | IMPL §2 |

## 3. 接口验收

本批不新增或修改公共 API 签名、文件名或字段，故无接口验收项。

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 waiting 原子化 | spy 断言 | 调用 `atomic_write_text` | ✅ | IMPL §2 |
| J-2 feedback 无 TOCTOU | 异常注入 | 返回 `None` | ✅ | IMPL §3 |
| J-3 released 不可复活 | release→renew | 抛 `LeaseLost`，磁盘仍 True | ✅ | IMPL §2 |
| J-4 正常续约 | renew | 成功、fencing 不变 | ✅ | IMPL §2 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| feedback 文件缺失 | 注入 `FileNotFoundError` | 不向上抛 | ✅ | J-2 |
| 租约已释放 | `renew` | 抛 `LeaseLost` | ✅ | J-3 |

## 6. 性能验收

本批仅替换一次文件写与新增一个终态判断，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 外部契约不变 | 审阅 | 文件名/字段不变 | ✅ | DESIGN §6 |
| heavy marker/排除表不变 | `git diff` | 无命中 | ✅ | IMPL §6 |

## 8. ADD 审计

本批为缺陷修复，无 ADD 新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 3 条先红后绿；正常路径有回归 |
| 可逆性 | 三处均为最小改动，逐条可回退 |
| 风险 | 未做故障注入，已登记 |
| 卫生 | 批外 vendor CRLF 未纳入 |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 8 | 8 | 0 | 0 |
| 接口 | 0 | 0 | 0 | 0 |
| 不变式 | 4 | 4 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **20** | **20** | **0** | **0** |

算术自洽：20 = 4+8+0+4+2+0+2+0；通过 20 = 总数 20。

### 10.2 验收结论

- [x] 验收通过：20/20 全通过；3 条先红后绿有读数。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 押后 | 窗口 2 结束后合并 |
| 全量回归 | 通过（环境性 6 失败） | 与 P-134 同一组，零交集 |
| 外部 UI 原子写 | 观察 | 不在本仓 |
| 故障注入 | 未做 | J-2 用异常注入覆盖 |
