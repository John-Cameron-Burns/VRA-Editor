from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
)


class DisplayEditorPanel(QWidget):
    """Form widget for a VRA <display>/<notes> element's per-language
    translations (see vra_editor.core.display_i18n for the encoding
    scheme). Shows one row per language -- a short lang-code box and a
    text field -- with add/remove controls.
    """

    display_changed = Signal(dict)  # emits the full {lang: text} map on any edit

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[QLineEdit, QLineEdit, QWidget]] = []
        self._loading = False

        outer = QVBoxLayout(self)

        header = QLabel("<b>Display Editor</b>")
        outer.addWidget(header)

        self._rows_layout = QVBoxLayout()
        outer.addLayout(self._rows_layout)

        add_row = QHBoxLayout()
        add_btn = QPushButton("+ Add language")
        add_btn.clicked.connect(lambda: self._add_row('', '', emit_changed=True))
        add_row.addWidget(add_btn)
        add_row.addStretch()
        outer.addLayout(add_row)
        outer.addStretch()

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, lang: str, text: str, emit_changed: bool):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        lang_edit = QLineEdit(lang)
        lang_edit.setPlaceholderText("lang")
        lang_edit.setFixedWidth(50)

        text_edit = QLineEdit(text)
        text_edit.setPlaceholderText("translated text")

        remove_btn = QPushButton("✕")
        remove_btn.setFixedWidth(24)

        row_layout.addWidget(lang_edit)
        row_layout.addWidget(text_edit)
        row_layout.addWidget(remove_btn)

        self._rows_layout.addWidget(row_widget)
        entry = (lang_edit, text_edit, row_widget)
        self._rows.append(entry)

        def _remove():
            self._rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self._rows.remove(entry)
            self._emit_changed()

        remove_btn.clicked.connect(_remove)
        lang_edit.textChanged.connect(lambda _text: self._emit_changed())
        text_edit.textChanged.connect(lambda _text: self._emit_changed())

        if emit_changed:
            self._emit_changed()

    def _clear_rows(self):
        for lang_edit, text_edit, row_widget in self._rows:
            self._rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
        self._rows.clear()

    def _emit_changed(self):
        if self._loading:
            return
        self.display_changed.emit(self.get_translations())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_display_data(self, translations: dict):
        self._loading = True
        self._clear_rows()
        for lang, text in translations.items():
            self._add_row(lang, text, emit_changed=False)
        if not translations:
            self._add_row('en', '', emit_changed=False)
        self._loading = False

    def get_translations(self) -> dict:
        result = {}
        for lang_edit, text_edit, _ in self._rows:
            lang = lang_edit.text().strip()
            text = text_edit.text().strip()
            if lang and text:
                result[lang] = text
        return result
