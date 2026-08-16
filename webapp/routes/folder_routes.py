from flask import Blueprint, jsonify

from vra_editor.config import load_locations
from vra_editor.core import record_locks
from vra_editor.core.record_titles import extract_title

from ..auth import config_path_for_request, login_required
from ..records_common import ALLOWED_FOLDERS

folder_bp = Blueprint('folders', __name__, url_prefix='/api/folders')


@folder_bp.get('/<key>')
@login_required
def list_folder(key):
    if key not in ALLOWED_FOLDERS:
        return jsonify({'error': f"Unknown or unsupported folder '{key}'"}), 404

    config_path = config_path_for_request()
    locations = load_locations(config_path)
    folder = locations.get(key)
    if folder is None or not folder.exists():
        return jsonify({'error': f"No '{key}' folder configured"}), 404

    records = []
    for path in sorted(folder.rglob('*.xml')):
        lock = record_locks.status(path, config_path)
        records.append({
            'rel_path': str(path.relative_to(folder)),
            'title': extract_title(path),
            'locked_by': lock['holder'] if lock and not lock['expired'] else None,
        })
    return jsonify({'records': records})
