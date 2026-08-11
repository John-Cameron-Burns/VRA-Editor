import datetime
import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from lxml import etree

from vra_editor.config import load_locations
from vra_editor.core import audit_log, media_metadata, review_notes, vra_structure
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

    # Fields kept in sync between record and file, keyed by the same name
    # used throughout compute_media_sync/apply_media_sync's selections dict
    # -- see _record_field_value/_file_field_value for how each side reads
    # its current value, and _fill_record_field/_file_fields_to_write for
    # how a chosen direction actually gets written.
    _SYNC_FIELDS = ('title', 'description', 'rights', 'agent', 'subject', 'date', 'location')

    # Fields with a real "write into the file" implementation (see
    # _file_fields_to_write) -- location is deliberately not one of them:
    # there's no GPS-EXIF writer, only a GPS reader (see
    # media_metadata.read_image_info), so a record's location can only
    # ever flow file -> record, never the other way. compute_media_sync
    # downgrades what would otherwise be a 'fill_file' classification for
    # location to 'empty' (nothing actionable), and MediaSyncDialog hides
    # the "use record value" choice on a location conflict, for the same
    # reason.
    _FILE_WRITABLE_FIELDS = ('title', 'description', 'rights', 'agent', 'subject', 'date')

    def compute_media_sync(self, path) -> dict:
        """Read-only comparison between the current record and an image
        file the cataloguer just picked (there's no persisted link to
        read this from -- see the module docstring in media_metadata.py
        and the "purist" design this replaced). Returns:

          {'measurements': {'width': int, 'height': int,
                             'resolution': Optional[int], 'file_size': int},
           'fields': {field_name: {'record': value, 'file': value,
                                    'status': 'fill_record'|'fill_file'|
                                              'conflict'|'in_sync'|'empty'}}}

        measurements are always "file replaces record" (dimensions/size are
        physical facts about the file, not an editorial choice) so they're
        reported separately, not classified like the other fields.

        fields covers title/description/rights/agent/subject/date/location,
        each classified by comparing the record's current value against
        the file's IPTC/EXIF value -- see apply_media_sync for what each
        status means and _record_field_value/_file_field_value for how
        each side is actually read."""
        path = Path(path)
        info = media_metadata.read_image_info(path)
        iptc_fields = media_metadata.read_iptc(path)

        measurements = {
            'width': info.width,
            'height': info.height,
            'resolution': int(info.dpi) if info.dpi is not None else None,
            'file_size': info.file_size,
        }

        root = self.xml_doc.xml_root
        fields = {}
        for name in self._SYNC_FIELDS:
            record_value = self._record_field_value(root, name)
            file_value = self._file_field_value(name, info, iptc_fields)
            status = self._classify_sync_field(record_value, file_value)
            if status == 'fill_file' and name not in self._FILE_WRITABLE_FIELDS:
                status = 'empty'
            fields[name] = {'record': record_value, 'file': file_value, 'status': status}

        return {'measurements': measurements, 'fields': fields}

    @staticmethod
    def _classify_sync_field(record_value, file_value) -> str:
        if not record_value and not file_value:
            return 'empty'
        if record_value and not file_value:
            return 'fill_file'
        if file_value and not record_value:
            return 'fill_record'
        return 'in_sync' if record_value == file_value else 'conflict'

    def _record_field_value(self, root, name: str):
        """The record's current value for a sync field, in the same
        shape _file_field_value returns for it (str for scalars, list[str]
        for agent/subject, a '{lat}, {lon}' string for location) so the
        two are directly comparable in compute_media_sync."""
        if root is None:
            return '' if name not in ('agent', 'subject') else []
        if name == 'title':
            return self._first_text(root, 'title')
        if name == 'description':
            return self._first_text(root, 'description')
        if name == 'rights':
            elem = root.find(f'.//{{{VRA_NS}}}rights/{{{VRA_NS}}}text')
            return (elem.text or '').strip() if elem is not None else ''
        if name == 'agent':
            return self._all_sub_text(root, 'agent', 'name')
        if name == 'subject':
            return self._all_sub_text(root, 'subject', 'term')
        if name == 'date':
            return self._creation_date_text(root)
        if name == 'location':
            for location in root.iter(f'{{{VRA_NS}}}location'):
                if location.get('type') != 'creation':
                    continue
                name_elem = location.find(f'{{{VRA_NS}}}name')
                if name_elem is not None and name_elem.get('type') == 'geographic':
                    return (name_elem.text or '').strip()
            return ''
        raise ValueError(name)

    @staticmethod
    def _file_field_value(name: str, info, iptc_fields: dict):
        if name == 'title':
            return iptc_fields.get('Iptc.Application2.ObjectName', '').strip()
        if name == 'description':
            return iptc_fields.get('Iptc.Application2.Caption', '').strip()
        if name == 'rights':
            return iptc_fields.get('Iptc.Application2.Copyright', '').strip()
        if name == 'agent':
            return [n.strip() for n in iptc_fields.get('Iptc.Application2.Byline', []) if n.strip()]
        if name == 'subject':
            return [k.strip() for k in iptc_fields.get('Iptc.Application2.Keywords', []) if k.strip()]
        if name == 'date':
            return info.date or ''
        if name == 'location':
            if info.gps_lat is None or info.gps_lon is None:
                return ''
            return f'{info.gps_lat:.6f}, {info.gps_lon:.6f}'
        raise ValueError(name)

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

        measurements_set = self._ensure_set(record_elem, record_specs, 'measurementsSet')
        measurements_type = self._type_name_of(record_specs, 'measurementsSet')
        self._replace_measurement(measurements_set, measurements_type, 'width',
                                   str(info.width), {'unit': 'px', **self._AAT_PIXELS})
        self._replace_measurement(measurements_set, measurements_type, 'height',
                                   str(info.height), {'unit': 'px', **self._AAT_PIXELS})
        if info.dpi is not None:
            self._replace_measurement(measurements_set, measurements_type, 'resolution',
                                       str(int(info.dpi)), {'unit': 'dpi', **self._AAT_DPI})
        self._replace_measurement(measurements_set, measurements_type, 'fileSize',
                                   str(info.file_size), {'unit': 'bytes'})

        record_fields_to_write = {}
        for name, direction in selections.items():
            if direction == 'record':
                self._fill_record_field(record_elem, record_specs, name, info, iptc_fields)
            elif direction == 'file':
                record_fields_to_write[name] = True

        if record_fields_to_write:
            fields, exif_fields = self._file_fields_to_write(record_fields_to_write)
            if fields:
                self.inject_iptc(path, fields, exif_fields)

        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)

    def _fill_record_field(self, record_elem, record_specs, name: str, info, iptc_fields: dict):
        """Writes one field's file-side value into the record -- the
        'record' half of apply_media_sync's per-field selections, and
        (for location/date) the same shape link_media_file's old
        _populate_from_media used, now driven by an explicit selection
        instead of an implicit gap-check."""
        if name == 'title':
            title = iptc_fields.get('Iptc.Application2.ObjectName', '').strip()
            if not title:
                return
            title_set = self._ensure_set(record_elem, record_specs, 'titleSet')
            title_type = self._type_name_of(record_specs, 'titleSet')
            for existing in title_set.findall(f'{{{VRA_NS}}}title'):
                self.xml_doc.remove_element(existing)
            # 'main' reads naturally but isn't actually one of
            # titleTypeType's enumerated values (see vra_core4_strict.xsd)
            # -- 'descriptive' is the closest fit for a plain imported
            # title with no more specific classification available.
            self._add_set_item(title_set, title_type, 'title', title, {'type': 'descriptive'})
        elif name == 'description':
            description = iptc_fields.get('Iptc.Application2.Caption', '').strip()
            if not description:
                return
            description_set = self._ensure_set(record_elem, record_specs, 'descriptionSet')
            description_type = self._type_name_of(record_specs, 'descriptionSet')
            for existing in description_set.findall(f'{{{VRA_NS}}}description'):
                self.xml_doc.remove_element(existing)
            self._add_set_item(description_set, description_type, 'description', description)
        elif name == 'rights':
            rights = iptc_fields.get('Iptc.Application2.Copyright', '').strip()
            if not rights:
                return
            rights_set = self._ensure_set(record_elem, record_specs, 'rightsSet')
            rights_type = self._type_name_of(record_specs, 'rightsSet')
            for existing in rights_set.findall(f'{{{VRA_NS}}}rights'):
                self.xml_doc.remove_element(existing)
            rights_elem = self._add_set_item(rights_set, rights_type, 'rights')
            self._add_set_item(rights_elem, 'rightsType', 'text', rights)
        elif name == 'agent':
            names = [n.strip() for n in iptc_fields.get('Iptc.Application2.Byline', []) if n.strip()]
            if not names:
                return
            agent_set = self._ensure_set(record_elem, record_specs, 'agentSet')
            agent_type = self._type_name_of(record_specs, 'agentSet')
            for existing in agent_set.findall(f'{{{VRA_NS}}}agent'):
                self.xml_doc.remove_element(existing)
            for person_name in names:
                agent_elem = self._add_set_item(agent_set, agent_type, 'agent')
                self._add_set_item(agent_elem, 'agentType', 'name', person_name)
        elif name == 'subject':
            keywords = [k.strip() for k in iptc_fields.get('Iptc.Application2.Keywords', []) if k.strip()]
            if not keywords:
                return
            subject_set = self._ensure_set(record_elem, record_specs, 'subjectSet')
            subject_type = self._type_name_of(record_specs, 'subjectSet')
            for existing in subject_set.findall(f'{{{VRA_NS}}}subject'):
                self.xml_doc.remove_element(existing)
            for keyword in keywords:
                subject_elem = self._add_set_item(subject_set, subject_type, 'subject')
                self._add_set_item(subject_elem, 'subjectType', 'term', keyword)
        elif name == 'date':
            if info.date is None:
                return
            date_set = self._ensure_set(record_elem, record_specs, 'dateSet')
            date_type = self._type_name_of(record_specs, 'dateSet')
            for existing in date_set.findall(f'{{{VRA_NS}}}date'):
                if existing.get('type') == 'creation':
                    self.xml_doc.remove_element(existing)
            date_elem = self._add_set_item(date_set, date_type, 'date', attrs={'type': 'creation'})
            self._add_set_item(date_elem, 'dateType', 'earliestDate', info.date)
            self._add_set_item(date_elem, 'dateType', 'latestDate', info.date)
        elif name == 'location':
            if info.gps_lat is None or info.gps_lon is None:
                return
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
        else:
            raise ValueError(name)

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

        dest_path = Path(self._current_file)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(xml_bytes)
        self._dirty = False
        return True, f"Saved to {self._current_file}"

    def _move_to_location(self, location_key: str, validate: bool) -> tuple[bool, str]:
        """Shared shape for submit/approve/reject: writes the current
        in-memory document (any edits made along the way included) to
        location_key's configured folder, preserving whatever subfolder
        path the record currently has relative to its own location (see
        _relative_record_path) -- edit/collectionA/foo.xml submits to
        pending/collectionA/foo.xml, not a flattened pending/foo.xml --
        then removes it from wherever it was. Returns (success,
        message) -- the validation error or a missing-location message
        on failure, or the new path on success.

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

        src_path = Path(self._current_file).resolve()
        dest_path = (dest_dir / self._relative_record_path(src_path)).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(xml_bytes)

        if src_path != dest_path and src_path.exists():
            src_path.unlink()

        self._current_file = str(dest_path)
        self.file_loaded.emit(self._current_file)
        self._dirty = False
        return True, str(dest_path)

    @staticmethod
    def _relative_record_path(src_path: Path) -> Path:
        """src_path's path relative to whichever configured location
        (edit/ingest/pending/rejected/reviewed/released) it currently
        sits under, so a submit/approve/reject move can reproduce that
        same subfolder structure at the destination instead of
        flattening it to just the filename. Falls back to the bare
        filename if src_path isn't under any configured location --
        shouldn't normally happen, but better than raising over it."""
        for root in load_locations().values():
            try:
                return src_path.relative_to(root.resolve())
            except ValueError:
                continue
        return Path(src_path.name)

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
