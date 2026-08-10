from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox

from vra_editor.core.friendly_labels import FIELD_LABELS, friendly_label, friendly_enum_value
from vra_editor.ui.dialogs.vocabulary_search_dialog import VocabularySearchDialog
from vra_editor.ui.widgets.auto_grow_text_edit import AutoGrowTextEdit

# Every vraAttributes member currently exposed in this row; kept as a list
# (not named fields) so adding another one later (dataDate, source, rules,
# ...) is extending this list and FIELD_LABELS, not redesigning the widget.
# lang is xml:lang -- VRA Core's real mechanism for multi-language content:
# a second <title>/<description>/... element with a different lang, not
# multiple languages crammed into one element's text.
_VOCAB_LINK_ATTRS = ('lang', 'vocab', 'refid', 'href')


class FieldRow(QWidget):
    """One compact, self-contained editor for a single VRA Core leaf
    element, used inside a section's list of item cards where many of
    these may be on screen at once -- unlike ElementEditorPanel, which
    owns the whole center pane for one element at a time.

    Owns a direct reference to `doc_controller` and the lxml `element`
    it edits, rather than emitting a signal for a parent to relay --
    with a dynamic, rebuilt-on-every-structural-change list of rows,
    that's simpler than managing per-row signal connections. Every
    write goes through doc_controller.set_current_element() first, so
    undo coalescing and XML-preview highlighting work exactly as they
    do for the tree/single-element view.
    """

    def __init__(self, doc_controller, element, tag: str, text: str, has_vocab: bool,
                 attributes: dict, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller
        self.element = element
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 6)

        main_row = QHBoxLayout()
        main_row.setSpacing(8)
        label = QLabel(friendly_label(tag))
        label.setMinimumWidth(110)
        main_row.addWidget(label)

        self.type_combo = None
        type_choices = attributes.get('type_choices') or ()
        if type_choices:
            self.type_combo = QComboBox()
            self.type_combo.addItem('', '')  # "type" is optional per the schema
            for value in type_choices:
                self.type_combo.addItem(friendly_enum_value(value), value)
            current_type = attributes.get('type', '')
            idx = self.type_combo.findData(current_type)
            self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.type_combo.setToolTip(f"What kind of {friendly_label(tag).lower()} this is.")
            self.type_combo.currentIndexChanged.connect(self._on_changed)
            main_row.addWidget(self.type_combo)

        self.text_input = AutoGrowTextEdit(min_height=46, max_height=240)
        self.text_input.setPlainText(text)
        self.text_input.textChanged.connect(self._on_changed)
        main_row.addWidget(self.text_input, stretch=1)

        remove_button = QPushButton("✕")
        remove_button.setFixedSize(28, 28)
        remove_button.setToolTip(f"Remove this {friendly_label(tag)}")
        remove_button.clicked.connect(self._on_remove_clicked)
        main_row.addWidget(remove_button, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addLayout(main_row)

        self._attr_inputs = {}
        if has_vocab:
            attr_row = QHBoxLayout()
            attr_row.addSpacing(110)
            for attr_name in _VOCAB_LINK_ATTRS:
                edit = QLineEdit(attributes.get(attr_name, ''))
                edit.setPlaceholderText(FIELD_LABELS.get(attr_name, attr_name))
                if attr_name == 'lang':
                    edit.setFixedWidth(50)  # holds a short ISO 639 code, not a value like the others
                    edit.setToolTip("Language of this text (ISO 639 code, e.g. en, fr, ar)")
                edit.textChanged.connect(self._on_changed)
                attr_row.addWidget(edit)
                self._attr_inputs[attr_name] = edit

            search_button = QPushButton("Search authority...")
            search_button.setToolTip(
                "Look this term up in a controlled vocabulary (VIAF, Getty, GNS, "
                "Library of Congress) and fill in Linked to/Record ID/Link from the result."
            )
            search_button.clicked.connect(self._on_search_clicked)
            attr_row.addWidget(search_button)
            outer.addLayout(attr_row)

    def _on_changed(self):
        if self._loading:
            return
        self._doc_controller.set_current_element(self.element)
        vocab = self._attr_inputs.get('vocab')
        refid = self._attr_inputs.get('refid')
        href = self._attr_inputs.get('href')
        lang = self._attr_inputs.get('lang')
        self._doc_controller.update_element_data(
            self.text_input.toPlainText(),
            vocab.text() if vocab else '',
            refid.text() if refid else '',
            href.text() if href else '',
            lang.text() if lang else '',
            self.type_combo.currentData() if self.type_combo else '',
        )

    def _on_remove_clicked(self):
        self._doc_controller.remove_element(self.element)

    def _on_search_clicked(self):
        dlg = VocabularySearchDialog(initial_query=self.text_input.toPlainText(), parent=self)
        if not dlg.exec() or dlg.selected_result is None:
            return
        result = dlg.selected_result
        self._loading = True
        self.text_input.setPlainText(result.label)
        if 'vocab' in self._attr_inputs:
            self._attr_inputs['vocab'].setText(result.vocab)
        if 'refid' in self._attr_inputs:
            self._attr_inputs['refid'].setText(result.refid)
        if 'href' in self._attr_inputs:
            self._attr_inputs['href'].setText(result.href)
        self._loading = False
        self._on_changed()  # one atomic write with the final combined state
