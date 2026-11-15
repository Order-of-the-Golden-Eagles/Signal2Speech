"""Small drawn icons for the tiles (#174). Vector only: no image files, fonts, or network."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def draw_icon(p: QPainter, kind: str, box: QRectF, colour: str) -> None:
    """Draw `kind` (satellite, chart, speech, check, cross) inside `box`. Unknown kinds draw nothing."""
    s = min(box.width(), box.height())
    x, y = box.x() + (box.width() - s) / 2, box.y() + (box.height() - s) / 2
    pen = QPen(QColor(colour), max(2.0, s * 0.09), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "satellite":                      # a planet with an orbit and a satellite
        p.drawEllipse(QRectF(x + s * .28, y + s * .28, s * .44, s * .44))
        p.save()
        p.translate(x + s / 2, y + s / 2)
        p.rotate(-25)
        p.drawEllipse(QRectF(-s * .48, -s * .18, s * .96, s * .36))
        p.restore()
        p.setBrush(QColor(colour))
        p.drawEllipse(QPointF(x + s * .84, y + s * .3), s * .07, s * .07)
    elif kind == "chart":                        # three rising bars on a baseline
        base = y + s * .88
        p.drawLine(QPointF(x + s * .08, base), QPointF(x + s * .92, base))
        for i, h in enumerate((.3, .5, .72)):
            bx = x + s * (.18 + i * .25)
            p.drawLine(QPointF(bx, base - s * .06), QPointF(bx, base - s * h))
    elif kind == "speech":                       # a speech bubble with a tail
        path = QPainterPath()
        path.addRoundedRect(QRectF(x + s * .08, y + s * .12, s * .84, s * .58), s * .16, s * .16)
        p.drawPath(path)
        p.drawLine(QPointF(x + s * .3, y + s * .7), QPointF(x + s * .22, y + s * .9))
        p.drawLine(QPointF(x + s * .22, y + s * .9), QPointF(x + s * .46, y + s * .7))
    elif kind == "check":
        p.drawLine(QPointF(x + s * .14, y + s * .52), QPointF(x + s * .4, y + s * .78))
        p.drawLine(QPointF(x + s * .4, y + s * .78), QPointF(x + s * .88, y + s * .24))
    elif kind == "cross":
        p.drawLine(QPointF(x + s * .2, y + s * .2), QPointF(x + s * .8, y + s * .8))
        p.drawLine(QPointF(x + s * .8, y + s * .2), QPointF(x + s * .2, y + s * .8))
    p.restore()
