from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QLabel, QDialogButtonBox,
)

from vra_editor.core.authority_lookup import (
    VOCABULARIES, VOCABULARY_LABELS, AuthorityResult, AuthorityLookupError, search,
)


class VocabularySearchDialog(QDialog):
    """Modal controlled-vocabulary lookup: pick VIAF/AAT/TGN/ULAN/GNS,
    search, and select a result. The caller reads `selected_result` after
    exec() returns Accepted.

    Usage:
        dlg = VocabularySearchDialog(initial_query="van gogh", parent=self)
        if dlg.exec() and dlg.selected_result is not None:
            result = dlg.selected_result  # AuthorityResult
    """

    def __init__(self, initial_query: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search authority vocabulary")
        self.setModal(True)
        self.resize(520, 420)

        self.selected_result: Optional[AuthorityResult] = None

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.vocab_combo = QComboBox()
        self.vocab_combo.addItems(VOCABULARIES)
        self.vocab_combo.currentTextChanged.connect(self._on_vocab_changed)
        search_row.addWidget(self.vocab_combo)

        self.query_input = QLineEdit(initial_query)
        self.query_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self.query_input, stretch=1)

        self.search_button = QPushButton("Search")
        self.search_button.setToolTip("Search the selected vocabulary for this term.")
        self.search_button.clicked.connect(self._on_search)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        self.vocab_description = QLabel(VOCABULARY_LABELS.get(self.vocab_combo.currentText(), ""))
        self.vocab_description.setWordWrap(True)
        self.vocab_description.setStyleSheet("color: #666;")
        layout.addWidget(self.vocab_description)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.results_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if initial_query:
            self._on_search()

    def _on_vocab_changed(self, vocab: str):
        self.vocab_description.setText(VOCABULARY_LABELS.get(vocab, ""))

    def _on_search(self):
        vocab = self.vocab_combo.currentText()
        query = self.query_input.text().strip()
        if not query:
            return

        self.results_list.clear()
        self.status_label.setText("Searching...")
        self.search_button.setEnabled(False)
        self.repaint()  # show "Searching..." before the blocking network call below

        try:
            results = search(vocab, query)
        except AuthorityLookupError as e:
            self.status_label.setText(str(e))
            self.search_button.setEnabled(True)
            return

        self.search_button.setEnabled(True)
        if not results:
            self.status_label.setText("No results.")
            return

        self.status_label.setText(f"{len(results)} result(s)")
        for result in results:
            item = QListWidgetItem(f"{result.label}  [{result.vocab} {result.refid}]")
            item.setData(Qt.UserRole, result)
            self.results_list.addItem(item)

    def _accept_selection(self, *_ignored):
        item = self.results_list.currentItem()
        if item is None:
            return
        self.selected_result = item.data(Qt.UserRole)
        self.accept()
