import os

# Define the complete project structure and file contents
PROJECT_FILES = {
    "requirements.txt": """PySide6>=6.5.0
lxml>=4.9.0
""",
    "ARCHITECTURE.md": """# VRA Core 4 Editor Architecture

This application strictly separates domain logic from user interface elements to ensure easy long-term maintenance.

## Folder Overview

- `main.py`: Entry point for the application.
- `vra_editor/core/`: **Pure Python logic.** Handles XML parsing (via lxml), dataclasses, and XSD schema validation. Contains zero PySide6/Qt code.
- `vra_editor/controllers/`: Application state management, document workflows, and event handling.
- `vra_editor/ui/`: PySide6 graphical components.
  - `main_window.py`: Layout assembly container using QSplitter.
  - `panels/tree_panel/`: Hierarchy navigation tree.
  - `panels/form_panel/`: Individual modular forms for editing specific VRA tags.
  - `panels/xml_preview/`: Syntax/raw text preview.
- `vra_editor/resources/`: Stylesheets and static assets.

## How to Add a New Element Form
1. Add a new editor widget in `vra_editor/ui/panels/form_panel/`.
2. Register the widget inside `FormContainerPanel` in `form_container.py`.
3. Connect signal updates to `DocumentController`.
""",
    "main.py": """import sys
from PySide6.QtWidgets import QApplication
from vra_editor.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
""",
    "vra_editor/__init__.py": '"""VRA Core 4 Editor Package."""\n',
    "vra_editor/core/__init__.py": '"""Core pure-python domain logic."""\n',
    "vra_editor/core/models.py": """from dataclasses import dataclass, field
from typing import List

@dataclass
class VraAgent:
    name: str = ""
    role: str = ""

@dataclass
class VraTitle:
    title: str = ""
    type_: str = ""

@dataclass
class VraWork:
    id: str = "w1"
    titles: List[VraTitle] = field(default_factory=list)
    agents: List[VraAgent] = field(default_factory=list)
""",
    "vra_editor/core/xml_parser.py": """from lxml import etree

VRA_NS = "http://www.vraweb.org/vracore4.htm"
NSMAP = {None: VRA_NS}

class VraXmlParser:
    \"\"\"Pure Python XML generator and parser.\"\"\"

    @staticmethod
    def create_sample_xml() -> str:
        root = etree.Element(f"{{{VRA_NS}}}vra", nsmap=NSMAP)
        work = etree.SubElement(root, f"{{{VRA_NS}}}work", id="w_101")
        
        # Agent Set
        agent_set = etree.SubElement(work, f"{{{VRA_NS}}}agentSet")
        agent = etree.SubElement(agent_set, f"{{{VRA_NS}}}agent")
        name = etree.SubElement(agent, f"{{{VRA_NS}}}name")
        name.text = "Vincent van Gogh"
        role = etree.SubElement(agent, f"{{{VRA_NS}}}role")
        role.text = "Artist"

        # Title Set
        title_set = etree.SubElement(work, f"{{{VRA_NS}}}titleSet")
        title = etree.SubElement(title_set, f"{{{VRA_NS}}}title")
        title.text = "Starry Night"

        return etree.tostring(root, pretty_print=True, encoding="utf-8").decode("utf-8")
""",
    "vra_editor/core/schema_validator.py": """from lxml import etree

class SchemaValidator:
    \"\"\"Validates XML against VRA Core 4 XSD definitions.\"\"\"

    def __init__(self, xsd_path: str = None):
        self.xsd_path = xsd_path

    def validate(self, xml_bytes: bytes) -> tuple[bool, str]:
        if not self.xsd_path:
            return True, "Validation skipped (No XSD file set)"
        try:
            schema_doc = etree.parse(self.xsd_path)
            schema = etree.XMLSchema(schema_doc)
            doc = etree.fromstring(xml_bytes)
            schema.assertValid(doc)
            return True, "XML Valid"
        except Exception as e:
            return False, str(e)
""",
    "vra_editor/controllers/__init__.py": '"""Controller state package."""\n',
    "vra_editor/controllers/document_controller.py": """from PySide6.QtCore import QObject, Signal
from vra_editor.core.xml_parser import VraXmlParser

class DocumentController(QObject):
    \"\"\"Coordinates application state between models and UI updates.\"\"\"

    xml_updated = Signal(str)

    def __init__(self):
        super().__init__()
        self.current_xml = VraXmlParser.create_sample_xml()

    def get_initial_xml(self) -> str:
        return self.current_xml

    def update_agent_data(self, name: str, role: str):
        # Update logic: updates raw XML string representation
        self.current_xml = self.current_xml.replace(
            "Vincent van Gogh", name if name else "Vincent van Gogh"
        )
        self.xml_updated.emit(self.current_xml)
""",
    "vra_editor/ui/__init__.py": '"""UI Components Package."""\n',
    "vra_editor/ui/components/__init__.py": '"""Reusable Widgets."""\n',
    "vra_editor/ui/dialogs/__init__.py": '"""Modal Dialogs."""\n',
    "vra_editor/ui/panels/__init__.py": '"""Sub-package for UI Panels."""\n',
    "vra_editor/ui/panels/tree_panel/__init__.py": '"""Tree Navigation Sub-package."""\n',
    "vra_editor/ui/panels/tree_panel/tree_widget.py": """from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem

class VraTreePanel(QWidget):
    \"\"\"Left Panel: XML Hierarchy Tree.\"\"\"

    element_selected = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("VRA Core 4 Structure")
        layout.addWidget(self.tree)

        self._populate_tree()
        self.tree.itemClicked.connect(self._on_item_clicked)

    def _populate_tree(self):
        root = QTreeWidgetItem(self.tree, ["Work (id: w_101)"])
        root.setData(0, 100, "work")

        agent_node = QTreeWidgetItem(root, ["Agent: Vincent van Gogh"])
        agent_node.setData(0, 100, "agent")
        agent_node.setData(0, 101, {"name": "Vincent van Gogh", "role": "Artist"})

        title_node = QTreeWidgetItem(root, ["Title: Starry Night"])
        title_node.setData(0, 100, "title")
        title_node.setData(0, 101, {"title": "Starry Night", "type": "Repository"})

        self.tree.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, 100)
        node_data = item.data(0, 101) or {}
        if node_type:
            self.element_selected.emit(node_type, node_data)
""",
    "vra_editor/ui/panels/form_panel/__init__.py": '"""Form Editors Sub-package."""\n',
    "vra_editor/ui/panels/form_panel/agent_editor.py": """from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel

class AgentEditorPanel(QWidget):
    \"\"\"Form widget for VRA Agent elements.\"\"\"

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
""",
    "vra_editor/ui/panels/form_panel/title_editor.py": """from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit, QLabel

class TitleEditorPanel(QWidget):
    \"\"\"Form widget for VRA Title elements.\"\"\"

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
""",
    "vra_editor/ui/panels/form_panel/form_container.py": """from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QStackedLayout, QLabel

from vra_editor.ui.panels.form_panel.agent_editor import AgentEditorPanel
from vra_editor.ui.panels.form_panel.title_editor import TitleEditorPanel

class FormContainerPanel(QWidget):
    \"\"\"Panel container displaying the active form based on selection.\"\"\"

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
""",
    "vra_editor/ui/panels/xml_preview/__init__.py": '"""XML Preview Sub-package."""\n',
    "vra_editor/ui/panels/xml_preview/code_editor.py": """from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel

class XmlPreviewPanel(QWidget):
    \"\"\"Right Panel: Raw XML Preview.\"\"\"

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
""",
    "vra_editor/ui/main_window.py": """from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QSplitter

from vra_editor.controllers.document_controller import DocumentController
from vra_editor.ui.panels.tree_panel.tree_widget import VraTreePanel
from vra_editor.ui.panels.form_panel.form_container import FormContainerPanel
from vra_editor.ui.panels.xml_preview.code_editor import XmlPreviewPanel

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRA Core 4 XML Editor")
        self.resize(1100, 650)

        self.doc_controller = DocumentController()

        # Simple main layout using QSplitter
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        self.tree_panel = VraTreePanel()
        self.form_panel = FormContainerPanel()
        self.xml_preview_panel = XmlPreviewPanel()

        splitter.addWidget(self.tree_panel)
        splitter.addWidget(self.form_panel)
        splitter.addWidget(self.xml_preview_panel)
        splitter.setSizes([250, 425, 425])

        self._wire_connections()
        self.xml_preview_panel.update_xml_text(self.doc_controller.get_initial_xml())

    def _wire_connections(self):
        self.tree_panel.element_selected.connect(self.form_panel.show_editor)
        self.form_panel.agent_data_changed.connect(self.doc_controller.update_agent_data)
        self.doc_controller.xml_updated.connect(self.xml_preview_panel.update_xml_text)
""",
    "vra_editor/resources/styles.qss": """QMainWindow {
    background-color: #f8f9fa;
}
QTreeWidget, QTextEdit, QLineEdit {
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 4px;
}
""",
}


def build_project():
    """Generates the directory tree and writes all source files."""
    for relative_path, content in PROJECT_FILES.items():
        dir_name = os.path.dirname(relative_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(relative_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Created: {relative_path}")


if __name__ == "__main__":
    build_project()
    print("\nProject structure generated successfully!")