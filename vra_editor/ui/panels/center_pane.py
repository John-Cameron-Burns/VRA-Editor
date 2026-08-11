from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton

from vra_editor.ui.panels.media_preview_panel import MediaPreviewPanel

THUMBNAIL_SIZE = 50
THUMBNAIL_MARGIN = 10


class CenterPane(QWidget):
    """Wraps the Simple/Advanced form stack together with the linked
    media preview (see MediaPreviewPanel), so the preview persists
    across the two views -- it's about which file the record is
    linked to, not which editor view happens to be showing.

    The preview docks as a fixed-height band above the form by
    default. Its own "Thumbnail" button collapses it to a small
    button floating over the form's top-right corner instead (click
    it again to bring the full preview back) -- for when a
    cataloguer working a dense form wants the vertical space back
    without losing the linked-file context entirely.
    """

    def __init__(self, doc_controller, form_stack: QWidget, parent=None):
        super().__init__(parent)
        self._media_relevant = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.media_panel = MediaPreviewPanel(doc_controller)
        self.media_panel.collapse_requested.connect(self._show_thumbnail)
        self.media_panel.hide()  # hidden until set_media_relevant(True) -- see there
        layout.addWidget(self.media_panel)
        layout.addWidget(form_stack, stretch=1)

        # Deliberately not part of the layout above -- it floats over
        # whatever the layout is currently showing in that corner
        # (positioned by hand in resizeEvent) rather than displacing it.
        self.thumbnail_button = QPushButton(self)
        self.thumbnail_button.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        self.thumbnail_button.setToolTip("Restore the media preview")
        self.thumbnail_button.setStyleSheet(
            "QPushButton { border: 2px solid white; border-radius: 4px; background-color: #ddd; }"
        )
        self.thumbnail_button.clicked.connect(self._show_docked)
        self.thumbnail_button.hide()

    def refresh(self):
        self.media_panel.refresh()
        if not self.media_panel.isVisible():
            self._update_thumbnail_icon()

    def set_media_relevant(self, relevant: bool):
        """Shows/hides the whole media band -- not just its placeholder
        content -- based on whether the open record could ever have a
        linked file. A Collection or Work (or no document at all) can
        never have one, so the band would otherwise just be a
        permanent 200px "No media file linked yet" with nothing to
        link, on every screen including the home screen.

        Always resets to the docked (non-thumbnail) state -- this is
        only called from file_loaded (a genuine new record, not a
        plain edit), so there's no risk of undoing a mid-edit collapse
        the way tying this to document_loaded would (see main_window's
        _on_file_loaded)."""
        self._media_relevant = relevant
        self.thumbnail_button.hide()
        self.media_panel.setVisible(relevant)
        if relevant:
            self.media_panel.refresh()

    def _show_thumbnail(self):
        self.media_panel.hide()
        self._update_thumbnail_icon()
        self.thumbnail_button.show()
        self.thumbnail_button.raise_()
        self._reposition_thumbnail()

    def _show_docked(self):
        self.thumbnail_button.hide()
        self.media_panel.show()
        self.media_panel.refresh()

    def _update_thumbnail_icon(self):
        pixmap = self.media_panel.current_pixmap()
        if pixmap.isNull():
            self.thumbnail_button.setIcon(QIcon())
            self.thumbnail_button.setText("")
            return
        inset = THUMBNAIL_SIZE - 8
        scaled = pixmap.scaled(
            inset, inset, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail_button.setText("")
        self.thumbnail_button.setIcon(QIcon(scaled))
        self.thumbnail_button.setIconSize(scaled.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_thumbnail()

    def _reposition_thumbnail(self):
        x = self.width() - THUMBNAIL_SIZE - THUMBNAIL_MARGIN
        self.thumbnail_button.move(max(0, x), THUMBNAIL_MARGIN)
