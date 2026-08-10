from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QCheckBox,
)

from vra_editor.ui.widgets.auto_grow_text_edit import AutoGrowTextEdit


class ReviewNotesPanel(QWidget):
    """A reviewer's todo list for the editor -- see core/review_notes.py
    for where this actually lives (an XML comment, not document
    content). Shown in both Edit and Review mode: reviewers add notes,
    editors see and resolve them.

    Owns a direct reference to doc_controller and calls its
    add/resolve/remove methods immediately, refreshing its own display
    right after -- the same direct-call style FieldRow uses, rather
    than a signal round-trip, since this panel is the only thing that
    needs to react to its own edits.
    """

    def __init__(self, doc_controller, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller

        outer = QVBoxLayout(self)

        header = QLabel("<b>Review Notes</b>")
        outer.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # A plain QWidget defaults to the app's own grey chrome background
        # (the Window palette role), not white like the Sections list (a
        # QListWidget, white by default) -- left alone, an empty notes
        # list is a big grey blank box with only a small white input
        # strip at the bottom, easy to mistake for a disabled panel.
        self.scroll.setStyleSheet("QScrollArea { background-color: white; border: 1px solid #ccc; }")
        self.rows_container = QWidget()
        self.rows_container.setStyleSheet("background-color: white;")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.addStretch()
        self.scroll.setWidget(self.rows_container)
        outer.addWidget(self.scroll, stretch=1)

        add_row = QHBoxLayout()
        self.new_note_input = AutoGrowTextEdit(min_height=60, max_height=160)
        self.new_note_input.setPlaceholderText("Add a note for the editor...")
        add_row.addWidget(self.new_note_input, stretch=1)
        add_button = QPushButton("Add")
        add_button.setToolTip("Add this note for the editor to see.")
        add_button.clicked.connect(self._on_add_clicked)
        add_row.addWidget(add_button, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addLayout(add_row)

    def refresh(self):
        while self.rows_layout.count() > 1:  # keep the trailing stretch
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, note in enumerate(self._doc_controller.get_review_notes()):
            row = self._build_row(index, note)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)

    def has_unresolved_notes(self) -> bool:
        return any(not note.get('resolved') for note in self._doc_controller.get_review_notes())

    def _build_row(self, index: int, note: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 6)

        checkbox = QCheckBox()
        checkbox.setChecked(bool(note.get('resolved')))
        checkbox.setToolTip("Mark resolved")
        checkbox.toggled.connect(lambda checked, i=index: self._on_resolved_toggled(i, checked))
        layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_label = QLabel(note.get('text', ''))
        text_label.setWordWrap(True)
        if note.get('resolved'):
            text_label.setStyleSheet("color: #888; text-decoration: line-through;")
        text_col.addWidget(text_label)

        meta = QLabel(f"{note.get('author', '') or 'Unknown'} — {note.get('date', '')}")
        meta.setStyleSheet("color: #888; font-size: 11px;")
        text_col.addWidget(meta)
        layout.addLayout(text_col, stretch=1)

        remove_button = QPushButton("✕")
        remove_button.setFixedSize(24, 24)
        remove_button.setToolTip("Remove this note")
        remove_button.clicked.connect(lambda _checked=False, i=index: self._on_remove_clicked(i))
        layout.addWidget(remove_button, alignment=Qt.AlignmentFlag.AlignTop)

        return row

    def _on_add_clicked(self):
        text = self.new_note_input.toPlainText().strip()
        if not text:
            return
        self._doc_controller.add_review_note(text)
        self.new_note_input.clear()
        self.refresh()

    def _on_resolved_toggled(self, index: int, checked: bool):
        self._doc_controller.set_review_note_resolved(index, checked)
        self.refresh()

    def _on_remove_clicked(self, index: int):
        self._doc_controller.remove_review_note(index)
        self.refresh()
