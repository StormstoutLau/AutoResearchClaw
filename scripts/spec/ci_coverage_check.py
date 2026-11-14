#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI 测试覆盖闭合守卫（D-5 / I-3 / I-6）。

左集 L = `git ls-files tests/test_*.py`
右集 R = `tests/ci_exclusions.yaml` 登记的 path（唯一声明源）
实收 C = `python -m pytest tests -m "not heavy" --collect-only -q` 的文件集合

双向闭合（缺一即出口 1，fail-closed）：
  1. R ⊆ L                          登记项不得指向已删除/不存在的测试文件
  2. L \\ R ⊆ C                     未登记的测试必须真被 CI 收集
  3. 登记项必须 marker: heavy，且文件内含 `pytest.mark.heavy`
  4. 打了 heavy marker 的文件必须在 R 内（O-4：声明源与运行时开关同改）

用法：
  python scripts/spec/ci_coverage_check.py --check      # 默认
  python scripts/spec/ci_coverage_check.py --selftest   # 内嵌 C1-C4
退出码：0 闭合 / 1 存在缺口 / 2 工具自身错误。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXCLUSIONS = "tests/ci_exclusions.yaml"
MARKER_TOKEN = "pytest.mark.heavy"
LEFT_GLOB = "tests/test_*.py"
FIELDS = ("path", "reason", "marker", "owner", "since")


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git 执行失败")
    return proc.stdout


def load_left(root=ROOT) -> list[str]:
    """L：git index 内的测试模块（仓库相对、正斜杠；排除包 __init__.py 等非 test_* 文件）。"""
    out = _git(root, "ls-files", "-z", "--", LEFT_GLOB)
    paths = {_norm(p.decode("utf-8", "replace")) for p in out.split(b"\0") if p}
    return sorted(p for p in paths if p.rsplit("/", 1)[-1].startswith("test_"))


def load_right(path) -> list[dict]:
    """R：排除登记表条目；缺表 / 版本不符 / 字段缺失 ⇒ 抛错（fail-closed）。"""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if data.get("version") != 1:
        raise ValueError("%s: version 必须为 1" % EXCLUSIONS)
    entries = data.get("exclusions") or []
    if not isinstance(entries, list):
        raise ValueError("%s: exclusions 必须是列表" % EXCLUSIONS)
    for entry in entries:
        missing = [k for k in FIELDS if not entry.get(k)]
        if missing:
            raise ValueError("%s: 登记项缺少字段 %s：%s" % (EXCLUSIONS, missing, entry))
        entry["path"] = _norm(entry["path"])
    return entries


def load_collected(root=ROOT) -> set[str]:
    """C：CI 实际收集集合（与 ci.yml tests job 同一命令）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-m", "not heavy", "--collect-only", "-q"],
        cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        tail = "\n".join(text.splitlines()[-20:])
        raise RuntimeError("pytest 收集失败（exit %d）：\n%s" % (proc.returncode, tail))
    files = set()
    for line in text.splitlines():
        line = line.strip()
        head = line.split("::", 1)[0]
        if "::" in line and head.endswith(".py"):
            files.add(_norm(head))
    return files


def closure_violations(left, right, collected, root=ROOT) -> list[str]:
    """双向闭合判定；返回违规描述行（空 = 闭合）。"""
    violations = []
    rpaths = [e["path"] for e in right]
    for entry in right:
        p = entry["path"]
        if p not in left:
            violations.append("%s: 登记项不在 %s（已删除？删除该登记）" % (p, LEFT_GLOB))
            continue
        if entry.get("marker") != "heavy":
            violations.append("%s: marker 必须为 heavy（声明源与运行时开关必须同改）" % p)
            continue
        try:
            body = (Path(root) / p).read_text(encoding="utf-8")
        except OSError as exc:
            violations.append("%s: 读取失败：%s" % (p, exc))
            continue
        if MARKER_TOKEN not in body:
            violations.append("%s: 已登记 heavy 但文件内无 %s" % (p, MARKER_TOKEN))
    for p in left:
        if p in rpaths:
            continue
        try:
            body = (Path(root) / p).read_text(encoding="utf-8")
        except OSError:
            body = ""
        if MARKER_TOKEN in body:
            violations.append("%s: 打了 heavy marker 但未登记（登记到 %s）" % (p, EXCLUSIONS))
            continue
        if p not in collected:
            violations.append("%s: 未被 CI 收集（确认可运行，或登记到 %s）" % (p, EXCLUSIONS))
    return violations


def run_selftest() -> bool:
    import tempfile

    ok = True

    def expect(cond, label):
        nonlocal ok
        print("  %s %s" % ("PASS" if cond else "FAIL", label))
        ok = ok and cond

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "tests").mkdir()
        (tmp / "tests" / "test_marked.py").write_text(
            "import pytest\n\n@pytest.mark.heavy\ndef test_x():\n    pass\n", encoding="utf-8")
        (tmp / "tests" / "test_plain.py").write_text(
            "def test_y():\n    pass\n", encoding="utf-8")
        A = "tests/test_marked.py"
        B = "tests/test_plain.py"
        entry = {"path": A, "reason": "需要真实外部依赖", "marker": "heavy",
                 "owner": "P-112", "since": "2026-11-15"}

        # C1 正向闭合：登记项有 marker、文件有打标，未登记项全部被收集
        v = closure_violations([A, B], [entry], {B}, root=tmp)
        expect(v == [], "C1 闭合 ⇒ 0 违规")

        # C2 未登记且未收集 ⇒ 缺口
        v = closure_violations([A, B], [entry], set(), root=tmp)
        expect(len(v) == 1 and B in v[0] and "未被 CI 收集" in v[0], "C2 未登记未收集 ⇒ 缺口")

        # C3 登记项不在左集 ⇒ 死项
        gone = dict(entry, path="tests/test_gone.py")
        v = closure_violations([A, B], [gone], {B}, root=tmp)
        expect(any("登记项不在" in x for x in v), "C3 死项 ⇒ 违规")

        # C4 已登记 heavy 但文件无 marker ⇒ 声明源与开关不一致
        v = closure_violations([A, B], [dict(entry, path=B)], {A}, root=tmp)
        expect(any("文件内无 %s" % MARKER_TOKEN in x for x in v), "C4 缺 marker ⇒ 违规")

    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ci_coverage_check", description="CI 测试覆盖闭合守卫")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="校验闭合（默认）")
    mode.add_argument("--selftest", action="store_true", help="内嵌 C1-C4 自测")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.selftest:
        passed = run_selftest()
        print("selftest: %s" % ("4/4 PASS" if passed else "FAIL"))
        return 0 if passed else 1

    try:
        left = load_left()
        right = load_right(ROOT / EXCLUSIONS)
        collected = load_collected()
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        sys.stderr.write("[fail-closed] %s\n" % exc)
        return 1

    violations = closure_violations(left, right, collected)
    if not violations:
        print("覆盖闭合：L=%d，R=%d，C=%d" % (len(left), len(right), len(collected)))
        return 0
    for line in violations:
        print("[gap] %s" % line)
    print("覆盖未闭合：%d 处" % len(violations))
    return 1


if __name__ == "__main__":
    sys.exit(main())
