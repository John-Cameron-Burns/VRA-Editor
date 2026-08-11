from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextBrowser, QDialogButtonBox,
)

MANUAL_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "user_manual.md"


class HelpDialog(QDialog):
    """The user manual (resources/user_manual.md), rendered read-only
    with a simple find-in-page box. Non-modal -- unlike Settings/About,
    this is meant to stay open on the side while you work through
    whatever it's explaining, not block the rest of the app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Manual")
        self.resize(700, 700)

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Find:"))
        self.search_input = QLineEdit()
        self.search_input.returnPressed.connect(self._on_find)
        search_row.addWidget(self.search_input, stretch=1)
        find_button = QPushButton("Find")
        find_button.clicked.connect(self._on_find)
        search_row.addWidget(find_button)
        layout.addLayout(search_row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMarkdown(self._load_manual_text())
        layout.addWidget(self.browser, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        layout.addWidget(buttons)

    @staticmethod
    def _load_manual_text() -> str:
        try:
            return MANUAL_PATH.read_text(encoding='utf-8')
        except OSError as exc:
            return f"# User Manual\n\nCouldn't load the manual file:\n\n```\n{exc}\n```"

    def _on_find(self):
        query = self.search_input.text().strip()
        if not query:
            return
        found = self.browser.find(query)
        if found:
            return
        # Not found from the current position -- wrap around once by
        # resetting the cursor to the top of the document and retrying,
        # rather than leaving the user stuck with no feedback at all.
        cursor = self.browser.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.browser.setTextCursor(cursor)
        self.browser.find(query)
