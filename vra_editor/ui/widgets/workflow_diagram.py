import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

# Same palette as ModeStrip's edit/review banners and the Submit/Approve
# buttons (main_window.py), so a stage here reads as the same state a
# user sees once a record is actually open. Ingest and Released aren't
# app modes, so they get a neutral gray instead.
_STAGES = [
    ("Ingest", "#e8e8e8", "#444444"),
    ("Draft", "#DCEEFB", "#0B4C7C"),
    ("Review", "#FDECC8", "#7A4E00"),
    ("Approved", "#DCEEDD", "#1F5239"),
    ("Released", "#f0f0f0", "#666666"),
]

_LOOP_COLOR = "#B3261E"  # matches REJECT_BUTTON_STYLE -- this is the reject path


class WorkflowDiagramWidget(QWidget):
    """A static picture of how a record moves through the app: Ingest ->
    Draft -> Review -> Approved -> Released.

    Shown on the home screen (see SectionFormPanel.show_no_document) so
    a new user can see the whole lifecycle before opening anything.
    Review can also bounce a record back to Draft with notes attached
    (see core/review_notes.py) -- drawn as a separate curved arrow so it
    doesn't get mistaken for a second forward path. Released has no
    button anywhere in this app (see config.LOCATION_KEYS / the Settings
    dialog) -- a scholar moves a record there by hand once it's ready to
    publish, so it's drawn dashed and captioned accordingly.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        boxes = self._stage_boxes()
        for rect, (label, fill, fg) in zip(boxes, _STAGES):
            self._draw_stage(painter, rect, label, fill, fg)

        arrow_pen = QPen(QColor("#666666"))
        arrow_pen.setWidth(2)
        for i in range(len(boxes) - 1):
            start = QPointF(boxes[i].right(), boxes[i].center().y())
            end = QPointF(boxes[i + 1].left(), boxes[i + 1].center().y())
            self._draw_arrow(painter, arrow_pen, start, end)

        self._draw_return_loop(painter, boxes[1], boxes[2])
        self._draw_released_caption(painter, boxes[-1])

        painter.end()
        super().paintEvent(event)

    def _stage_boxes(self) -> list[QRectF]:
        n = len(_STAGES)
        margin_x, top, box_w_min, gap, box_h = 30, 40, 90, 24, 56
        available = max(self.width() - 2 * margin_x - gap * (n - 1), box_w_min * n)
        box_w = available / n
        return [
            QRectF(margin_x + i * (box_w + gap), top, box_w, box_h)
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

    def _draw_return_loop(self, painter: QPainter, draft_rect: QRectF, review_rect: QRectF):
        """Review -> Draft: a record sent back for revision, carrying
        the reviewer's notes with it."""
        loop_y = draft_rect.bottom() + 46
        path = QPainterPath()
        path.moveTo(review_rect.center().x(), review_rect.bottom())
        path.cubicTo(
            review_rect.center().x(), loop_y,
            draft_rect.center().x(), loop_y,
            draft_rect.center().x(), draft_rect.bottom(),
        )
        pen = QPen(QColor(_LOOP_COLOR))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self._draw_arrowhead(
            painter, pen, QPointF(draft_rect.center().x(), draft_rect.bottom()),
            QPointF(draft_rect.center().x(), loop_y),
        )

        font = painter.font()
        font.setBold(False)
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor(_LOOP_COLOR))
        label_rect = QRectF(
            draft_rect.center().x(), loop_y - 9,
            review_rect.center().x() - draft_rect.center().x(), 18,
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "notes back to editor")

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
