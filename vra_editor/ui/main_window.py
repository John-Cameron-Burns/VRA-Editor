from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QSplitter, QSizePolicy,
)

# application imports
from ..config import config as CONFIG
from vra_editor.controllers.document_controller import DocumentController
from vra_editor.ui.panels.form_panel.form_container import FormContainerPanel
from vra_editor.ui.panels.tree_panel.tree_widget import VraTreePanel
from vra_editor.ui.panels.settings_dialog import SettingsDialog

from vra_editor.ui.panels.xml_preview.code_editor import XmlPreviewPanel
from ..utils import user_name as system_user_name

# Assumes these exist elsewhere in your project, as in the original code:
# from your_app import DocumentController, VraTreePanel, FormContainerPanel, XmlPreviewPanel
#
# NOTE: file_loaded / user_changed / archive_changed below are illustrative --
# swap in whatever signals DocumentController (or other panels) actually emit.


class ModeBar(QWidget):
    """A single row of buttons whose visible subset changes with the app mode.

    Buttons are created once and behave identically regardless of mode;
    only their visibility changes. This avoids duplicating widgets per
    mode and avoids the reparenting bug that comes from sharing widget
    instances across multiple layouts.
    """

    def __init__(self, variants: dict[str, list[str]], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preserve first-seen order across all variants.
        ordered_names = []
        for names in variants.values():
            for name in names:
                if name not in ordered_names:
                    ordered_names.append(name)

        self.buttons: dict[str, QPushButton] = {
            name: QPushButton(name) for name in ordered_names
        }
        for btn in self.buttons.values():
            layout.addWidget(btn)
        layout.addStretch()

        self.variants = variants
        self.current_mode: str | None = None

    def set_mode(self, mode: str):
        visible = set(self.variants[mode])
        for name, btn in self.buttons.items():
            btn.setVisible(name in visible)
        self.current_mode = mode


class StatusBar(QWidget):
    """Owns the status-bar labels and exposes setters for them.

    Callers never touch individual QLabel objects directly -- they call
    set_user(...), set_file(...), etc. This keeps 'who can change the
    status bar' answerable by 'whoever calls these methods', and means
    the labels can be relabelled/restyled here without hunting down
    every call site.
    """

    FIELDS = ['User', 'File', 'Mode', 'Archive']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #f0f0f0; border-top: 1px solid #ccc;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)

        self._labels: dict[str, QLabel] = {}
        for name in self.FIELDS:
            lbl = QLabel(f"<b>{name}:</b> <none>")
            lbl.setMinimumWidth(100)
            self._labels[name] = lbl
            layout.addWidget(lbl)

        self._labels['File'].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _set(self, name: str, value: str):
        self._labels[name].setText(f"<b>{name}:</b> {value}")

    def set_user(self, value: str):
        self._set('User', value)

    def set_file(self, value: str):
        self._set('File', value)

    def set_mode(self, value: str):
        self._set('Mode', value)

    def set_archive(self, value: str):
        self._set('Archive', value)


class MainWindow(QMainWindow):

    # Central place for what's visible in each mode. Extend this if
    # other widgets (not just buttons) need to change with mode --
    # see register_mode_widget / apply_mode below.
    BASE_BUTTONS = ['Home', 'Open', 'Create', 'Review']
    VARIANTS = dict(
        initial=BASE_BUTTONS + ['Settings', 'About'],
        edit=BASE_BUTTONS + ['Save', 'Submit', 'Cancel', 'About'],
        review=BASE_BUTTONS + ['Approve', 'Reject', 'Cancel', 'About'],
        settings=BASE_BUTTONS + ['Autofill', 'Import', 'Save', 'Cancel', 'About'],
    )

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRA Core 4 XML Editor")
        self.resize(1100, 650)

        self.doc_controller = DocumentController()

        self.mode_bar: ModeBar | None = None
        self.tree_panel = None          # Shows the elements tree
        self.form_panel = None
        self.xml_preview_panel = None   # Shows the current XML
        self.status_bar: StatusBar | None = None

        # Registry of any widget (not just mode-bar buttons) that should
        # be shown/hidden per mode. Populate via register_mode_widget().
        self.mode_widgets: dict[str, QWidget] = {}

        self.initialise_layout()
        self.apply_mode('initial')

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def initialise_layout(self):
        top_bar = self._build_top_bar()

        splitter = QSplitter(Qt.Horizontal)
        self.tree_panel = VraTreePanel()
        self.form_panel = FormContainerPanel()
        self.xml_preview_panel = XmlPreviewPanel()
        splitter.addWidget(self.tree_panel)
        splitter.addWidget(self.form_panel)
        splitter.addWidget(self.xml_preview_panel)
        splitter.setSizes([250, 425, 425])

        self.status_bar = StatusBar()

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(top_bar)
        main_layout.addWidget(splitter, stretch=1)
        main_layout.addWidget(self.status_bar)
        self.setCentralWidget(central)

        self.tree_panel.element_selected.connect(self.form_panel.show_editor)
        self.form_panel.agent_data_changed.connect(self.doc_controller.update_agent_data)
        self.doc_controller.xml_updated.connect(self.xml_preview_panel.update_xml_text)

        # Status bar updates as a side effect of other actions: connect
        # each relevant signal straight to the matching setter. No other
        # code needs to know the status bar exists.
        self.doc_controller.file_loaded.connect(self.status_bar.set_file)
        #self.doc_controller.user_changed.connect(self.status_bar.set_user)
        #self.doc_controller.archive_changed.connect(self.status_bar.set_archive)
        # todo -- implement archive stats
        self.status_bar.set_archive('<na>/<na>')
        self.status_bar.set_user(system_user_name())
        # If a signal doesn't map 1:1 onto a setter, connect to a small
        # slot instead, e.g.:
        # self.doc_controller.document_saved.connect(
        #     lambda path: self.status_bar.set_file(f"{path} (saved)")
        # )

        self.xml_preview_panel.update_xml_text(self.doc_controller.get_initial_xml())

    def _build_top_bar(self) -> QWidget:
        top_bar = QWidget()
        top_bar.setFixedHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(5, 5, 5, 5)

        self.mode_bar = ModeBar(self.VARIANTS)
        top_layout.addWidget(self.mode_bar)

        # Register buttons in the shared mode-widget registry too, so
        # apply_mode() can drive both the bar and any other mode-aware
        # widgets from a single call.
        for name, btn in self.mode_bar.buttons.items():
            self.register_mode_widget(name, btn)

        self._connect_button_signals()

        return top_bar

    def _connect_button_signals(self):
        """Wire each button's behaviour exactly once, independent of mode."""
        buttons = self.mode_bar.buttons
        buttons['Home'].clicked.connect(self._on_home)
        buttons['Open'].clicked.connect(self._on_open)
        buttons['Create'].clicked.connect(self._on_create)
        buttons['Review'].clicked.connect(self._on_review)
        buttons['Settings'].clicked.connect(self._on_settings)
        buttons['About'].clicked.connect(self._on_about)
        buttons['Save'].clicked.connect(self._on_save)
        buttons['Submit'].clicked.connect(self._on_submit)
        buttons['Cancel'].clicked.connect(self._on_cancel)
        buttons['Approve'].clicked.connect(self._on_approve)
        buttons['Reject'].clicked.connect(self._on_reject)
        buttons['Autofill'].clicked.connect(self._on_autofill)
        buttons['Import'].clicked.connect(self._on_import)

    # ------------------------------------------------------------------
    # Mode handling
    # ------------------------------------------------------------------

    def register_mode_widget(self, name: str, widget: QWidget):
        """Register any widget (button, panel, label...) that should be
        shown/hidden based on which names appear in self.VARIANTS[mode]."""
        self.mode_widgets[name] = widget

    def apply_mode(self, mode: str):
        visible_names = set(self.VARIANTS[mode])
        for name, widget in self.mode_widgets.items():
            widget.setVisible(name in visible_names)
        self.mode_bar.current_mode = mode
        self.status_bar.set_mode(mode)

    # ------------------------------------------------------------------
    # Button handlers -- implement these; mode-independent by design
    # ------------------------------------------------------------------

    def _on_home(self): ...
    def _on_open(self): ...
    def _on_create(self): self.apply_mode('edit')
    def _on_review(self): self.apply_mode('review')
    def _on_settings(self):
        dlg = SettingsDialog(parent=self)
        dlg.exec()  # modal -- blocks until the user Saves or Cancels

    def _on_about(self): ...
    def _on_save(self): ...
    def _on_submit(self): ...
    def _on_cancel(self): self.apply_mode('initial')
    def _on_approve(self): ...
    def _on_reject(self): ...
    def _on_autofill(self): ...
    def _on_import(self): ...