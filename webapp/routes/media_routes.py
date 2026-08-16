"""Media Sync's compare + fill-record-from-file -- the web-scoped half
of desktop's Media Sync (MediaSyncDialog / DocumentController.
compute_media_sync/apply_media_sync), now backed by the same shared
core/media_sync.py both use (see that module's own docstring for how
it was extracted). File-direction sync -- writing the record's chosen
fields INTO the uploaded file, and serving a modified file back for
download -- is out of scope here by design (an earlier, explicit
scoping decision this session), so unlike desktop's dialog, "use
record value" isn't offered as a choice at all: only 'record' or
skip.

pyexiv2 (IPTC read/write) is treated as optional on this deployment,
unlike desktop where it's a hard requirement: 5 of the 7 compared
fields (title/description/rights/agent/subject) come from IPTC, only
measurements/date/location are pure-Pillow/EXIF (see
core/media_metadata.py). Each request feature-detects it fresh rather
than caching the result at import time, so installing/removing it
takes effect without restarting the process.
"""

import json
import os
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request
from lxml import etree

from vra_editor.core import media_metadata, media_sync
from vra_editor.core.schema_validator import DEFAULT_XSD_PATH, SchemaValidator
from vra_editor.core.xml_parser import VraXmlParser

from ..auth import config_path_for_request, current_username, login_required
from ..records_common import commit_change, owns_lock, resolve_record_path
from ..tree_json import node_to_json

media_bp = Blueprint('media', __name__, url_prefix='/api/records')

# The 5 of media_sync.SYNC_FIELDS that need pyexiv2/IPTC -- the other
# 2 (date, location) are pure-Pillow/EXIF and work either way.
IPTC_FIELDS = ('title', 'description', 'rights', 'agent', 'subject')


def _pyexiv2_available() -> bool:
    try:
        import pyexiv2  # noqa: F401
    except ImportError:
        return False
    return True


def _save_upload_to_temp(file_storage) -> Path:
    """Uploaded file saved to a throwaway temp path for the duration
    of this request only -- there's no persistent linked-media concept
    here (matching desktop's own by-design lack of one; see
    DocumentController.guess_linked_media_path's docstring), and no
    session state to carry a compare step's file across to a later
    apply request, so apply re-uploads the same file rather than
    referencing anything left over from compare."""
    suffix = Path(file_storage.filename or '').suffix
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'wb') as f:
        file_storage.save(f)
    return Path(temp_path)


def _load_record(key, rel_path, config_path):
    """(record_path, parser, record_node) or a ready-to-return error
    tuple -- exactly one is None."""
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return None, (jsonify({'error': 'Not found'}), 404)
    _folder, record_path = resolved

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return None, (jsonify({'error': 'Could not parse this record'}), 500)
    return (record_path, parser, records[0]), None


@media_bp.post('/<key>/<path:rel_path>/media-sync/compare')
@login_required
def compare_media(key, rel_path):
    """Read-only -- doesn't require the record's lock, matching
    export_routes.py's own no-lock-needed stance for anything that
    doesn't write."""
    config_path = config_path_for_request()
    context, error = _load_record(key, rel_path, config_path)
    if error:
        return error
    _record_path, _parser, record_node = context

    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return jsonify({'error': 'file is required'}), 400

    iptc_available = _pyexiv2_available()
    temp_path = _save_upload_to_temp(upload)
    try:
        info = media_metadata.read_image_info(temp_path)
        iptc_fields = media_metadata.read_iptc(temp_path) if iptc_available else {}
    except Exception as e:
        return jsonify({'error': f"Could not read this file: {e}"}), 400
    finally:
        temp_path.unlink(missing_ok=True)

    result = media_sync.compute_media_sync_from_info(record_node.element, info, iptc_fields)
    if not iptc_available:
        for name in IPTC_FIELDS:
            result['fields'][name]['status'] = 'unavailable'
    result['iptc_available'] = iptc_available
    return jsonify(result)


@media_bp.post('/<key>/<path:rel_path>/media-sync/apply')
@login_required
def apply_media(key, rel_path):
    """selections (a JSON object in the 'selections' form field,
    alongside the re-uploaded 'file') maps field name -> 'record';
    anything else is 400 -- there is no file-direction here (see this
    module's own docstring). Measurements are always written from the
    file, unconditionally, matching desktop's own apply_media_sync.
    Schema-validates before writing -- unlike the structure_routes.py
    endpoints, a media-sync fill is a single atomic action that
    produces a complete, schema-valid sub-tree for each field it
    touches (e.g. a full <agentSet><agent><name>...) rather than an
    intentionally-incomplete intermediate step, so there's no two-click
    workflow here for validation to get in the way of."""
    config_path = config_path_for_request()
    context, error = _load_record(key, rel_path, config_path)
    if error:
        return error
    record_path, parser, record_node = context

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to change it'}), 409

    upload = request.files.get('file')
    if upload is None or not upload.filename:
        return jsonify({'error': 'file is required'}), 400

    try:
        selections = json.loads(request.form.get('selections') or '{}')
    except json.JSONDecodeError:
        return jsonify({'error': 'selections must be valid JSON'}), 400
    for name, direction in selections.items():
        if name not in media_sync.SYNC_FIELDS:
            return jsonify({'error': f"Unknown field '{name}'"}), 400
        if direction != 'record':
            return jsonify({'error': "File-direction sync isn't supported here -- only 'record' is accepted"}), 400

    iptc_available = _pyexiv2_available()
    temp_path = _save_upload_to_temp(upload)
    try:
        info = media_metadata.read_image_info(temp_path)
        iptc_fields = media_metadata.read_iptc(temp_path) if iptc_available else {}
    except Exception as e:
        return jsonify({'error': f"Could not read this file: {e}"}), 400
    finally:
        temp_path.unlink(missing_ok=True)

    record_elem = record_node.element
    record_specs = record_node.child_specs
    media_sync.write_measurements(parser, record_elem, record_specs, info)
    for name in selections:
        if name in IPTC_FIELDS and not iptc_available:
            continue  # iptc_fields is empty anyway -- fill_record_field would just no-op
        media_sync.fill_record_field(parser, record_elem, record_specs, name, info, iptc_fields)

    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    validator = SchemaValidator(str(DEFAULT_XSD_PATH))
    valid, message = validator.validate(xml_bytes)
    if not valid:
        return jsonify({'error': message}), 422

    record_path.parent.mkdir(parents=True, exist_ok=True)
    with open(record_path, 'wb') as f:
        f.write(xml_bytes)
    commit_change(record_path, None, username, config_path, default_message='Fill record from media file')

    records = parser.build_tree()
    return jsonify({'record': node_to_json(records[0])})
