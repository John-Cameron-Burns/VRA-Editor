from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel

class AgentEditorPanel(QWidget):
    """Form widget for VRA Agent elements."""

    agent_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)

        title = QLabel("<b>Agent Element Editor</b>")
        layout.addRow(title)

        self.name_input = QLineEdit()
        self.role_input = QLineEdit()

        layout.addRow("Agent Name:", self.name_input)
        layout.addRow("Role:", self.role_input)

        self.name_input.textChanged.connect(self._on_field_changed)
        self.role_input.textChanged.connect(self._on_field_changed)

    def _on_field_changed(self):
        self.agent_changed.emit(self.name_input.text(), self.role_input.text())

    def set_agent_data(self, name: str, role: str):
        self.name_input.blockSignals(True)
        self.role_input.blockSignals(True)
        self.name_input.setText(name)
        self.role_input.setText(role)
        self.name_input.blockSignals(False)
        self.role_input.blockSignals(False)
