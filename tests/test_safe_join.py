"""H-7: safe_join must reject the four escape classes."""

from __future__ import annotations

from pathlib import Path

import pytest

from researchclaw.utils.paths import safe_join


def test_valid_relative_path(tmp_path: Path) -> None:
    target = safe_join(tmp_path, "a", "b.txt")
    assert target == (tmp_path / "a" / "b.txt").resolve()


def test_parent_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../escape.txt")


def test_absolute_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_join(tmp_path, str(tmp_path.parent / "escape.txt"))


def test_nested_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_join(tmp_path, "a", "..", "..", "escape.txt")


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    link = base / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted on this platform")
    with pytest.raises(ValueError):
        safe_join(base, "link", "escape.txt")
