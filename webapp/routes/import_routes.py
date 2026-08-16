"""Import (ingest -> edit) + orphan media -- the web equivalent of
desktop's Import button (ImportProgressDialog) and its Stash/Ignore/
Leave orphan-media follow-up (OrphanMediaDialog). Same core.ingest
module desktop uses; no new ingest logic here.

Deliberately synchronous, same as desktop: process_vra_directory
already blocks the GUI thread there too (see its own module
docstring -- desktop just pumps QApplication.processEvents() from the
progress callback instead of using a worker thread). This endpoint
has no progress callback at all -- an HTTP request/response has no
equivalent of a progress bar to drive, and there's no background-job
infrastructure in this app yet for a large ingest backlog that would
make a synchronous request take too long for one HTTP round trip;
flagged here as a known limitation, not solved.

No git commit here, matching desktop exactly: process_vra_directory
writes fresh copies into edit_dir but never touches git, and the
originals it consumed are preserved (moved to ingest_dir/done/, not
deleted) -- so unlike Create record/structural edits, there's already
a recovery path without one.
"""

from pathlib import Path

from flask import Blueprint, jsonify, request

from vra_editor.config import load_locations, load_media_extensions
from vra_editor.core import ingest, ingest_ignored_cache

from ..auth import config_path_for_request, login_required

import_bp = Blueprint('import_', __name__, url_prefix='/api/import')


def _ingest_dir_or_error(config_path):
    """(ingest_dir, edit_dir) or a ready-to-return error tuple -- both
    locations must be configured, matching desktop's own _on_import
    guard exactly."""
    locations = load_locations(config_path)
    ingest_dir = locations.get('ingest')
    edit_dir = locations.get('edit')
    if ingest_dir is None or edit_dir is None:
        return None, (jsonify({'error': "Both 'ingest' and 'edit' folders must be configured"}), 400)
    return (ingest_dir, edit_dir), None


def _resolve_orphan_path(rel_path: str, ingest_dir: Path):
    """The ingest folder isn't one of records_common's ALLOWED_FOLDERS
    (it's not browsable/editable like edit/pending -- only Import ever
    reaches into it), so this is its own small traversal-safe resolver
    rather than reusing resolve_record_path for an unrelated location."""
    ingest_dir = ingest_dir.resolve()
    candidate = (ingest_dir / rel_path).resolve()
    if not candidate.is_relative_to(ingest_dir):
        return None
    return candidate


@import_bp.post('/run')
@login_required
def run_import():
    config_path = config_path_for_request()
    dirs, error = _ingest_dir_or_error(config_path)
    if error:
        return error
    ingest_dir, edit_dir = dirs

    media_extensions = load_media_extensions(config_path)
    leftover = ingest.process_vra_directory(str(ingest_dir), str(edit_dir), media_extensions=media_extensions)

    ingest_dir_resolved = ingest_dir.resolve()
    orphans = [
        {'rel_path': str(path.relative_to(ingest_dir_resolved))}
        for path in leftover
        if not ingest_ignored_cache.is_ignored(path, config_path)
    ]
    return jsonify({'ok': True, 'orphan_media': orphans})


@import_bp.post('/orphans/stash')
@login_required
def stash_orphan():
    config_path = config_path_for_request()
    dirs, error = _ingest_dir_or_error(config_path)
    if error:
        return error
    ingest_dir, _edit_dir = dirs

    data = request.get_json(silent=True) or {}
    rel_path = (data.get('rel_path') or '').strip()
    if not rel_path:
        return jsonify({'error': 'rel_path is required'}), 400

    file_path = _resolve_orphan_path(rel_path, ingest_dir)
    if file_path is None or not file_path.exists():
        return jsonify({'error': 'Not found'}), 404

    ingest.stash_orphan_media(str(file_path), str(ingest_dir))
    return jsonify({'ok': True})


@import_bp.post('/orphans/ignore')
@login_required
def ignore_orphan():
    config_path = config_path_for_request()
    dirs, error = _ingest_dir_or_error(config_path)
    if error:
        return error
    ingest_dir, _edit_dir = dirs

    data = request.get_json(silent=True) or {}
    rel_path = (data.get('rel_path') or '').strip()
    if not rel_path:
        return jsonify({'error': 'rel_path is required'}), 400

    file_path = _resolve_orphan_path(rel_path, ingest_dir)
    if file_path is None or not file_path.exists():
        return jsonify({'error': 'Not found'}), 404

    ingest_ignored_cache.mark_ignored(file_path, config_path)
    return jsonify({'ok': True})
