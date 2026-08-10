"""Human-readable names for VRA Core 4 element tags, for the UI layer to
display instead of raw schema vocabulary (agentSet, refid, ...). Purely
a presentation concern -- the underlying XML tags and attributes are
untouched; this only maps what gets shown on screen.

Lives in core/ rather than ui/ because it has no PySide6 dependency and
both the tree builder (core/xml_parser.py) and several UI widgets need
it; putting it in ui/ would make core/ depend on ui/, backwards from
the rest of the app's layering.
"""

# Record types (work/image/collection) and Set-level section headers.
TAG_LABELS = {
    'work': 'Work',
    'image': 'Image',
    'collection': 'Collection',

    'agentSet': 'People',
    'culturalContextSet': 'Cultural Context',
    'dateSet': 'Dates',
    'descriptionSet': 'Description',
    'inscriptionSet': 'Inscriptions',
    'locationSet': 'Locations',
    'materialSet': 'Materials',
    'measurementsSet': 'Measurements',
    'relationSet': 'Related Works',
    'rightsSet': 'Rights',
    'sourceSet': 'Source',
    'stateEditionSet': 'State / Edition',
    'stylePeriodSet': 'Style & Period',
    'subjectSet': 'Subjects',
    'techniqueSet': 'Technique',
    'textrefSet': 'Text References',
    'titleSet': 'Titles',
    'worktypeSet': 'Work Type',

    # Containers (one item within a Set above). Agents in VRA Core are
    # not always the maker -- role names the actual relationship
    # (creator, repository, funder, publisher, former owner...), so
    # this stays neutral rather than assuming "Creator".
    'agent': 'Person / Organisation',
    'date': 'Date',
    'location': 'Location',
    'source': 'Source',
    'rights': 'Rights Statement',
    'textref': 'Text Reference',
    'inscription': 'Inscription',
    'subject': 'Subject Term',
    'stateEdition': 'State / Edition',
    'dates': 'Active Dates',

    # Leaves.
    'name': 'Name',
    'role': 'Role',
    'culture': 'Culture',
    'attribution': 'Attribution',
    'earliestDate': 'From',
    'latestDate': 'To',
    'title': 'Title',
    'worktype': 'Type of Work',
    'technique': 'Technique',
    'culturalContext': 'Cultural Context',
    'description': 'Description',
    'material': 'Material',
    'measurements': 'Measurements',
    'relation': 'Relation',
    'rightsHolder': 'Rights Holder',
    'text': 'Text',
    'author': 'Author',
    'position': 'Position',
    'term': 'Term',
    'stylePeriod': 'Style / Period',
    'refid': 'Identifier',
    'notes': 'Notes',
    'display': 'Display',
}

# Field-level labels in the generic element editor (vocab/refid/href are
# the VRA Core attribute names; these are what a cataloguer sees instead).
FIELD_LABELS = {
    'lang': 'Language',
    'vocab': 'Linked to',
    'refid': 'Record ID',
    'href': 'Link',
    # Not wired into any editor yet, but the rest of the vraAttributes
    # group (see the schema's basicString type) -- present so a future
    # editor covering these is just adding the key, not designing a
    # second labelling scheme.
    'dataDate': 'Date recorded',
    'extent': 'Extent',
    'source': 'Source',
    'rules': 'Cataloguing rules',
    'pref': 'Preferred',
}


def friendly_label(tag: str) -> str:
    """Returns the display name for `tag`, or `tag` itself if there's no
    mapping -- never blank, never a crash, just less friendly."""
    return TAG_LABELS.get(tag, tag)
