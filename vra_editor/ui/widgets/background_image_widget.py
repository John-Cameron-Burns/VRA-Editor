import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "images"


def random_background_image() -> Optional[Path]:
    """One of the bundled JPEGs, chosen once and reused everywhere that
    wants the same background for a given app session (so toggling
    Advanced View doesn't swap the picture underneath you). None if the
    images folder has no JPEGs to pick from."""
    candidates = sorted(IMAGES_DIR.glob("*.jpg")) + sorted(IMAGES_DIR.glob("*.JPG"))
    return random.choice(candidates) if candidates else None


class BackgroundImageWidget(QWidget):
    """A QWidget that paints a background image scaled to fill (cropped,
    not stretched) and centered behind its normal contents -- the same
    treatment FormContainerPanel already uses for its placeholder state,
    factored out so panels with real content on top of it (a list, a
    tree) can use it too.
    """

    # Keeps the image inset from the widget's own edges on every side,
    # so it reads as sitting behind the panel's content rather than
    # bleeding edge-to-edge into the splitter divider next to it.
    _MARGIN = 10

    def __init__(self, image_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._background = QPixmap(str(image_path)) if image_path and image_path.exists() else QPixmap()
        # Extra clearance above the base margin -- for a subclass that
        # puts a title label directly on this widget (SectionListPanel's
        # "Sections" heading) with no opaque backing of its own, _MARGIN
        # alone isn't enough to keep the image from showing through
        # right behind/around that text. See set_top_inset().
        self._top_inset = 0

    def set_top_inset(self, pixels: int):
        """Push the image's top edge down by this many extra pixels
        (on top of _MARGIN), so it clears a header row that sits
        directly on this widget instead of inside its own opaque box."""
        self._top_inset = max(pixels, 0)
        self.update()

    def paintEvent(self, event):
        if not self._background.isNull():
            painter = QPainter(self)
            target_rect = self.rect().adjusted(
                self._MARGIN, self._MARGIN + self._top_inset, -self._MARGIN, -self._MARGIN
            )
            if target_rect.width() > 0 and target_rect.height() > 0:
                # Clip to the inset rect -- KeepAspectRatioByExpanding
                # overfills one dimension by design (that's how it crops
                # rather than letterboxes), and without a clip that
                # overfill would bleed straight back out to the widget's
                # real edge, undoing the margin on that side.
                painter.setClipRect(target_rect)
                scaled = self._background.scaled(
                    target_rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
                y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        super().paintEvent(event)
