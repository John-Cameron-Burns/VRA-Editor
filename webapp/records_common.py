"""Shared helpers for every records/folders blueprint -- record path
resolution, lock-ownership checks, and git-commit-on-change. Extracted
from record_routes.py once folder_routes.py needed its own copy too
and a second blueprint (structure_routes.py) was about to need a
third.
"""

from pathlib import Path
from typing import Optional

from vra_editor.config import load_locations
from vra_editor.core import commit_to_git, record_locks
from .tree_json import resolve_path

# 'edit' (cataloguing) and 'pending' (review queue) are the only
# locations exposed through the web app -- reviewed/rejected/released
# are reachable only via the transitions *into* them (Approve/Reject/
# Submit), never browsed/opened directly, matching how the desktop's
# own Review button only ever opens from 'pending'.
ALLOWED_FOLDERS = ('edit', 'pending')


def resolve_record_path(key: str, rel_path: str, config_path) -> Optional[tuple]:
    """(folder, record_path) for key/rel_path, or None if key isn't an
    allowed/configured location, or rel_path would resolve outside of
    it (e.g. via '../..' path traversal)."""
    if key not in ALLOWED_FOLDERS:
        return None
    locations = load_locations(config_path)
    folder = locations.get(key)
    if folder is None:
        return None
    folder = folder.resolve()
    record_path = (folder / rel_path).resolve()
    if not record_path.is_relative_to(folder):
        return None
    return folder, record_path


def owns_lock(record_path: Path, username: str, config_path) -> bool:
    lock = record_locks.status(record_path, config_path)
    return lock is not None and lock['holder'] == username and not lock['expired']


def apply_field_edits(parser, record_node, edits) -> Optional[str]:
    """Applies each {path, text, vocab, refid, href, lang, type} edit to
    record_node's tree via parser's own leaf/container write-back.
    Returns None on success, or an error message string if some edit's
    path doesn't resolve or targets a node type that isn't editable.

    Shared by save_record (validates afterwards -- the user-facing
    Save) and flush_edits (does not -- an internal step that persists
    pending field edits to the working file just before a structural
    mutation, which is allowed to leave the document momentarily
    schema-invalid; see structure_routes.py's module docstring).
    """
    for edit in edits:
        try:
            node = resolve_path(record_node, edit.get('path', []))
        except (IndexError, TypeError, KeyError):
            return f"Invalid edit path: {edit.get('path')}"

        if node.node_type == 'leaf':
            parser.set_element_data(
                node.element, edit.get('text', ''),
                vocab=edit.get('vocab', ''), refid=edit.get('refid', ''),
                href=edit.get('href', ''), lang=edit.get('lang', ''),
                type_value=edit.get('type', ''),
            )
        elif node.node_type in ('set', 'container'):
            parser.set_element_type(node.element, edit.get('type', ''))
        else:
            return f"Cannot edit a node of type '{node.node_type}'"
    return None


def commit_change(path, commit_message: Optional[str], username: str, config_path,
                   default_message: Optional[str] = None) -> None:
    """Records path's current content to the shared git history.

    If commit_message is blank and default_message is given, commits
    with default_message instead of skipping -- for mutations (add/
    remove element, approve/reject, ...) where skipping the commit
    entirely would leave no recovery path, since there's no client-
    side undo for the web app. If default_message is None (Save/
    Submit's own call sites), a blank commit_message means skip
    entirely, matching the desktop's own optional commit-comment
    prompt -- most saves don't need a permanent history entry.
    """
    commit_message = (commit_message or '').strip() or (default_message or '')
    if commit_message:
        commit_to_git.add_file_to_repo(
            str(path), commit_message,
            author=commit_to_git.format_author_identity(username),
            config_path=config_path,
        )
