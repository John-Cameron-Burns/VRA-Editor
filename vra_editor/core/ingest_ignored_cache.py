"""Remembers ingest-folder media files a cataloguer deliberately left
in place with no matching VRA record (via OrphanMediaDialog's "Ignore"
choice), so process_vra_directory's leftover-media report doesn't keep
resurfacing the same file as actionable on every subsequent Import
run. Identifies a file by the sha256 of its own content rather than
its path, so the entry still applies if the file is later renamed or
moved within ingest -- a plain path-based cache wouldn't survive that.

Deliberately kept out of core/ingest.py itself, which stays config-
decoupled and standalone-scriptable (see its own module docstring);
this module depends on app_data.get_cache_dir(), which resolves
through config.ini. Callers needing both (import_progress_dialog.py)
combine the two rather than ingest.py importing this directly.
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from ..app_data import get_cache_dir

_DB_FILENAME = "ingest_ignored.db"
_HASH_CHUNK_SIZE = 1024 * 1024


def _db_path(config_path: Optional[Path] = None) -> Path:
    return get_cache_dir(config_path) / _DB_FILENAME


def _connect(config_path: Optional[Path] = None) -> sqlite3.Connection:
    path = _db_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ignored_media ("
        "content_hash TEXT PRIMARY KEY, last_seen_name TEXT NOT NULL)"
    )
    return conn


def _content_hash(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_SIZE), b''):
            digest.update(chunk)
    return digest.hexdigest()


def is_ignored(path, config_path: Optional[Path] = None) -> bool:
    with _connect(config_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM ignored_media WHERE content_hash = ?", (_content_hash(path),),
        ).fetchone()
    return row is not None


def mark_ignored(path, config_path: Optional[Path] = None) -> None:
    with _connect(config_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ignored_media (content_hash, last_seen_name) VALUES (?, ?)",
            (_content_hash(path), Path(path).name),
        )
        conn.commit()
