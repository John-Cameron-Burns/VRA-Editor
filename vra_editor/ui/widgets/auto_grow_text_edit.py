from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextEdit


class AutoGrowTextEdit(QTextEdit):
    """A QTextEdit that grows to fit its content, up to max_height --
    beyond that it scrolls internally instead of continuing to grow --
    rather than staying a fixed, cramped size regardless of how much
    text it actually holds. Used anywhere a leaf element's text (title,
    description, notes, ...) is edited, since some of those run to
    several sentences and a couple of fixed lines was never enough for
    them.
    """

    def __init__(self, min_height: int = 46, max_height: int = 320, parent=None):
        super().__init__(parent)
        self._min_height = min_height
        self._max_height = max_height
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self._adjust_height)
        self._adjust_height()

    def _adjust_height(self):
        ideal = int(self.document().size().height()) + (self.frameWidth() * 2) + 6
        new_height = max(self._min_height, min(self._max_height, ideal))
        if new_height != self.height():
            self.setFixedHeight(new_height)
        needs_scroll = ideal > self._max_height
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if needs_scroll else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Word-wrapped document height depends on the widget's current
        # width, which isn't final until it's actually been laid out --
        # re-check once it is, not just on text changes.
        self._adjust_height()
