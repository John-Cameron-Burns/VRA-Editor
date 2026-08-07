from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel

class TitleEditorPanel(QWidget):
    """Form widget for VRA Title elements."""

    title_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        header = QLabel("<b>Title Element Editor</b>")
        layout.addRow(header)

        self.title_input = QLineEdit()
        self.type_input = QLineEdit()

        layout.addRow("Title Text:", self.title_input)
        layout.addRow("Title Type:", self.type_input)

        self.title_input.textChanged.connect(self._on_field_changed)
        self.type_input.textChanged.connect(self._on_field_changed)

    def _on_field_changed(self):
        self.title_changed.emit(self.title_input.text(), self.type_input.text())

    def set_title_data(self, title: str, type_: str):
        self.title_input.blockSignals(True)
        self.type_input.blockSignals(True)
        self.title_input.setText(title)
        self.type_input.setText(type_)
        self.title_input.blockSignals(False)
        self.type_input.blockSignals(False)
