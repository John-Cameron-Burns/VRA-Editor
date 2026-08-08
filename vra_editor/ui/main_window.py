from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QHBoxLayout, QPushButton, QStackedLayout, QSizePolicy, \
    QLabel

from vra_editor.controllers.document_controller import DocumentController
from vra_editor.ui.panels.form_panel.form_container import FormContainerPanel
from vra_editor.ui.panels.tree_panel.tree_widget import VraTreePanel
# application imports
from vra_editor.ui.panels.xml_preview.code_editor import XmlPreviewPanel


class ModeBar(QWidget):
    def __init__(self, variants: dict[str, list[str]], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # preserve first-seen order across all variants
        ordered_names = []
        for names in variants.values():
            for name in names:
                if name not in ordered_names:
                    ordered_names.append(name)

        self.buttons = {name: QPushButton(name) for name in ordered_names}
        for btn in self.buttons.values():
            layout.addWidget(btn)
        layout.addStretch()

        self.variants = variants
        self.current_mode = None

    def set_mode(self, mode: str):
        visible = set(self.variants[mode])
        for name, btn in self.buttons.items():
            btn.setVisible(name in visible)
        self.current_mode = mode

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRA Core 4 XML Editor")
        self.resize(1100, 650)

        self.doc_controller = DocumentController()
        self.mode_stack = None  # set of top mennu buttons
        self.tree_panel = None  # Show the elements  tree
        self.form_panel = None
        self.xml_preview_panel = None  # shows the current XML
        self.status_bar = None  # defines the lower (status)
        self.labels = None  # the status bar fields
        self.buttons = None
        self.initialise_layout()

    def initialise_layout(self):
        # vertical layout
        # 1.  Top Bar(s)
        top_bar = QWidget()
        top_bar.setFixedHeight(40)  # Fixed height for the bar
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(5, 5, 5, 5)

        base_buttons = ['Home', 'Open', 'Create', 'Review', ]
        # Todo ... put this somewhere more central
        variants = dict(
            initial=base_buttons + ['Settings', 'About'],
            edit=base_buttons + ['Save', 'Submit', 'Cancel', 'About'],
            review=base_buttons + ['Approve', 'Reject', 'Cancel', 'About'],
            settings=base_buttons + ['Autofill', 'Import', 'Save', 'Cancel', 'About']
        )
        # Create a control for each distinct button
        _ = set()
        for button_names in variants.values():
            _ |= set(button_names)

        self.buttons: dict[str, QPushButton] = dict([(k, QPushButton(k)) for k in _])
        # Ok, now we have a button, now populate all the mode_stack views

        self.mode_stack = QStackedLayout()
        self.mode_stack.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(self.mode_stack)  # Add the button bar to the layout
        # Now we have a different set of buttons for each "mode"
        for mode, buttons in variants.items():
            mode_button_set = QWidget()
            mode_layout = QHBoxLayout(mode_button_set)
            mode_layout.setContentsMargins(0, 0, 0, 0)
            for button_name in buttons:
                self.buttons: dict[str, QPushButton]
                mode_layout.addWidget(self.buttons[button_name])
            mode_layout.addStretch()
            self.mode_stack.addWidget(mode_button_set)

        # Create the Stacked Layout
        self.mode_stack = QStackedLayout()
        self.mode_stack.setContentsMargins(0, 0, 0, 0)

        #   main layout using QSplitter
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        self.tree_panel = VraTreePanel()
        self.form_panel = FormContainerPanel()
        self.xml_preview_panel = XmlPreviewPanel()

        splitter.addWidget(self.tree_panel)
        splitter.addWidget(self.form_panel)
        splitter.addWidget(self.xml_preview_panel)
        splitter.setSizes([250, 425, 425])
        self.create_status_bar()

        self.tree_panel.element_selected.connect(self.form_panel.show_editor)
        self.form_panel.agent_data_changed.connect(self.doc_controller.update_agent_data)
        self.doc_controller.xml_updated.connect(self.xml_preview_panel.update_xml_text)

        #self._wire_connections()
        self.xml_preview_panel.update_xml_text(self.doc_controller.get_initial_xml())

    def create_status_bar(self):
        # bottom,(status ) bar
        self.status_bar = QWidget()
        self.status_bar.setFixedHeight(30)
        self.status_bar.setStyleSheet("background-color: #f0f0f0; border-top: 1px solid #ccc;")

        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(15)  # Space between fields

        # Helper to create a styled label
        def create_status_label(name, initial_text=""):
            lbl = QLabel(f"<b>{name}:</b> {initial_text}")
            lbl.setMinimumWidth(100)  # Ensure minimum width for short fields
            return lbl

        # Define Fields
        status_items = ['User', 'File', 'Mode', 'Archive']
        self.labels = dict([(lbl,create_status_label(lbl, '<none>')) for lbl in status_items])
        for label in self.labels.values():
            status_layout.addWidget(label)
        # Allow 'File' to expand and fill extra space
        self.labels['File'].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Add a permanent separator style (optional, using a simple line or spacer)
        # Here we just rely on spacing, but you can add QFrame(VLine) between items if needed.

