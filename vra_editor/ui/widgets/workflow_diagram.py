import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

# Labelled with the actual folder names from config.LOCATION_KEYS / the
# Settings dialog (_LOCATION_LABELS there), not friendlier synonyms, so
# the diagram and Settings always agree on what to call each stage.
# Colors reuse ModeStrip's edit/review banners and the Submit/Approve
# buttons (main_window.py), so a stage here still reads as the same
# state a user sees once a record is actually open. Ingest and Released
# aren't app modes, so they get a neutral gray instead.
_STAGES = [
    ("Ingest", "#e8e8e8", "#444444"),
    ("Edit", "#DCEEFB", "#0B4C7C"),
    ("Pending", "#FDECC8", "#7A4E00"),
    ("Reviewed", "#DCEEDD", "#1F5239"),
    ("Released", "#f0f0f0", "#666666"),
]

# One entry per forward arrow (boxes[i] -> boxes[i+1]): the mode-bar
# button that actually performs that move (see BUTTON_TOOLTIPS and
# DocumentController.submit_file/approve_file in main_window.py /
# document_controller.py). None where no button does it -- Reviewed ->
# Released has no button anywhere in the app; see _draw_released_caption.
_ARROW_BUTTONS = ["Import", "Submit", "Approve", None]

_LOOP_COLOR = "#B3261E"  # matches REJECT_BUTTON_STYLE -- this is the Reject path
_SETTINGS_COLOR = "#666666"  # matches SECONDARY_BUTTON_STYLE -- Settings lives in that muted admin cluster


class WorkflowDiagramWidget(QWidget):
    """A static, top-to-bottom picture of how a record moves through the
    app: Ingest -> Edit -> Pending -> Reviewed -> Released, with each
    arrow labelled with the mode-bar button that actually triggers it.

    Shown on the home screen (see SectionFormPanel.show_no_document) so
    a new user can see the whole lifecycle before opening anything.
    Pending can also bounce a record back to Edit via Reject, carrying
    the reviewer's notes with it (see core/review_notes.py) -- drawn as
    a curved arrow bulging out to the left of the boxes so it doesn't
    get mistaken for the forward flow running down the middle. Released
    has no button anywhere in this app (see config.LOCATION_KEYS / the
    Settings dialog) -- a scholar moves a record there by hand once it's
    ready to publish, so it's drawn dashed and captioned accordingly
    instead of getting a button label.

    None of these boxes are real folders until Settings points them at
    some -- see _draw_settings_note -- which is why that note sits above
    Ingest rather than on any one arrow: it's a prerequisite for the
    whole diagram, not one step in it.
    """

    _BOX_WIDTH = 200
    _BOX_HEIGHT = 48
    _BOX_GAP = 42
    _TOP_MARGIN = 46  # extra room above Ingest for the Settings note
    _LOOP_REACH = 90  # how far left of the boxes the return-loop curve bulges
    _RIGHT_ROOM = 90  # space reserved right of the boxes for arrow-button chips

    def __init__(self, parent=None):
        super().__init__(parent)
        n = len(_STAGES)
        total_height = self._TOP_MARGIN + n * self._BOX_HEIGHT + (n - 1) * self._BOX_GAP + 46
        total_width = self._LOOP_REACH + 10 + self._BOX_WIDTH + self._RIGHT_ROOM
        self.setMinimumSize(total_width, total_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        boxes = self._stage_boxes()
        self._draw_settings_note(painter, boxes[0])
        for rect, (label, fill, fg) in zip(boxes, _STAGES):
            self._draw_stage(painter, rect, label, fill, fg)

        arrow_pen = QPen(QColor("#666666"))
        arrow_pen.setWidth(2)
        for i in range(len(boxes) - 1):
            start = QPointF(boxes[i].center().x(), boxes[i].bottom())
            end = QPointF(boxes[i + 1].center().x(), boxes[i + 1].top())
            self._draw_arrow(painter, arrow_pen, start, end)
            button = _ARROW_BUTTONS[i]
            if button:
                mid_y = (start.y() + end.y()) / 2
                self._draw_button_chip(
                    painter, QPointF(boxes[i].center().x() + 16, mid_y), button, "#444444", align="left",
                )

        self._draw_return_loop(painter, boxes[1], boxes[2])
        self._draw_released_caption(painter, boxes[-1])

        painter.end()
        super().paintEvent(event)

    def _stage_boxes(self) -> list[QRectF]:
        n = len(_STAGES)
        min_x = self._LOOP_REACH + 10
        x = max((self.width() - self._BOX_WIDTH) / 2, min_x)
        return [
            QRectF(
                x, self._TOP_MARGIN + i * (self._BOX_HEIGHT + self._BOX_GAP),
                self._BOX_WIDTH, self._BOX_HEIGHT,
            )
            for i in range(n)
        ]

    @staticmethod
    def _draw_stage(painter: QPainter, rect: QRectF, label: str, fill: str, fg: str):
        pen = QPen(QColor(fg))
        pen.setWidth(2)
        if label == "Released":
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawRoundedRect(rect, 8, 8)

        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(fg))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    @staticmethod
    def _draw_button_chip(painter: QPainter, anchor: QPointF, text: str, color: str, align: str) -> QRectF:
        """A small pill mimicking a mode-bar button, so the arrow reads
        as "this button does this move" rather than a bare description.
        anchor is the chip's left edge if align == "left", its right
        edge if align == "right", vertically centered on anchor.y().
        Returns the chip's rect, so a caller can position a caption
        relative to it."""
        font = painter.font()
        font.setBold(True)
        font.setItalic(False)
        font.setPointSize(max(font.pointSize() - 1, 7))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        pad_x, pad_y = 7, 3
        w = metrics.horizontalAdvance(text) + 2 * pad_x
        h = metrics.height() + 2 * pad_y
        x = anchor.x() if align == "left" else anchor.x() - w
        rect = QRectF(x, anchor.y() - h / 2, w, h)

        pen = QPen(QColor(color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        return rect

    def _draw_settings_note(self, painter: QPainter, ingest_rect: QRectF):
        """Where Ingest/Edit/Pending/... actually point on disk is
        configured once, under Settings -- not something any button in
        this diagram touches. Sits above Ingest as a heads-up before the
        flow itself, rather than on any single arrow."""
        chip_text = "Settings"
        caption = "sets up these folders first"
        y = ingest_rect.top() - 22

        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize() - 1, 7))
        painter.setFont(font)
        chip_w = painter.fontMetrics().horizontalAdvance(chip_text) + 14

        font.setBold(False)
        font.setItalic(True)
        painter.setFont(font)
        caption_w = painter.fontMetrics().horizontalAdvance(caption)

        gap = 6
        start_x = ingest_rect.center().x() - (chip_w + gap + caption_w) / 2
        chip_rect = self._draw_button_chip(
            painter, QPointF(start_x, y), chip_text, _SETTINGS_COLOR, align="left",
        )

        painter.setPen(QColor(_SETTINGS_COLOR))
        caption_rect = QRectF(chip_rect.right() + gap, y - 9, caption_w + 4, 18)
        painter.drawText(caption_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, caption)

    def _draw_return_loop(self, painter: QPainter, edit_rect: QRectF, pending_rect: QRectF):
        """Pending -> Edit: Reject sends a record back for revision,
        carrying the reviewer's notes with it."""
        loop_x = edit_rect.left() - self._LOOP_REACH
        path = QPainterPath()
        path.moveTo(pending_rect.left(), pending_rect.center().y())
        path.cubicTo(
            loop_x, pending_rect.center().y(),
            loop_x, edit_rect.center().y(),
            edit_rect.left(), edit_rect.center().y(),
        )
        pen = QPen(QColor(_LOOP_COLOR))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self._draw_arrowhead(
            painter, pen, QPointF(edit_rect.left(), edit_rect.center().y()),
            QPointF(loop_x, edit_rect.center().y()),
        )

        mid_y = (edit_rect.bottom() + pending_rect.top()) / 2
        self._draw_button_chip(painter, QPointF(loop_x - 8, mid_y - 9), "Reject", _LOOP_COLOR, align="right")

        font = painter.font()
        font.setBold(False)
        font.setItalic(True)
        font.setPointSize(max(font.pointSize() - 1, 7))
        painter.setFont(font)
        painter.setPen(QColor(_LOOP_COLOR))
        caption_rect = QRectF(4, mid_y + 3, loop_x - 12, 18)
        painter.drawText(
            caption_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "(with notes)",
        )

    @staticmethod
    def _draw_released_caption(painter: QPainter, released_rect: QRectF):
        font = painter.font()
        font.setBold(False)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor("#888888"))
        caption_rect = QRectF(
            released_rect.x() - 25, released_rect.bottom() + 8,
            released_rect.width() + 50, 36,
        )
        painter.drawText(
            caption_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "unmanaged — moved by hand, outside this app",
        )

    @classmethod
    def _draw_arrow(cls, painter: QPainter, pen: QPen, start: QPointF, end: QPointF):
        painter.setPen(pen)
        painter.drawLine(start, end)
        cls._draw_arrowhead(painter, pen, end, start)

    @staticmethod
    def _draw_arrowhead(painter: QPainter, pen: QPen, tip: QPointF, tail: QPointF):
        angle = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
        size = 8
        spread = math.pi / 6
        p1 = QPointF(tip.x() - size * math.cos(angle - spread), tip.y() - size * math.sin(angle - spread))
        p2 = QPointF(tip.x() - size * math.cos(angle + spread), tip.y() - size * math.sin(angle + spread))
        path = QPainterPath()
        path.moveTo(tip)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(pen.color()))
        painter.drawPath(path)
        painter.setPen(pen)
