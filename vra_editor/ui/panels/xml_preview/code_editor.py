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
