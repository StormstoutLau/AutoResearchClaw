#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vendored 元数据同步器（D-1）：以 git blob 为唯一真值源重算 SOURCE.json。

blob 语义（DESIGN §4.4）：`bytes`/`sha256` 定义为该路径在 **git index** 中的原始字节数与
摘要（LF 规范态），与工作树、`core.autocrlf`、平台无关。只读 `:<path>`，不读工作树。

用法：
  python scripts/spec/vendor_source_sync.py --check   # 0 一致 / 1 有差异
  python scripts/spec/vendor_source_sync.py --write   # 重算校验和字段（需再 git add）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIR = "researchclaw/vendor/auto_prover"
SOURCE_JSON = f"{VENDOR_DIR}/SOURCE.json"

WRITE_HINT = "跑 `python scripts/spec/vendor_source_sync.py --write` 后提交"


def blob_bytes(paths: list[str], root: Path = ROOT) -> dict[str, bytes]:
    """{rel: 原始字节}；一次 `git cat-file --batch`（读 index）；未入库路径不出现在结果中。"""
    if not paths:
        return {}
    request = "".join(":%s\n" % p for p in paths).encode("utf-8")
    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=str(root),
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git cat-file 执行失败")
    out, pos, blobs = proc.stdout, 0, {}
    for rel in paths:
        eol = out.find(b"\n", pos)
        if eol < 0:
            break
        header = out[pos:eol].decode("utf-8", "replace")
        pos = eol + 1
        parts = header.split(" ")
        if len(parts) < 3 or parts[1] != "blob":
            continue  # "<input> missing"：未入库
        size = int(parts[2])
        blobs[rel] = out[pos:pos + size]
        pos += size + 1  # 内容 + 尾随 LF
    return blobs


def blob_facts(paths: list[str], root: Path = ROOT) -> dict[str, tuple[int, str]]:
    """{rel: (nbytes, sha256hex)}；由 blob_bytes 派生（单一实现）。"""
    return {rel: (len(data), hashlib.sha256(data).hexdigest())
            for rel, data in blob_bytes(paths, root).items()}


def all_paths(source: dict) -> list[str]:
    """SOURCE.json 中参与字节溯源的仓库相对路径（files[] + license_files[]）。"""
    return [key for key, _ in _keys(source)]


def _keys(source: dict) -> list[tuple[str, dict]]:
    """[(repo 相对路径, 条目)]，覆盖 files[] 与 license_files[]。"""
    keys = [(f"{VENDOR_DIR}/{e['path']}", e) for e in source.get("files", [])]
    keys += [(f"{VENDOR_DIR}/{e['path']}", e) for e in source.get("license_files", [])]
    return keys


def diff_entries(source: dict, facts: dict[str, tuple[int, str]]) -> list[str]:
    """返回差异描述行（空列表 = 一致）；覆盖 files[] 与 license_files[]。"""
    diffs = []
    files = source.get("files", [])
    if source.get("file_count") != len(files):
        diffs.append("file_count 声明 %s ≠ files[] 条数 %s" % (source.get("file_count"), len(files)))
    for key, entry in _keys(source):
        got = facts.get(key)
        if got is None:
            diffs.append("%s: 未入库（git index 无此 blob）" % entry["path"])
            continue
        nbytes, sha = got
        fields = []
        if "bytes" in entry and entry["bytes"] != nbytes:
            fields.append("bytes 记录 %s ≠ blob %s" % (entry["bytes"], nbytes))
        if entry.get("sha256") != sha:
            fields.append("sha256 记录 %s ≠ blob %s" % (entry["sha256"], sha))
        if fields:
            diffs.append("%s: %s" % (entry["path"], "；".join(fields)))
    return diffs


def _apply(source: dict, facts: dict[str, tuple[int, str]]) -> None:
    """就地重写校验和字段：files[] 为 bytes/sha256，license_files[] 仅 sha256。"""
    for key, entry in _keys(source):
        got = facts.get(key)
        if got is None:
            raise KeyError(key)
        nbytes, sha = got
        if "bytes" in entry:
            entry["bytes"] = nbytes
        entry["sha256"] = sha


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="vendor_source_sync", description="vendored 元数据 blob 同步器")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只校验（默认）")
    mode.add_argument("--write", action="store_true", help="按 blob 重写 bytes/sha256")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))

    source_path = ROOT / SOURCE_JSON
    raw = source_path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"      # 沿用现有行尾，避免全文件 diff
    source = json.loads(raw.decode("utf-8"))
    try:
        facts = blob_facts([key for key, _ in _keys(source)])
    except (OSError, RuntimeError) as exc:
        sys.stderr.write("[tool-error] git 不可用：%s\n" % exc)
        return 2

    if args.write:
        try:
            _apply(source, facts)
        except KeyError as exc:
            sys.stderr.write("[fail-closed] %s 未入库，拒绝写入：%s\n" % (exc.args[0], WRITE_HINT))
            return 1
        source_path.write_text(
            json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline=eol)
        print("SOURCE.json 已按 git blob 重算（%d 条目）；请 git add 后提交" % len(facts))
        return 0

    diffs = diff_entries(source, facts)
    if not diffs:
        print("SOURCE.json 与 git blob 一致（%d 条目）" % len(facts))
        return 0
    for line in diffs:
        print("[diff] %s" % line)
    print("SOURCE.json 与 git blob 不一致：%d 处；%s" % (len(diffs), WRITE_HINT))
    return 1


if __name__ == "__main__":
    sys.exit(main())
