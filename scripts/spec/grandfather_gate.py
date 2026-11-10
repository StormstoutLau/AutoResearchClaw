#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grandfather 策略层（Q3 = B 基线 + 棘轮；P-020 F-1 方案 b）。

职责：复用 dc_validator 的检查结果，按 `(file, check_id)` 与 `expires` 做**豁免过滤**。
本文件不改 dc_validator 的任何规则——`dc_validator` 仍是契约的机器可读定义（I-3/I-4 保持），
豁免是**门禁策略**，位于其外层。

不可豁免：dc4（id 全仓唯一）/ dc5（版本引用）/ r7（计数自洽）——三者是全仓扫描语义（I-6），
按文件豁免不能使全仓命题成立，故显式拒绝登记。

用法：
  python scripts/spec/grandfather_gate.py                 # 全仓（等价 --all-files 语义）
  python scripts/spec/grandfather_gate.py file1.md ...    # staged 子集
  python scripts/spec/grandfather_gate.py --selftest      # 内置 fixture
退出码：0 无违规 / 1 存在违规（含过期豁免）/ 2 策略文件或工具错误。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dc_validator as dcv   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POLICY = os.path.join(ROOT, "spec", "grandfather.yaml")

EXEMPTIBLE = ("dc1", "dc2", "dc3")
ENTRY_KEYS = {"path", "check_ids", "reason", "owner", "expires",
              "renewals", "approved_by", "issue"}
TOP_KEYS = {"version", "cutoff", "expires_days", "entries"}
RENEWAL_KEYS = {"from", "to", "reason"}


def _iso(s):
    try:
        return _dt.date.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def _in_dc_scope(rel):
    """路径是否落在 dc_validator 的作用域（pre-commit files 正则同义）。"""
    p = str(rel).replace("\\", "/")
    if dcv.is_excluded(p):
        return False
    if p.startswith("spec/") and p.endswith(".md"):
        return True
    return p in ("docs/PROGRESS.md", "docs/CONSOLE.md")


def load_policy(path):
    """读取并做结构级校验。返回 (cfg, errors)。文件不存在 → 空策略（兼容）。"""
    import yaml
    if not os.path.exists(path):
        return {"version": 1, "cutoff": None, "expires_days": 90, "entries": []}, []
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except Exception as exc:                      # noqa: BLE001 — 策略文件任何解析错误都 fail-closed
        return None, ["策略文件解析失败: %s" % exc]
    if not isinstance(raw, dict):
        return None, ["策略文件顶层必须是映射"]
    errors = []
    unknown = set(raw) - TOP_KEYS
    if unknown:
        errors.append("未知顶层字段: %s" % sorted(unknown))
    if raw.get("version") != 1:
        errors.append("version 必须为 1（实际 %r）" % raw.get("version"))
    cutoff = _iso(raw.get("cutoff"))
    if cutoff is None:
        errors.append("cutoff 不是合法 ISO 日期: %r" % raw.get("cutoff"))
    days = raw.get("expires_days", 90)
    if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
        errors.append("expires_days 必须是正整数（实际 %r）" % days)
        days = 90
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        errors.append("entries 必须是列表")
        entries = []
    cfg = {"version": 1, "cutoff": cutoff, "expires_days": days, "entries": entries}
    return cfg, errors


def validate_entries(cfg, root=ROOT):
    """条目级校验：path / check_ids / owner / reason / 日期上限 / renewals / 重复。"""
    errors = []
    cutoff, days = cfg["cutoff"], cfg["expires_days"]
    seen = set()
    for i, e in enumerate(cfg["entries"]):
        tag = "entries[%d]" % i
        if not isinstance(e, dict):
            errors.append("%s 必须是映射" % tag)
            continue
        unknown = set(e) - ENTRY_KEYS
        if unknown:
            errors.append("%s 未知字段: %s" % (tag, sorted(unknown)))
        path = e.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append("%s.path 必填" % tag)
            continue
        rel = path.replace("\\", "/")
        if rel in seen:
            errors.append("%s.path 重复: %s" % (tag, rel))
        seen.add(rel)
        if not os.path.exists(os.path.normpath(os.path.join(root, rel))):
            errors.append("%s.path 不存在: %s" % (tag, rel))
        if not _in_dc_scope(rel):
            errors.append("%s.path 不在 DC 作用域内（豁免无效）: %s" % (tag, rel))
        ids = e.get("check_ids")
        if not isinstance(ids, list) or not ids:
            errors.append("%s.check_ids 必须是非空列表" % tag)
        else:
            bad = [x for x in ids if x not in EXEMPTIBLE]
            if bad:
                errors.append("%s.check_ids 含不可豁免项 %s（仅允许 %s）"
                              % (tag, bad, list(EXEMPTIBLE)))
        for k in ("reason", "owner"):
            if not isinstance(e.get(k), str) or not e.get(k).strip():
                errors.append("%s.%s 必填且非空" % (tag, k))
        exp = _iso(e.get("expires"))
        if exp is None:
            errors.append("%s.expires 不是合法 ISO 日期" % tag)
            continue
        if cutoff is not None and exp > cutoff + _dt.timedelta(days=2 * days):
            errors.append("%s.expires %s 超过上限 %s（cutoff + 2*expires_days）"
                          % (tag, exp, cutoff + _dt.timedelta(days=2 * days)))
        renewals = e.get("renewals", [])
        if not isinstance(renewals, list):
            errors.append("%s.renewals 必须是列表" % tag)
            continue
        if len(renewals) > 1:
            errors.append("%s.renewals 最多 1 次（实际 %d）" % (tag, len(renewals)))
        for j, r in enumerate(renewals):
            rtag = "%s.renewals[%d]" % (tag, j)
            if not isinstance(r, dict):
                errors.append("%s 必须是映射" % rtag)
                continue
            if set(r) - RENEWAL_KEYS:
                errors.append("%s 未知字段: %s" % (rtag, sorted(set(r) - RENEWAL_KEYS)))
            f, t = _iso(r.get("from")), _iso(r.get("to"))
            if f is None or t is None:
                errors.append("%s.from/to 必须是 ISO 日期" % rtag)
                continue
            if f != exp:
                errors.append("%s.from %s 必须等于原 expires %s（append-only）" % (rtag, f, exp))
            if t != f + _dt.timedelta(days=days):
                errors.append("%s.to 必须等于 from + expires_days（%s）"
                              % (rtag, f + _dt.timedelta(days=days)))
            if cutoff is not None and t > cutoff + _dt.timedelta(days=2 * days):
                errors.append("%s.to %s 超过总寿命上限 cutoff+2*expires_days" % (rtag, t))
            if not isinstance(r.get("reason"), str) or not r["reason"].strip():
                errors.append("%s.reason 必填" % rtag)
    return errors


def effective_expiry(entry):
    """当前生效的到期日：有续期（append-only）取 to，否则取原 expires。"""
    renewals = entry.get("renewals") or []
    if renewals:
        return _iso(renewals[-1].get("to"))
    return _iso(entry.get("expires"))


def filter_results(results, cfg, today=None):
    """按策略过滤结果。返回 (kept, grandfathered, expired)。

    - severity 为空（skip）恒保留；
    - check_id 不在 EXEMPTIBLE 恒保留（dc4/dc5/r7 不豁免）；
    - 无 entry 或 entry 不含该 check_id 恒保留；
    - 命中且未过期 → 丢弃并计入 grandfathered；
    - 命中但已过期 → 保留并计入 expired。
    """
    today = today or _dt.date.today()
    by_path = {}
    for e in cfg.get("entries", []):
        if isinstance(e, dict) and isinstance(e.get("path"), str):
            by_path[e["path"].replace("\\", "/")] = e
    kept, grandfathered, expired = [], [], []
    for r in results:
        if not r.severity:
            kept.append(r)
            continue
        if r.check_id not in EXEMPTIBLE:
            kept.append(r)
            continue
        e = by_path.get(str(r.file).replace("\\", "/"))
        if e is None or r.check_id not in (e.get("check_ids") or []):
            kept.append(r)
            continue
        exp = effective_expiry(e)
        if exp is not None and today <= exp:
            grandfathered.append((r, e, exp))
        else:
            expired.append((r, e, exp))
            kept.append(r)
    return kept, grandfathered, expired


def run_gate(files, policy_path=POLICY, root=ROOT, today=None, checks=None):
    """执行门禁。返回 (exit_code, text)。供 main 与 selftest 复用。"""
    cfg, errors = load_policy(policy_path)
    if errors:
        return 2, "[grandfather] 策略文件非法:\n  " + "\n  ".join(errors)
    errors = validate_entries(cfg, root)
    if errors:
        return 2, "[grandfather] 条目非法:\n  " + "\n  ".join(errors)
    results = dcv.run_checks(files, checks or set(dcv.ALL_CHECKS), root=root)
    kept, grand, exp = filter_results(results, cfg, today=today)
    lines = []
    for r, e, expd in grand:
        lines.append("[grandfathered] %s (%s, expires=%s)"
                     % (r.file, ",".join(e.get("check_ids") or []), expd))
    for r, e, expd in exp:
        lines.append("[EXPIRED] %s: %s (expires=%s)" % (r.file, r.message, expd))
    for r in kept:
        if r.severity:
            loc = " (L%d)" % r.line if r.line else ""
            lines.append("[%s] %s: %s%s" % (r.severity, r.file, r.message, loc))
    violations = [r for r in kept if r.severity]
    lines.append("grandfather: grandfathered=%d expired=%d violations=%d"
                 % (len(grand), len(exp), len(violations)))
    return (1 if violations else 0), "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="grandfather_gate",
                                 description="DC 契约门禁（含 grandfather 策略层）")
    ap.add_argument("--selftest", action="store_true", help="内置 fixture")
    ap.add_argument("--policy", default=POLICY, help="策略文件路径（默认 spec/grandfather.yaml）")
    ap.add_argument("files", nargs="*", help="目标 .md（缺省 = 全仓）")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    try:
        chosen = args.files if args.files else [f for f in dcv.gather_md_files() if _in_dc_scope(f)]
        files = [f for f in chosen if not dcv.is_excluded(f)]
        code, text = run_gate(files, policy_path=args.policy)
    except Exception as exc:                      # noqa: BLE001 — 工具错误 ≠ 通过
        sys.stderr.write("[tool-error] %s: %s\n" % (type(exc).__name__, exc))
        return 2
    print(text)
    return code


# ---------------------------------------------------------------- selftest

FM = ("---\nid: gf-%s\ntype: design\nversion: 1.0\nstatus: draft\n"
      "date: 2026-11-10\ndepends: [x]\nupstream: null\n---\n\n# t\n")


def run_selftest():
    """T-1/T-5/T-6/T-7 等 fixture（DESIGN §9、IMPLEMENTATION §6）。"""
    import shutil
    import tempfile
    import yaml

    tmp = tempfile.mkdtemp(prefix="gf_selftest_")
    fails, total = [], [0]

    def expect(cond, msg):
        total[0] += 1
        print("  %s %s" % ("PASS" if cond else "FAIL", msg))
        if not cond:
            fails.append(msg)

    def w(rel, content):
        p = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        return rel

    def policy(entries, extra=None):
        cfg = {"version": 1, "cutoff": "2026-11-10", "expires_days": 90, "entries": entries}
        cfg.update(extra or {})
        p = os.path.join(tmp, "gf.yaml")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            yaml.safe_dump(cfg, fh, allow_unicode=True)
        return p

    try:
        good = w("spec/f-good.md", FM % "good")
        bad = w("spec/f-bad.md", (FM % "bad").replace("status: draft\n", ""))
        outside = w("docs/note.md", "# 无 front-matter\n")

        # F1 空清单：缺字段必须红
        code, text = run_gate([good, bad], policy_path=policy([]), root=tmp)
        expect(code == 1 and "grandfathered=0" in text, "F1 空清单 → 缺 status 报红 (exit 1)")

        # F2 合法豁免：仅 dc1 被跳过
        e = [{"path": "spec/f-bad.md", "check_ids": ["dc1"], "reason": "legacy",
              "owner": "arc", "expires": "2027-02-08"}]
        code, text = run_gate([good, bad], policy_path=policy(e), root=tmp)
        expect(code == 0 and "grandfathered=1" in text, "F2 合法豁免 → 全通过 (exit 0)")

        # F3 过期豁免：仍红
        e[0]["expires"] = "2026-11-09"
        code, text = run_gate([good, bad], policy_path=policy(e), root=tmp)
        expect(code == 1 and "expired=1" in text, "F3 过期豁免 → 仍红 (exit 1)")

        # F4 作用域外文件不消耗条目，且域外 path 登记非法
        code, text = run_gate([outside], policy_path=policy([]), root=tmp)
        expect(code == 0 and "grandfathered=0" in text, "F4a 域外文件 → 0 豁免 0 违规")
        e_out = [{"path": "docs/note.md", "check_ids": ["dc1"], "reason": "x",
                  "owner": "arc", "expires": "2027-02-08"}]
        code, _ = run_gate([outside], policy_path=policy(e_out), root=tmp)
        expect(code == 2, "F4b 域外 path 登记 → exit 2")

        # F5 非法 check_ids（dc4 不可豁免）
        e_bad = [{"path": "spec/f-bad.md", "check_ids": ["dc1", "dc4"], "reason": "x",
                  "owner": "arc", "expires": "2027-02-08"}]
        code, _ = run_gate([bad], policy_path=policy(e_bad), root=tmp)
        expect(code == 2, "F5 check_ids 含 dc4 → exit 2")

        # F6 超过 2*expires_days 上限
        e_cap = [{"path": "spec/f-bad.md", "check_ids": ["dc1"], "reason": "x",
                  "owner": "arc", "expires": "2027-06-01"}]
        code, _ = run_gate([bad], policy_path=policy(e_cap), root=tmp)
        expect(code == 2, "F6 expires 超过 cutoff+180 → exit 2")

        # F7 合法续期：from=原 expires, to=+90
        e_ren = [{"path": "spec/f-bad.md", "check_ids": ["dc1"], "reason": "x",
                  "owner": "arc", "expires": "2026-12-01",
                  "renewals": [{"from": "2026-12-01", "to": "2027-03-01", "reason": "延迟"}]}]
        code, _ = run_gate([bad], policy_path=policy(e_ren), root=tmp, today=_dt.date(2027, 1, 1))
        expect(code == 0, "F7 合法续期 → 新到期日内仍豁免")

        # F8 二次续期非法
        e_ren2 = [{"path": "spec/f-bad.md", "check_ids": ["dc1"], "reason": "x",
                   "owner": "arc", "expires": "2026-12-01",
                   "renewals": [{"from": "2026-12-01", "to": "2027-03-01", "reason": "a"},
                                {"from": "2027-03-01", "to": "2027-06-01", "reason": "b"}]}]
        code, _ = run_gate([bad], policy_path=policy(e_ren2), root=tmp)
        expect(code == 2, "F8 二次续期 → exit 2")

        # F9 未知字段 fail-closed
        e_unk = [{"path": "spec/f-bad.md", "check_ids": ["dc1"], "reason": "x",
                  "owner": "arc", "expires": "2027-02-08", "silent": True}]
        code, _ = run_gate([bad], policy_path=policy(e_unk), root=tmp)
        expect(code == 2, "F9 未知字段 → exit 2")

        # F10 重复 path
        e_dup = [dict(e[0]), dict(e[0])]
        code, _ = run_gate([bad], policy_path=policy(e_dup), root=tmp)
        expect(code == 2, "F10 重复 path → exit 2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("grandfather_gate selftest: %d/%d PASS" % (total[0] - len(fails), total[0]))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
