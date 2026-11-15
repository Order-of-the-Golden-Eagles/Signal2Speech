"""Short fades for things that appear: the preview and the revealed map.

A fade is a cover the colour of the background, laid over the widget and thinned to nothing. No
graphics effects are involved, so it is safe over custom-painted widgets and never nests.

Never used on the choice tiles. Their flashes must stay instant and exact: the P300 response is
timed against them.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

#: Off in tests and for --screenshot, where a picture taken mid-fade would be wrong.
ENABLED = os.environ.get("QT_QPA_PLATFORM", "") != "offscreen"
DURATION_MS = 240


class FadeCover(QWidget):
    """A background-coloured sheet over ``parent`` whose opacity runs from 1 to 0."""

    def __init__(self, parent: QWidget, colour: str):
        super().__init__(parent)
        self.colour = QColor(colour)
        self.alpha = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self.hide)

    def _step(self, value) -> None:
        self.alpha = float(value)
        self.update()

    def play(self, ms: int = DURATION_MS) -> None:
        self._anim.stop()
        self.setGeometry(self.parentWidget().rect())
        self.alpha = 1.0
        self.show()
        self.raise_()
        self._anim.setDuration(ms)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        if self.alpha <= 0.0:
            return
        p = QPainter(self)
        c = QColor(self.colour)
        c.setAlphaF(max(0.0, min(1.0, self.alpha)))
        p.fillRect(self.rect(), c)
        p.end()


def fade_in(widget: QWidget, colour: str, ms: int = DURATION_MS) -> None:
    """Fade ``widget``'s content in from ``colour`` (its background). Does nothing when fades are
    off or the widget isn't on screen yet."""
    if not ENABLED or not widget.isVisible():
        return
    cover = getattr(widget, "_fade_cover", None)
    if cover is None:
        cover = FadeCover(widget, colour)
        widget._fade_cover = cover
    cover.play(ms)
