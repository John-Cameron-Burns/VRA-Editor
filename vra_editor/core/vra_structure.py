"""Schema-derived element structure for VRA Core 4.

Parses the bundled vra_core4.xsd once and exposes, for any element tag,
whether it's a text leaf (and so can carry vocab/refid/href) or a
container, and -- for containers -- its schema-ordered allowed children
with cardinality. This is what drives the tree's "Add child" menu and
the generic leaf editor, so both stay grounded in the actual schema
instead of a hand-maintained guess at VRA Core's structure.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from lxml import etree

XSD_PATH = Path(__file__).resolve().parent.parent / "resources" / "vra_core4.xsd"
_XSD_NS = "http://www.w3.org/2001/XMLSchema"


def _q(tag: str) -> str:
    return f"{{{_XSD_NS}}}{tag}"


@dataclass(frozen=True)
class ChildSpec:
    tag: str
    is_leaf: bool
    has_vocab: bool  # basicString-derived leaves only (not e.g. dateWrapperType)
    min_occurs: int
    max_occurs: Optional[int]  # None means unbounded
    type_name: Optional[str]  # lets callers recurse via children_of_type() even for
    # locally-declared tags (e.g. "dates", "display") that
    # aren't in the schema's global element table


@dataclass(frozen=True)
class ElementSpec:
    tag: str
    is_leaf: bool
    has_vocab: bool
    children: tuple  # tuple[ChildSpec, ...], empty for leaves


@lru_cache(maxsize=1)
def _schema():
    tree = etree.parse(str(XSD_PATH))
    complex_types = {}
    top_elements = {}
    for child in tree.getroot():
        if child.tag == _q("complexType") and child.get("name"):
            complex_types[child.get("name")] = child
        elif child.tag == _q("element") and child.get("name"):
            top_elements[child.get("name")] = child
    return complex_types, top_elements


def _direct_base(complex_types, type_name):
    ct = complex_types.get(type_name)
    if ct is None:
        return None
    simple_content = ct.find(_q("simpleContent"))
    if simple_content is not None:
        ext = simple_content.find(_q("extension"))
        return ext.get("base") if ext is not None else None
    return None


def _has_vocab_attrs(complex_types, type_name, _seen=None):
    """True if type_name transitively derives (via simpleContent extension) from basicString."""
    if type_name is None:
        return False
    if _seen is None:
        _seen = set()
    if type_name in _seen:
        return False
    _seen.add(type_name)
    if type_name == "basicString":
        return True
    base = _direct_base(complex_types, type_name)
    if base is None:
        return False
    if base == "basicString":
        return True
    return _has_vocab_attrs(complex_types, base, _seen)


def _is_leaf_type(complex_types, type_name):
    if type_name is None or type_name.startswith("xsd:"):
        return True
    ct = complex_types.get(type_name)
    if ct is None:
        return True  # unknown type -- treat as an opaque leaf rather than crash
    return ct.find(_q("simpleContent")) is not None


def _resolve_element_type(top_elements, tag, explicit_type):
    if explicit_type:
        return explicit_type
    gdecl = top_elements.get(tag)
    return gdecl.get("type") if gdecl is not None else None


def _collect_children(complex_types, top_elements, type_name):
    """Direct + inherited (base complexType) children, in schema order."""
    ct = complex_types.get(type_name)
    if ct is None:
        return []

    children = []
    complex_content = ct.find(_q("complexContent"))
    if complex_content is not None:
        ext = complex_content.find(_q("extension"))
        base_name = ext.get("base")
        children.extend(_collect_children(complex_types, top_elements, base_name))
        seq_source = ext
    else:
        seq_source = ct

    for seq in seq_source.findall(_q("sequence")):
        seq_min = seq.get("minOccurs", "1")
        seq_max = seq.get("maxOccurs", "1")
        for el in seq.findall(_q("element")):
            tag = el.get("ref") or el.get("name")
            el_type = _resolve_element_type(top_elements, tag, el.get("type"))
            # An element with no cardinality of its own inherits the
            # enclosing sequence's (e.g. agentSet's <agent> is declared
            # bare, but its <xsd:sequence maxOccurs="unbounded"> is what
            # actually makes multiple <agent>s valid).
            min_o = int(el.get("minOccurs", seq_min))
            max_raw = el.get("maxOccurs", seq_max)
            max_o = None if max_raw == "unbounded" else int(max_raw)
            is_leaf = _is_leaf_type(complex_types, el_type)
            has_vocab = _has_vocab_attrs(complex_types, el_type) if is_leaf else False
            children.append(ChildSpec(
                tag=tag, is_leaf=is_leaf, has_vocab=has_vocab,
                min_occurs=min_o, max_occurs=max_o, type_name=el_type,
            ))
    return children


@lru_cache(maxsize=None)
def children_of_type(type_name: Optional[str]) -> tuple:
    """Public, type_name-keyed entry point into _collect_children -- lets
    callers (the tree builder) recurse into a child's own children even
    when that child is only locally declared (e.g. agent's "dates", or
    "display"/"notes" wherever they appear) and so has no entry in the
    schema's global element table."""
    if type_name is None:
        return ()
    complex_types, top_elements = _schema()
    return tuple(_collect_children(complex_types, top_elements, type_name))


@lru_cache(maxsize=1)
def _element_specs():
    complex_types, top_elements = _schema()
    specs = {}
    for tag, el in top_elements.items():
        type_name = el.get("type")
        is_leaf = _is_leaf_type(complex_types, type_name)
        if is_leaf:
            specs[tag] = ElementSpec(
                tag=tag, is_leaf=True,
                has_vocab=_has_vocab_attrs(complex_types, type_name),
                children=(),
            )
        else:
            children = tuple(_collect_children(complex_types, top_elements, type_name))
            specs[tag] = ElementSpec(tag=tag, is_leaf=False, has_vocab=False, children=children)
    return specs


def element_spec(tag: str) -> Optional[ElementSpec]:
    return _element_specs().get(tag)


def allowed_children(tag: str) -> list:
    spec = element_spec(tag)
    return list(spec.children) if spec else []
