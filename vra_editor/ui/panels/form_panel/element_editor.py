from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel, QPushButton, QComboBox

from vra_editor.core.friendly_labels import FIELD_LABELS, friendly_label, friendly_enum_value
from vra_editor.ui.dialogs.vocabulary_search_dialog import VocabularySearchDialog
from vra_editor.ui.widgets.auto_grow_text_edit import AutoGrowTextEdit


class ElementEditorPanel(QWidget):
    """Generic form widget for any VRA Core leaf element -- title, name,
    role, technique, subject/term, and roughly twenty others -- rather
    than one hand-written editor per tag. Elements that carry
    vocab/refid/href (nearly all of them; see vra_structure.has_vocab)
    get an authority-vocabulary search button that fills in all four
    fields from a VIAF/AAT/TGN/ULAN/GNS lookup.
    """

    element_changed = Signal(str, str, str, str, str, str)  # text, vocab, refid, href, lang, type

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._original = ('', '', '', '', '', '')  # (text, vocab, refid, href, lang, type) as loaded, for Cancel

        layout = QFormLayout(self)

        self.tag_label = QLabel()
        layout.addRow(self.tag_label)

        self.text_input = AutoGrowTextEdit(min_height=80, max_height=400)
        self.text_input.textChanged.connect(self._on_field_changed)
        layout.addRow("Text:", self.text_input)

        self.type_label = QLabel("Type:")
        self.type_combo = QComboBox()
        self.type_combo.currentIndexChanged.connect(self._on_field_changed)
        layout.addRow(self.type_label, self.type_combo)

        self.lang_label = QLabel(f"{FIELD_LABELS['lang']}:")
        self.lang_input = QLineEdit()
        self.lang_input.setPlaceholderText("ISO 639 code, e.g. en, fr, ar")
        self.lang_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.lang_label, self.lang_input)

        self.vocab_label = QLabel(f"{FIELD_LABELS['vocab']}:")
        self.vocab_input = QLineEdit()
        self.vocab_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.vocab_label, self.vocab_input)

        self.refid_label = QLabel(f"{FIELD_LABELS['refid']}:")
        self.refid_input = QLineEdit()
        self.refid_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.refid_label, self.refid_input)

        self.href_label = QLabel(f"{FIELD_LABELS['href']}:")
        self.href_input = QLineEdit()
        self.href_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.href_label, self.href_input)

        self.search_button = QPushButton("Search authority vocabulary...")
        self.search_button.setToolTip(
            "Look this term up in a controlled vocabulary (VIAF, Getty, GNS, "
            "Library of Congress) and fill in Text/Linked to/Record ID/Link from the result."
        )
        self.search_button.clicked.connect(self._on_search_clicked)
        layout.addRow(self.search_button)

        self.cancel_button = QPushButton("Cancel edit")
        self.cancel_button.setToolTip("Revert this element back to its value before you started editing it.")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addRow(self.cancel_button)

        self._extra_attr_widgets = (
            self.lang_label, self.lang_input,
            self.vocab_label, self.vocab_input,
            self.refid_label, self.refid_input,
            self.href_label, self.href_input,
            self.search_button,
        )

    def _on_field_changed(self):
        if self._loading:
            return
        self.element_changed.emit(
            self.text_input.toPlainText(), self.vocab_input.text(),
            self.refid_input.text(), self.href_input.text(), self.lang_input.text(),
            self.type_combo.currentData() or '',
        )

    def set_element_data(self, tag: str, text: str, has_vocab: bool, vocab: str, refid: str, href: str,
                          lang: str = '', type_choices: tuple = (), type_value: str = ''):
        self._loading = True
        self.tag_label.setText(f"<b>{friendly_label(tag)}</b>")
        self.text_input.setPlainText(text)
        self.vocab_input.setText(vocab)
        self.refid_input.setText(refid)
        self.href_input.setText(href)
        self.lang_input.setText(lang)

        # Rebuilt every time, not just shown/hidden -- unlike vocab/refid/
        # href/lang, which fields exist doesn't change, but which *values*
        # are valid for "type" does, per the specific tag being edited.
        self.type_combo.clear()
        self.type_combo.addItem('', '')
        for value in type_choices:
            self.type_combo.addItem(friendly_enum_value(value), value)
        idx = self.type_combo.findData(type_value)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_label.setVisible(bool(type_choices))
        self.type_combo.setVisible(bool(type_choices))

        for widget in self._extra_attr_widgets:
            widget.setVisible(has_vocab)
        self._loading = False
        self._original = (text, vocab, refid, href, lang, type_value)

    def _on_cancel_clicked(self):
        text, vocab, refid, href, lang, type_value = self._original
        self.text_input.setPlainText(text)
        self.vocab_input.setText(vocab)
        self.refid_input.setText(refid)
        self.href_input.setText(href)
        self.lang_input.setText(lang)
        idx = self.type_combo.findData(type_value)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_search_clicked(self):
        dlg = VocabularySearchDialog(initial_query=self.text_input.toPlainText(), parent=self)
        if dlg.exec() and dlg.selected_result is not None:
            result = dlg.selected_result
            self.text_input.setPlainText(result.label)
            self.vocab_input.setText(result.vocab)
            self.refid_input.setText(result.refid)
            self.href_input.setText(result.href)
