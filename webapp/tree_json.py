"""JSON serialization of VraTreeNode (see vra_editor.core.xml_parser)
for the web API -- the same generic, schema-driven tree the desktop's
Simple and Advanced views both render, reused here instead of a
hand-built record-specific JSON shape, so this stays correct as
vra_structure.py's schema-derived rules evolve.

VraTreeNode.element (a raw lxml Element) has no stable identity across
requests -- a fresh document is loaded and re-walked on every request
-- so nodes are addressed by position from the record root: path is a
list of child indices, e.g. [2, 0, 1] means
record.children[2].children[0].children[1]. Never persisted or
compared across requests, only resolved against the tree just built
for the current one.
"""

from vra_editor.core.friendly_labels import friendly_label
from vra_editor.core.vra_structure import ChildSpec
from vra_editor.core.xml_parser import VraTreeNode


def _child_spec_to_json(spec: ChildSpec) -> dict:
    return {
        'tag': spec.tag,
        'label': friendly_label(spec.tag),
        'is_leaf': spec.is_leaf,
        'has_vocab': spec.has_vocab,
        'min_occurs': spec.min_occurs,
        'max_occurs': spec.max_occurs,
        'type_choices': list(spec.type_choices),
    }


def node_to_json(node: VraTreeNode, path: tuple = ()) -> dict:
    return {
        'path': list(path),
        'label': node.label,
        'node_type': node.node_type,
        'data': node.data,
        'child_specs': [_child_spec_to_json(s) for s in node.child_specs],
        'children': [node_to_json(c, path + (i,)) for i, c in enumerate(node.children)],
    }


def resolve_path(record_node: VraTreeNode, path: list) -> VraTreeNode:
    """Inverse of node_to_json's path addressing: walks
    record_node.children[path[0]].children[path[1]]... to recover the
    VraTreeNode (and hence .element) a field-edit or insert-child
    payload targets, against a document freshly loaded for this
    request. Raises IndexError for a path that doesn't resolve (e.g.
    stale client state from before another edit changed the tree
    shape) -- callers should turn that into a 409/400, not a 500."""
    node = record_node
    for i in path:
        node = node.children[i]
    return node
