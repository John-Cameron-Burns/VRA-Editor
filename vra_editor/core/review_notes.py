"""Reviewer-to-editor notes: a todo list attached to the document as an
XML comment, not a schema element.

Deliberately not part of the VRA Core content model: unlike a Set's own
<notes> (real archival content any VRA Core consumer would see), these
are internal review-workflow state -- what a reviewer flags for the
editor to address, not a fact about the artifact. An XML comment is
invisible to schema validation entirely (the bundled strict schema has
no xsd:any wildcard anywhere, so a real element -- in any namespace --
would fail to validate), and lxml preserves comments through this
app's existing load/save round-trip with no changes needed elsewhere.

Lives as the first child of the document's true root (xml_root) --
either the record element itself, or a wrapper around one or more of
them -- so there's exactly one notes list per file, independent of how
many records it contains.
"""

import json

from lxml import etree

_MARKER = "VRA-EDITOR-REVIEW-NOTES"

# XML comments may not contain "--" or end in "-". A note's own text is
# free-form and could easily contain "--", so on write every "--" gets a
# zero-width space spliced into the middle of it, then stripped back out
# on read -- invisible to a human reading the note either way.
_ZWSP = '\u200b'


def _escape(payload: str) -> str:
    return payload.replace('--', f'-{_ZWSP}-')


def _unescape(payload: str) -> str:
    return payload.replace(_ZWSP, '')


def _find_comment(root):
    for child in root:
        if child.tag is etree.Comment and (child.text or '').strip().startswith(_MARKER):
            return child
    return None


def get_review_notes(root) -> list:
    """Returns the list of {text, author, date, resolved} dicts, in the
    order they were added. [] if there's no notes comment yet, or if
    it's present but unparseable (never raises -- a malformed comment
    shouldn't block opening the file)."""
    if root is None:
        return []
    comment = _find_comment(root)
    if comment is None:
        return []
    raw = _unescape(comment.text or '')
    _marker_line, _, payload = raw.partition('\n')
    try:
        notes = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return []
    return notes if isinstance(notes, list) else []


def set_review_notes(root, notes: list) -> None:
    """Writes notes back to the comment: created as root's first child
    if it doesn't exist yet, updated in place if it does, or removed
    entirely once the list is empty -- a fully-resolved/empty todo
    list shouldn't leave a stale marker behind."""
    if root is None:
        return
    comment = _find_comment(root)
    if not notes:
        if comment is not None:
            root.remove(comment)
        return

    payload = _escape(f"{_MARKER}\n{json.dumps(notes, indent=2, ensure_ascii=False)}")
    if comment is not None:
        comment.text = payload
    else:
        root.insert(0, etree.Comment(payload))
