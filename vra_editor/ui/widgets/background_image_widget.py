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

    def __init__(self, image_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._background = QPixmap(str(image_path)) if image_path and image_path.exists() else QPixmap()

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
