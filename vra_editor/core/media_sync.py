"""Compares a VRA record's fields against an image/media file's own
embedded IPTC/EXIF metadata, and computes what filling the record's
gaps from the file would write. Extracted from
DocumentController.compute_media_sync/apply_media_sync (whose bodies
are now thin wrappers around compute_media_sync/write_measurements/
fill_record_field below), the same way core/record_transitions.py was
pulled out of _move_to_location earlier -- so this logic is reusable
by the web backend, which has no Qt/DocumentController at all.

Deliberately record-direction only: DocumentController's own
apply_media_sync can also write chosen fields INTO the file (IPTC/EXIF
injection) -- that half stays exactly where it is, unextracted, since
the web app's own Media Sync feature was scoped down to compare +
fill-record-from-file only (never modifying or serving back the
uploaded file). fill_record_field here is the "record" direction of
apply_media_sync's per-field selections handling; there is no
"file" direction function in this module by design.

The low-level element helpers below (_first_text, _all_sub_text,
_creation_date_text, _ensure_set, _add_set_item, _type_name_of,
_replace_measurement) are intentionally small private duplicates of
same-named methods still on DocumentController, rather than a further
shared extraction -- DocumentController's own copies are also used by
build_iptc_fields/get_creation_date_text/set_creation_date, none of
which are part of media sync or in scope here; touching those to
de-duplicate a handful of simple lxml-walking helpers would widen this
change into unrelated (and already working, already tested) desktop
Inject/fuzzy-date code for no benefit to this module's own callers.
"""

from typing import Optional

from . import media_metadata, vra_structure
from .xml_parser import VRA_NS, VraXmlParser

# AAT unit terms for the auto-populated pixel/dpi measurements, in the
# vocab/refid/href form used throughout this archive's own sample data.
AAT_PIXELS = {
    'vocab': 'AAT', 'refid': '300266190',
    'href': 'http://vocab.getty.edu/page/aat/300266190',
}
AAT_DPI = {
    'vocab': 'AAT', 'refid': '300410385',
    'href': 'http://vocab.getty.edu/page/aat/300410385',
}

# Fields kept in sync between record and file, keyed by the same name
# used throughout compute_media_sync/fill_record_field.
SYNC_FIELDS = ('title', 'description', 'rights', 'agent', 'subject', 'date', 'location')

# Fields with a real "write into the file" implementation on
# DocumentController (see its own _file_fields_to_write) -- location is
# deliberately not one of them: there's no GPS-EXIF writer, only a GPS
# reader (media_metadata.read_image_info), so a record's location can
# only ever flow file -> record. compute_media_sync downgrades what
# would otherwise be a 'fill_file' classification for location to
# 'empty' (nothing actionable) for exactly this reason.
FILE_WRITABLE_FIELDS = ('title', 'description', 'rights', 'agent', 'subject', 'date')


def compute_media_sync(record_root, path) -> dict:
    """Read-only comparison between record_root (the record element,
    e.g. a VraTreeNode's .element for a work/image/collection) and an
    image file at path. Returns:

      {'measurements': {'width': int, 'height': int,
                         'resolution': Optional[int], 'file_size': int},
       'fields': {field_name: {'record': value, 'file': value,
                                'status': 'fill_record'|'fill_file'|
                                          'conflict'|'in_sync'|'empty'}}}

    measurements are always "file replaces record" (dimensions/size are
    physical facts about the file, not an editorial choice) so they're
    reported separately, not classified like the other fields.

    fields covers title/description/rights/agent/subject/date/location,
    each classified by comparing the record's current value against
    the file's IPTC/EXIF value. Raises ImportError from
    media_metadata.read_iptc if pyexiv2 isn't installed -- callers
    that need to run without it (e.g. the web backend) should catch
    that themselves and fall back to file_value='' for the five
    IPTC-backed fields rather than calling this function at all with
    IPTC assumed available; see webapp/routes/media_routes.py.
    """
    info = media_metadata.read_image_info(path)
    iptc_fields = media_metadata.read_iptc(path)
    return compute_media_sync_from_info(record_root, info, iptc_fields)


def compute_media_sync_from_info(record_root, info, iptc_fields: dict) -> dict:
    """compute_media_sync's actual logic, split out so a caller that
    already read info/iptc_fields itself (e.g. to feature-detect pyexiv2
    and substitute an empty iptc_fields when it's unavailable) doesn't
    need to re-read the file."""
    measurements = {
        'width': info.width,
        'height': info.height,
        'resolution': int(info.dpi) if info.dpi is not None else None,
        'file_size': info.file_size,
    }

    fields = {}
    for name in SYNC_FIELDS:
        record_value = _record_field_value(record_root, name)
        file_value = _file_field_value(name, info, iptc_fields)
        status = _classify_sync_field(record_value, file_value)
        if status == 'fill_file' and name not in FILE_WRITABLE_FIELDS:
            status = 'empty'
        fields[name] = {'record': record_value, 'file': file_value, 'status': status}

    return {'measurements': measurements, 'fields': fields}


def _classify_sync_field(record_value, file_value) -> str:
    if not record_value and not file_value:
        return 'empty'
    if record_value and not file_value:
        return 'fill_file'
    if file_value and not record_value:
        return 'fill_record'
    return 'in_sync' if record_value == file_value else 'conflict'


def _record_field_value(root, name: str):
    """The record's current value for a sync field, in the same shape
    _file_field_value returns for it (str for scalars, list[str] for
    agent/subject, a '{lat}, {lon}' string for location) so the two are
    directly comparable."""
    if root is None:
        return '' if name not in ('agent', 'subject') else []
    if name == 'title':
        return _first_text(root, 'title')
    if name == 'description':
        return _first_text(root, 'description')
    if name == 'rights':
        elem = root.find(f'.//{{{VRA_NS}}}rights/{{{VRA_NS}}}text')
        return (elem.text or '').strip() if elem is not None else ''
    if name == 'agent':
        return _all_sub_text(root, 'agent', 'name')
    if name == 'subject':
        return _all_sub_text(root, 'subject', 'term')
    if name == 'date':
        return _creation_date_text(root)
    if name == 'location':
        for location in root.iter(f'{{{VRA_NS}}}location'):
            if location.get('type') != 'creation':
                continue
            name_elem = location.find(f'{{{VRA_NS}}}name')
            if name_elem is not None and name_elem.get('type') == 'geographic':
                return (name_elem.text or '').strip()
        return ''
    raise ValueError(name)


def _file_field_value(name: str, info, iptc_fields: dict):
    if name == 'title':
        return iptc_fields.get('Iptc.Application2.ObjectName', '').strip()
    if name == 'description':
        return iptc_fields.get('Iptc.Application2.Caption', '').strip()
    if name == 'rights':
        return iptc_fields.get('Iptc.Application2.Copyright', '').strip()
    if name == 'agent':
        return [n.strip() for n in iptc_fields.get('Iptc.Application2.Byline', []) if n.strip()]
    if name == 'subject':
        return [k.strip() for k in iptc_fields.get('Iptc.Application2.Keywords', []) if k.strip()]
    if name == 'date':
        return info.date or ''
    if name == 'location':
        if info.gps_lat is None or info.gps_lon is None:
            return ''
        return f'{info.gps_lat:.6f}, {info.gps_lon:.6f}'
    raise ValueError(name)


def write_measurements(parser: VraXmlParser, record_elem, record_specs, info) -> None:
    """The always-unconditional part of applying a media sync:
    width/height/resolution/file_size, replacing whatever measurements
    were already there -- dimensions/size are physical facts about the
    file, not an editorial per-field choice like the other sync fields."""
    measurements_set = _ensure_set(parser, record_elem, record_specs, 'measurementsSet')
    measurements_type = _type_name_of(record_specs, 'measurementsSet')
    _replace_measurement(parser, measurements_set, measurements_type, 'width',
                          str(info.width), {'unit': 'px', **AAT_PIXELS})
    _replace_measurement(parser, measurements_set, measurements_type, 'height',
                          str(info.height), {'unit': 'px', **AAT_PIXELS})
    if info.dpi is not None:
        _replace_measurement(parser, measurements_set, measurements_type, 'resolution',
                              str(int(info.dpi)), {'unit': 'dpi', **AAT_DPI})
    _replace_measurement(parser, measurements_set, measurements_type, 'fileSize',
                          str(info.file_size), {'unit': 'bytes'})


def fill_record_field(parser: VraXmlParser, record_elem, record_specs, name: str, info, iptc_fields: dict) -> None:
    """Writes one field's file-side value into the record -- the
    'record' direction of a media-sync selection. No-op if the file
    side is empty for that field (nothing to fill in with)."""
    if name == 'title':
        title = iptc_fields.get('Iptc.Application2.ObjectName', '').strip()
        if not title:
            return
        title_set = _ensure_set(parser, record_elem, record_specs, 'titleSet')
        title_type = _type_name_of(record_specs, 'titleSet')
        for existing in title_set.findall(f'{{{VRA_NS}}}title'):
            parser.remove_element(existing)
        # 'main' reads naturally but isn't actually one of
        # titleTypeType's enumerated values (see vra_core4_strict.xsd)
        # -- 'descriptive' is the closest fit for a plain imported
        # title with no more specific classification available.
        _add_set_item(parser, title_set, title_type, 'title', title, {'type': 'descriptive'})
    elif name == 'description':
        description = iptc_fields.get('Iptc.Application2.Caption', '').strip()
        if not description:
            return
        description_set = _ensure_set(parser, record_elem, record_specs, 'descriptionSet')
        description_type = _type_name_of(record_specs, 'descriptionSet')
        for existing in description_set.findall(f'{{{VRA_NS}}}description'):
            parser.remove_element(existing)
        _add_set_item(parser, description_set, description_type, 'description', description)
    elif name == 'rights':
        rights = iptc_fields.get('Iptc.Application2.Copyright', '').strip()
        if not rights:
            return
        rights_set = _ensure_set(parser, record_elem, record_specs, 'rightsSet')
        rights_type = _type_name_of(record_specs, 'rightsSet')
        for existing in rights_set.findall(f'{{{VRA_NS}}}rights'):
            parser.remove_element(existing)
        rights_elem = _add_set_item(parser, rights_set, rights_type, 'rights')
        _add_set_item(parser, rights_elem, 'rightsType', 'text', rights)
    elif name == 'agent':
        names = [n.strip() for n in iptc_fields.get('Iptc.Application2.Byline', []) if n.strip()]
        if not names:
            return
        agent_set = _ensure_set(parser, record_elem, record_specs, 'agentSet')
        agent_type = _type_name_of(record_specs, 'agentSet')
        for existing in agent_set.findall(f'{{{VRA_NS}}}agent'):
            parser.remove_element(existing)
        for person_name in names:
            agent_elem = _add_set_item(parser, agent_set, agent_type, 'agent')
            _add_set_item(parser, agent_elem, 'agentType', 'name', person_name)
    elif name == 'subject':
        keywords = [k.strip() for k in iptc_fields.get('Iptc.Application2.Keywords', []) if k.strip()]
        if not keywords:
            return
        subject_set = _ensure_set(parser, record_elem, record_specs, 'subjectSet')
        subject_type = _type_name_of(record_specs, 'subjectSet')
        for existing in subject_set.findall(f'{{{VRA_NS}}}subject'):
            parser.remove_element(existing)
        for keyword in keywords:
            subject_elem = _add_set_item(parser, subject_set, subject_type, 'subject')
            _add_set_item(parser, subject_elem, 'subjectType', 'term', keyword)
    elif name == 'date':
        if info.date is None:
            return
        date_set = _ensure_set(parser, record_elem, record_specs, 'dateSet')
        date_type = _type_name_of(record_specs, 'dateSet')
        for existing in date_set.findall(f'{{{VRA_NS}}}date'):
            if existing.get('type') == 'creation':
                parser.remove_element(existing)
        date_elem = _add_set_item(parser, date_set, date_type, 'date', attrs={'type': 'creation'})
        _add_set_item(parser, date_elem, 'dateType', 'earliestDate', info.date)
        _add_set_item(parser, date_elem, 'dateType', 'latestDate', info.date)
    elif name == 'location':
        if info.gps_lat is None or info.gps_lon is None:
            return
        location_set = _ensure_set(parser, record_elem, record_specs, 'locationSet')
        location_type = _type_name_of(record_specs, 'locationSet')
        for existing in location_set.findall(f'{{{VRA_NS}}}location'):
            if existing.get('type') == 'creation':
                parser.remove_element(existing)
        location_elem = _add_set_item(parser, location_set, location_type, 'location',
                                       attrs={'type': 'creation'})
        # Raw EXIF coordinates aren't a verified gazetteer lookup, so
        # deliberately no vocab= here -- unlike this archive's usual
        # vocab="GNS" convention for actual GNS-confirmed places.
        _add_set_item(parser, location_elem, 'locationType', 'name',
                      f'{info.gps_lat:.6f}, {info.gps_lon:.6f}', {'type': 'geographic'})
    else:
        raise ValueError(name)


def _replace_measurement(parser: VraXmlParser, measurements_set, measurements_type,
                          measurement_type: str, text: str, attrs: dict):
    for existing in measurements_set.findall(f'{{{VRA_NS}}}measurements'):
        if existing.get('type') == measurement_type:
            parser.remove_element(existing)
    _add_set_item(parser, measurements_set, measurements_type, 'measurements',
                  text, {'type': measurement_type, **attrs})


def _type_name_of(specs, tag: str) -> Optional[str]:
    return next((s.type_name for s in specs if s.tag == tag), None)


def _ensure_set(parser: VraXmlParser, record_elem, record_specs, set_tag: str):
    """The existing <set_tag> under record_elem, or a freshly created
    empty one at its schema-correct position."""
    existing = record_elem.find(f'{{{VRA_NS}}}{set_tag}')
    if existing is not None:
        return existing
    sibling_order = [s.tag for s in record_specs]
    return parser.add_child(record_elem, set_tag, sibling_order)


def _add_set_item(parser: VraXmlParser, parent_elem, parent_type_name: Optional[str], tag: str,
                   text: str = '', attrs: Optional[dict] = None):
    """Adds <tag> as a new child of parent_elem at its schema-correct
    position (parent_type_name is parent_elem's own complexType, used
    to look up its schema-declared child order), optionally with text
    and attributes."""
    sibling_order = [s.tag for s in vra_structure.children_of_type(parent_type_name)]
    new_elem = parser.add_child(parent_elem, tag, sibling_order)
    if text:
        new_elem.text = text
    for key, value in (attrs or {}).items():
        new_elem.set(key, value)
    return new_elem


def _first_text(root, tag: str) -> str:
    elem = root.find(f'.//{{{VRA_NS}}}{tag}')
    return (elem.text or '').strip() if elem is not None else ''


def _all_sub_text(root, item_tag: str, sub_tag: str) -> list:
    results = []
    for item in root.iter(f'{{{VRA_NS}}}{item_tag}'):
        sub = item.find(f'{{{VRA_NS}}}{sub_tag}')
        text = (sub.text or '').strip() if sub is not None else ''
        if text:
            results.append(text)
    return results


def _creation_date_text(root) -> str:
    """The record's <date type="creation"><earliestDate> text."""
    for date_elem in root.iter(f'{{{VRA_NS}}}date'):
        if date_elem.get('type') == 'creation':
            earliest = date_elem.find(f'{{{VRA_NS}}}earliestDate')
            return (earliest.text or '').strip() if earliest is not None else ''
    return ''
