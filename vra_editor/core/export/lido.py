"""VRA Core 4 -> LIDO (Lightweight Information Describing Objects) v1.1
crosswalk.

LIDO is event-centric rather than flat: instead of a single dateSet/
agentSet/locationSet living side by side (as in VRA Core), LIDO groups
"who did what, where, when" into one or more <lido:event> entries. This
module maps VRA's creation-related fields (agent, creation date,
creation location, culturalContext) onto a single synthesized
"creation" event, which covers the overwhelmingly common case (a work
with one production event) without attempting to infer multiple
events from data VRA Core doesn't structure that way.

Element names, nesting and cardinality below are taken directly from
the LIDO v1.1 XSD (https://github.com/nfdi4objects/lido-schema,
lido-v1.1.xsd), not from LIDO's own (denser) prose documentation --
each helper's docstring or comment names the complexType it fills in
for.
"""

from lxml import etree

from vra_editor.core.xml_parser import VRA_NS, XML_NS

LIDO_NS = "http://www.lido-schema.org"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
LIDO_SCHEMA_LOCATION = "http://www.lido-schema.org http://www.lido-schema.org/schema/v1.1/lido-v1.1.xsd"


def _vq(tag: str) -> str:
    return f'{{{VRA_NS}}}{tag}'


def _lq(tag: str) -> str:
    return f'{{{LIDO_NS}}}{tag}'


def _text(elem) -> str:
    return (elem.text or '').strip() if elem is not None else ''


def _sub(parent, tag: str):
    return etree.SubElement(parent, _lq(tag))


def _text_child(parent, tag: str, text: str, lang: str = ''):
    """Appends <lido:tag xml:lang="lang">text</lido:tag> to parent (the
    textComplexType pattern used throughout LIDO for display/free-text
    elements) -- only if text is non-empty. Returns the new element, or
    None."""
    text = (text or '').strip()
    if not text:
        return None
    el = _sub(parent, tag)
    el.text = text
    if lang:
        el.set(f'{{{XML_NS}}}lang', lang)
    return el


def _appellation_value(parent, text: str, lang: str = ''):
    """Appends <lido:appellationValue> -- the one required child of
    appellationComplexType (titleSet, nameActorSet, namePlaceSet,
    legalBodyName all extend/use it for their actual name text)."""
    return _text_child(parent, 'appellationValue', text, lang)


def _concept(parent, tag: str, text: str, lang: str = ''):
    """Appends <lido:tag><lido:term xml:lang="lang">text</lido:term>
    </lido:tag> -- conceptComplexType's plain-term form (no conceptID/
    authority reference), used for every controlled-vocabulary element
    below (eventType, roleActor, objectWorkType, subjectConcept, ...).
    Only if text is non-empty."""
    text = (text or '').strip()
    if not text:
        return None
    el = _sub(parent, tag)
    term = _sub(el, 'term')
    term.text = text
    if lang:
        term.set(f'{{{XML_NS}}}lang', lang)
    return el


def _leaf_texts(root, tag: str) -> list:
    return [t for t in (_text(e) for e in root.iter(_vq(tag))) if t]


def _repository_name(root) -> str:
    for location in root.iter(_vq('location')):
        if location.get('type') == 'repository':
            name = _text(location.find(_vq('name')))
            if name:
                return name
    return ''


def _creation_location_name(root) -> str:
    for location in root.iter(_vq('location')):
        if location.get('type') == 'creation':
            name = _text(location.find(_vq('name')))
            if name:
                return name
    return ''


def _creation_date(root):
    """The first <date type="creation"> element, or None."""
    for date_elem in root.iter(_vq('date')):
        if date_elem.get('type') == 'creation':
            return date_elem
    return None


# ------------------------------------------------------------------
# objectIdentificationWrap (objectIdentificationWrapComplexType):
# titleWrap, repositoryWrap, objectDescriptionWrap,
# objectMeasurementsWrap, objectMaterialsTechWrap, in that schema order.
# ------------------------------------------------------------------

def _build_title_wrap(parent, root, lang: str):
    """titleWrap is the one mandatory child of objectIdentificationWrap
    (objectIdentificationWrapComplexType's own sequence has no
    minOccurs="0" on it), so this always emits one -- falling back to
    the record id if VRA Core has no title at all, the same way
    _build_classification_wrap and _build_record_wrap fall back for
    their own required fields."""
    titles = _leaf_texts(root, 'title') or [root.get('id', '').strip() or 'Untitled']
    title_wrap = _sub(parent, 'titleWrap')
    for title in titles:
        title_set = _sub(title_wrap, 'titleSet')
        _appellation_value(title_set, title, lang)


def _build_repository_wrap(parent, root, lang: str):
    repository = _repository_name(root)
    if not repository:
        return
    repository_wrap = _sub(parent, 'repositoryWrap')
    repository_set = _sub(repository_wrap, 'repositorySet')
    repository_name_el = _sub(repository_set, 'repositoryName')
    legal_body_name = _sub(repository_name_el, 'legalBodyName')
    _appellation_value(legal_body_name, repository, lang)


def _build_description_wrap(parent, root, lang: str):
    descriptions = _leaf_texts(root, 'description')
    if not descriptions:
        return
    description_wrap = _sub(parent, 'objectDescriptionWrap')
    for description in descriptions:
        description_set = _sub(description_wrap, 'objectDescriptionSet')
        _text_child(description_set, 'descriptiveNoteValue', description, lang)


def _build_measurements_wrap(parent, root, lang: str):
    entries = []
    for m in root.iter(_vq('measurements')):
        value = _text(m)
        if not value:
            continue
        entries.append((m.get('type', ''), m.get('unit', ''), value))
    if not entries:
        return

    measurements_wrap = _sub(parent, 'objectMeasurementsWrap')
    measurements_set = _sub(measurements_wrap, 'objectMeasurementsSet')
    display = '; '.join(f'{kind}: {value} {unit}'.strip() for kind, unit, value in entries)
    _text_child(measurements_set, 'displayObjectMeasurements', display, lang)
    object_measurements = _sub(measurements_set, 'objectMeasurements')
    for kind, unit, value in entries:
        one = _sub(object_measurements, 'measurementsSet')
        _text_child(one, 'measurementType', kind or 'dimension', lang)
        if unit:
            _text_child(one, 'measurementUnit', unit, lang)
        _text_child(one, 'measurementValue', value)


def _build_materials_tech_wrap(parent, root, lang: str):
    terms = _leaf_texts(root, 'material') + _leaf_texts(root, 'technique')
    if not terms:
        return
    wrap = _sub(parent, 'objectMaterialsTechWrap')
    tech_set = _sub(wrap, 'objectMaterialsTechSet')
    for term in terms:
        materials_tech = _sub(tech_set, 'materialsTech')
        _concept(materials_tech, 'termMaterialsTech', term, lang)


def _build_object_identification_wrap(parent, root, lang: str):
    wrap = _sub(parent, 'objectIdentificationWrap')
    _build_title_wrap(wrap, root, lang)
    _build_repository_wrap(wrap, root, lang)
    _build_description_wrap(wrap, root, lang)
    _build_measurements_wrap(wrap, root, lang)
    _build_materials_tech_wrap(wrap, root, lang)
    return wrap


# ------------------------------------------------------------------
# objectClassificationWrap: objectWorkTypeWrap (required if the wrap
# is present -- one objectWorkType per VRA worktype).
# ------------------------------------------------------------------

def _build_classification_wrap(parent, root, lang: str):
    worktypes = _leaf_texts(root, 'worktype')
    wrap = _sub(parent, 'objectClassificationWrap')
    work_type_wrap = _sub(wrap, 'objectWorkTypeWrap')
    for worktype in worktypes or ['unspecified']:
        _concept(work_type_wrap, 'objectWorkType', worktype, lang)
    return wrap


# ------------------------------------------------------------------
# eventWrap -- one synthesized "creation" event gathering agent,
# creation date, creation location and cultural context, since VRA
# Core doesn't structure these as separate named events the way LIDO
# does. See module docstring.
# ------------------------------------------------------------------

def _build_event_wrap(parent, root, lang: str):
    agents = [(_text(a.find(_vq('name'))), _text(a.find(_vq('role'))))
              for a in root.iter(_vq('agent'))]
    agents = [(name, role) for name, role in agents if name]
    date_elem = _creation_date(root)
    place_name = _creation_location_name(root)
    cultures = _leaf_texts(root, 'culturalContext')

    if not (agents or date_elem is not None or place_name or cultures):
        return

    event_wrap = _sub(parent, 'eventWrap')
    event_set = _sub(event_wrap, 'eventSet')
    event = _sub(event_set, 'event')
    _concept(event, 'eventType', 'creation', lang)

    for name, role in agents:
        event_actor = _sub(event, 'eventActor')
        actor_in_role = _sub(event_actor, 'actorInRole')
        actor = _sub(actor_in_role, 'actor')
        name_actor_set = _sub(actor, 'nameActorSet')
        _appellation_value(name_actor_set, name, lang)
        if role:
            _concept(actor_in_role, 'roleActor', role, lang)

    for culture in cultures:
        _concept(event, 'culture', culture, lang)

    if date_elem is not None:
        earliest = _text(date_elem.find(_vq('earliestDate')))
        latest = _text(date_elem.find(_vq('latestDate')))
        if earliest or latest:
            event_date = _sub(event, 'eventDate')
            display = f'{earliest}/{latest}' if earliest and latest and earliest != latest else (earliest or latest)
            _text_child(event_date, 'displayDate', display, lang)
            date_el = _sub(event_date, 'date')
            if earliest:
                _text_child(date_el, 'earliestDate', earliest)
            if latest:
                _text_child(date_el, 'latestDate', latest)

    if place_name:
        event_place = _sub(event, 'eventPlace')
        place = _sub(event_place, 'place')
        name_place_set = _sub(place, 'namePlaceSet')
        _appellation_value(name_place_set, place_name, lang)


# ------------------------------------------------------------------
# objectRelationWrap: subjectWrap (subject terms + stylePeriod) and
# relatedWorksWrap (VRA relation).
# ------------------------------------------------------------------

def _build_subject_wrap(parent, root, lang: str):
    terms = [_text(t) for s in root.iter(_vq('subject')) for t in s.findall(_vq('term')) if _text(t)]
    terms += _leaf_texts(root, 'stylePeriod')
    if not terms:
        return
    wrap = _sub(parent, 'subjectWrap')
    subject_set = _sub(wrap, 'subjectSet')
    subject = _sub(subject_set, 'subject')
    for term in terms:
        _concept(subject, 'subjectConcept', term, lang)


def _build_related_works_wrap(parent, root, lang: str):
    relations = []
    for r in root.iter(_vq('relation')):
        text = _text(r)
        if text:
            relations.append((text, r.get('type', '')))
    if not relations:
        return
    wrap = _sub(parent, 'relatedWorksWrap')
    for text, rel_type in relations:
        related_set = _sub(wrap, 'relatedWorkSet')
        _text_child(related_set, 'displayRelatedWork', text, lang)
        if rel_type:
            _concept(related_set, 'relatedWorkRelType', rel_type, lang)


def _build_object_relation_wrap(parent, root, lang: str):
    has_subject = any(True for s in root.iter(_vq('subject')) for t in s.findall(_vq('term')) if _text(t))
    has_subject = has_subject or bool(_leaf_texts(root, 'stylePeriod'))
    has_relation = any(_text(r) for r in root.iter(_vq('relation')))
    if not (has_subject or has_relation):
        return
    wrap = _sub(parent, 'objectRelationWrap')
    _build_subject_wrap(wrap, root, lang)
    _build_related_works_wrap(wrap, root, lang)


# ------------------------------------------------------------------
# administrativeMetadata: rightsWorkWrap + the mandatory recordWrap.
# ------------------------------------------------------------------

def _build_rights_work_wrap(parent, root, lang: str):
    entries = []
    for r in root.iter(_vq('rights')):
        text = _text(r.find(_vq('text')))
        holder = _text(r.find(_vq('rightsHolder')))
        if text or holder:
            entries.append((text, holder))
    if not entries:
        return
    wrap = _sub(parent, 'rightsWorkWrap')
    for text, holder in entries:
        rights_set = _sub(wrap, 'rightsWorkSet')
        if holder:
            rights_holder = _sub(rights_set, 'rightsHolder')
            legal_body_name = _sub(rights_holder, 'legalBodyName')
            _appellation_value(legal_body_name, holder, lang)
        if text:
            _text_child(rights_set, 'creditLine', text, lang)


def _build_record_wrap(parent, record_id: str, root, lang: str):
    """recordWrap is mandatory in administrativeMetadataComplexType, and
    within it recordID/recordType/recordSource are all required (each
    at least 1) -- so this always emits something, falling back to
    generic values where VRA Core has no equivalent field."""
    wrap = _sub(parent, 'recordWrap')
    record_id_el = _sub(wrap, 'recordID')
    record_id_el.text = record_id or 'unknown'
    record_id_el.set(_lq('type'), 'local')

    _concept(wrap, 'recordType', 'item', lang)

    record_source = _sub(wrap, 'recordSource')
    legal_body_name = _sub(record_source, 'legalBodyName')
    _appellation_value(legal_body_name, _repository_name(root) or 'Not specified', lang)


def to_lido_xml(record_element) -> str:
    """Serializes one VRA Core 4 work/image/collection record as a
    LIDO v1.1 document rooted at <lido:lido>. record_element is the
    record's own lxml element (as returned by
    VraXmlParser.build_tree()[i].element), not the whole document."""
    root = record_element
    # xml:lang is required on descriptiveMetadata/administrativeMetadata
    # (descriptiveMetadataComplexType declares it use="required") -- VRA
    # Core's own records always carry one (VraXmlParser.new_document
    # sets it, defaulting to 'en'), but fall back rather than emit
    # invalid LIDO for the rare record that somehow lacks it.
    lang = root.get(f'{{{XML_NS}}}lang', '').strip() or 'en'
    record_id = (root.get('id') or '').strip()

    lido = etree.Element(_lq('lido'), nsmap={'lido': LIDO_NS, 'xsi': XSI_NS})
    lido.set(f'{{{XSI_NS}}}schemaLocation', LIDO_SCHEMA_LOCATION)

    lido_rec_id = _sub(lido, 'lidoRecID')
    lido_rec_id.text = record_id or 'unknown'
    lido_rec_id.set(_lq('type'), 'local')

    descriptive = _sub(lido, 'descriptiveMetadata')
    descriptive.set(f'{{{XML_NS}}}lang', lang)
    _build_classification_wrap(descriptive, root, lang)
    _build_object_identification_wrap(descriptive, root, lang)
    _build_event_wrap(descriptive, root, lang)
    _build_object_relation_wrap(descriptive, root, lang)

    administrative = _sub(lido, 'administrativeMetadata')
    administrative.set(f'{{{XML_NS}}}lang', lang)
    _build_rights_work_wrap(administrative, root, lang)
    _build_record_wrap(administrative, record_id, root, lang)

    return etree.tostring(lido, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
