#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 黑盒烟雾门禁（G0b A0-1 必需钩子之一）。

语义（P-017 §7.3 + P-021 RESEARCH §6.3）：
  - 强制：`python -m researchclaw --help`，超时 30s，非 0 / 超时 / 无 usage 输出 → exit 1；
  - 条件：`researchclaw` 控制台脚本仅当 `shutil.which` 命中时执行；
    未安装 → `[skip] console script not installed`（打包层由 CI packaging job 用 wheel 验证）。
  - 目标耗时 < 10s（实测 --help < 1s）。
用法：python scripts/spec/blackbox_check.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time

TIMEOUT = 30


def _run(cmd):
    """返回 (ok, detail)。"""
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT)
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timeout >%ds" % TIMEOUT
    elapsed = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        return False, "exit %d (%.1fs)" % (p.returncode, elapsed)
    if "usage" not in out.lower():
        return False, "no usage output (%.1fs)" % elapsed
    return True, "%.1fs" % elapsed


def main():
    ok, detail = _run([sys.executable, "-m", "researchclaw", "--help"])
    if not ok:
        print("blackbox: module=fail (%s)" % detail)
        return 1
    module_detail = detail
    exe = shutil.which("researchclaw")
    if exe:
        ok2, detail2 = _run([exe, "--help"])
        if not ok2:
            print("blackbox: module=ok console=fail (%s)" % detail2)
            return 1
        console = "ok(%s)" % detail2
    else:
        console = "skip"
        print("[skip] console script not installed（CI packaging job 覆盖）")
    print("blackbox: module=ok(%s) console=%s" % (module_detail, console))
    return 0


if __name__ == "__main__":
    sys.exit(main())
