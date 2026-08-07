from PySide6.QtCore import Qt
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
