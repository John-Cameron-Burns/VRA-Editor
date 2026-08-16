from flask import Blueprint, jsonify

from vra_editor.config import load_locations
from vra_editor.core import record_locks
from vra_editor.core.record_titles import extract_title

from ..auth import config_path_for_request, login_required
from ..records_common import FOLDER_SOURCES

folder_bp = Blueprint('folders', __name__, url_prefix='/api/folders')


@folder_bp.get('/<key>')
@login_required
def list_folder(key):
    """Lists every record reachable through key -- for 'edit' this
    merges the 'edit' and 'rejected' locations (see
    records_common.FOLDER_SOURCES), each record tagged with which one
    it's actually sitting in via 'status' so the UI can tell them
    apart (and open/save/submit still resolves correctly either way,
    via resolve_record_path)."""
    if key not in FOLDER_SOURCES:
        return jsonify({'error': f"Unknown or unsupported folder '{key}'"}), 404

    config_path = config_path_for_request()
    locations = load_locations(config_path)

    records = []
    any_configured = False
    for source_key in FOLDER_SOURCES[key]:
        folder = locations.get(source_key)
        if folder is None or not folder.exists():
            continue
        any_configured = True
        for path in sorted(folder.rglob('*.xml')):
            lock = record_locks.status(path, config_path)
            records.append({
                'rel_path': str(path.relative_to(folder)),
                'title': extract_title(path),
                'status': source_key,
                'locked_by': lock['holder'] if lock and not lock['expired'] else None,
            })
    if not any_configured:
        return jsonify({'error': f"No '{key}' folder configured"}), 404
    return jsonify({'records': records})
