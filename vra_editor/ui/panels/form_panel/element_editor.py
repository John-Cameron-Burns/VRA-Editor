from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel, QPushButton, QTextEdit

from vra_editor.ui.dialogs.vocabulary_search_dialog import VocabularySearchDialog


class ElementEditorPanel(QWidget):
    """Generic form widget for any VRA Core leaf element -- title, name,
    role, technique, subject/term, and roughly twenty others -- rather
    than one hand-written editor per tag. Elements that carry
    vocab/refid/href (nearly all of them; see vra_structure.has_vocab)
    get an authority-vocabulary search button that fills in all four
    fields from a VIAF/AAT/TGN/ULAN/GNS lookup.
    """

    element_changed = Signal(str, str, str, str)  # text, vocab, refid, href

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._original = ('', '', '', '')  # (text, vocab, refid, href) as loaded, for Cancel

        layout = QFormLayout(self)

        self.tag_label = QLabel()
        layout.addRow(self.tag_label)

        self.text_input = QTextEdit()
        self.text_input.setFixedHeight(80)
        self.text_input.textChanged.connect(self._on_field_changed)
        layout.addRow("Text:", self.text_input)

        self.vocab_label = QLabel("Vocabulary:")
        self.vocab_input = QLineEdit()
        self.vocab_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.vocab_label, self.vocab_input)

        self.refid_label = QLabel("Ref ID:")
        self.refid_input = QLineEdit()
        self.refid_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.refid_label, self.refid_input)

        self.href_label = QLabel("URL:")
        self.href_input = QLineEdit()
        self.href_input.textChanged.connect(self._on_field_changed)
        layout.addRow(self.href_label, self.href_input)

        self.search_button = QPushButton("Search authority vocabulary...")
        self.search_button.clicked.connect(self._on_search_clicked)
        layout.addRow(self.search_button)

        self.cancel_button = QPushButton("Cancel edit")
        self.cancel_button.setToolTip("Revert this element back to its value before you started editing it.")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addRow(self.cancel_button)

        self._vocab_widgets = (
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
            self.refid_input.text(), self.href_input.text(),
        )

    def set_element_data(self, tag: str, text: str, has_vocab: bool, vocab: str, refid: str, href: str):
        self._loading = True
        self.tag_label.setText(f"<b>{tag}</b>")
        self.text_input.setPlainText(text)
        self.vocab_input.setText(vocab)
        self.refid_input.setText(refid)
        self.href_input.setText(href)
        for widget in self._vocab_widgets:
            widget.setVisible(has_vocab)
        self._loading = False
        self._original = (text, vocab, refid, href)

    def _on_cancel_clicked(self):
        text, vocab, refid, href = self._original
        self.text_input.setPlainText(text)
        self.vocab_input.setText(vocab)
        self.refid_input.setText(refid)
        self.href_input.setText(href)

    def _on_search_clicked(self):
        dlg = VocabularySearchDialog(initial_query=self.text_input.toPlainText(), parent=self)
        if dlg.exec() and dlg.selected_result is not None:
            result = dlg.selected_result
            self.text_input.setPlainText(result.label)
            self.vocab_input.setText(result.vocab)
            self.refid_input.setText(result.refid)
            self.href_input.setText(result.href)
