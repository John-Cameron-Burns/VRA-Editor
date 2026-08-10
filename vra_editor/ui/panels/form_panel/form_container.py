from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget, QStackedLayout, QLabel

from vra_editor.core.friendly_labels import friendly_label
from vra_editor.ui.panels.form_panel.display_editor import DisplayEditorPanel
from vra_editor.ui.panels.form_panel.element_editor import ElementEditorPanel

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "images"
BACKGROUND_IMAGE_PATH = IMAGES_DIR / "background-1.jpg"


class FormContainerPanel(QWidget):
    """Panel container displaying the active form based on selection."""

    element_data_changed = Signal(str, str, str, str, str)  # text, vocab, refid, href, lang
    display_data_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._background = QPixmap(str(BACKGROUND_IMAGE_PATH)) if BACKGROUND_IMAGE_PATH.exists() else QPixmap()
        self.layout = QStackedLayout(self)

        self.placeholder = QLabel("-Select  an element from the structure tree on the left.")
        self.layout.addWidget(self.placeholder)

        self.container_info = QLabel()
        self.container_info.setWordWrap(True)
        self.layout.addWidget(self.container_info)

        self.element_editor = ElementEditorPanel()
        self.element_editor.element_changed.connect(self.element_data_changed.emit)
        self.layout.addWidget(self.element_editor)

        self.display_editor = DisplayEditorPanel()
        self.display_editor.display_changed.connect(self.display_data_changed.emit)
        self.layout.addWidget(self.display_editor)

    def paintEvent(self, event):
        if not self._background.isNull():
            painter = QPainter(self)
            scaled = self._background.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        super().paintEvent(event)

    def show_editor(self, node_type: str, data: dict):
        if node_type == "leaf":
            self.element_editor.set_element_data(
                data.get("tag", ""), data.get("text", ""), data.get("has_vocab", False),
                data.get("vocab", ""), data.get("refid", ""), data.get("href", ""),
                data.get("lang", ""),
            )
            self.layout.setCurrentWidget(self.element_editor)
        elif node_type == "display":
            self.display_editor.set_display_data(data.get("translations", {}))
            self.layout.setCurrentWidget(self.display_editor)
        elif node_type in ("record", "set", "container"):
            label = friendly_label(data.get("tag", node_type))
            self.container_info.setText(
                f"<b>{label}</b><br><br>Right-click “{label}” in the list on "
                f"the left to add or remove items here."
            )
            self.layout.setCurrentWidget(self.container_info)
        else:
            self.layout.setCurrentWidget(self.placeholder)
