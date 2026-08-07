from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QStackedLayout, QLabel

from vra_editor.ui.panels.form_panel.agent_editor import AgentEditorPanel
from vra_editor.ui.panels.form_panel.title_editor import TitleEditorPanel

class FormContainerPanel(QWidget):
    """Panel container displaying the active form based on selection."""

    agent_data_changed = Signal(str, str)
    title_data_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QStackedLayout(self)

        self.placeholder = QLabel("Select an element from the structure tree on the left.")
        self.layout.addWidget(self.placeholder)

        self.agent_editor = AgentEditorPanel()
        self.agent_editor.agent_changed.connect(self.agent_data_changed.emit)
        self.layout.addWidget(self.agent_editor)

        self.title_editor = TitleEditorPanel()
        self.title_editor.title_changed.connect(self.title_data_changed.emit)
        self.layout.addWidget(self.title_editor)

    def show_editor(self, node_type: str, data: dict):
        if node_type == "agent":
            self.agent_editor.set_agent_data(data.get("name", ""), data.get("role", ""))
            self.layout.setCurrentWidget(self.agent_editor)
        elif node_type == "title":
            self.title_editor.set_title_data(data.get("title", ""), data.get("type", ""))
            self.layout.setCurrentWidget(self.title_editor)
        else:
            self.layout.setCurrentWidget(self.placeholder)
