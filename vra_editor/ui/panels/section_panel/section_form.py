from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QGroupBox, QStackedLayout,
    QComboBox, QMessageBox, QFileDialog, QInputDialog,
)

from vra_editor.config import load_locations
from vra_editor.core.friendly_labels import friendly_label, friendly_enum_value
from vra_editor.ui.panels.form_panel.display_editor import DisplayEditorPanel
from vra_editor.ui.panels.section_panel.field_row import FieldRow

_MEDIA_FILE_NAME_FILTER = "Images (*.tif *.tiff *.jpg *.jpeg *.png);;All Files (*)"


class SectionFormPanel(QWidget):
    """Center pane for the sectioned form: for the Set currently chosen
    in SectionListPanel, shows its Display translations (if any) plus
    one card per existing item, and an "+ Add" button for a new one.

    Card rendering is recursive (see _build_card / _build_container_card)
    and driven entirely by the same VraTreeNode/child_specs data
    build_tree() already produces -- nothing about VRA Core's structure
    is hard-coded here a second time.
    """

    def __init__(self, doc_controller, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller
        self._current_node = None
        self._add_spec = None

        self.layout = QStackedLayout(self)

        self.placeholder = QLabel()
        self.placeholder.setWordWrap(True)
        self._no_section_message()
        self.layout.addWidget(self.placeholder)

        self.content = QWidget()
        outer = QVBoxLayout(self.content)

        header_row = QHBoxLayout()
        self.header = QLabel()
        header_row.addWidget(self.header, stretch=1)
        self.remove_section_button = QPushButton("Remove this section")
        self.remove_section_button.setToolTip(
            "Removes this whole section, including everything in it. "
            "Undo (Ctrl+Z) brings it back."
        )
        self.remove_section_button.clicked.connect(self._on_remove_section_clicked)
        header_row.addWidget(self.remove_section_button)

        self.link_media_button = QPushButton("+ Link Media File")
        self.link_media_button.setToolTip(
            "Pick an image file from anywhere on disk (with the option to "
            "rename it as it comes in). It's copied into the media folder -- "
            "the original is left where it was -- and its dimensions/"
            "resolution (and GPS/capture date, if the file has them) are "
            "filled in automatically, along with a relation entry linking "
            "this record to it."
        )
        self.link_media_button.clicked.connect(self._on_link_media_clicked)
        header_row.addWidget(self.link_media_button)
        outer.addLayout(header_row)

        self.display_editor = DisplayEditorPanel()
        self.display_editor.display_changed.connect(self._on_display_changed)
        outer.addWidget(self.display_editor)

        self.add_display_button = QPushButton("+ Add translations (Display)")
        self.add_display_button.setToolTip(
            "Add a language-tagged summary for this section, shown in place "
            "of (or alongside) the individual items below."
        )
        self.add_display_button.clicked.connect(self._on_add_display_clicked)
        outer.addWidget(self.add_display_button)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_container)
        outer.addWidget(self.scroll, stretch=1)

        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._on_add_clicked)
        outer.addWidget(self.add_button)

        self.layout.addWidget(self.content)
        self.layout.setCurrentWidget(self.placeholder)

    def show_section(self, node):
        """node is the Set-level VraTreeNode to display (e.g. the
        'titleSet' node). Called both on section selection and, by the
        caller, after any edit that rebuilds the document tree, with a
        freshly re-fetched node for the same Set."""
        self._current_node = node
        self.header.setText(f"<h2>{friendly_label(node.data.get('tag', ''))}</h2>")
        self.link_media_button.setVisible(node.data.get('tag') == 'relationSet')
        self._rebuild_cards()
        self.layout.setCurrentWidget(self.content)

    def clear(self):
        """A document is loaded, but no section is selected yet."""
        self._current_node = None
        self.placeholder.setText("Select a section on the left to begin.")
        self.layout.setCurrentWidget(self.placeholder)

    def show_no_document(self):
        """Nothing is loaded at all -- the app's true first-run state."""
        self._current_node = None
        self._no_section_message()
        self.layout.setCurrentWidget(self.placeholder)

    def _no_section_message(self):
        self.placeholder.setText(
            "No record is open yet.\n\nClick Open to edit an existing record, "
            "or Create to start a new one."
        )

    def _rebuild_cards(self):
        while self.cards_layout.count() > 1:  # keep the trailing stretch
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        node = self._current_node
        display_node = next((c for c in node.children if c.node_type == 'display'), None)
        display_addable = any(spec.tag == 'display' for spec in node.child_specs)
        if display_node is not None:
            self.display_editor.set_display_data(display_node.data.get('translations', {}))
            self.display_editor.show()
            self.add_display_button.hide()
        else:
            self.display_editor.hide()
            self.add_display_button.setVisible(display_addable)

        item_nodes = [c for c in node.children if c.node_type != 'display']
        for item_node in item_nodes:
            card = self._build_card(item_node)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

        addable = [spec for spec in node.child_specs if spec.tag not in ('display', 'notes')]
        if addable:
            self._add_spec = addable[0]
            label = friendly_label(self._add_spec.tag)
            self.add_button.setText(f"+ Add {label}")
            self.add_button.setToolTip(f"Add another {label} to this section.")
            self.add_button.setEnabled(True)
        else:
            self._add_spec = None
            self.add_button.setEnabled(False)

    def _build_card(self, item_node):
        if item_node.node_type == 'leaf':
            data = item_node.data
            return FieldRow(
                self._doc_controller, item_node.element, data['tag'], data['text'],
                data['has_vocab'], data,
            )
        return self._build_container_card(item_node)

    def _build_container_card(self, item_node):
        """A container item (agent, location, subject, ...) as a titled
        group of its own sub-fields, recursing into any of its own
        sub-containers (e.g. agent > dates > earliestDate/latestDate).
        Driven by the same child_specs the tree already computes."""
        tag = item_node.data.get('tag', '')
        box = QGroupBox(friendly_label(tag))
        outer = QVBoxLayout(box)

        remove_row = QHBoxLayout()
        remove_row.addStretch()
        remove_button = QPushButton(f"Remove this {friendly_label(tag)}")
        remove_button.setToolTip(f"Remove this {friendly_label(tag)} entirely. Undo (Ctrl+Z) brings it back.")
        remove_button.clicked.connect(
            lambda _checked=False, elem=item_node.element: self._doc_controller.remove_element(elem)
        )
        remove_row.addWidget(remove_button)
        outer.addLayout(remove_row)

        type_row = self._build_type_row(item_node)
        if type_row is not None:
            outer.addLayout(type_row)

        self._render_container_fields(item_node, outer)
        return box

    def _build_type_row(self, item_node):
        """A "Type: [dropdown]" row for a container item's own
        controlled-vocabulary "type" attribute (date, location, rights,
        stateEdition, agent's own "dates") -- these are containers, not
        leaves, so unlike a leaf's type (see FieldRow) they don't have
        anywhere else to be edited. None if this item has no type
        attribute, or the strict schema doesn't constrain it."""
        type_choices = item_node.data.get('type_choices') or ()
        if not type_choices:
            return None

        row = QHBoxLayout()
        row.addWidget(QLabel("Type:"))
        combo = QComboBox()
        combo.addItem('', '')  # "type" is optional per the schema
        for value in type_choices:
            combo.addItem(friendly_enum_value(value), value)
        current_type = item_node.data.get('type', '')
        idx = combo.findData(current_type)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.currentIndexChanged.connect(
            lambda _index, c=combo, elem=item_node.element:
            self._doc_controller.update_element_type(elem, c.currentData())
        )
        row.addWidget(combo)
        row.addStretch()
        return row

    def _render_container_fields(self, item_node, layout):
        """Adds one FieldRow per existing leaf sub-field, or a nested
        QGroupBox per sub-container, into `layout`, then a row of
        "+ <sub-field>" buttons for whatever schema-valid children
        aren't at their cardinality limit yet (covers both "never
        added" and "unbounded, can add another" -- e.g. an agent can
        have more than one name/role)."""
        for child in item_node.children:
            if child.node_type == 'display':
                continue
            if child.node_type == 'leaf':
                data = child.data
                row = FieldRow(
                    self._doc_controller, child.element, data['tag'], data['text'],
                    data['has_vocab'], data,
                )
                layout.addWidget(row)
            else:
                sub_tag = child.data.get('tag', '')
                sub_box = QGroupBox(friendly_label(sub_tag))
                sub_layout = QVBoxLayout(sub_box)
                sub_type_row = self._build_type_row(child)
                if sub_type_row is not None:
                    sub_layout.addLayout(sub_type_row)
                self._render_container_fields(child, sub_layout)
                layout.addWidget(sub_box)

        self._add_child_buttons(item_node, layout)

    def _add_child_buttons(self, item_node, layout):
        sibling_order = [spec.tag for spec in item_node.child_specs]
        addable_specs = []
        for spec in item_node.child_specs:
            if spec.tag in ('display', 'notes'):
                continue
            count = len([c for c in item_node.children if c.data.get('tag') == spec.tag])
            if spec.max_occurs is None or count < spec.max_occurs:
                addable_specs.append(spec)
        if not addable_specs:
            return

        parent_label = friendly_label(item_node.data.get('tag', ''))
        row = QHBoxLayout()
        for spec in addable_specs:
            button = QPushButton(f"+ {friendly_label(spec.tag)}")
            button.setToolTip(f"Add a {friendly_label(spec.tag)} to this {parent_label}.")
            button.clicked.connect(
                lambda _checked=False, elem=item_node.element, tag=spec.tag, order=sibling_order:
                self._doc_controller.insert_child(elem, tag, order)
            )
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

    def _on_remove_section_clicked(self):
        if self._current_node is None:
            return
        self._doc_controller.remove_element(self._current_node.element)

    def _on_link_media_clicked(self):
        media_dir = load_locations().get('media')
        if media_dir is None:
            QMessageBox.warning(self, "Missing location", "No 'media' folder is configured in vra-config.ini.")
            return

        # Unrestricted -- the source file can be anywhere on disk, not just
        # the ingest folder, which is only used as a starting point if it
        # exists (a cataloguer usually does have new files sitting there).
        ingest_dir = load_locations().get('ingest')
        start_dir = str(ingest_dir) if ingest_dir and ingest_dir.exists() else str(Path.home())
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select Media File", start_dir, _MEDIA_FILE_NAME_FILTER,
        )
        if not path_str:
            return
        source_path = Path(path_str)

        new_name, ok = QInputDialog.getText(
            self, "Save into media folder as", "Filename:", text=source_path.name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if any(sep in new_name for sep in ('/', '\\')):
            QMessageBox.warning(self, "Invalid name", "The filename can't contain '/' or '\\'.")
            return
        if (media_dir / new_name).exists():
            QMessageBox.warning(
                self, "File already exists",
                f'"{new_name}" already exists in the media folder. Pick a different name and try again.',
            )
            return

        self._doc_controller.link_media_file(source_path, dest_name=new_name)

    def _on_add_clicked(self):
        if self._current_node is None or self._add_spec is None:
            return
        sibling_order = [spec.tag for spec in self._current_node.child_specs]
        self._doc_controller.insert_child(self._current_node.element, self._add_spec.tag, sibling_order)

    def _on_display_changed(self, translations: dict):
        if self._current_node is None:
            return
        self._doc_controller.set_current_element(self._current_node.element)
        self._doc_controller.update_display_data(translations)

    def _on_add_display_clicked(self):
        if self._current_node is None:
            return
        # Defensive: display's maxOccurs is 1, so this must not run if one
        # already exists, even though the button itself is only ever
        # visible when it doesn't.
        if any(c.node_type == 'display' for c in self._current_node.children):
            return
        sibling_order = [spec.tag for spec in self._current_node.child_specs]
        self._doc_controller.insert_child(self._current_node.element, 'display', sibling_order)
