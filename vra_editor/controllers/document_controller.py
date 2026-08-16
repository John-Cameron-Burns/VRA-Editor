import datetime
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from lxml import etree

from vra_editor.config import load_locations, load_media_extensions
from vra_editor.core import audit_log, media_files, media_metadata, media_sync, record_locks, record_transitions, review_notes, vra_structure
from vra_editor.core.export import dublin_core, lido
from vra_editor.core.record_transitions import LocationUnavailableError
from vra_editor.core.schema_validator import DEFAULT_XSD_PATH, SchemaValidator
from vra_editor.core.xml_parser import VRA_NS, VraXmlParser
from vra_editor.utils import user_name

# LocationUnavailableError re-exported from core/record_transitions.py (also
# raised directly by save_file below) -- kept importable from here so
# main_window.py's existing `from ...document_controller import
# DocumentController, LocationUnavailableError` doesn't need to change.


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
    lock_lost = Signal()  # this record's advisory lock expired/was taken by someone else

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

        # Advisory locking (core/record_locks.py) -- the same mechanism
        # the web app already uses, so two people editing the same
        # shared archive (desktop or web, in any combination) don't
        # silently clobber each other. _lock_path/_lock_holder track
        # what *this* controller currently holds, independently of
        # _current_file (which a submit/approve/reject moves out from
        # under it -- see _move_to_location).
        self._lock_path: Optional[Path] = None
        self._lock_holder: Optional[str] = None
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._do_heartbeat)

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

    def try_open_file(self, path: str) -> tuple[bool, str]:
        """Like load_file, but first acquires this record's advisory
        lock (core/record_locks.py) -- the same mechanism the web app
        already uses -- so two people can't silently clobber each
        other's edits to the same shared record. Returns (False,
        "<name>") without loading anything if someone else already
        holds it; (True, "") on success. Acquires the *new* lock
        before touching anything else, so a failed attempt never costs
        the document (or lock) already open -- only load_file (called
        here on success) releases that."""
        holder_name = user_name() or ''
        other_holder = record_locks.acquire(Path(path), holder_name)
        if other_holder is not None:
            return False, other_holder
        self.load_file(path)
        self._lock_path = Path(path)
        self._lock_holder = holder_name
        self._heartbeat_timer.start(record_locks.HEARTBEAT_INTERVAL_SECONDS * 1000)
        return True, ""

    def release_lock(self):
        """Releases whatever record this controller currently holds
        the lock on, if any -- idempotent, safe to call whether or not
        a lock is actually held. Called from every path that stops
        editing the locked record: load_file/create_new_record/clear
        (replacing or leaving the open document) and _move_to_location
        (the record moved away, so there's nothing left to protect at
        its old path)."""
        self._heartbeat_timer.stop()
        if self._lock_path is not None:
            record_locks.release(self._lock_path, self._lock_holder or '')
        self._lock_path = None
        self._lock_holder = None

    def _do_heartbeat(self):
        if self._lock_path is None:
            return
        if not record_locks.heartbeat(self._lock_path, self._lock_holder or ''):
            # Lock expired (we went quiet too long) and someone else
            # may have taken it -- advisory, so this doesn't block
            # Save, just warns (see main_window's lock_lost handler).
            self._heartbeat_timer.stop()
            self._lock_path = None
            self._lock_holder = None
            self.lock_lost.emit()

    def load_file(self, path: str):
        self.release_lock()
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
        self.release_lock()  # a brand-new record can't be locked by anyone -- nothing to acquire
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
        self.release_lock()
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

    def restore_revision(self, revision: audit_log.Revision, dest_path) -> bool:
        """Writes revision's historical content (see core/audit_log.py)
        to dest_path -- which must not already exist, restoring into a
        new file rather than overwriting anything -- and loads it as
        the current document, the same as opening any other file.
        Returns False if dest_path already exists or the content
        cannot be read from the archive's history.
        """
        dest_path = Path(dest_path)
        if dest_path.exists():
            return False
        try:
            content = audit_log.read_revision_content(revision)
        except Exception:
            return False
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)
        self.load_file(str(dest_path))
        return True

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
    # Media sync -- compares the open record against an image file the
    # cataloguer picks (there's no XML-stored link to a file; VRA Core's
    # relation element is for record-to-record links, each end with its
    # own id, not a pointer to a raw file with none, so the file is
    # located fresh each time from MediaSyncDialog) and fills gaps in
    # either direction. See core/media_metadata.py for the actual
    # dimension/EXIF/IPTC work; this class just classifies each field and
    # orchestrates writing the chosen results into the document or file.
    # ------------------------------------------------------------------

    def compute_media_sync(self, path) -> dict:
        """Read-only comparison between the current record and an image
        file the cataloguer just picked (there's no persisted link to
        read this from -- see the module docstring in media_metadata.py
        and the "purist" design this replaced). See
        core/media_sync.py's compute_media_sync for the return shape
        and field-classification details -- this is now a thin wrapper
        around it (the same logic the web backend's media-sync compare
        endpoint also calls, since it has no DocumentController)."""
        return media_sync.compute_media_sync(self.xml_doc.xml_root, Path(path))

    def apply_media_sync(self, path, selections: dict) -> None:
        """Applies a media sync: selections is {field_name: 'record'|'file'}
        for whichever of compute_media_sync's fields the cataloguer chose
        to actually write (fill_record/fill_file rows default to their
        one legal direction; conflict rows may go either way; empty/
        in_sync rows are typically omitted since there's nothing to do).
        Measurements (width/height/resolution/file_size) always get
        written from the file, unconditionally -- see compute_media_sync.

        One undo snapshot for the whole thing, the same way
        link_media_file/extract_media_metadata used to -- this works
        directly against xml_doc rather than the public per-field
        wrappers (insert_child, update_element_data, ...), each of which
        snapshots independently.

        Callers wanting to write 'date' as 'file' (i.e. into the file's
        IPTC/EXIF) must first make sure the record's date is an exact
        calendar date -- see media_metadata.parse_vra_date -- since a
        fuzzy one silently contributes nothing to build_iptc_fields/
        build_exif_fields. MediaSyncDialog resolves that before calling
        this, the same way MediaPreviewPanel's Inject flow used to."""
        if self.xml_doc.xml_root is None:
            return
        path = Path(path)
        info = media_metadata.read_image_info(path)
        iptc_fields = media_metadata.read_iptc(path)

        records = self.xml_doc.build_tree()
        if not records:
            return
        record_node = records[0]
        record_elem = record_node.element
        record_specs = record_node.child_specs

        self._snapshot_before_structural_change()

        media_sync.write_measurements(self.xml_doc, record_elem, record_specs, info)

        record_fields_to_write = {}
        for name, direction in selections.items():
            if direction == 'record':
                media_sync.fill_record_field(self.xml_doc, record_elem, record_specs, name, info, iptc_fields)
            elif direction == 'file':
                record_fields_to_write[name] = True

        if record_fields_to_write:
            fields, exif_fields = self._file_fields_to_write(record_fields_to_write)
            if fields:
                self.inject_iptc(path, fields, exif_fields)

        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)

    def _file_fields_to_write(self, selected_names: dict) -> tuple:
        """Builds the (Iptc.Application2.* dict, Exif.* dict) pair for
        apply_media_sync's 'file' selections, reusing build_iptc_fields/
        build_exif_fields (the same mapping Inject always used) but
        limited to just the selected field names -- so a conflict row
        the cataloguer resolved as "keep record, don't touch the file"
        for Title doesn't also silently push Description into the file
        just because Description happened to be a clean fill_file."""
        name_to_iptc_key = {
            'title': 'Iptc.Application2.ObjectName',
            'description': 'Iptc.Application2.Caption',
            'rights': 'Iptc.Application2.Copyright',
            'agent': 'Iptc.Application2.Byline',
            'subject': 'Iptc.Application2.Keywords',
            'date': 'Iptc.Application2.DateCreated',
        }
        all_fields = self.build_iptc_fields()
        fields = {
            key: all_fields[key]
            for name, key in name_to_iptc_key.items()
            if name in selected_names and key in all_fields
        }
        exif_fields = self.build_exif_fields() if 'date' in selected_names else {}
        return fields, exif_fields

    def guess_linked_media_path(self) -> Optional[Path]:
        """A file sitting next to the record's own XML file whose stem
        matches the record's id -- not an authoritative link (there is
        none, by design), just a convenience default for
        MediaSyncDialog's file picker so a file previously saved via
        copy_media_alongside is found again without re-browsing."""
        if self.xml_doc.xml_root is None or self._current_file is None:
            return None
        records = self.xml_doc.build_tree()
        if not records:
            return None
        record_id = records[0].element.get('id', '').strip()
        if not record_id:
            return None
        record_dir = Path(self._current_file).parent
        for ext in ('.tif', '.tiff', '.jpg', '.jpeg', '.png'):
            candidate = record_dir / f'{record_id}{ext}'
            if candidate.exists():
                return candidate
        return None

    def copy_media_alongside(self, path) -> Optional[Path]:
        """Copies path to sit next to the record's own XML file, named
        after the record's own id -- plain file I/O, not a document
        edit, so no undo snapshot and no signal emitted. None if
        there's no document loaded or no file currently open."""
        if self.xml_doc.xml_root is None or self._current_file is None:
            return None
        records = self.xml_doc.build_tree()
        if not records:
            return None
        record_id = records[0].element.get('id', '').strip()
        if not record_id:
            return None
        path = Path(path)
        dest_path = Path(self._current_file).parent / f'{record_id}{path.suffix}'
        if dest_path.resolve() == path.resolve():
            return dest_path
        shutil.copy2(str(path), str(dest_path))
        return dest_path

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

    def build_iptc_fields(self) -> dict:
        """The {Iptc.Application2.*: value} dict for inject_iptc, built
        from this record's own data per the approved mapping: record id
        -> TransmissionReference, Title -> ObjectName, Description ->
        Caption, People -> By-line, Rights -> Copyright, Subjects ->
        Keywords, creation Date -> DateCreated.

        TransmissionReference (not a dedicated ID field -- legacy IIM
        IPTC doesn't have one) is the standard field for a reference/
        tracking number, unused by the rest of this mapping, and its
        32-character limit comfortably fits VRA record ids."""
        root = self.xml_doc.xml_root
        if root is None:
            return {}
        fields = {}

        records = self.xml_doc.build_tree()
        record_id = records[0].element.get('id', '').strip() if records else ''
        if record_id:
            fields['Iptc.Application2.TransmissionReference'] = record_id

        title = self._first_text(root, 'title')
        if title:
            fields['Iptc.Application2.ObjectName'] = title

        description = self._first_text(root, 'description')
        if description:
            fields['Iptc.Application2.Caption'] = description

        names = self._all_sub_text(root, 'agent', 'name')
        if names:
            fields['Iptc.Application2.Byline'] = names

        # rights has no text of its own -- its actual statement lives in a
        # <text> child (see rightsType in the schema) -- so this needs a
        # scoped lookup rather than _first_text's bare tag search, which
        # would either find nothing (rights.text is always blank) or, worse,
        # match some other element's <text> child (inscription has one too).
        rights_text_elem = root.find(f'.//{{{VRA_NS}}}rights/{{{VRA_NS}}}text')
        if rights_text_elem is not None and (rights_text_elem.text or '').strip():
            fields['Iptc.Application2.Copyright'] = rights_text_elem.text.strip()

        subjects = self._all_sub_text(root, 'subject', 'term')
        if subjects:
            fields['Iptc.Application2.Keywords'] = subjects

        # IPTC's DateCreated expects a strict CCYYMMDD, not free text --
        # writing the raw VRA text (which can be "circa 1990") straight
        # through fails silently at the libexiv2 level. Same fuzziness
        # rule as EXIF: only ever write a date that actually parses as
        # one, omit it entirely otherwise. See MediaSyncDialog's
        # _resolve_fuzzy_date, which prompts to fix or skip a fuzzy date
        # before this is ever reached, rather than silently dropping it
        # here unremarked.
        creation_date = self._creation_date_text(root)
        if creation_date:
            parsed = media_metadata.parse_vra_date(creation_date)
            if parsed is not None:
                fields['Iptc.Application2.DateCreated'] = parsed.strftime('%Y%m%d')

        return fields

    def build_exif_fields(self) -> dict:
        """The {Exif.*: value} dict for inject_iptc's EXIF half -- just
        the creation date today. Empty if there's no creation date, or
        it doesn't parse as a real calendar date (see
        media_metadata.build_exif_date_field) -- VRA dates can be far
        fuzzier ("circa 1990") than EXIF has any way to represent."""
        root = self.xml_doc.xml_root
        if root is None:
            return {}
        creation_date = self._creation_date_text(root)
        if not creation_date:
            return {}
        return media_metadata.build_exif_date_field(creation_date)

    def get_creation_date_text(self) -> str:
        """The record's raw creation-date text (e.g. "circa 1990"), for
        UI that needs to check whether it is an exact calendar date
        (see media_metadata.parse_vra_date) before relying on
        build_iptc_fields/build_exif_fields to have included it. Empty
        string if there is no creation date, or no document loaded."""
        root = self.xml_doc.xml_root
        if root is None:
            return ''
        return self._creation_date_text(root)

    def set_creation_date(self, date_str: str):
        """Sets the record's creation date (creating Dates/date/
        earliestDate/latestDate if none exists yet) to date_str,
        replacing whatever was there. Used when Inject's fuzzy-date
        prompt asks for -- and gets -- an exact replacement; a plain
        edit like any other, so it is undoable and shows up in the
        section form immediately, not just in the injected file."""
        if self.xml_doc.xml_root is None:
            return
        records = self.xml_doc.build_tree()
        if not records:
            return
        record_node = records[0]
        record_elem = record_node.element
        record_specs = record_node.child_specs

        self._snapshot_before_structural_change()
        date_set = self._ensure_set(record_elem, record_specs, 'dateSet')
        date_type = self._type_name_of(record_specs, 'dateSet')
        date_elem = next(
            (d for d in date_set.findall(f'{{{VRA_NS}}}date') if d.get('type') == 'creation'),
            None,
        )
        if date_elem is None:
            date_elem = self._add_set_item(date_set, date_type, 'date', attrs={'type': 'creation'})
        for sub_tag in ('earliestDate', 'latestDate'):
            existing = date_elem.find(f'{{{VRA_NS}}}{sub_tag}')
            if existing is not None:
                self.xml_doc.remove_element(existing)
            self._add_set_item(date_elem, 'dateType', sub_tag, date_str)

        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)

    @staticmethod
    def _creation_date_text(root) -> str:
        """The record's <date type="creation"><earliestDate> text, used
        as the source of truth for both IPTC DateCreated and the EXIF
        capture date -- one field in the record, two places it goes
        back out to in the file."""
        for date_elem in root.iter(f'{{{VRA_NS}}}date'):
            if date_elem.get('type') == 'creation':
                earliest = date_elem.find(f'{{{VRA_NS}}}earliestDate')
                return (earliest.text or '').strip() if earliest is not None else ''
        return ''

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

    def inject_iptc(self, path, fields: dict, exif_fields: Optional[dict] = None) -> None:
        """Writes fields (Iptc.Application2.* -- see build_iptc_fields)
        as the file's IPTC block, and exif_fields (see build_exif_fields)
        as its EXIF block -- defaulting to build_exif_fields() itself if
        the caller doesn't pass exif_fields explicitly, so a plain
        inject_iptc(path, build_iptc_fields()) call still pushes the
        record's creation date into EXIF too, the way it always has.
        apply_media_sync passes an explicit (possibly empty) exif_fields
        instead, since the creation date is just one of several fields
        that may or may not have been selected to write into the file."""
        media_metadata.write_iptc(path, fields)
        media_metadata.write_exif(path, self.build_exif_fields() if exif_fields is None else exif_fields)

    # ------------------------------------------------------------------
    # Export -- crosswalks to other metadata schemas (see core/export/).
    # ------------------------------------------------------------------

    def export_dublin_core_xml(self) -> Optional[str]:
        """The open record as Simple Dublin Core (oai_dc XML), or None
        if there's no document loaded. See core/export/dublin_core.py
        for the crosswalk itself."""
        if self.xml_doc.xml_root is None:
            return None
        records = self.xml_doc.build_tree()
        if not records:
            return None
        return dublin_core.to_oai_dc_xml(records[0].element)

    def export_lido_xml(self) -> Optional[str]:
        """The open record as LIDO v1.1 XML, or None if there's no
        document loaded. See core/export/lido.py for the crosswalk
        itself."""
        if self.xml_doc.xml_root is None:
            return None
        records = self.xml_doc.build_tree()
        if not records:
            return None
        return lido.to_lido_xml(records[0].element)

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
        success. Never writes an invalid document to disk.

        Raises LocationUnavailableError (distinct from the (bool,
        message) contract above) if the destination folder itself can't
        be written to -- e.g. a network share that's gone offline --
        rather than the validation failure this method otherwise
        reports through its return value."""
        if self.xml_doc.xml_root is None or self._current_file is None:
            return False, "No document loaded."

        xml_bytes = etree.tostring(
            self.xml_doc.xml_root, pretty_print=True,
            xml_declaration=True, encoding='UTF-8',
        )

        valid, message = self._validator.validate(xml_bytes)
        if not valid:
            return False, message

        dest_path = Path(self._current_file)
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(xml_bytes)
        except OSError as e:
            raise LocationUnavailableError(
                f"Couldn't save -- {dest_path.parent} isn't reachable right now ({e})."
            ) from e
        self._dirty = False
        return True, f"Saved to {self._current_file}"

    def _move_to_location(self, location_key: str, validate: bool) -> tuple[bool, str]:
        """Shared shape for submit/approve/reject: thin wrapper around
        core/record_transitions.move_to_location (the actual file-move/
        validate/sibling-media logic, extracted there since none of it
        touches Qt) that additionally tracks this controller's own
        "currently open file" state and emits its signal. Returns
        (success, message) -- the validation error or a missing-location
        message on failure, or the new path on success.

        validate gates whether this transition requires a schema-valid
        document first. Submit does -- it's the actual gate keeping
        invalid records out of the review queue. Approve/Reject don't:
        by then the document was already validated at Submit time, and
        a reviewer needs to be able to reject something broken without
        first having to fix it themselves.

        Raises LocationUnavailableError (see save_file's docstring) if
        location_key's folder can't actually be written to -- distinct
        from the (bool, message) "no such location configured" case
        below, which is a Settings problem, not a connectivity one.
        """
        if self.xml_doc.xml_root is None or self._current_file is None:
            return False, "No document loaded."

        result = record_transitions.move_to_location(
            self.xml_doc.xml_root, location_key, load_locations(),
            Path(self._current_file), self._validator, validate, load_media_extensions(),
        )
        if not result.success:
            return False, result.message

        self.release_lock()  # moved away -- nothing left to protect at the old path
        self._current_file = str(result.dest_path)
        self.file_loaded.emit(self._current_file)
        self._dirty = False
        return True, str(result.dest_path)

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
