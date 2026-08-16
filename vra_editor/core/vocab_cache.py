"""Persists authority-vocabulary search results (see authority_lookup.py)
in a local SQLite FTS5 index, so a query already looked up once never
needs a repeat network round-trip -- and, just as importantly, so a
*different but related* query still surfaces an entry already in the
index ahead of anything freshly fetched. That's deliberate: the same
heading should get reused for the same concept across the archive
rather than the cataloguer picking a different-but-equally-valid
alternative each time, so search results favour precedent over novelty.

Three tables:
  - vocab_entries (an FTS5 table): every entry ever returned by a
    search, full-text indexed on its label. INSERT OR IGNORE semantics
    on (vocab, refid) -- enforced by hand, since FTS5 tables don't
    support real uniqueness constraints -- so the first-recorded label
    for a given entry sticks even if a later fetch phrases it
    slightly differently.
  - query_results: which entries each exact (vocab, query) search
    actually returned, so repeating that exact search reproduces the
    same result set faithfully -- a suggest API can match an entry via
    a variant/cross-reference label this app never indexes, so FTS
    matching on vocab_entries alone can't be relied on to reconstruct
    an exact past result.
  - queries_seen (derivable from query_results, kept separately as a
    fast existence check): which exact (vocab, query) searches have
    already gone to the network at all, including ones with zero
    results, so a no-hits search doesn't get repeated either.

Stores plain dicts, not AuthorityResult -- keeps this module dependency-
free; authority_lookup.py (the only caller) handles converting to/from
the dataclass.
"""

import re
import sqlite3
from pathlib import Path
from typing import Optional

from ..app_data import get_cache_dir

_DB_FILENAME = "vocab_cache.db"
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _db_path(config_path: Optional[Path] = None) -> Path:
    return get_cache_dir(config_path) / _DB_FILENAME


def _connect(config_path: Optional[Path] = None) -> sqlite3.Connection:
    path = _db_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS vocab_entries USING fts5("
        "vocab UNINDEXED, refid UNINDEXED, label, href UNINDEXED)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS queries_seen ("
        "vocab TEXT NOT NULL, query TEXT NOT NULL, PRIMARY KEY (vocab, query))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS query_results ("
        "vocab TEXT NOT NULL, query TEXT NOT NULL, refid TEXT NOT NULL, "
        "PRIMARY KEY (vocab, query, refid))"
    )
    return conn


def _match_expr(query: str) -> str:
    """Each word becomes a quoted prefix term ANDed together, e.g.
    "bronze sculp" -> '"bronze"* "sculp"*' -- quoting each token avoids
    passing FTS5 query-syntax characters straight through from
    whatever the user typed."""
    tokens = _TOKEN_RE.findall(query)
    return " ".join(f'"{tok}"*' for tok in tokens)


def search_local(vocab: str, query: str, config_path: Optional[Path] = None) -> list:
    """Every previously-cached entry for `vocab` whose label matches
    query's tokens, best match first. These represent precedent --
    entries already in use for a similar concept -- and are meant to
    be shown ahead of anything freshly fetched."""
    match_expr = _match_expr(query)
    if not match_expr:
        return []
    with _connect(config_path) as conn:
        rows = conn.execute(
            "SELECT label, vocab, refid, href FROM vocab_entries "
            "WHERE vocab = ? AND vocab_entries MATCH ? ORDER BY rank",
            (vocab, match_expr),
        ).fetchall()
    return [{"label": r[0], "vocab": r[1], "refid": r[2], "href": r[3]} for r in rows]


def already_fetched(vocab: str, query: str, config_path: Optional[Path] = None) -> bool:
    """True if this exact (vocab, query) has already gone to the
    network before -- distinct from search_local finding matches,
    since a genuinely new query should still be fetched even when
    related entries already exist locally."""
    key = query.strip().lower()
    with _connect(config_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM queries_seen WHERE vocab = ? AND query = ?", (vocab, key),
        ).fetchone()
    return row is not None


def get_exact(vocab: str, query: str, config_path: Optional[Path] = None) -> list:
    """Reconstructs exactly what an earlier fetch of this (vocab,
    query) returned, via query_results -- not by re-running
    search_local's fuzzy label match, which can miss entries a suggest
    API matched through a variant/cross-reference label this app
    doesn't index. Labels come from vocab_entries, i.e. whichever
    fetch recorded that entry first (see merge_entries)."""
    key = query.strip().lower()
    with _connect(config_path) as conn:
        rows = conn.execute(
            "SELECT e.label, e.vocab, e.refid, e.href FROM query_results q "
            "JOIN vocab_entries e ON e.vocab = q.vocab AND e.refid = q.refid "
            "WHERE q.vocab = ? AND q.query = ?",
            (vocab, key),
        ).fetchall()
    return [{"label": r[0], "vocab": r[1], "refid": r[2], "href": r[3]} for r in rows]


def record_fetch(vocab: str, query: str, entries: list, config_path: Optional[Path] = None) -> None:
    """Records a completed network fetch: which entries it returned
    (query_results, for faithful replay of this exact query later),
    merged into the entry index (vocab_entries -- first-recorded label
    per (vocab, refid) wins), and that this query itself is now
    answerable without the network (queries_seen), even if entries was
    empty."""
    key = query.strip().lower()
    with _connect(config_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO queries_seen (vocab, query) VALUES (?, ?)", (vocab, key),
        )
        for entry in entries:
            conn.execute(
                "INSERT OR IGNORE INTO query_results (vocab, query, refid) VALUES (?, ?, ?)",
                (vocab, key, entry["refid"]),
            )
            exists = conn.execute(
                "SELECT 1 FROM vocab_entries WHERE vocab = ? AND refid = ?",
                (vocab, entry["refid"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO vocab_entries (vocab, refid, label, href) VALUES (?, ?, ?, ?)",
                (vocab, entry["refid"], entry["label"], entry["href"]),
            )
        conn.commit()
