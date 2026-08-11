from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMessageBox, QSizePolicy,
)

from vra_editor.core import media_metadata

PANEL_HEIGHT = 200


class MediaPreviewPanel(QWidget):
    """Docked band, at the top of the centre pane (see CenterPane),
    showing the image file linked to the current record (see
    DocumentController.find_linked_media_path/link_media_file), with
    buttons to write record fields into the file as IPTC metadata
    (Inject), to re-read dimensions/GPS/date from the file into the
    record (Extract), and to collapse this band to a floating
    thumbnail (Thumbnail -- CenterPane owns what that actually does,
    hence the signal rather than a direct call).

    Owns a direct reference to doc_controller, matching FieldRow/
    ReviewNotesPanel's style, rather than a signal round-trip for
    every action.
    """

    collapse_requested = Signal()

    def __init__(self, doc_controller, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller
        self._media_path = None
        self._pixmap = QPixmap()

        self.setFixedHeight(PANEL_HEIGHT)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setWordWrap(True)
        outer.addWidget(self.image_label, stretch=1)

        button_col = QVBoxLayout()
        button_col.setSpacing(4)

        self.inject_button = QPushButton("Inject")
        self.inject_button.setToolTip(
            "Writes this record's Title, Description, People, Rights, "
            "Subjects, and creation Date into the linked file's own IPTC "
            "metadata, so the file stays useful outside this app too. "
            "Modifies the actual file on disk."
        )
        self.inject_button.clicked.connect(self._on_inject_clicked)
        button_col.addWidget(self.inject_button)

        self.extract_button = QPushButton("Extract")
        self.extract_button.setToolTip(
            "Re-reads this file's dimensions, resolution, and (if present) "
            "GPS position and capture date, refreshing the record's "
            "Measurements/Location/Date sections. Useful if the linked "
            "file was replaced after it was first linked."
        )
        self.extract_button.clicked.connect(self._on_extract_clicked)
        button_col.addWidget(self.extract_button)

        self.thumbnail_button = QPushButton("Thumbnail")
        self.thumbnail_button.setToolTip(
            "Collapse this preview to a small thumbnail so the form below "
            "has more room. Click the thumbnail to bring it back."
        )
        self.thumbnail_button.clicked.connect(lambda: self.collapse_requested.emit())
        button_col.addWidget(self.thumbnail_button)

        button_col.addStretch()
        outer.addLayout(button_col)

    def current_pixmap(self) -> QPixmap:
        """The full (unscaled) linked-image pixmap, or a null QPixmap if
        nothing's linked -- used by CenterPane to build the floating
        thumbnail's icon without re-decoding the file."""
        return self._pixmap

    def refresh(self):
        self._media_path = self._doc_controller.find_linked_media_path()
        if self._media_path is None:
            self._pixmap = QPixmap()
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText('No media file linked yet.\n\nUse "+ Link Media File" in the Relations section.')
            self.image_label.setToolTip("")
            self.inject_button.setEnabled(False)
            self.extract_button.setEnabled(False)
            return

        self.image_label.setToolTip(str(self._media_path))
        self.inject_button.setEnabled(True)
        self.extract_button.setEnabled(True)
        try:
            qimage = media_metadata.load_preview_image(self._media_path)
        except Exception as exc:
            self._pixmap = QPixmap()
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText(f"Couldn't preview this file:\n{exc}")
            return

        self._pixmap = QPixmap.fromImage(qimage)
        self._rescale()

    def _rescale(self):
        if self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(
            self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setText("")
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _on_extract_clicked(self):
        if self._media_path is None:
            return
        if not self._doc_controller.extract_media_metadata():
            QMessageBox.warning(
                self, "Extract failed",
                "Could not re-read metadata from the linked file.",
            )

    def _on_inject_clicked(self):
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
