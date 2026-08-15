"""VRA Core 4 -> Simple Dublin Core crosswalk.

Grounded in the VRA Core 4 Element Description (Library of Congress)
and the DC/MODS/VRA element mapping table in Miller, "Metadata for
Digital Collections" (ALA, 2011):
https://alastore.ala.org/sites/default/files/MDC_DC-MODS-VRA_Mapping_Table.pdf

That table itself notes several VRA elements map ambiguously -- e.g.
date can land on DC Date or DC Coverage depending on how it's used,
and Location has no clean DC equivalent except as Contributor for
repository/custodian information. Each such call is documented at the
point it's made below rather than picked silently.
"""

from lxml import etree

from vra_editor.core.xml_parser import VRA_NS, XML_NS

DC_NS = "http://purl.org/dc/elements/1.1/"
OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# Role terms treated as "primarily responsible for creating the work"
# (-> DC Creator) rather than some other kind of contribution (-> DC
# Contributor). VRA's <role> is free text, typically drawn from a
# controlled list like the Getty AAT, not an enumerated schema value --
# so this is a heuristic over common terms, not a lookup table.
_CREATOR_ROLES = {
    'creator', 'artist', 'photographer', 'architect', 'sculptor',
    'painter', 'printmaker', 'engraver', 'author', 'designer', 'maker',
}

# Simple DC's 15 elements, in Dublin Core's own canonical order.
_ELEMENT_ORDER = (
    'title', 'creator', 'subject', 'description', 'publisher',
    'contributor', 'date', 'type', 'format', 'identifier', 'source',
    'language', 'relation', 'coverage', 'rights',
)


def _q(tag: str) -> str:
    return f'{{{VRA_NS}}}{tag}'


def _text(elem) -> str:
    return (elem.text or '').strip() if elem is not None else ''


def _leaf_texts(root, tag: str) -> list:
    """Every non-empty text value of a basicString-derived leaf tag
    (title, worktype, description, material, technique, stylePeriod,
    culturalContext, relation), wherever it appears under root."""
    return [t for t in (_text(e) for e in root.iter(_q(tag))) if t]


def _date_text(date_elem) -> str:
    earliest = _text(date_elem.find(_q('earliestDate')))
    latest = _text(date_elem.find(_q('latestDate')))
    if earliest and latest and earliest != latest:
        return f'{earliest}/{latest}'
    return earliest or latest


def _agents(root) -> tuple:
    """(creator names, contributor names), classified by each agent's
    <role> text against _CREATOR_ROLES. An agent with no role, or a
    role outside that set, becomes a Contributor rather than being
    assumed to be the creator -- the conservative default, since DC
    Creator specifically means "primarily responsible"."""
    creators, contributors = [], []
    for agent in root.iter(_q('agent')):
        name = _text(agent.find(_q('name')))
        if not name:
            continue
        role = _text(agent.find(_q('role'))).lower()
        (creators if role in _CREATOR_ROLES else contributors).append(name)
    return creators, contributors


def _locations(root) -> tuple:
    """(spatial coverage names, contributor names) -- a repository/
    holding institution is treated as a DC Contributor (per the Miller
    mapping table's own Location -> Contributor row); every other
    location type (creation place, discovery place, ...) becomes DC
    spatial Coverage, which is the standard use of that element for
    physical/cultural-heritage material."""
    coverage, contributors = [], []
    for location in root.iter(_q('location')):
        name = _text(location.find(_q('name')))
        if not name:
            continue
        (contributors if location.get('type') == 'repository' else coverage).append(name)
    return coverage, contributors


def _measurements(root) -> list:
    results = []
    for m in root.iter(_q('measurements')):
        text = _text(m)
        if not text:
            continue
        value = f'{text} {m.get("unit", "")}'.strip()
        kind = m.get('type', '')
        results.append(f'{kind}: {value}' if kind else value)
    return results


def _rights(root) -> list:
    results = []
    for r in root.iter(_q('rights')):
        text = _text(r.find(_q('text')))
        holder = _text(r.find(_q('rightsHolder')))
        if text:
            results.append(text)
        if holder:
            results.append(f'Rights holder: {holder}')
    return results


def _subjects(root) -> list:
    return [
        _text(term)
        for subject in root.iter(_q('subject'))
        for term in subject.findall(_q('term'))
        if _text(term)
    ]


def _inscriptions(root) -> list:
    """Folded into DC Description (per the Miller table's Description
    <- inscription row) -- DC has no dedicated inscription element."""
    return [
        f'Inscription: {_text(i.find(_q("text")))}'
        for i in root.iter(_q('inscription'))
        if _text(i.find(_q('text')))
    ]


def _sources(root) -> list:
    return [_text(s.find(_q('name'))) for s in root.iter(_q('source')) if _text(s.find(_q('name')))]


def _textref_identifiers(root) -> list:
    results = []
    for textref in root.iter(_q('textref')):
        refid = _text(textref.find(_q('refid')))
        name = _text(textref.find(_q('name')))
        results.append(refid or name)
    return [r for r in results if r]


def build_dc_fields(record_element) -> dict:
    """Maps one VRA Core 4 work/image/collection record onto Simple
    Dublin Core. record_element is the record's own lxml element (as
    returned by VraXmlParser.build_tree()[i].element), not the whole
    document. Returns {dc_element_name: [values, ...]}, omitting
    elements with nothing to say -- see the module docstring for the
    crosswalk this follows.

    Not carried over, since the Miller table found no clean DC
    equivalent: stateEdition, record type (work/image/collection).
    """
    root = record_element
    fields: dict = {}

    def add(name, values):
        values = [v for v in values if v]
        if values:
            fields.setdefault(name, []).extend(values)

    record_id = (root.get('id') or '').strip()
    add('identifier', [record_id, *_textref_identifiers(root)])

    add('language', [root.get(f'{{{XML_NS}}}lang', '').strip()])

    add('title', _leaf_texts(root, 'title'))
    add('type', _leaf_texts(root, 'worktype'))
    add('description', _leaf_texts(root, 'description') + _inscriptions(root))
    add('format', _leaf_texts(root, 'material') + _leaf_texts(root, 'technique') + _measurements(root))
    add('subject', _subjects(root) + _leaf_texts(root, 'stylePeriod'))
    add('coverage', _leaf_texts(root, 'culturalContext'))
    add('relation', _leaf_texts(root, 'relation'))
    add('rights', _rights(root))
    add('source', _sources(root))
    add('date', [_date_text(d) for d in root.iter(_q('date'))])

    creators, contributors = _agents(root)
    add('creator', creators)
    add('contributor', contributors)

    loc_coverage, loc_contributors = _locations(root)
    add('coverage', loc_coverage)
    add('contributor', loc_contributors)

    return fields


def to_oai_dc_xml(record_element) -> str:
    """Serializes build_dc_fields' output as an oai_dc document -- the
    de facto standard container for Simple Dublin Core records (used
    by DSpace, CONTENTdm, and any OAI-PMH-harvestable repository), so
    the result is importable wherever plain DC is expected."""
    fields = build_dc_fields(record_element)
    root = etree.Element(
        f'{{{OAI_DC_NS}}}dc',
        nsmap={'oai_dc': OAI_DC_NS, 'dc': DC_NS, 'xsi': XSI_NS},
    )
    root.set(
        f'{{{XSI_NS}}}schemaLocation',
        f'{OAI_DC_NS} http://www.openarchives.org/OAI/2.0/oai_dc.xsd',
    )
    for name in _ELEMENT_ORDER:
        for value in fields.get(name, []):
            etree.SubElement(root, f'{{{DC_NS}}}{name}').text = value
    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8').decode('utf-8')
