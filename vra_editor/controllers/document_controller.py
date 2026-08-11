import datetime
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from lxml import etree

from vra_editor.config import load_locations
from vra_editor.core import media_metadata, review_notes, vra_structure
from vra_editor.core.schema_validator import SchemaValidator
from vra_editor.core.xml_parser import VRA_NS, VraXmlParser
from vra_editor.utils import user_name

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
# vra_core4.xsd is explicitly the *unrestricted* variant ("all attributes are
# uncontrolled", per its own header) -- every sample record's own
# xsi:schemaLocation declares conformance to the *strict* schema instead,
# which redefines vra_core4_strict.xsd's controlled-vocabulary attributes
# (title type, relation type, ...) as real enumerations. Validating against
# the unrestricted one let invalid attribute values silently pass.
DEFAULT_XSD_PATH = RESOURCES_DIR / "vra_core4_strict.xsd"


class DocumentController(QObject):
    """Owns document state and announces changes to it via signals.

    Signals are declared once, at class level, as Signal(...) instances.
    PySide6 turns each one into a bound signal per-instance at runtime,
    which is what gives you .connect() / .emit() on self.file_loaded etc.
    Nothing further needs to be written to make .connect() work -- it's
    provided by QObject once the class above it in the MRO is QObject
    (or a subclass of QObject) and the attribute is a Signal.
    """

    file_loaded = Signal(str)  # emits the file path
    archive_changed = Signal(str)  # emits the archive name
    xml_updated = Signal(str)  # emits the new XML text
    document_loaded = Signal(object)  # emits the VraXmlParser, once a file has been parsed

    def __init__(self):
        super().__init__()  # QObject.__init__ must run for signals to work
        self.xml_doc = VraXmlParser()
        self._current_file: Optional[str] = None
        self._current_archive: Optional[str] = None
        self._current_element = None  # the lxml element currently selected in the tree
        self._xml_text: str = ""
        self._validator = SchemaValidator(str(DEFAULT_XSD_PATH))
        self._undo_stack: list = []  # serialized (bytes) snapshots, most recent last
        self._undo_snapshot_element = None  # element the top-of-stack snapshot precedes editing
        self._dirty = False
        # Every content-changing method funnels through xml_updated, so
        # this one connection is enough to catch all of them -- load_file/
        # create_new_record/clear/save_file/_move_to_location each reset
        # the flag back to False afterward (they emit xml_updated too, as
        # part of refreshing the preview, but that's not a real edit).
        self.xml_updated.connect(self._mark_dirty)

    def _mark_dirty(self, _xml_text: str = ""):
        self._dirty = True

    @property
    def is_dirty(self) -> bool:
        """True if there are changes since the record was last loaded,
        created, or saved -- used to gate navigation (Home/Open/Create/
        Review) so it can warn before silently discarding work."""
        return self._dirty

    # ------------------------------------------------------------------
    # Actions that change state -- each emits the matching signal once
    # the change is actually made, not before.
    # ------------------------------------------------------------------

    def load_file(self, path: str):
        xml_string = self.xml_doc.load(path)
        self._current_file = path
        self._current_element = None  # nothing selected yet in the freshly-loaded doc
        self._xml_text = xml_string or ""
        self._undo_stack.clear()  # a new document starts with a clean undo history
        self._undo_snapshot_element = None
        self.file_loaded.emit(path)
        self.document_loaded.emit(self.xml_doc)  # tree panel rebuilds itself from this
        self.xml_updated.emit(self._xml_text)
        self._dirty = False  # a freshly-loaded document has nothing unsaved yet

    def create_new_record(self, record_type: str, record_id: str, dest_path):
        """Starts a brand-new, empty record of the given type. Not
        written to disk yet -- that happens on the first Save/Submit,
        same as any other edit -- dest_path is just where it will land."""
        xml_string = self.xml_doc.new_document(record_type, record_id)
        self._current_file = str(dest_path)
        self._current_element = None
        self._xml_text = xml_string or ""
        self._undo_stack.clear()
        self._undo_snapshot_element = None
        self.file_loaded.emit(self._current_file)
        self.document_loaded.emit(self.xml_doc)
        self.xml_updated.emit(self._xml_text)
        self._dirty = False

    def clear(self):
        """Returns to the pristine no-document state -- used by Home/
        Cancel to actually leave the current record, rather than just
        hiding the buttons that act on it while it stays loaded and
        visible underneath (see is_dirty for the guard that should
        run before this, if there's anything worth keeping)."""
        self.xml_doc = VraXmlParser()
        self._current_file = None
        self._current_element = None
        self._xml_text = ""
        self._undo_stack.clear()
        self._undo_snapshot_element = None
        self.document_loaded.emit(self.xml_doc)
        self.file_loaded.emit("")
        self.xml_updated.emit(self._xml_text)
        self._dirty = False

    @property
    def current_record_type(self) -> Optional[str]:
        """The open record's own tag ('collection'/'work'/'image'), or
        None if nothing's loaded -- used to gate record-type-specific
        UI, e.g. the media preview band only ever applies to images."""
        if self.xml_doc.xml_root is None:
            return None
        records = self.xml_doc.build_tree()
        return records[0].data.get('tag') if records else None

    def set_archive(self, archive_name: str):
        self._current_archive = archive_name
        self.archive_changed.emit(archive_name)

    def set_current_element(self, element):
        """Called when the tree selection changes -- tracks which real
        lxml element subsequent edits should write into. Not a signal:
        nothing else needs to react to this, it's just state the
        update_* methods below read from."""
        self._current_element = element

    def update_element_data(self, text: str, vocab: str, refid: str, href: str, lang: str = '',
                             type_value: str = ''):
        """Generic write-back for any leaf element (title, name, role,
        technique, subject/term, ...) -- covers every basicString-derived
        tag uniformly rather than one method per tag."""
        if self._current_element is not None:
            self._snapshot_before_edit(self._current_element)
            self.xml_doc.set_element_data(self._current_element, text, vocab, refid, href, lang, type_value)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    def update_element_type(self, element, type_value: str):
        """Sets a container element's own "type" attribute (date,
        location, rights, stateEdition, agent's "dates") -- these don't
        go through update_element_data since they're containers, not
        leaves with text of their own to write alongside it."""
        if element is None:
            return
        self._snapshot_before_edit(element)
        self.xml_doc.set_element_type(element, type_value)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    def insert_child(self, parent_element, tag: str, sibling_order: list):
        """Adds a new empty <tag> under parent_element and rebuilds the
        tree/preview around it. sibling_order is the parent's schema-valid
        child tags in sequence order (from the tree node's child_specs).
        Returns the new lxml element so the caller (main_window) can
        re-select it in the tree."""
        self._snapshot_before_structural_change()
        new_elem = self.xml_doc.add_child(parent_element, tag, sibling_order)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)
        return new_elem

    def remove_element(self, element):
        if element is None:
            return
        self._snapshot_before_structural_change()
        self.xml_doc.remove_element(element)
        if self._current_element is element:
            self._current_element = None
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)

    def update_display_data(self, translations: dict):
        if self._current_element is not None:
            self._snapshot_before_edit(self._current_element)
            self.xml_doc.set_display_translations(self._current_element, translations)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    # ------------------------------------------------------------------
    # Media linking -- picks up a raw image/media file, moves it into the
    # configured 'media' folder, and auto-populates whatever the file
    # itself can tell us (see core/media_metadata.py for the actual
    # dimension/EXIF/IPTC work; this class just orchestrates writing the
    # results into the document).
    # ------------------------------------------------------------------

    # AAT unit terms for the auto-populated pixel/dpi measurements, in the
    # vocab/refid/href form used throughout this archive's own sample data.
    _AAT_PIXELS = {
        'vocab': 'AAT', 'refid': '300266190',
        'href': 'http://vocab.getty.edu/page/aat/300266190',
    }
    _AAT_DPI = {
        'vocab': 'AAT', 'refid': '300410385',
        'href': 'http://vocab.getty.edu/page/aat/300410385',
    }

    def link_media_file(self, image_path) -> Optional[Path]:
        """Moves image_path into the 'media' location, adds a relation
        entry recording which file this record is linked to, and
        populates measurements/location/date from it (see
        _populate_from_media). One undo snapshot for the whole cascade --
        the public per-field methods (insert_child, update_element_data,
        ...) each snapshot independently, so this works directly against
        xml_doc instead, the same way create_new_record/_move_to_location
        already bypass those wrappers. Returns the file's final path in
        media/, or None if there's no document loaded or no 'media'
        location configured.
        """
        if self.xml_doc.xml_root is None or self._current_file is None:
            return None
        media_dir = load_locations().get('media')
        if media_dir is None:
            return None

        records = self.xml_doc.build_tree()
        if not records:
            return None
        record_node = records[0]
        record_elem = record_node.element
        record_specs = record_node.child_specs

        media_dir.mkdir(parents=True, exist_ok=True)
        image_path = Path(image_path)
        dest_path = (media_dir / image_path.name).resolve()
        shutil.move(str(image_path), str(dest_path))

        self._snapshot_before_structural_change()

        relation_set = self._ensure_set(record_elem, record_specs, 'relationSet')
        relation_type = self._type_name_of(record_specs, 'relationSet')
        self._add_set_item(relation_set, relation_type, 'relation',
                            dest_path.name, {'type': 'imageIs'})

        self._populate_from_media(record_elem, record_specs, dest_path)

        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)
        return dest_path

    def extract_media_metadata(self) -> bool:
        """Re-reads the currently-linked media file's dimensions/EXIF and
        refreshes the record's Measurements/Location/Date sections from
        it, without touching the relation entry or moving anything --
        for when the linked file changed after it was first linked, or
        the initial auto-extraction (see link_media_file) missed
        something worth retrying. One undo snapshot, like link_media_file.
        Returns False if there's no document loaded or no file linked.
        """
        path = self.find_linked_media_path()
        if path is None:
            return False
        records = self.xml_doc.build_tree()
        if not records:
            return False
        record_node = records[0]

        self._snapshot_before_structural_change()
        self._populate_from_media(record_node.element, record_node.child_specs, path)

        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)
        return True

    def _populate_from_media(self, record_elem, record_specs, path: Path):
        """Writes dimensions/DPI (always) and GPS/capture-date (only
        when the file's EXIF actually has them) into record_elem's
        Measurements/Location/Date sections. Replaces (rather than
        duplicates) whichever of its own previously-auto-populated
        entries are still there, identified by their 'type' attribute,
        so this is safe to call more than once for the same record --
        see extract_media_metadata, which is exactly that: a deliberate
        re-run. Caller owns the undo snapshot and the emit/rebuild."""
        info = media_metadata.read_image_info(path)

        measurements_set = self._ensure_set(record_elem, record_specs, 'measurementsSet')
        measurements_type = self._type_name_of(record_specs, 'measurementsSet')
        self._replace_measurement(measurements_set, measurements_type, 'width',
                                   str(info.width), {'unit': 'px', **self._AAT_PIXELS})
        self._replace_measurement(measurements_set, measurements_type, 'height',
                                   str(info.height), {'unit': 'px', **self._AAT_PIXELS})
        if info.dpi is not None:
            self._replace_measurement(measurements_set, measurements_type, 'resolution',
                                       str(int(info.dpi)), {'unit': 'dpi', **self._AAT_DPI})

        if info.gps_lat is not None and info.gps_lon is not None:
            location_set = self._ensure_set(record_elem, record_specs, 'locationSet')
            location_type = self._type_name_of(record_specs, 'locationSet')
            for existing in location_set.findall(f'{{{VRA_NS}}}location'):
                if existing.get('type') == 'creation':
                    self.xml_doc.remove_element(existing)
            location_elem = self._add_set_item(location_set, location_type, 'location',
                                                attrs={'type': 'creation'})
            # Raw EXIF coordinates aren't a verified gazetteer lookup, so
            # deliberately no vocab= here -- unlike this archive's usual
            # vocab="GNS" convention for actual GNS-confirmed places.
            self._add_set_item(location_elem, 'locationType', 'name',
                                f'{info.gps_lat:.6f}, {info.gps_lon:.6f}', {'type': 'geographic'})

        if info.date is not None:
            date_set = self._ensure_set(record_elem, record_specs, 'dateSet')
            date_type = self._type_name_of(record_specs, 'dateSet')
            for existing in date_set.findall(f'{{{VRA_NS}}}date'):
                if existing.get('type') == 'creation':
                    self.xml_doc.remove_element(existing)
            date_elem = self._add_set_item(date_set, date_type, 'date', attrs={'type': 'creation'})
            self._add_set_item(date_elem, 'dateType', 'earliestDate', info.date)
            self._add_set_item(date_elem, 'dateType', 'latestDate', info.date)

    def _replace_measurement(self, measurements_set, measurements_type, measurement_type: str,
                              text: str, attrs: dict):
        for existing in measurements_set.findall(f'{{{VRA_NS}}}measurements'):
            if existing.get('type') == measurement_type:
                self.xml_doc.remove_element(existing)
        self._add_set_item(measurements_set, measurements_type, 'measurements',
                            text, {'type': measurement_type, **attrs})

    @staticmethod
    def _type_name_of(specs, tag: str) -> Optional[str]:
        return next((s.type_name for s in specs if s.tag == tag), None)

    def _ensure_set(self, record_elem, record_specs, set_tag: str):
        """The existing <set_tag> under record_elem, or a freshly
        created empty one at its schema-correct position."""
        existing = record_elem.find(f'{{{VRA_NS}}}{set_tag}')
        if existing is not None:
            return existing
        sibling_order = [s.tag for s in record_specs]
        return self.xml_doc.add_child(record_elem, set_tag, sibling_order)

    def _add_set_item(self, parent_elem, parent_type_name: Optional[str], tag: str,
                       text: str = '', attrs: Optional[dict] = None):
        """Adds <tag> as a new child of parent_elem at its schema-correct
        position (parent_type_name is parent_elem's own complexType, used
        to look up its schema-declared child order), optionally with text
        and attributes."""
        sibling_order = [s.tag for s in vra_structure.children_of_type(parent_type_name)]
        new_elem = self.xml_doc.add_child(parent_elem, tag, sibling_order)
        if text:
            new_elem.text = text
        for key, value in (attrs or {}).items():
            new_elem.set(key, value)
        return new_elem

    def find_linked_media_path(self) -> Optional[Path]:
        """Resolves the media file linked via a type="imageIs" relation
        entry (see link_media_file) against the 'media' location. None
        if there's no such relation, the file's missing, or no 'media'
        location is configured."""
        if self.xml_doc.xml_root is None:
            return None
        media_dir = load_locations().get('media')
        if media_dir is None:
            return None
        for relation in self.xml_doc.xml_root.iter(f'{{{VRA_NS}}}relation'):
            if relation.get('type') == 'imageIs' and (relation.text or '').strip():
                candidate = media_dir / relation.text.strip()
                if candidate.exists():
                    return candidate
        return None

    def build_iptc_fields(self) -> dict:
        """The {Iptc.Application2.*: value} dict for inject_iptc, built
        from this record's own data per the approved mapping: Title ->
        ObjectName, Description -> Caption, People -> By-line, Rights ->
        Copyright, Subjects -> Keywords, creation Date -> DateCreated."""
        root = self.xml_doc.xml_root
        if root is None:
            return {}
        fields = {}

        title = self._first_text(root, 'title')
        if title:
            fields['Iptc.Application2.ObjectName'] = title

        description = self._first_text(root, 'description')
        if description:
            fields['Iptc.Application2.Caption'] = description

        names = self._all_sub_text(root, 'agent', 'name')
        if names:
            fields['Iptc.Application2.Byline'] = names

        rights = self._first_text(root, 'rights')
        if rights:
            fields['Iptc.Application2.Copyright'] = rights

        subjects = self._all_sub_text(root, 'subject', 'term')
        if subjects:
            fields['Iptc.Application2.Keywords'] = subjects

        for date_elem in root.iter(f'{{{VRA_NS}}}date'):
            if date_elem.get('type') == 'creation':
                earliest = date_elem.find(f'{{{VRA_NS}}}earliestDate')
                if earliest is not None and (earliest.text or '').strip():
                    fields['Iptc.Application2.DateCreated'] = earliest.text.strip()
                break

        return fields

    @staticmethod
    def _first_text(root, tag: str) -> str:
        elem = root.find(f'.//{{{VRA_NS}}}{tag}')
        return (elem.text or '').strip() if elem is not None else ''

    @staticmethod
    def _all_sub_text(root, item_tag: str, sub_tag: str) -> list:
        results = []
        for item in root.iter(f'{{{VRA_NS}}}{item_tag}'):
            sub = item.find(f'{{{VRA_NS}}}{sub_tag}')
            text = (sub.text or '').strip() if sub is not None else ''
            if text:
                results.append(text)
        return results

    def inject_iptc(self, path, fields: dict) -> None:
        media_metadata.write_iptc(path, fields)

    # ------------------------------------------------------------------
    # Review notes -- a reviewer's todo list for the editor, stored as an
    # XML comment rather than document content (see core/review_notes.py).
    # ------------------------------------------------------------------

    def get_review_notes(self) -> list:
        return review_notes.get_review_notes(self.xml_doc.xml_root)

    def add_review_note(self, text: str):
        text = text.strip()
        if not text:
            return
        notes = self.get_review_notes()
        notes.append({
            'text': text,
            'author': user_name() or '',
            'date': datetime.date.today().isoformat(),
            'resolved': False,
        })
        self._write_review_notes(notes)

    def set_review_note_resolved(self, index: int, resolved: bool):
        notes = self.get_review_notes()
        if 0 <= index < len(notes):
            notes[index]['resolved'] = resolved
            self._write_review_notes(notes)

    def remove_review_note(self, index: int):
        notes = self.get_review_notes()
        if 0 <= index < len(notes):
            notes.pop(index)
            self._write_review_notes(notes)

    def _write_review_notes(self, notes: list):
        self._snapshot_before_structural_change()
        review_notes.set_review_notes(self.xml_doc.xml_root, notes)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    # ------------------------------------------------------------------
    # Undo -- whole-document snapshots rather than fine-grained command
    # objects, since these documents are small enough (a few hundred
    # lines) that this is negligible cost and much simpler to get right.
    # ------------------------------------------------------------------

    _UNDO_STACK_LIMIT = 100

    def _push_undo_snapshot(self):
        if self.xml_doc.xml_root is None:
            return
        self._undo_stack.append(etree.tostring(self.xml_doc.xml_root))
        if len(self._undo_stack) > self._UNDO_STACK_LIMIT:
            self._undo_stack.pop(0)

    def _snapshot_before_edit(self, element):
        """For field edits, which fire on every keystroke: only push a
        new snapshot when the edit target changes, so continuous typing
        into one field collapses into a single undo step instead of one
        per character."""
        if self._undo_stack and self._undo_snapshot_element is element:
            return
        self._push_undo_snapshot()
        self._undo_snapshot_element = element

    def _snapshot_before_structural_change(self):
        """Insert/remove always get their own undo step, and force the
        next field edit (even to the same element as before) to start a
        fresh step too, rather than coalescing across the structural
        change."""
        self._push_undo_snapshot()
        self._undo_snapshot_element = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def undo(self) -> bool:
        """Reverts to the state before the last edit/insert/remove.
        Returns False if there's nothing to undo."""
        if not self._undo_stack:
            return False
        snapshot = self._undo_stack.pop()
        self._undo_snapshot_element = None
        new_root = etree.fromstring(snapshot)
        self.xml_doc.xml_root = new_root
        self.xml_doc.xml_etree = etree.ElementTree(new_root)
        self._current_element = None
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)
        # An empty stack means every edit since load/create has been
        # undone -- back to the pristine state, so nothing's unsaved.
        self._dirty = bool(self._undo_stack)
        return True

    def get_initial_xml(self) -> str:
        return self._xml_text

    @property
    def current_file(self) -> Optional[str]:
        return self._current_file

    @property
    def current_element(self):
        return self._current_element

    def save_file(self) -> tuple[bool, str]:
        """Validates the current document against the VRA Core 4 schema
        and, only if it passes, writes it back to the file it was
        loaded from. Returns (success, message) -- message is the
        schema validation error on failure, or a short confirmation on
        success. Never writes an invalid document to disk."""
        if self.xml_doc.xml_root is None or self._current_file is None:
            return False, "No document loaded."

        xml_bytes = etree.tostring(
            self.xml_doc.xml_root, pretty_print=True,
            xml_declaration=True, encoding='UTF-8',
        )

        valid, message = self._validator.validate(xml_bytes)
        if not valid:
            return False, message

        with open(self._current_file, 'wb') as f:
            f.write(xml_bytes)
        self._dirty = False
        return True, f"Saved to {self._current_file}"

    def _move_to_location(self, location_key: str, validate: bool) -> tuple[bool, str]:
        """Shared shape for submit/approve/reject: writes the current
        in-memory document (any edits made along the way included) to
        location_key's configured folder under the same filename, then
        removes it from wherever it was. Returns (success, message) --
        the validation error or a missing-location message on failure,
        or the new path on success.

        validate gates whether this transition requires a schema-valid
        document first. Submit does -- it's the actual gate keeping
        invalid records out of the review queue. Approve/Reject don't:
        by then the document was already validated at Submit time, and
        a reviewer needs to be able to reject something broken without
        first having to fix it themselves.
        """
        if self.xml_doc.xml_root is None or self._current_file is None:
            return False, "No document loaded."

        xml_bytes = etree.tostring(
            self.xml_doc.xml_root, pretty_print=True,
            xml_declaration=True, encoding='UTF-8',
        )
        if validate:
            valid, message = self._validator.validate(xml_bytes)
            if not valid:
                return False, message

        dest_dir = load_locations().get(location_key)
        if dest_dir is None:
            return False, f"No '{location_key}' folder configured in vra-config.ini."
        dest_dir.mkdir(parents=True, exist_ok=True)

        src_path = Path(self._current_file).resolve()
        dest_path = (dest_dir / src_path.name).resolve()
        with open(dest_path, 'wb') as f:
            f.write(xml_bytes)

        if src_path != dest_path and src_path.exists():
            src_path.unlink()

        self._current_file = str(dest_path)
        self.file_loaded.emit(self._current_file)
        self._dirty = False
        return True, str(dest_path)

    def submit_file(self) -> tuple[bool, str]:
        """Moves the current record from 'edit' into 'pending', for review."""
        return self._move_to_location('pending', validate=True)

    def approve_file(self) -> tuple[bool, str]:
        """Moves the current record from 'pending' into 'reviewed'."""
        return self._move_to_location('reviewed', validate=False)

    def reject_file(self) -> tuple[bool, str]:
        """Moves the current record from 'pending' into 'rejected', for
        the editor to revisit."""
        return self._move_to_location('rejected', validate=False)

    def _rebuild_xml(self) -> str:
        if self.xml_doc.xml_root is None:
            return self._xml_text
        return etree.tostring(self.xml_doc.xml_root, pretty_print=True).decode('utf-8')
