"""H-2: stage-level max_retries must be consumed."""

from __future__ import annotations

from researchclaw.pipeline.executor import _call_with_retries
from researchclaw.pipeline.stages import Stage, StageStatus


class _Result:
    def __init__(self, status: StageStatus) -> None:
        self.status = status


def test_zero_retries_calls_once() -> None:
    calls = []

    def call():
        calls.append(1)
        return _Result(StageStatus.FAILED)

    result = _call_with_retries(call, 0, Stage.TOPIC_INIT)
    assert result.status is StageStatus.FAILED
    assert len(calls) == 1


def test_two_retries_allows_three_attempts() -> None:
    calls = []

    def call():
        calls.append(1)
        return _Result(StageStatus.FAILED)

    _call_with_retries(call, 2, Stage.TOPIC_INIT)
    assert len(calls) == 3


def test_success_stops_retrying() -> None:
    calls = []

    def call():
        calls.append(1)
        if len(calls) < 2:
            return _Result(StageStatus.FAILED)
        return _Result(StageStatus.DONE)

    result = _call_with_retries(call, 5, Stage.TOPIC_INIT)
    assert result.status is StageStatus.DONE
    assert len(calls) == 2
