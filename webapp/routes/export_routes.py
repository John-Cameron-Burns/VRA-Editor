"""Dublin Core / LIDO crosswalk downloads -- the web equivalent of
desktop's Export button (DocumentController.export_dublin_core_xml/
export_lido_xml). No new crosswalk logic here: both call straight
into core/export/dublin_core.py and core/export/lido.py, the same
modules desktop uses. Read-only, so unlike the record/structure
routes this doesn't require (or touch) the edit lock -- exporting
shouldn't block, or be blocked by, someone else having the record open.
"""

from flask import Blueprint, Response, jsonify

from vra_editor.core.export import dublin_core, lido
from vra_editor.core.xml_parser import VraXmlParser

from ..auth import config_path_for_request, login_required
from ..records_common import resolve_record_path

export_bp = Blueprint('export', __name__, url_prefix='/api/records')


def _load_record_element(key, rel_path, config_path):
    """(element, filename_stem) for the record at key/rel_path, or
    None if it doesn't resolve to a parseable record."""
    resolved = resolve_record_path(key, rel_path, config_path)
    if resolved is None or not resolved[1].exists():
        return None
    _folder, record_path = resolved

    parser = VraXmlParser()
    parser.load(str(record_path))
    records = parser.build_tree()
    if not records:
        return None
    return records[0].element, record_path.stem


@export_bp.get('/<key>/<path:rel_path>/export/dublin-core')
@login_required
def export_dublin_core(key, rel_path):
    config_path = config_path_for_request()
    result = _load_record_element(key, rel_path, config_path)
    if result is None:
        return jsonify({'error': 'Not found'}), 404
    element, stem = result

    xml = dublin_core.to_oai_dc_xml(element)
    return Response(xml, mimetype='application/xml', headers={
        'Content-Disposition': f'attachment; filename="{stem}-dc.xml"',
    })


@export_bp.get('/<key>/<path:rel_path>/export/lido')
@login_required
def export_lido(key, rel_path):
    config_path = config_path_for_request()
    result = _load_record_element(key, rel_path, config_path)
    if result is None:
        return jsonify({'error': 'Not found'}), 404
    element, stem = result

    xml = lido.to_lido_xml(element)
    return Response(xml, mimetype='application/xml', headers={
        'Content-Disposition': f'attachment; filename="{stem}-lido.xml"',
    })
