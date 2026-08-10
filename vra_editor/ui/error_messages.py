"""Turns raw lxml/XSD validation errors into plain-English sentences.

Built from what the validator actually produces against this app's own
schema and sample data, not guessed patterns: a genuinely missing
required item (e.g. deleting the last Title) reports cleanly against
the element that's actually short a child, but many other structural
breaks surface as a confusing "element not expected" error pointing at
some unrelated, later element in the document -- an artifact of how
the XSD validator reports the first place its content-model matching
gives up, not necessarily the field you touched. So this only ever
claims as much precision as the underlying error actually has; callers
should still offer the raw message as expandable detail for the rare
case someone needs it.
"""

import re

from vra_editor.core.friendly_labels import friendly_label

_NAMESPACE_RE = re.compile(r'\{[^}]*\}')
_MISSING_CHILD_RE = re.compile(
    r"Element '([\w:]+)': Missing child element\(s\)\. Expected is (?:one of )?\(([^)]*)\)"
)
_NOT_EXPECTED_RE = re.compile(r"Element '([\w:]+)': This element is not expected")


def _strip_namespace(text: str) -> str:
    return _NAMESPACE_RE.sub('', text)


def friendly_validation_error(raw_message: str) -> str:
    """Best-effort plain-English translation of a schema validation
    error. Always returns something sayable to a non-technical user;
    falls back to a generic sentence rather than raw parser text for
    anything it doesn't recognise."""
    cleaned = _strip_namespace(raw_message)

    match = _MISSING_CHILD_RE.search(cleaned)
    if match:
        parent = friendly_label(match.group(1))
        options = [friendly_label(name.strip()) for name in match.group(2).split(',') if name.strip()]
        # display/notes are optional extras on nearly every section; if
        # something more substantive is also a valid next item, lead
        # with that instead -- it's almost always the real gap.
        substantive = [o for o in options if o not in ('Display', 'Notes')]
        lead = substantive[0] if substantive else (options[0] if options else 'a required item')
        return f'"{parent}" is missing its {lead}. Add one, or remove "{parent}" if it\'s not needed.'

    match = _NOT_EXPECTED_RE.search(cleaned)
    if match:
        tag = friendly_label(match.group(1))
        return (
            f'Something about the record\'s structure doesn\'t match the VRA Core '
            f'standard near "{tag}". This often follows removing or reordering a '
            f'related field -- try Undo (Ctrl+Z) and check what\'s nearby.'
        )

    return "This record doesn't fully match the VRA Core standard yet."
