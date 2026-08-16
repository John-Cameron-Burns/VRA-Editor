"""Tree mutation: adding a missing/repeatable child element, removing
an element, and editing an element's <display> translations. Each
endpoint reads the file, applies exactly one change, writes
immediately, and returns the freshly rebuilt tree (see the
implementation plan's "immediate-apply" design -- these change tree
shape, so they can't be batched with the staged-until-Save field
edits PUT /api/records/... handles).

Deliberately unvalidated, matching the desktop's own insert_child/
remove_element/update_display_data (DocumentController) exactly: none
of those validate either -- only Save/Submit do. A record mid-edit is
routinely schema-invalid for a moment (e.g. a freshly added titleSet
has zero <title> children until the next click adds one, but titleSet
requires at least one) -- on desktop that's just in-memory state, only
ever written to disk by a validated Save. The web app is stateless
per request, so the file in edit/ *is* that in-memory state; gating
every structural step on validity here would make the ordinary
"add a section, then fill in its first field" workflow impossible in
two clicks. Save/Submit remain the real validation gates, exactly as
before.
"""

from lxml import etree
from flask import Blueprint, jsonify, request

from vra_editor.core.xml_parser import VraXmlParser

from ..auth import config_path_for_request, current_username, login_required
from ..records_common import commit_change, owns_lock, resolve_record_path
from ..tree_json import node_to_json, resolve_path

structure_bp = Blueprint('structure', __name__, url_prefix='/api/records')


def _load_and_authorize(key, rel_path):
    """Common prologue for all three endpoints below: resolve the
    path, require the caller to hold the lock, load a fresh document.

    Returns (context, error) -- exactly one is None. context is
    (config_path, record_path, username, parser, record_node); error
    is a ready-to-return (jsonify(...), status) tuple.
    """
    config_path = config_path_for_request()
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return None, (jsonify({'error': 'Not found'}), 404)
    _folder, record_path = resolved

    username = current_username()
    if not owns_lock(record_path, username, config_path):
        return None, (jsonify({'error': 'You must have this record open (and its lock) to change its structure'}), 409)

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return None, (jsonify({'error': 'Could not parse this record'}), 500)

    return (config_path, record_path, username, parser, records[0]), None


def _write_and_commit(parser: VraXmlParser, record_path, username, config_path, default_message: str) -> None:
    """Writes parser's current tree to record_path and auto-commits.
    No schema validation -- see this module's docstring."""
    xml_bytes = etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with open(record_path, 'wb') as f:
        f.write(xml_bytes)
    commit_change(record_path, None, username, config_path, default_message=default_message)


@structure_bp.post('/<key>/<path:rel_path>/children')
@login_required
def add_child(key, rel_path):
    """Adds a new <tag> under the node at parent_path. 400 if tag
    isn't one of that node's schema-declared children; 422 if it's
    already at max_occurs -- server enforces the correct (section-
    view-style) cardinality gate, not the tree-view's looser one."""
    context, error = _load_and_authorize(key, rel_path)
    if error:
        return error
    config_path, record_path, username, parser, record_node = context

    data = request.get_json(silent=True) or {}
    tag = data.get('tag')
    try:
        parent_node = resolve_path(record_node, data.get('parent_path', []))
    except (IndexError, TypeError, KeyError):
        return jsonify({'error': f"Invalid parent_path: {data.get('parent_path')}"}), 400

    spec = next((s for s in parent_node.child_specs if s.tag == tag), None)
    if spec is None:
        return jsonify({'error': f"'{tag}' isn't a valid child here"}), 400

    existing_count = sum(1 for c in parent_node.children if c.data.get('tag') == tag)
    if spec.max_occurs is not None and existing_count >= spec.max_occurs:
        return jsonify({'error': f"'{tag}' already has the maximum of {spec.max_occurs}"}), 422

    sibling_order = [s.tag for s in parent_node.child_specs]
    parser.add_child(parent_node.element, tag, sibling_order)

    _write_and_commit(parser, record_path, username, config_path, default_message=f'Add {tag}')

    records = parser.build_tree()
    return jsonify({'record': node_to_json(records[0])})


@structure_bp.post('/<key>/<path:rel_path>/remove-element')
@login_required
def remove_element(key, rel_path):
    """Removes the element at path."""
    context, error = _load_and_authorize(key, rel_path)
    if error:
        return error
    config_path, record_path, username, parser, record_node = context

    data = request.get_json(silent=True) or {}
    path = data.get('path', [])
    if not path:
        return jsonify({'error': 'Cannot remove the record itself'}), 400
    try:
        node = resolve_path(record_node, path)
    except (IndexError, TypeError, KeyError):
        return jsonify({'error': f'Invalid path: {path}'}), 400

    parser.remove_element(node.element)

    _write_and_commit(parser, record_path, username, config_path, default_message='Remove element')

    records = parser.build_tree()
    return jsonify({'record': node_to_json(records[0])})


@structure_bp.post('/<key>/<path:rel_path>/display')
@login_required
def set_display(key, rel_path):
    """Sets (creating if absent) the <display> translations on the
    element at path -- path may point at an existing 'display'-type
    node or at its containing set/container node directly (both
    resolve to the same underlying element; see tree_json.py's
    module docstring on how a display node's .element is set)."""
    context, error = _load_and_authorize(key, rel_path)
    if error:
        return error
    config_path, record_path, username, parser, record_node = context

    data = request.get_json(silent=True) or {}
    translations = data.get('translations')
    if not isinstance(translations, dict):
        return jsonify({'error': 'translations must be an object of {lang: text}'}), 400
    try:
        node = resolve_path(record_node, data.get('path', []))
    except (IndexError, TypeError, KeyError):
        return jsonify({'error': f"Invalid path: {data.get('path')}"}), 400

    parser.set_display_translations(node.element, translations)

    _write_and_commit(parser, record_path, username, config_path, default_message='Update display translations')

    records = parser.build_tree()
    return jsonify({'record': node_to_json(records[0])})
