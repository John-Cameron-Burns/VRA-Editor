"""Revision history browsing + restore -- the web equivalent of
desktop's Audits dialog (AuditDialog / DocumentController's restore
flow), backed by the same core/audit_log.py this session threaded
config_path through as prep for this phase (matching record_locks.py/
vocab_cache.py's earlier fix -- see audit_log.py's own docstrings).
"""

import datetime

from flask import Blueprint, jsonify, request

from vra_editor.core import audit_log

from ..auth import config_path_for_request, current_username, login_required
from ..records_common import commit_change, resolve_record_path

audit_bp = Blueprint('audits', __name__, url_prefix='/api/audits')


@audit_bp.get('')
@login_required
def list_audits():
    limit = request.args.get('limit', 1000, type=int)
    config_path = config_path_for_request()
    revisions = audit_log.list_revisions(limit=limit, config_path=config_path)
    return jsonify({'revisions': [
        {
            'sha': r.sha, 'filename': r.filename, 'author': r.author,
            'date': r.date.isoformat(), 'message': r.message,
        }
        for r in revisions
    ]})


@audit_bp.post('/restore')
@login_required
def restore_audit():
    """Restores a past revision's content into a NEW file under edit/
    -- never overwrites, matching DocumentController.restore_revision's
    own guard exactly (dest_path.exists() -> refuse). Always commits,
    same reasoning as Create record: no client-side undo exists for
    the web app, so a mistaken restore needs a recovery path.

    Body: {"sha", "filename", "dest_rel_path"}. filename is repo-
    relative (e.g. "edit/foo.xml" or "reviewed/foo.xml") -- exactly
    what GET /api/audits returned for the chosen row, echoed back
    unchanged; dest_rel_path is where under edit/ to write it.
    """
    config_path = config_path_for_request()
    data = request.get_json(silent=True) or {}

    sha = (data.get('sha') or '').strip()
    filename = (data.get('filename') or '').strip()
    dest_rel_path = (data.get('dest_rel_path') or '').strip()
    if not sha or not filename or not dest_rel_path:
        return jsonify({'error': 'sha, filename, and dest_rel_path are required'}), 400

    resolved = resolve_record_path('edit', dest_rel_path, config_path)
    if resolved is None:
        return jsonify({'error': "No 'edit' folder is configured"}), 404
    _folder, dest_path = resolved
    if dest_path.exists():
        return jsonify({'error': f'{dest_path.name} already exists'}), 409

    # read_revision_content only reads .sha/.filename off the Revision
    # it's given -- author/date/message are irrelevant here, since the
    # frontend already has that metadata from list_audits and doesn't
    # need it echoed back. It deliberately wraps every failure -- an
    # unreachable repo AND a bad/unknown sha or path alike -- into the
    # same RuntimeError (see its own docstring), so there's no reliable
    # way to tell "the repo is offline" apart from "that revision
    # doesn't exist" here; 404 covers both reasonably ("this revision
    # isn't there to restore").
    revision = audit_log.Revision(sha=sha, filename=filename, author='', date=datetime.datetime.now(), message='')
    try:
        content = audit_log.read_revision_content(revision, config_path)
    except RuntimeError:
        return jsonify({'error': f"Could not find {filename} at revision {sha[:8]}"}), 404

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)
    except OSError as e:
        return jsonify({'error': f"Couldn't restore -- {dest_path.parent} isn't reachable right now ({e})."}), 503

    commit_change(
        dest_path, data.get('commit_message'), current_username(), config_path,
        default_message=f'Restore {filename}@{sha[:8]} to {dest_rel_path}',
    )
    return jsonify({'rel_path': dest_rel_path}), 201
