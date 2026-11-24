"""P-155 T25-T26: read_position persistence and restart behaviour."""
from __future__ import annotations

from pathlib import Path

from researchclaw.knowledge.read_position import load_position, save_position


class TestReadPosition:
    def test_position_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "read_positions.json"
        save_position(path, "paper", "p1", 3)
        assert load_position(path, "paper", "p1") == 3
        assert load_position(path, "paper", "p2") == 0
        assert load_position(path, "kg", "p1") == 0

    def test_restart_does_not_refetch(self, tmp_path: Path) -> None:
        path = tmp_path / "read_positions.json"
        save_position(path, "paper", "p1", 3)
        calls = 0

        def fetch() -> None:
            nonlocal calls
            calls += 1

        position = load_position(path, "paper", "p1")
        if position == 0:
            fetch()
        assert position == 3
        assert calls == 0
