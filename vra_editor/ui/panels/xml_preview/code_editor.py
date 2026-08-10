from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel


class XmlPreviewPanel(QWidget):
    """Right Panel: Raw XML Preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        label = QLabel("<b>XML Preview</b>")
        layout.addWidget(label)

        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setStyleSheet("font-family: Consolas, Monospace, Courier;")
        layout.addWidget(self.editor)

    def update_xml_text(self, xml_text: str):
        self.editor.setPlainText(xml_text)

    def highlight_span(self, start: int, end: int):
        """Highlights xml_text[start:end] (character offsets), replacing
        any previous highlight, and scrolls it into view. Uses an
        ExtraSelection rather than the editor's own text selection, so
        the highlight doesn't compete visually with (or get cleared by)
        normal cursor/selection interaction."""
        highlight_cursor = QTextCursor(self.editor.document())
        highlight_cursor.setPosition(start)
        highlight_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff3a0"))

        selection = QTextEdit.ExtraSelection()
        selection.cursor = highlight_cursor
        selection.format = fmt
        self.editor.setExtraSelections([selection])

        scroll_cursor = QTextCursor(self.editor.document())
        scroll_cursor.setPosition(start)
        self.editor.setTextCursor(scroll_cursor)

    def clear_highlight(self):
        self.editor.setExtraSelections([])
