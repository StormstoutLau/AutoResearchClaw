#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容壳：转发到 scripts/spec/dc_validator.py（P-021 T-1）。

真身唯一位于 scripts/spec/；本文件不含逻辑，仅保证历史根路径引用可用。
"""
import os
import runpy
import sys

_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec", "dc_validator.py")
sys.path.insert(0, os.path.dirname(_TARGET))
sys.argv[0] = _TARGET
runpy.run_path(_TARGET, run_name="__main__")
