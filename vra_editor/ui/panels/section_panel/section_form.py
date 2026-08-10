from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QGroupBox, QStackedLayout,
)

from vra_editor.core.friendly_labels import friendly_label
from vra_editor.ui.panels.form_panel.display_editor import DisplayEditorPanel
from vra_editor.ui.panels.section_panel.field_row import FieldRow


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
            self.add_button.setText(f"+ Add {friendly_label(self._add_spec.tag)}")
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
        remove_button.clicked.connect(
            lambda _checked=False, elem=item_node.element: self._doc_controller.remove_element(elem)
        )
        remove_row.addWidget(remove_button)
        outer.addLayout(remove_row)

        self._render_container_fields(item_node, outer)
        return box

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

        row = QHBoxLayout()
        for spec in addable_specs:
            button = QPushButton(f"+ {friendly_label(spec.tag)}")
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
