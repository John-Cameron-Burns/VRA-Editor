from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMessageBox, QSizePolicy,
    QInputDialog,
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
            "metadata (and the creation date into its EXIF capture date "
            "too), so the file stays useful outside this app. Modifies "
            "the actual file on disk."
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

    def _resolve_fuzzy_date(self) -> bool:
        """If the record's creation date is not an exact calendar date,
        asks whether to correct it or skip writing a date at all --
        IPTC/EXIF have no way to represent "circa 1990", and writing it
        verbatim just gets silently dropped by build_iptc_fields/
        build_exif_fields further down. Returns False if the user backs
        out of Inject entirely rather than resolving it."""
        date_text = self._doc_controller.get_creation_date_text()
        if not date_text or media_metadata.parse_vra_date(date_text) is not None:
            return True  # nothing to resolve -- no creation date, or already exact

        box = QMessageBox(
            QMessageBox.Icon.Warning, "Creation date isn't exact",
            f'This record\'s creation date is "{date_text}", which isn\'t a specific '
            f'calendar date -- IPTC/EXIF have no way to store that. Enter an exact '
            f'date, or skip writing a date at all?',
            parent=self,
        )
        enter_button = box.addButton("Enter Exact Date...", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Skip Date", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()

        if clicked is cancel_button:
            return False
        if clicked is not enter_button:
            return True  # "Skip Date" -- leave the record's date as-is; it's simply omitted below

        while True:
            new_date, ok = QInputDialog.getText(
                self, "Enter exact date", "Creation date (YYYY-MM-DD):", text=date_text,
            )
            if not ok:
                return False
            new_date = new_date.strip()
            if media_metadata.parse_vra_date(new_date) is not None:
                self._doc_controller.set_creation_date(new_date)
                return True
            QMessageBox.warning(
                self, "Not a valid date",
                "Enter a date as YYYY-MM-DD, YYYY-MM, or YYYY.",
            )

    def _on_inject_clicked(self):
        if self._media_path is None:
            return
        if not self._resolve_fuzzy_date():
            return

        fields = self._doc_controller.build_iptc_fields()
        if not fields:
            QMessageBox.information(
                self, "Nothing to write",
                "None of the mapped fields (Title, Description, People, Rights, "
                "Subjects, creation Date) have a value yet in this record.",
            )
            return

        exif_fields = self._doc_controller.build_exif_fields()
        summary = "\n".join(f"  {k.split('.')[-1]}: {v}" for k, v in fields.items())
        if exif_fields:
            summary += "\n\nAlso updates the file's own EXIF capture date to match:\n" \
                       + "\n".join(f"  {k.split('.')[-1]}: {v}" for k, v in exif_fields.items())
        confirmed = QMessageBox.question(
            self, "Write metadata into file?",
            f"This will modify the actual file:\n{self._media_path}\n\nFields to write:\n{summary}",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            self._doc_controller.inject_iptc(self._media_path, fields)
        except Exception as exc:
            QMessageBox.warning(self, "Write failed", f"Could not write metadata:\n{exc}")
            return
        QMessageBox.information(self, "Done", "Metadata written.")
