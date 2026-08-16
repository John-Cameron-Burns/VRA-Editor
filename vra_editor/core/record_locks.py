"""Advisory locking for a record file being edited, so two clients
(desktop or web) don't silently clobber each other's changes to the
same record concurrently. Nothing enforces this today -- a record is
genuinely unprotected against concurrent edits on a shared network
drive -- so this lives in core/ rather than being web-only, even
though only the web backend wires it in for v1.

SQLite under app_data.get_cache_dir(), following vocab_cache.py's
precedent for auxiliary server-side state: connect-per-call, CREATE
TABLE IF NOT EXISTS, no ORM.
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from ..app_data import get_cache_dir

DB_FILENAME = "record_locks.db"

# A lock not refreshed within this many seconds is treated as
# abandoned (e.g. a browser tab closed without releasing it) -- no
# cleanup daemon needed, acquire()/status() just check the age.
LOCK_TTL_SECONDS = 120

# How often a client holding a lock should call heartbeat() while the
# record stays open for editing.
HEARTBEAT_INTERVAL_SECONDS = 30


class LockStoreUnavailableError(Exception):
    """Raised when the lock database's own folder (config_path's
    [locations] app_data entry) can't actually be reached -- e.g. an
    offline network share, or a service account without permission on
    it. Locking here is explicitly advisory, not enforced (see this
    module's own docstring), so every public function below catches
    this and degrades to "as if locking weren't in the way" rather
    than failing the caller's request outright."""


def _db_path(config_path: Optional[Path] = None) -> Path:
    return get_cache_dir(config_path) / DB_FILENAME


def _connect(config_path: Optional[Path] = None) -> sqlite3.Connection:
    path = _db_path(config_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS locks ("
            "record_path TEXT PRIMARY KEY, "
            "holder TEXT NOT NULL, "
            "acquired_at REAL NOT NULL, "
            "heartbeat_at REAL NOT NULL)"
        )
        return conn
    except (OSError, sqlite3.Error) as e:
        raise LockStoreUnavailableError(f"Couldn't reach the lock database at {path} ({e}).") from e


def _key(record_path: Path) -> str:
    return str(Path(record_path).resolve())


def acquire(record_path: Path, holder: str, config_path: Optional[Path] = None) -> Optional[str]:
    """Acquires the lock on record_path for holder. Returns None on
    success -- the record was free, its lock had expired, or holder
    already held it (an idempotent refresh) -- or the current holder's
    username if someone else holds an unexpired lock.

    config_path overrides which vra-config.ini's [locations] app_data
    entry the lock database itself lives under -- the desktop app
    never passes this (it only has the one, OS-default config.ini),
    but a caller reading a different config.ini (the web backend, or a
    test) needs its lock state to follow that same config, not
    silently fall back to the OS default.

    Fails open (returns None, as if uncontested) if the lock store
    itself can't be reached -- locking here is advisory, not a
    guarantee (see module docstring), so refusing every edit outright
    because a network share hiccuped would be worse than the rare
    genuine double-edit this leaves unguarded against."""
    key = _key(record_path)
    now = time.time()
    try:
        conn = _connect(config_path)
    except LockStoreUnavailableError:
        return None
    try:
        row = conn.execute(
            "SELECT holder, heartbeat_at FROM locks WHERE record_path = ?", (key,)
        ).fetchone()
        if row is not None:
            current_holder, heartbeat_at = row
            expired = (now - heartbeat_at) > LOCK_TTL_SECONDS
            if current_holder != holder and not expired:
                return current_holder
        conn.execute(
            "INSERT INTO locks (record_path, holder, acquired_at, heartbeat_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(record_path) DO UPDATE SET holder = excluded.holder, "
            "acquired_at = excluded.acquired_at, heartbeat_at = excluded.heartbeat_at",
            (key, holder, now, now),
        )
        conn.commit()
        return None
    finally:
        conn.close()


def heartbeat(record_path: Path, holder: str, config_path: Optional[Path] = None) -> bool:
    """Refreshes the lock's heartbeat. False if record_path isn't
    currently held by holder (e.g. it expired and someone else took
    it, or it was never acquired) -- the caller should treat that as
    having lost the edit session. See acquire() for config_path.

    True (not "lock lost") if the lock store itself can't be reached
    -- same fail-open reasoning as acquire(); returning False here
    would read as "someone else has this record," which isn't what an
    unreachable store actually tells you."""
    key = _key(record_path)
    try:
        conn = _connect(config_path)
    except LockStoreUnavailableError:
        return True
    try:
        cur = conn.execute(
            "UPDATE locks SET heartbeat_at = ? WHERE record_path = ? AND holder = ?",
            (time.time(), key, holder),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def release(record_path: Path, holder: str, config_path: Optional[Path] = None) -> None:
    """Releases the lock if held by holder. Idempotent -- a no-op if
    it's not held, or held by someone else, or if the lock store can't
    be reached (nothing meaningful to release there either way). See
    acquire() for config_path."""
    key = _key(record_path)
    try:
        conn = _connect(config_path)
    except LockStoreUnavailableError:
        return
    try:
        conn.execute("DELETE FROM locks WHERE record_path = ? AND holder = ?", (key, holder))
        conn.commit()
    finally:
        conn.close()


def release_all_for_holder(holder: str, config_path: Optional[Path] = None) -> None:
    """Releases every lock currently held by holder, regardless of
    which record -- used on logout, since that only knows who's
    logging out, not which record(s) they had open. A no-op if the
    lock store can't be reached -- logout must never fail just because
    lock cleanup couldn't run. See acquire() for config_path."""
    try:
        conn = _connect(config_path)
    except LockStoreUnavailableError:
        return
    try:
        conn.execute("DELETE FROM locks WHERE holder = ?", (holder,))
        conn.commit()
    finally:
        conn.close()


def status(record_path: Path, config_path: Optional[Path] = None) -> Optional[dict]:
    """{'holder': ..., 'expired': bool} if a lock row exists for
    record_path -- even an expired one, so a caller can distinguish
    "never locked" from "was locked, now stale" -- else None, also
    used if the lock store itself can't be reached (no lock
    information available reads the same as "never locked"). See
    acquire() for config_path."""
    key = _key(record_path)
    try:
        conn = _connect(config_path)
    except LockStoreUnavailableError:
        return None
    try:
        row = conn.execute(
            "SELECT holder, heartbeat_at FROM locks WHERE record_path = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        holder, heartbeat_at = row
        return {'holder': holder, 'expired': (time.time() - heartbeat_at) > LOCK_TTL_SECONDS}
    finally:
        conn.close()
