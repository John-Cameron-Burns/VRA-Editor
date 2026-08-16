"""Tests for vra_editor.core.record_locks -- normal locking behavior,
plus the degraded-mode ("fail open") behavior every public function
falls back to when the lock store itself can't be reached (e.g. a
network share the service account has no permission on -- the real
bug this locks in a regression test for: it used to crash every
request that touched locking with an uncaught PermissionError)."""

from pathlib import Path

from vra_editor.core import record_locks


def _write_config(tmp_path: Path, app_data: Path) -> Path:
    config_path = tmp_path / 'config.ini'
    config_path.write_text(f"[locations]\napp_data = {app_data}\n")
    return config_path


def test_acquire_then_status_shows_holder(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'

    assert record_locks.acquire(record, 'jsmith', config_path) is None
    status = record_locks.status(record, config_path)
    assert status == {'holder': 'jsmith', 'expired': False}


def test_acquire_blocks_a_different_holder(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'

    assert record_locks.acquire(record, 'jsmith', config_path) is None
    assert record_locks.acquire(record, 'mdoe', config_path) == 'jsmith'


def test_acquire_is_idempotent_for_the_same_holder(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'

    assert record_locks.acquire(record, 'jsmith', config_path) is None
    assert record_locks.acquire(record, 'jsmith', config_path) is None


def test_release_frees_the_lock(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'

    record_locks.acquire(record, 'jsmith', config_path)
    record_locks.release(record, 'jsmith', config_path)
    assert record_locks.status(record, config_path) is None


def test_release_all_for_holder_clears_every_record(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    rec1, rec2 = tmp_path / 'rec1.xml', tmp_path / 'rec2.xml'

    record_locks.acquire(rec1, 'jsmith', config_path)
    record_locks.acquire(rec2, 'jsmith', config_path)
    record_locks.release_all_for_holder('jsmith', config_path)

    assert record_locks.status(rec1, config_path) is None
    assert record_locks.status(rec2, config_path) is None


def test_heartbeat_true_when_held_by_holder(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'
    record_locks.acquire(record, 'jsmith', config_path)
    assert record_locks.heartbeat(record, 'jsmith', config_path) is True


def test_heartbeat_false_when_not_held_by_holder(tmp_path):
    config_path = _write_config(tmp_path, tmp_path / 'appdata')
    record = tmp_path / 'rec1.xml'
    assert record_locks.heartbeat(record, 'jsmith', config_path) is False


# ----------------------------------------------------------------------
# Degraded mode -- lock store unreachable (regression coverage for a
# real production crash: OSError propagating uncaught out of every
# lock operation, 500ing login/logout/record-open whenever the
# configured clutter folder is a network share the service account
# can't actually reach).
# ----------------------------------------------------------------------

def _write_config_with_blocked_cache(tmp_path: Path) -> Path:
    """A config.ini whose app_data/cache path is occupied by a FILE,
    so record_locks._connect()'s mkdir(exist_ok=True) genuinely fails
    with a real OSError -- not a mock, the actual failure mode."""
    app_data = tmp_path / 'appdata'
    app_data.mkdir()
    (app_data / 'cache').write_text('not a directory')
    return _write_config(tmp_path, app_data)


def test_connect_raises_lock_store_unavailable_on_real_failure(tmp_path):
    config_path = _write_config_with_blocked_cache(tmp_path)
    try:
        record_locks._connect(config_path)
        assert False, "expected LockStoreUnavailableError"
    except record_locks.LockStoreUnavailableError:
        pass


def test_acquire_fails_open_when_store_unreachable(tmp_path):
    config_path = _write_config_with_blocked_cache(tmp_path)
    record = tmp_path / 'rec1.xml'
    # None == "acquired uncontested" -- the caller can't tell this
    # apart from a real success, which is the point: don't block edits
    # just because the lock store itself is down.
    assert record_locks.acquire(record, 'jsmith', config_path) is None


def test_heartbeat_true_when_store_unreachable(tmp_path):
    config_path = _write_config_with_blocked_cache(tmp_path)
    record = tmp_path / 'rec1.xml'
    assert record_locks.heartbeat(record, 'jsmith', config_path) is True


def test_release_does_not_raise_when_store_unreachable(tmp_path):
    config_path = _write_config_with_blocked_cache(tmp_path)
    record = tmp_path / 'rec1.xml'
    record_locks.release(record, 'jsmith', config_path)  # must not raise


def test_release_all_for_holder_does_not_raise_when_store_unreachable(tmp_path):
    """The exact call that crashed logout in production."""
    config_path = _write_config_with_blocked_cache(tmp_path)
    record_locks.release_all_for_holder('jsmith', config_path)  # must not raise


def test_status_none_when_store_unreachable(tmp_path):
    config_path = _write_config_with_blocked_cache(tmp_path)
    record = tmp_path / 'rec1.xml'
    assert record_locks.status(record, config_path) is None
