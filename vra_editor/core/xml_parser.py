import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from lxml import etree

from vra_editor.core import vra_structure
from vra_editor.core.display_i18n import DisplayTranslations, get_display, set_display
from vra_editor.core.friendly_labels import friendly_label

VRA_NS = "http://www.vraweb.org/vracore4.htm"
NSMAP = {None: VRA_NS}
XML_NS = "http://www.w3.org/XML/1998/namespace"  # the reserved xml: prefix, for xml:lang

# Top-level record types build_tree looks for when walking the document.
_RECORD_TAGS = ('work', 'image', 'collection')


@dataclass
class VraTreeNode:
    """One node in the tree built from a loaded document.

    element is the real lxml element this node represents -- it's what
    gets passed back through DocumentController.set_current_element so
    that later edits know what to write into.
    """
    label: str
    node_type: str  # "record" | "set" | "container" | "leaf" | "display"
    data: dict  # payload shape matches FormContainerPanel.show_editor's expectations
    element: Any  # the lxml element itself, or None for purely structural nodes
    child_specs: tuple = ()  # vra_structure.ChildSpec entries valid to insert under this node
    children: list = field(default_factory=list)


class VraXmlParser:
    """Pure Python XML generator and parser."""

    def __init__(self, xml: Union[Path, str, bytes] = None):
        self.file_name = 'none'
        self.xml_root = None
        self.xml_etree = None

    def load(self, filename):
        try:
            self.xml_root = etree.parse(filename).getroot()
            self.xml_etree = etree.ElementTree(self.xml_root)
            self.file_name = filename
            return etree.tostring(self.xml_root, pretty_print=True).decode('utf-8')
        except Exception as e:
            print(e)

    # ------------------------------------------------------------------
    # Tree building -- generic, schema-driven walk of whatever's actually
    # in the document, used to populate VraTreePanel dynamically. Every
    # leaf/container tag in VRA Core 4 is handled uniformly via
    # vra_structure, rather than one-off cases per tag.
    # ------------------------------------------------------------------

    def build_tree(self) -> list:
        """Returns one top-level VraTreeNode per work/image/collection
        record found in the loaded document. Empty list if nothing's
        loaded yet."""
        if self.xml_root is None:
            return []

        if self._localname(self.xml_root) in _RECORD_TAGS:
            records = [self.xml_root]
        else:
            records = [
                child for child in self.xml_root
                if isinstance(child.tag, str) and self._localname(child) in _RECORD_TAGS
            ]

        return [self._build_record_node(record) for record in records]

    def _build_record_node(self, record_elem) -> VraTreeNode:
        record_type = self._localname(record_elem)
        record_id = record_elem.get('id', '')
        child_specs = vra_structure.allowed_children(record_type)
        node = VraTreeNode(
            label=f"{friendly_label(record_type)} (id: {record_id})",
            node_type='record',
            data={'tag': record_type},
            element=record_elem,
            child_specs=tuple(child_specs),
        )
        self._append_children(node, record_elem, child_specs)
        return node

    def _build_node(self, elem, is_leaf: bool, has_vocab: bool, type_name: Optional[str]) -> VraTreeNode:
        tag = self._localname(elem)

        if is_leaf:
            return self._build_leaf_node(elem, tag, has_vocab)

        child_specs = vra_structure.children_of_type(type_name)
        node = VraTreeNode(
            label=friendly_label(tag),
            node_type='set' if tag.endswith('Set') else 'container',
            data={'tag': tag},
            element=elem,
            child_specs=tuple(child_specs),
        )

        # Keyed on the <display> element's existence, not on whether it
        # currently has any parseable content -- a freshly-added, still-
        # empty <display/> (the moment after clicking "+ Add translations")
        # has no translations yet either, but must still show up as an
        # editable Display entry rather than silently vanishing until
        # the user has typed something.
        if elem.find(f'{{{VRA_NS}}}display') is not None:
            translations = self.get_display_translations(elem)
            preview = next(iter(translations.values()), '') if translations else ''
            node.children.append(VraTreeNode(
                label=f"Display: {preview}" if preview else "Display",
                node_type='display',
                data={'translations': translations},
                element=elem,  # display methods take the containing element, not <display> itself
            ))

        self._append_children(node, elem, child_specs)
        return node

    def _append_children(self, node: VraTreeNode, elem, child_specs):
        specs_by_tag = {spec.tag: spec for spec in child_specs}
        for child_elem in elem:
            if not isinstance(child_elem.tag, str):
                continue  # skip comments/processing instructions (real VRA exports contain both)
            child_tag = self._localname(child_elem)
            if child_tag == 'display':
                continue  # already surfaced above as a translation-preview node
            spec = specs_by_tag.get(child_tag)
            if spec is None:
                continue  # not part of this element's schema-declared children -- nothing to show/edit
            node.children.append(self._build_node(child_elem, spec.is_leaf, spec.has_vocab, spec.type_name))

    def _build_leaf_node(self, elem, tag: str, has_vocab: bool) -> VraTreeNode:
        text = (elem.text or '').strip()
        label = friendly_label(tag)
        return VraTreeNode(
            label=f"{label}: {text}" if text else label,
            node_type='leaf',
            data={
                'tag': tag,
                'text': text,
                'has_vocab': has_vocab,
                'vocab': elem.get('vocab', ''),
                'refid': elem.get('refid', ''),
                'href': elem.get('href', ''),
                'lang': elem.get(f'{{{XML_NS}}}lang', ''),
            },
            element=elem,
        )

    @staticmethod
    def _localname(element) -> str:
        return etree.QName(element).localname

    def find_element_span(self, element, xml_text: str) -> Optional[tuple]:
        """Returns (start, end) character offsets within xml_text
        spanning element's complete serialized block (its opening tag's
        line through its closing tag's line), or None if it can't be
        located.

        Doesn't try to reproduce lxml's serialization of `element` in
        isolation and search for that -- namespace prefixes and
        attribute declarations come out differently for a standalone
        element than for the same element serialized in place inside
        the full document, so that match would frequently fail.
        Instead: lxml's pretty-printer always starts an element's
        opening tag at the beginning of its own line, in document
        order, so counting which occurrence of this tag `element` is
        among same-tagged elements and finding that same occurrence's
        opening-tag line in xml_text locates it exactly, regardless of
        prefix/attribute-order/escaping details.
        """
        root = element.getroottree().getroot()
        localname = self._localname(element)
        same_tag_elements = list(root.iter(element.tag))
        try:
            target_index = same_tag_elements.index(element)
        except ValueError:
            return None

        tag_pattern = r'(?:\w+:)?' + re.escape(localname)
        open_re = re.compile(r'^\s*<' + tag_pattern + r'(?=[\s/>])')
        open_count_re = re.compile(r'<' + tag_pattern + r'(?=[\s/>])')
        close_re = re.compile(r'</' + tag_pattern + r'>')
        selfclose_re = re.compile(r'<' + tag_pattern + r'\b[^>]*/>')

        lines = xml_text.split('\n')
        line_offsets = []
        offset = 0
        for line in lines:
            line_offsets.append(offset)
            offset += len(line) + 1  # +1 for the '\n' consumed by split()

        occurrence = -1
        open_line_idx = None
        for i, line in enumerate(lines):
            if open_re.match(line):
                occurrence += 1
                if occurrence == target_index:
                    open_line_idx = i
                    break
        if open_line_idx is None:
            return None

        depth = 0
        end_line_idx = None
        for i in range(open_line_idx, len(lines)):
            line = lines[i]
            opens = len(open_count_re.findall(line))
            selfcloses = len(selfclose_re.findall(line))
            closes = len(close_re.findall(line))
            depth += (opens - selfcloses) - closes
            if depth == 0:
                end_line_idx = i
                break
        if end_line_idx is None:
            return None

        open_line = lines[open_line_idx]
        start = line_offsets[open_line_idx] + (len(open_line) - len(open_line.lstrip()))
        close_line = lines[end_line_idx]
        end = line_offsets[end_line_idx] + len(close_line.rstrip())
        return start, end

    # ------------------------------------------------------------------
    # Tree mutation -- insert/remove elements anywhere in the document.
    # ------------------------------------------------------------------

    def add_child(self, parent_elem, tag: str, sibling_order: list):
        """Creates a new empty <tag> child under parent_elem, inserted at
        the position schema order requires (not just appended), so the
        result doesn't fail XSD validation on element ordering alone.
        sibling_order is the parent's own schema-valid child tags in
        sequence order -- the tree already knows this (VraTreeNode.child_specs
        from the walk that built it), so it's passed in rather than
        re-derived here, which would break for locally-declared parents
        (e.g. agent's "dates") that have no entry in the schema's global
        element table."""
        new_elem = etree.Element(f'{{{VRA_NS}}}{tag}')
        if tag in sibling_order:
            insert_pos = sibling_order.index(tag)
            for existing in parent_elem:
                if not isinstance(existing.tag, str):
                    continue
                existing_tag = self._localname(existing)
                if existing_tag in sibling_order and sibling_order.index(existing_tag) > insert_pos:
                    existing.addprevious(new_elem)
                    return new_elem
        parent_elem.append(new_elem)
        return new_elem

    def remove_element(self, elem):
        parent = elem.getparent()
        if parent is not None:
            parent.remove(elem)

    # ------------------------------------------------------------------
    # Display translations (see display_i18n.py for the encoding scheme)
    # ------------------------------------------------------------------

    def get_display_translations(self, element) -> DisplayTranslations:
        """element is any lxml element that may have a <display> child
        (e.g. an agentSet/dateSet/materialSet node). Returns {} if
        there's no display child or no element at all.

        IMPORTANT: because the document uses a default namespace
        (xmlns="http://www.vraweb.org/vracore4.htm"), a plain
        element.find('display') silently returns None -- it has to be
        namespace-qualified, hence the {VRA_NS}display lookup below.

        Falls back to {'': text} when <display> exists but its content
        isn't in this app's own div-per-language format -- real VRA
        exports often have a plain-text <display>, predating (or simply
        not using) that convention. Surfacing it with a blank language
        key, rather than returning {} and hiding it entirely, is what
        lets the UI show it as "specify the language" instead of
        silently losing access to existing content.
        """
        if element is None:
            return {}
        display_elem = element.find(f'{{{VRA_NS}}}display')
        if display_elem is None:
            return {}
        translations = get_display(display_elem)
        if translations:
            return translations
        plain_text = (display_elem.text or '').strip()
        return {'': plain_text} if plain_text else {}

    def set_display_translations(self, element, translations: DisplayTranslations):
        """Writes translations onto element's <display> child, creating
        it as the first child (matching the standard's own examples) if
        it doesn't exist yet."""
        display_elem = element.find(f'{{{VRA_NS}}}display')
        if display_elem is None:
            display_elem = etree.SubElement(element, f'{{{VRA_NS}}}display')
            element.remove(display_elem)
            element.insert(0, display_elem)
        set_display(display_elem, translations)

    # ------------------------------------------------------------------
    # Generic leaf write-back (any basicString-derived element: title,
    # name, role, technique, subject/term, and ~20 others)
    # ------------------------------------------------------------------

    def set_element_data(self, elem, text: str, vocab: str = '', refid: str = '', href: str = '',
                          lang: str = ''):
        """elem is the leaf element itself. Clears an attribute entirely
        rather than writing it empty, so untouched fields don't start
        appearing as vocab="" in the saved file. lang is xml:lang --
        namespace-qualified, unlike the other three, since it's the
        reserved XML attribute rather than a VRA Core one."""
        elem.text = text
        for attr_name, value in (('vocab', vocab), ('refid', refid), ('href', href)):
            value = (value or '').strip()
            if value:
                elem.set(attr_name, value)
            elif attr_name in elem.attrib:
                del elem.attrib[attr_name]
        lang = (lang or '').strip()
        lang_attr = f'{{{XML_NS}}}lang'
        if lang:
            elem.set(lang_attr, lang)
        elif lang_attr in elem.attrib:
            del elem.attrib[lang_attr]
