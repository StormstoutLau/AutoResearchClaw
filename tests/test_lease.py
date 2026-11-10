"""Single-writer lease with fencing tokens (G1a / A1-4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from researchclaw.runtime.lease import (
    LeaseBusy,
    LeaseLost,
    acquire,
    check_fencing,
    is_expired,
    read_lease,
    release,
    renew,
)


def test_acquire_creates_lease_with_fencing_one(tmp_path):
    lease = acquire(tmp_path, owner="host:1")
    assert lease.fencing == 1
    assert read_lease(tmp_path) == lease
    assert (tmp_path / "lease.json").is_file()


def test_second_owner_is_rejected(tmp_path):
    acquire(tmp_path, owner="host:1")
    with pytest.raises(LeaseBusy):
        acquire(tmp_path, owner="host:2")


def test_same_owner_can_reacquire_without_bumping_fencing(tmp_path):
    first = acquire(tmp_path, owner="host:1")
    again = acquire(tmp_path, owner="host:1")
    assert again.fencing == first.fencing == 1


def test_expired_lease_can_be_taken_over_with_higher_fencing(tmp_path):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    acquire(tmp_path, owner="host:1", ttl=1, now=past)
    assert is_expired(read_lease(tmp_path))
    takeover = acquire(tmp_path, owner="host:2")
    assert takeover.fencing == 2


def test_renew_requires_ownership(tmp_path):
    lease = acquire(tmp_path, owner="host:1")
    acquire(tmp_path, owner="host:2", now=datetime.now(timezone.utc) + timedelta(hours=2))
    with pytest.raises(LeaseLost):
        renew(tmp_path, lease)


def test_release_then_reacquire_bumps_fencing(tmp_path):
    lease = acquire(tmp_path, owner="host:1")
    release(tmp_path, lease)
    assert read_lease(tmp_path).released is True
    nxt = acquire(tmp_path, owner="host:2")
    assert nxt.fencing == 2


def test_check_fencing_semantics(tmp_path):
    lease = acquire(tmp_path, owner="host:1")
    assert check_fencing(lease, 1) is True
    assert check_fencing(lease, 2) is False
