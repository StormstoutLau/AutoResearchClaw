"""分支保护实证探针（P-122，一次性）——故意让 CI 红，用于验证 main 的必需检查阻断。

本文件仅在临时分支 `probe/bp-violation` 存在，取证后随分支一并删除，不入 main。
"""


def test_probe_violation_is_intentional() -> None:
    assert False, "intentional CI red: branch protection probe (P-122)"
