from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMessageBox

from vra_editor.core import media_metadata


class MediaPreviewPanel(QWidget):
    """Shows the image file linked to the current record (see
    DocumentController.find_linked_media_path/link_media_file), plus a
    button to write key record fields into the file as IPTC metadata.
    Shown in both Edit and Review mode, toggled alongside Show XML/
    Review Notes.

    Owns a direct reference to doc_controller, matching FieldRow/
    ReviewNotesPanel's style, rather than a signal round-trip.
    """

    def __init__(self, doc_controller, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller
        self._media_path = None

        outer = QVBoxLayout(self)

        header = QLabel("<b>Media Preview</b>")
        outer.addWidget(header)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        self.image_label.setMinimumHeight(200)
        self.image_label.setWordWrap(True)
        outer.addWidget(self.image_label, stretch=1)

        self.path_label = QLabel()
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.path_label.setWordWrap(True)
        outer.addWidget(self.path_label)

        self.inject_iptc_button = QPushButton("Inject IPTC into file...")
        self.inject_iptc_button.setToolTip(
            "Writes this record's Title, Description, People, Rights, "
            "Subjects, and creation Date into the linked file's own IPTC "
            "metadata, so the file stays useful outside this app too. "
            "Modifies the actual file on disk."
        )
        self.inject_iptc_button.clicked.connect(self._on_inject_iptc_clicked)
        outer.addWidget(self.inject_iptc_button)

    def refresh(self):
        self._media_path = self._doc_controller.find_linked_media_path()
        if self._media_path is None:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No media file linked yet.\n\nUse \"+ Link Media File\" in the Relations section.")
            self.path_label.setText("")
            self.inject_iptc_button.setEnabled(False)
            return

        self.path_label.setText(str(self._media_path))
        self.inject_iptc_button.setEnabled(True)
        try:
            qimage = media_metadata.load_preview_image(self._media_path)
        except Exception as exc:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(f"Couldn't preview this file:\n{exc}")
            return

        pixmap = QPixmap.fromImage(qimage)
        scaled = pixmap.scaled(
            self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setText("")
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._media_path is not None:
            self.refresh()  # re-scale the pixmap to the new size

    def _on_inject_iptc_clicked(self):
        if self._media_path is None:
            return
        fields = self._doc_controller.build_iptc_fields()
        if not fields:
            QMessageBox.information(
                self, "Nothing to write",
                "None of the mapped fields (Title, Description, People, Rights, "
                "Subjects, creation Date) have a value yet in this record.",
            )
            return

        summary = "\n".join(f"  {k.split('.')[-1]}: {v}" for k, v in fields.items())
        confirmed = QMessageBox.question(
            self, "Write IPTC metadata?",
            f"This will modify the actual file:\n{self._media_path}\n\nFields to write:\n{summary}",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            self._doc_controller.inject_iptc(self._media_path, fields)
        except Exception as exc:
            QMessageBox.warning(self, "Write failed", f"Could not write IPTC metadata:\n{exc}")
            return
        QMessageBox.information(self, "Done", "IPTC metadata written.")
