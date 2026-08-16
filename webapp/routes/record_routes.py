import datetime

from lxml import etree
from flask import Blueprint, jsonify, request

from vra_editor.config import load_locations, load_media_extensions
from vra_editor.core import record_locks, record_transitions, review_notes
from vra_editor.core.schema_validator import DEFAULT_XSD_PATH, SchemaValidator
from vra_editor.core.xml_parser import VraXmlParser

from ..auth import config_path_for_request, current_username, login_required
from ..records_common import apply_field_edits, commit_change, owns_lock, resolve_record_path
from ..tree_json import node_to_json

record_bp = Blueprint('records', __name__, url_prefix='/api/records')

# work/image/collection, matching desktop's own record-type dropdown
# exactly (main_window.py's _on_create) -- these three are the only
# valid top-level VRA Core 4 record elements.
RECORD_TYPES = ('work', 'image', 'collection')


@record_bp.post('/edit')
@login_required
def create_record():
    """Creates a new, empty record directly under the edit location --
    the same operation as desktop's New action (main_window.py's
    _on_create / DocumentController.create_new_record): same three
    record types, same record_id validation (non-empty, no '/' or
    '\\'), same destination (edit_dir/{record_id}.xml, flat, no
    subfolders), same already-exists check.

    Deliberately written to disk immediately, unlike desktop (which
    holds the new record in memory until the first Save) -- the web
    app has no server-side "open unsaved document" state between
    requests, so there's nowhere else for it to live between this call
    and a later Save/structural edit. Always commits, same reasoning
    as the structural-mutation endpoints: no client-side undo exists
    for the web app, so skipping the commit would leave no recovery
    path if a record were created by mistake.

    Body: {"record_type": "work"|"image"|"collection", "record_id": "..."}.
    Returns {"rel_path": "{record_id}.xml"}, 201.
    """
    config_path = config_path_for_request()
    data = request.get_json(silent=True) or {}

    record_type = (data.get('record_type') or '').strip()
    if record_type not in RECORD_TYPES:
        return jsonify({'error': f"record_type must be one of {', '.join(RECORD_TYPES)}"}), 400

    record_id = (data.get('record_id') or '').strip()
    if not record_id:
        return jsonify({'error': 'record_id is required'}), 400
    if '/' in record_id or '\\' in record_id:
        return jsonify({'error': "record_id can't contain '/' or '\\'"}), 400

    resolved = resolve_record_path('edit', f'{record_id}.xml', config_path)
    if resolved is None:
        return jsonify({'error': "No 'edit' folder is configured"}), 404
    _folder, record_path = resolved
    if record_path.exists():
        return jsonify({'error': f'{record_path.name} already exists'}), 409

    parser = VraXmlParser()
    parser.new_document(record_type, record_id)
    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')

    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with open(record_path, 'wb') as f:
            f.write(xml_bytes)
    except OSError as e:
        return jsonify({'error': f"Couldn't create -- {record_path.parent} isn't reachable right now ({e})."}), 503

    commit_change(
        record_path, data.get('commit_message'), current_username(), config_path,
        default_message=f'Create {record_type} {record_id}',
    )
    return jsonify({'rel_path': f'{record_id}.xml'}), 201


@record_bp.get('/<key>/<path:rel_path>')
@login_required
def open_record(key, rel_path):
    """Opens a record for editing: acquires the lock (409 if someone
    else holds it) and returns the record's tree as JSON (see
    tree_json.node_to_json) plus its review notes."""
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved
    username = current_username()

    held_by = record_locks.acquire(record_path, username, config_path)
    if held_by is not None:
        return jsonify({'error': f'Locked by {held_by}'}), 409

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        record_locks.release(record_path, username, config_path)
        return jsonify({'error': 'Could not parse this record'}), 500

    return jsonify({
        'record': node_to_json(records[0]),
        'review_notes': review_notes.get_review_notes(parser.xml_root),
        'heartbeat_interval': record_locks.HEARTBEAT_INTERVAL_SECONDS,
    })


@record_bp.post('/<key>/<path:rel_path>/heartbeat')
@login_required
def heartbeat_record(key, rel_path):
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None:
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved
    if not record_locks.heartbeat(record_path, current_username(), config_path):
        return jsonify({'error': 'Lock lost -- someone else may hold this record now'}), 409
    return jsonify({'ok': True})


@record_bp.post('/<key>/<path:rel_path>/release')
@login_required
def release_record(key, rel_path):
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None:
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved
    record_locks.release(record_path, current_username(), config_path)
    return jsonify({'ok': True})


@record_bp.put('/<key>/<path:rel_path>')
@login_required
def save_record(key, rel_path):
    """Applies field edits, validates, and writes to disk (Save).

    Body: {"edits": [{"path": [i, j, ...], "text": "...", "vocab": "...",
    "refid": "...", "href": "...", "lang": "...", "type": "..."}, ...],
    "commit_message": "..." (optional)}.

    Each edit's node is resolved fresh against a just-reloaded document
    (tree_json.resolve_path -- the path addressing has no meaning past
    a single request) and written back with the same leaf/container
    write-back VraXmlParser.set_element_data/set_element_type uses
    everywhere else in this app. Requires the caller to currently hold
    this record's lock (i.e. they opened it via GET first) -- prevents
    writing over someone else's edit after losing the lock to an
    expired heartbeat.
    """
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to save it'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return jsonify({'error': 'Could not parse this record'}), 500
    record_node = records[0]

    error = apply_field_edits(parser, record_node, data.get('edits', []))
    if error:
        return jsonify({'error': error}), 400

    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    validator = SchemaValidator(str(DEFAULT_XSD_PATH))
    valid, message = validator.validate(xml_bytes)
    if not valid:
        return jsonify({'error': message}), 422

    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with open(record_path, 'wb') as f:
            f.write(xml_bytes)
    except OSError as e:
        return jsonify({'error': f"Couldn't save -- {record_path.parent} isn't reachable right now ({e})."}), 503

    commit_change(record_path, data.get('commit_message'), username, config_path)
    return jsonify({'ok': True})


@record_bp.post('/<key>/<path:rel_path>/flush-edits')
@login_required
def flush_edits(key, rel_path):
    """Writes pending field edits to the working file WITHOUT schema
    validation and without committing -- used internally by the
    frontend right before a structural/display/notes/lifecycle action
    (see RecordEditView.vue's flushEdits/runStructureAction), never
    called directly by a user action.

    Save (PUT above) always validates, because it's the real "I'm done
    editing" gate. But a structural mutation is allowed to leave the
    document momentarily invalid (structure_routes.py's whole module
    docstring is about exactly that -- an empty freshly-added titleSet,
    say). If the pre-action flush went through the validating Save
    instead, it would 422 whenever the document happened to already be
    in one of those allowed-but-invalid in-between states, permanently
    blocking the very next structural click that would have fixed it
    -- a deadlock. This endpoint exists to break that: same unvalidated
    write structure_routes.py's own endpoints already use. The
    structural action that follows does its own write immediately
    after and carries its own commit, which captures these field edits
    too (both land in the same commit) -- no separate commit here.
    """
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to edit it'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return jsonify({'error': 'Could not parse this record'}), 500
    record_node = records[0]

    error = apply_field_edits(parser, record_node, data.get('edits', []))
    if error:
        return jsonify({'error': error}), 400

    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with open(record_path, 'wb') as f:
            f.write(xml_bytes)
    except OSError as e:
        return jsonify({'error': f"Couldn't save -- {record_path.parent} isn't reachable right now ({e})."}), 503

    return jsonify({'ok': True})


@record_bp.post('/<key>/<path:rel_path>/xml')
@login_required
def record_xml(key, rel_path):
    """Returns the record's current raw XML as text, for the 'Show
    XML' panel -- the read-only counterpart to desktop's own Show XML
    toggle. Flushes pending field edits first (same unvalidated write
    flush_edits above uses), so what's shown reflects in-progress
    changes rather than just the last Save.

    Body: same {"edits": [...]} shape as flush-edits.
    """
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to view its XML'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return jsonify({'error': 'Could not parse this record'}), 500
    record_node = records[0]

    error = apply_field_edits(parser, record_node, data.get('edits', []))
    if error:
        return jsonify({'error': error}), 400

    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    try:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with open(record_path, 'wb') as f:
            f.write(xml_bytes)
    except OSError as e:
        return jsonify({'error': f"Couldn't save -- {record_path.parent} isn't reachable right now ({e})."}), 503

    return jsonify({'xml': xml_bytes.decode('utf-8')})


@record_bp.post('/<key>/<path:rel_path>/submit')
@login_required
def submit_record(key, rel_path):
    """Validates and moves the record from 'edit' into 'pending', for
    review -- the same operation as the desktop's Submit button,
    calling the same extracted core/record_transitions.move_to_location
    both use. Releases the lock on success (there's nothing left under
    'edit' to hold a lock on)."""
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to submit it'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    if parser.xml_root is None:
        return jsonify({'error': 'Could not parse this record'}), 500

    validator = SchemaValidator(str(DEFAULT_XSD_PATH))
    result = record_transitions.move_to_location(
        parser.xml_root, 'pending', load_locations(config_path), record_path,
        validator, validate=True, media_extensions=load_media_extensions(config_path),
    )
    if not result.success:
        return jsonify({'error': result.message}), 422

    commit_change(result.dest_path, data.get('commit_message'), username, config_path)
    record_locks.release(record_path, username, config_path)
    return jsonify({'ok': True, 'dest_path': str(result.dest_path)})


@record_bp.post('/<key>/<path:rel_path>/approve')
@login_required
def approve_record(key, rel_path):
    """Moves the record from 'pending' into 'reviewed' -- the same
    operation as the desktop's Approve button. Unlike Submit, doesn't
    re-validate (the document was already validated at Submit time --
    see record_transitions.move_to_location's own docstring), and
    always commits (a reviewer action needs a permanent history entry,
    unlike a routine Save)."""
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to approve it'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    if parser.xml_root is None:
        return jsonify({'error': 'Could not parse this record'}), 500

    result = record_transitions.move_to_location(
        parser.xml_root, 'reviewed', load_locations(config_path), record_path,
        SchemaValidator(str(DEFAULT_XSD_PATH)), validate=False,
        media_extensions=load_media_extensions(config_path),
    )
    if not result.success:
        return jsonify({'error': result.message}), 422

    commit_change(result.dest_path, data.get('commit_message'), username, config_path,
                  default_message=f'Approved by {username}')
    record_locks.release(record_path, username, config_path)
    return jsonify({'ok': True, 'dest_path': str(result.dest_path)})


@record_bp.post('/<key>/<path:rel_path>/reject')
@login_required
def reject_record(key, rel_path):
    """Moves the record from 'pending' into 'rejected', for the
    editor to revisit -- the same operation as the desktop's Reject
    button. An optional {"reason": "..."} is appended as a review
    note (so it travels with the file) before the move."""
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to reject it'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    if parser.xml_root is None:
        return jsonify({'error': 'Could not parse this record'}), 500

    reason = (data.get('reason') or '').strip()
    if reason:
        notes = review_notes.get_review_notes(parser.xml_root)
        notes.append({'text': reason, 'author': username,
                       'date': datetime.date.today().isoformat(), 'resolved': False})
        review_notes.set_review_notes(parser.xml_root, notes)

    result = record_transitions.move_to_location(
        parser.xml_root, 'rejected', load_locations(config_path), record_path,
        SchemaValidator(str(DEFAULT_XSD_PATH)), validate=False,
        media_extensions=load_media_extensions(config_path),
    )
    if not result.success:
        return jsonify({'error': result.message}), 422

    commit_change(result.dest_path, data.get('commit_message'), username, config_path,
                  default_message=f'Rejected by {username}')
    record_locks.release(record_path, username, config_path)
    return jsonify({'ok': True, 'dest_path': str(result.dest_path)})


@record_bp.post('/<key>/<path:rel_path>/notes')
@login_required
def add_note(key, rel_path):
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to add a note'}), 409

    text = ((request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return jsonify({'error': 'text is required'}), 400

    parser = VraXmlParser()
    parser.load(str(record_path))
    notes = review_notes.get_review_notes(parser.xml_root)
    notes.append({'text': text, 'author': username,
                   'date': __import__('datetime').date.today().isoformat(), 'resolved': False})
    review_notes.set_review_notes(parser.xml_root, notes)
    _write_notes_only(parser, record_path)

    commit_change(record_path, None, username, config_path, default_message='Add review note')
    return jsonify({'notes': notes})


@record_bp.put('/<key>/<path:rel_path>/notes/<int:index>')
@login_required
def update_note(key, rel_path, index):
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to update a note'}), 409

    data = request.get_json(silent=True) or {}

    parser = VraXmlParser()
    parser.load(str(record_path))
    notes = review_notes.get_review_notes(parser.xml_root)
    if not 0 <= index < len(notes):
        return jsonify({'error': 'No such note'}), 404
    if 'resolved' in data:
        notes[index]['resolved'] = bool(data['resolved'])
    review_notes.set_review_notes(parser.xml_root, notes)
    _write_notes_only(parser, record_path)

    commit_change(record_path, None, username, config_path, default_message='Update review note')
    return jsonify({'notes': notes})


@record_bp.delete('/<key>/<path:rel_path>/notes/<int:index>')
@login_required
def delete_note(key, rel_path, index):
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return jsonify({'error': 'Not found'}), 404
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return jsonify({'error': 'You must have this record open (and its lock) to remove a note'}), 409

    parser = VraXmlParser()
    parser.load(str(record_path))
    notes = review_notes.get_review_notes(parser.xml_root)
    if not 0 <= index < len(notes):
        return jsonify({'error': 'No such note'}), 404
    notes.pop(index)
    review_notes.set_review_notes(parser.xml_root, notes)
    _write_notes_only(parser, record_path)

    commit_change(record_path, None, username, config_path, default_message='Remove review note')
    return jsonify({'notes': notes})


def _write_notes_only(parser: VraXmlParser, record_path) -> None:
    """Review notes are a structural (XML-comment) change, not a leaf
    edit, so it bypasses save_record's schema-validation/edits path --
    a comment can't make the document schema-invalid, so there's
    nothing to validate here."""
    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with open(record_path, 'wb') as f:
        f.write(xml_bytes)
