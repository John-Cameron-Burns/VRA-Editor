from pathlib import Path
from typing import Optional

from lxml import etree
from PySide6.QtCore import QObject, Signal

from vra_editor.core.xml_parser import VraXmlParser
from vra_editor.core.schema_validator import SchemaValidator
from vra_editor.config import load_locations

DEFAULT_XSD_PATH = Path(__file__).resolve().parent.parent / "resources" / "vra_core4.xsd"


class DocumentController(QObject):
    """Owns document state and announces changes to it via signals.

    Signals are declared once, at class level, as Signal(...) instances.
    PySide6 turns each one into a bound signal per-instance at runtime,
    which is what gives you .connect() / .emit() on self.file_loaded etc.
    Nothing further needs to be written to make .connect() work -- it's
    provided by QObject once the class above it in the MRO is QObject
    (or a subclass of QObject) and the attribute is a Signal.
    """

    file_loaded = Signal(str)          # emits the file path
    archive_changed = Signal(str)      # emits the archive name
    xml_updated = Signal(str)          # emits the new XML text
    document_loaded = Signal(object)   # emits the VraXmlParser, once a file has been parsed

    def __init__(self):
        super().__init__()  # QObject.__init__ must run for signals to work
        self.xml_doc = VraXmlParser()
        self._current_file: Optional[str] = None
        self._current_archive: Optional[str] = None
        self._current_element = None   # the lxml element currently selected in the tree
        self._xml_text: str = ""
        self._validator = SchemaValidator(str(DEFAULT_XSD_PATH))

    # ------------------------------------------------------------------
    # Actions that change state -- each emits the matching signal once
    # the change is actually made, not before.
    # ------------------------------------------------------------------

    def load_file(self, path: str):
        xml_string = self.xml_doc.load(path)
        self._current_file = path
        self._current_element = None  # nothing selected yet in the freshly-loaded doc
        self._xml_text = xml_string or ""
        self.file_loaded.emit(path)
        self.document_loaded.emit(self.xml_doc)  # tree panel rebuilds itself from this
        self.xml_updated.emit(self._xml_text)

    def set_archive(self, archive_name: str):
        self._current_archive = archive_name
        self.archive_changed.emit(archive_name)

    def set_current_element(self, element):
        """Called when the tree selection changes -- tracks which real
        lxml element subsequent edits should write into. Not a signal:
        nothing else needs to react to this, it's just state the
        update_* methods below read from."""
        self._current_element = element

    def update_element_data(self, text: str, vocab: str, refid: str, href: str):
        """Generic write-back for any leaf element (title, name, role,
        technique, subject/term, ...) -- covers every basicString-derived
        tag uniformly rather than one method per tag."""
        if self._current_element is not None:
            self.xml_doc.set_element_data(self._current_element, text, vocab, refid, href)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    def insert_child(self, parent_element, tag: str, sibling_order: list):
        """Adds a new empty <tag> under parent_element and rebuilds the
        tree/preview around it. sibling_order is the parent's schema-valid
        child tags in sequence order (from the tree node's child_specs).
        Returns the new lxml element so the caller (main_window) can
        re-select it in the tree."""
        new_elem = self.xml_doc.add_child(parent_element, tag, sibling_order)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)
        return new_elem

    def remove_element(self, element):
        if element is None:
            return
        self.xml_doc.remove_element(element)
        if self._current_element is element:
            self._current_element = None
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)
        self.document_loaded.emit(self.xml_doc)

    def update_display_data(self, translations: dict):
        if self._current_element is not None:
            self.xml_doc.set_display_translations(self._current_element, translations)
        self._xml_text = self._rebuild_xml()
        self.xml_updated.emit(self._xml_text)

    def get_initial_xml(self) -> str:
        return self._xml_text

    @property
    def current_file(self) -> Optional[str]:
        return self._current_file

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
        return True, f"Saved to {self._current_file}"

    def approve_file(self) -> tuple[bool, str]:
        """Moves the current record from 'pending' into 'reviewed':
        writes out whatever's currently in memory (any edits made
        during review included) to the reviewed location, then removes
        the original file. No schema validation here -- that only
        happens on Save. Returns (success, message) -- message is the
        new file path on success, or an error on failure."""
        if self.xml_doc.xml_root is None or self._current_file is None:
            return False, "No document loaded."

        reviewed_dir = load_locations().get('reviewed')
        if reviewed_dir is None:
            return False, "No 'reviewed' folder configured in vra-config.ini."
        reviewed_dir.mkdir(parents=True, exist_ok=True)

        src_path = Path(self._current_file).resolve()
        dest_path = (reviewed_dir / src_path.name).resolve()

        xml_bytes = etree.tostring(
            self.xml_doc.xml_root, pretty_print=True,
            xml_declaration=True, encoding='UTF-8',
        )
        with open(dest_path, 'wb') as f:
            f.write(xml_bytes)

        if src_path != dest_path and src_path.exists():
            src_path.unlink()

        self._current_file = str(dest_path)
        self.file_loaded.emit(self._current_file)
        return True, str(dest_path)

    def _rebuild_xml(self) -> str:
        if self.xml_doc.xml_root is None:
            return self._xml_text
        return etree.tostring(self.xml_doc.xml_root, pretty_print=True).decode('utf-8')
