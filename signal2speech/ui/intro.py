"""The opening: the two reply cards alone, then they settle into their places on the left.

The cards shown here are stand-ins drawn over the window. The real tiles underneath never move
or change, so nothing about the flashing or its timing is touched. Skipped when fades are off
(tests, ``--screenshot``).
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from PySide6.QtCore import (QEasingCurve, QEventLoop, QParallelAnimationGroup, QPoint,
                            QPropertyAnimation, QRect, QTimer)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import fade
from . import theme as T

HOLD_MS = 800       # the two cards alone
MOVE_MS = 700       # shrinking into place
GROW = 1.55         # how much bigger the cards start


class CardIntro(QWidget):
    """Covers ``root``, shows a large copy of each tile, and moves the copies onto the tiles."""

    def __init__(self, root: QWidget, window, choices: Iterable):
        super().__init__(root)
        from .window import Tile

        self.window = window
        self.setGeometry(root.rect())
        self.cards = []
        for choice in choices:
            real = window.tiles.get(choice.target_id)
            if real is None:
                continue
            card = Tile(choice.target_id, real.key, self)
            card.setMaximumHeight(16777215)            # the stand-in may be taller than a real tile
            card.set_label(choice.label, choice.action_id)
            end = QRect(real.mapTo(root, QPoint(0, 0)), real.size())
            self.cards.append((card, end))
        self._place_start()
        self._group: Optional[QParallelAnimationGroup] = None

    def _place_start(self) -> None:
        """Side by side, centred in the window, bigger than they will end up."""
        if not self.cards:
            return
        w = int(self.cards[0][1].width() * GROW)
        h = int(self.cards[0][1].height() * GROW)
        gap = int(T.XL * GROW)
        total = len(self.cards) * w + (len(self.cards) - 1) * gap
        x, y = (self.width() - total) // 2, (self.height() - h) // 2
        for i, (card, _end) in enumerate(self.cards):
            card.setGeometry(x + i * (w + gap), y, w, h)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG))
        p.end()

    def play(self, on_done: Optional[Callable[[], None]] = None) -> None:
        self.show()
        self.raise_()

        def move() -> None:
            self._group = QParallelAnimationGroup(self)
            for card, end in self.cards:
                a = QPropertyAnimation(card, b"geometry", self)
                a.setDuration(MOVE_MS)
                a.setStartValue(card.geometry())
                a.setEndValue(end)
                a.setEasingCurve(QEasingCurve.Type.InOutCubic)
                self._group.addAnimation(a)
            self._group.finished.connect(finish)
            self._group.start()

        def finish() -> None:
            self.hide()
            self.deleteLater()
            if on_done is not None:
                on_done()

        QTimer.singleShot(HOLD_MS, move)


def play_intro(root: QWidget, window, choices, reveal: Iterable[QWidget] = (),
               timeout_ms: int = 4000) -> bool:
    """Run the opening and return when it has finished. ``reveal`` are the panels that fade in
    once the cards are in place (the map, the latest-line box, the status pills). False if it was
    skipped."""
    choices = list(choices)
    if not fade.ENABLED or not root.isVisible() or not choices:
        return False
    for tile in window.tiles.values():                 # the real tiles show the same cards underneath
        pass
    loop = QEventLoop()
    intro = CardIntro(root, window, choices)
    if not intro.cards:
        intro.deleteLater()
        return False

    def done() -> None:
        for panel in reveal:
            fade.fade_in(panel, T.BG, 420)
        loop.quit()

    intro.play(done)
    QTimer.singleShot(timeout_ms, loop.quit)           # never hang the app on an animation
    loop.exec()
    return True
