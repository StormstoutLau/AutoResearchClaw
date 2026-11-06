#!/usr/bin/env python3
"""回写返工图对账器（rework graph）——「声明 → 实测 → 对账」三段式（2026-09-27 · P-051）

## 为什么有这个文件

回写流的**分叉原语**本仓已有（`spec_runner fork`），但 `cmd_fork` 只把
`fork: <new> <- <session>` **打到 stdout**（`spec_runner.py` L505-506），事件 schema 亦无
lineage 字段 ⇒ **分叉事实只存在于操作者的记忆里**（P-050 RESEARCH 洞察 1(c) 已自登记该缺口）。

本文件把那一步变成机制：**登记表（`docs/rework-graph.json`）声明返工图 → 回盘核
session 文件 → 对账**。设计见 `spec/rework-graph/DESIGN.md` §4（判定表 §4.4）。

## 关键机械信号（本设计得以成立的支点）

**`fork` 复制行时逐字复制原行——包括 `session` 字段。**故：

    一个 session 文件，若其行内 `session` 值 ≠ 该文件名词干 ⇒ 它就是一次 `fork` 的输出。

该信号**零新增契约**（不必给 `fork` 加字段），据此做**孤儿扫描**（判定表 D）。

## 不变式（DESIGN §8）

- **I-1 只读**：不写任何 session / 表 / 派生视图（只 stdout）。
- **I-2 确定性**：不读 wall clock；`updated` 字段不参与判定；同输入 → 同输出。
- **I-3 零依赖**：stdlib only（数据取 JSON 而非 YAML，正为此）。

## 边界（DESIGN §7，别读成「保证无漏登」）

登记表是**清单不是事实**。本器只保证「**已登记的分叉属实**」+「**fork 输出无漏登**」，
**不保证**「所有返工都被登记」（无信号者不可判），也**不评价**「该不该回写」。

用法：
    python scripts/rework_graph_check.py            # 默认 = check
    python scripts/rework_graph_check.py --json     # 机读输出
    python scripts/rework_graph_check.py --selftest # 内嵌自测（合成 fixture，不读真表）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "rework-graph.json"
SESSIONS = ROOT / "tools" / "spec_runner" / "sessions"

EXIT_OK, EXIT_BAD, EXIT_DEGRADED = 0, 1, 2

# ── 口径（唯一实现；改这里 ⇒ 须同步 DESIGN §4.4 判定表）─────────────────────────
DEAD_WORDS = ("unknown",)                      # 禁用词（承 RPC edges.yaml：自报不算来源）
REQ_KEYS = ("version", "updated", "owner", "truth_source",
            "trigger_kinds", "provenance_prefixes", "forks", "non_rework")
TRUTH_SOURCE = "registry"


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _blank(v) -> bool:
    """空 / 仅空白 / 命中禁用词 ⇒ True（三态都算「没写」）。"""
    t = _s(v)
    return (not t) or (t.lower() in DEAD_WORDS)


def _prov_bad(prov, prefixes) -> str | None:
    """`provenance` 的**7 类「缺」**→ 错误串 / None（承 RPC `_bad_provenance` 口径，免计数枚举）。"""
    if not isinstance(prov, str):
        return "非字符串"
    if prov == "":
        return "空串"
    if prov.strip() == "":
        return "仅含空白"
    if prov.strip().lower() in DEAD_WORDS:
        return f"命中禁用词 {prov.strip()!r}"
    if ":" not in prov:
        return "缺 `<前缀>:<载荷>` 形式"
    pref, _, payload = prov.partition(":")
    if prefixes and pref not in prefixes:
        return f"前缀 {pref!r} 不在封闭集 {list(prefixes)}"
    if payload.strip() == "":
        return "载荷为空（有前缀没有内容）"
    return None


def scan(sessions_dir) -> dict:
    """实测段：`stem → {rows, first_session, head}`；不可解析者记 `error`（不静默丢）。"""
    out: dict = {}
    for p in sorted(Path(sessions_dir).glob("*.jsonl")):
        try:
            lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            rows = [json.loads(ln) for ln in lines]
        except Exception as e:                                   # noqa: BLE001
            out[p.stem] = {"error": f"{type(e).__name__}: {e}"}
            continue
        out[p.stem] = {"rows": len(rows),
                       "first_session": (rows[0].get("session") if rows else None),
                       "head": rows}
    return out


def fork_outputs(sessions: dict) -> set:
    """fork 输出识别：行内 `session` ≠ 文件名 stem（见 docstring「关键机械信号」）。"""
    return {stem for stem, d in sessions.items()
            if "error" not in d and d.get("first_session") not in (None, stem)}


def check(reg, sessions: dict) -> tuple:
    """判定表（DESIGN §4.4）→ `(bad, notes)`。**纯函数**（离线可正反夹测）。"""
    bad, notes = [], []
    if not isinstance(reg, dict):
        return ["[A] 登记表顶层不是 JSON 对象"], notes

    # ── A 表结构 ───────────────────────────────────────────────────────────
    for k in REQ_KEYS:
        if k not in reg:
            bad.append(f"[A] 缺字段 `{k}` ⇒ 空必须显式（无法区分「清单为空」与「忘了写」）")
    tk, pp = reg.get("trigger_kinds"), reg.get("provenance_prefixes")
    if not isinstance(tk, list) or not tk:
        bad.append("[A] `trigger_kinds` 为空 ⇒ 无封闭集可判")
    elif len(tk) != len(set(tk)):
        bad.append(f"[A] `trigger_kinds` 有重复项: {tk}")
    if not isinstance(pp, list) or not pp:
        bad.append("[A] `provenance_prefixes` 为空 ⇒ 无封闭集可判")
    elif len(pp) != len(set(pp)):
        bad.append(f"[A] `provenance_prefixes` 有重复项: {pp}")
    if reg.get("truth_source") != TRUTH_SOURCE:
        bad.append(f"[A] `truth_source` 必须为 {TRUTH_SOURCE!r}（真值源须显式声明为本表）")
    forks, non = reg.get("forks"), reg.get("non_rework")
    if forks is not None and not isinstance(forks, list):
        bad.append("[A] `forks` 必须是数组")
    if non is not None and not isinstance(non, list):
        bad.append("[A] `non_rework` 必须是数组")
    forks = forks if isinstance(forks, list) else []
    non = non if isinstance(non, list) else []
    tk = tk if isinstance(tk, list) else []
    pp = pp if isinstance(pp, list) else []

    # ── B 边自洽 ───────────────────────────────────────────────────────────
    seen_new: set = set()
    for i, f in enumerate(forks):
        at = f"forks[{i}]"
        if not isinstance(f, dict):
            bad.append(f"[B] {at} 不是对象")
            continue
        f_new, f_org = _s(f.get("new")), _s(f.get("origin"))
        if not f_new:
            bad.append(f"[B] {at} 缺/空 `new`")
        if not f_org:
            bad.append(f"[B] {at} 缺/空 `origin`")
        if f_new and f_org and f_new == f_org:
            bad.append(f"[B] {at} `new` == `origin`（自环不是返工）")
        if f_new in seen_new:
            bad.append(f"[B] {at} `new` 重复登记: {f_new}")
        seen_new.add(f_new)
        if f.get("trigger_kind") not in tk:
            bad.append(f"[B] {at} `trigger_kind`={f.get('trigger_kind')!r} 不在封闭集 {tk}")
        if _blank(f.get("reason")):
            bad.append(f"[B] {at} `reason` 空 / 仅空白 / 禁用词")
        sf = f.get("seq_from")
        if isinstance(sf, bool) or not isinstance(sf, int) or sf <= 0:
            bad.append(f"[B] {at} `seq_from` 必须是正整数: {sf!r}")
        pb = _prov_bad(f.get("provenance"), pp)
        if pb:
            bad.append(f"[B] {at} `provenance` {pb}")

    # ── C 声明 → 事实对账 ──────────────────────────────────────────────────
    for i, f in enumerate(forks):
        if not isinstance(f, dict):
            continue
        at = f"forks[{i}]"
        f_new, f_org, sf = _s(f.get("new")), _s(f.get("origin")), f.get("seq_from")
        if f_org and f_org not in sessions:
            bad.append(f"[C] {at} `origin` 会话不存在: {f_org}")
        if f_new and f_new not in sessions:
            bad.append(f"[C] {at} `new` 会话不存在: {f_new}")
        if not (f_new in sessions and f_org in sessions):
            continue
        if isinstance(sf, bool) or not isinstance(sf, int) or sf <= 0:
            continue
        dn, do = sessions[f_new], sessions[f_org]
        if "error" in dn or "error" in do:
            bad.append(f"[C] {at} 会话不可解析 ⇒ 无法对账（降级不当作通过）")
            continue
        if dn["rows"] != sf:
            bad.append(f"[C] {at} rows(new)={dn['rows']} ≠ seq_from={sf}（fork 恰复制 seq ≤ N 的行）")
        if do["rows"] < sf:
            bad.append(f"[C] {at} rows(origin)={do['rows']} < seq_from={sf}")
        if dn.get("first_session") != f_org:
            bad.append(f"[C] {at} new 行内携带的 session={dn.get('first_session')!r} ≠ 登记的 origin={f_org!r}")
        if dn["rows"] >= sf and do["rows"] >= sf and dn["head"][:sf] != do["head"][:sf]:
            bad.append(f"[C] {at} new 的前 {sf} 行 ≠ origin 的前 {sf} 行（逐行不等）")

    # ── D 孤儿扫描（反向：漏登即漂移） ──────────────────────────────────────
    outputs = fork_outputs(sessions)
    registered = seen_new | {_s(x.get("name")) for x in non if isinstance(x, dict)}
    for stem in sorted(outputs - registered):
        bad.append(f"[D] fork 输出未登记: {stem}（既不在 `forks[].new` 也不在 `non_rework`）")
    for i, x in enumerate(non):
        at = f"non_rework[{i}]"
        if not isinstance(x, dict):
            bad.append(f"[D] {at} 不是对象")
            continue
        nm = _s(x.get("name"))
        if not nm:
            bad.append(f"[D] {at} 缺 `name`")
        elif nm not in sessions:
            bad.append(f"[D] {at} `name` 会话不存在: {nm}")
        elif nm not in outputs:
            bad.append(f"[D] {at} `{nm}` **不是 fork 输出** ⇒ 豁免不能凭空写")
        if _blank(x.get("why")):
            bad.append(f"[D] {at} `why` 空 / 仅空白 / 禁用词")

    return bad, notes


# ── 内嵌自测（合成 fixture；不读真表、不写仓库）──────────────────────────────
def _selftest() -> int:
    import shutil
    import tempfile

    ok, fail = 0, 0

    def ck(name, cond):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok] {name}")
        else:
            fail += 1
            print(f"  [!!] {name}")

    base = {"version": 1, "updated": "2026-09-27", "owner": "x", "truth_source": "registry",
            "trigger_kinds": ["user-verdict", "undecided"], "provenance_prefixes": ["manual", "tool"],
            "forks": [], "non_rework": []}

    def mk(root, sessions):
        d = Path(root) / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        for stem, rows in sessions.items():
            (d / f"{stem}.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return d

    def has(bad, frag):
        return any(frag in b for b in bad)

    tmp = tempfile.mkdtemp(prefix="rg-selftest-")
    try:
        # 正例 fixture：o（3 行）+ f（= fork 于 seq 1，携 session=o）
        O = [{"seq": 1, "session": "o"}, {"seq": 2, "session": "o"}, {"seq": 3, "session": "o"}]
        F = [{"seq": 1, "session": "o"}]
        d = mk(tmp, {"o": O, "f": F})
        sess = scan(d)

        good = dict(base, forks=[{"new": "f", "origin": "o", "seq_from": 1,
                                  "trigger_kind": "user-verdict", "reason": "用户裁决回写",
                                  "provenance": "manual:x:2026-09-27", "date": "2026-09-27"}],
                    non_rework=[])
        ck("F01 合法表（空 non_rework + 1 条真 fork）→ 通过", check(good, sess)[0] == [])

        ck("F02 `forks` 缺 ⇒ 判红", has(check({k: v for k, v in base.items() if k != "forks"}, sess)[0], "`forks`"))
        ck("F03 `non_rework` 缺 ⇒ 判红", has(check({k: v for k, v in base.items() if k != "non_rework"}, sess)[0], "`non_rework`"))
        ck("F04 `truth_source` ≠ registry ⇒ 判红", has(check(dict(base, truth_source="x"), sess)[0], "truth_source"))
        ck("F05 `trigger_kinds` 空 ⇒ 判红", has(check(dict(base, trigger_kinds=[]), sess)[0], "trigger_kinds"))
        ck("F06 `provenance_prefixes` 空 ⇒ 判红", has(check(dict(base, provenance_prefixes=[]), sess)[0], "provenance_prefixes"))

        def one(**over):
            e = dict(good["forks"][0])
            e.update(over)
            return check(dict(good, forks=[e]), sess)[0]

        ck("F07 `trigger_kind` 不在封闭集 ⇒ 判红", has(one(trigger_kind="guess"), "不在封闭集"))
        ck("F08 `new` == `origin` ⇒ 判红", has(one(origin="f"), "自环"))
        ck("F09 `reason` = unknown ⇒ 判红", has(one(reason="unknown"), "reason"))
        ck("F10 `seq_from` = 0 ⇒ 判红", has(one(seq_from=0), "seq_from"))
        ck("F11 provenance 空串 ⇒ 判红", has(one(provenance=""), "空串"))
        ck("F12 provenance 仅空白 ⇒ 判红", has(one(provenance="   "), "仅含空白"))
        ck("F13 provenance 禁用词 ⇒ 判红", has(one(provenance="unknown"), "禁用词"))
        ck("F14 provenance 缺冒号 ⇒ 判红", has(one(provenance="manual"), "缺 `<前缀>"))
        ck("F15 provenance 前缀不在集 ⇒ 判红", has(one(provenance="guessed:x"), "前缀"))
        ck("F16 provenance 载荷为空 ⇒ 判红", has(one(provenance="manual:"), "载荷为空"))
        ck("F17 `new` 重复 ⇒ 判红", has(check(dict(good, forks=good["forks"] * 2), sess)[0], "重复登记"))

        ck("F18 origin 不存在 ⇒ 判红", has(one(origin="nope"), "`origin` 会话不存在"))
        ck("F19 new 不存在 ⇒ 判红", has(one(new="nope"), "`new` 会话不存在"))
        ck("F20 rows(new) ≠ seq_from ⇒ 判红", has(one(seq_from=2), "rows(new)"))
        d2 = mk(tmp + "/a", {"o": O, "g": [{"seq": 1, "session": "o", "diff": 1}]})
        ck("F21 前 N 行不等 ⇒ 判红",
           has(check(dict(good, forks=[dict(good["forks"][0], new="g", origin="o")]), scan(d2))[0], "逐行不等"))
        d3 = mk(tmp + "/b", {"o": O, "h": [{"seq": 1, "session": "z"}]})
        ck("F22 new 携带 session ≠ origin ⇒ 判红",
           has(check(dict(good, forks=[dict(good["forks"][0], new="h", origin="o")]), scan(d3))[0], "携带的 session"))

        ck("F23 孤儿（fork 输出未登记）⇒ 判红",
           has(check(dict(base, forks=[], non_rework=[]), sess)[0], "fork 输出未登记"))
        ck("F24 non_rework name 不存在 ⇒ 判红",
           has(check(dict(base, non_rework=[{"name": "zzz", "why": "w", "date": "2026-09-27"}]), sess)[0], "会话不存在"))
        ck("F25 non_rework name 不是 fork 输出 ⇒ 判红",
           has(check(dict(base, non_rework=[{"name": "o", "why": "w", "date": "2026-09-27"}]), sess)[0], "不是 fork 输出"))
        ck("F26 non_rework why 为空 ⇒ 判红",
           has(check(dict(base, non_rework=[{"name": "f", "why": "", "date": "2026-09-27"}]), sess)[0], "why"))
        ck("F27 non_rework 正确豁免 ⇒ 通过",
           check(dict(base, forks=[], non_rework=[{"name": "f", "why": "能力演示", "date": "2026-09-27"}]), sess)[0] == [])
        ck("F28 空表（forks/non_rework 皆显式 []）且无 fork 输出 ⇒ 通过",
           check(base, scan(mk(tmp + "/c", {"o": O})))[0] == [])
        # ★ Step 8 独立审查 P3-2 补齐：B4（new/origin 缺或空）与 C14（rows(origin) < seq_from）原**无单列 fixture**
        ck("F29 `new` 为空 ⇒ 判红（B4：new/origin 缺或空）", has(one(new=""), "缺/空 `new`"))
        d4 = mk(tmp + "/d", {"o": [{"seq": 1, "session": "o"}],
                             "p": [{"seq": 1, "session": "o"}, {"seq": 2, "session": "o"}]})
        ck("F30 rows(origin) < seq_from ⇒ 判红（C14）",
           has(check(dict(good, forks=[dict(good["forks"][0], new="p", origin="o", seq_from=2)]),
                     scan(d4))[0], "rows(origin)"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"[selftest] {ok}/{ok + fail} PASS")
    return EXIT_OK if fail == 0 else EXIT_BAD


def main() -> int:
    ap = argparse.ArgumentParser(description="回写返工图对账器（声明 → 实测 → 对账；只读）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    ap.add_argument("--selftest", action="store_true", help="内嵌自测（合成 fixture）")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if not REGISTRY.is_file():
        print(f"[FAIL] 登记表缺失: {REGISTRY.relative_to(ROOT)} ⇒ 先建表（DESIGN §4.1 schema）")
        return EXIT_DEGRADED
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception as e:                                        # noqa: BLE001
        print(f"[FAIL] 登记表不可解析: {type(e).__name__}: {e}（降级不当作通过）")
        return EXIT_DEGRADED

    sess = scan(SESSIONS)
    print(f"[登记] forks={len(reg.get('forks') or [])} · non_rework={len(reg.get('non_rework') or [])} · "
          f"trigger_kinds={reg.get('trigger_kinds')} · truth_source={reg.get('truth_source')}")
    print(f"[实测] sessions={len(sess)} · fork 输出={len(fork_outputs(sess))}"
          f"（{', '.join(sorted(fork_outputs(sess))) or '—'}）")
    bad, _ = check(reg, sess)
    if bad:
        for x in bad:
            print(f"  [FAIL] {x}")
        if a.json:
            print(json.dumps({"ok": False, "bad": bad}, ensure_ascii=False))
        print(f"[FAIL] {len(bad)} 项不一致 ⇒ exit 1（人工复核）")
        return EXIT_BAD
    print("[PASS] 登记表自洽，且与实测 session 一致（含孤儿扫描为空）")
    if a.json:
        print(json.dumps({"ok": True, "bad": []}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
