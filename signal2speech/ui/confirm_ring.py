"""The confirm ring on the preview screen (#175).

Holding key 1 fills it over HOLD_S seconds; releasing early empties it; completing confirms
exactly once. Eye input (the alpha switch's progress, or a simulated eye closure) drives the
same ring, so keyboard, simulated, and live EEG look the same. Nothing is confirmed before the
ring is full.

RingModel is plain Python with an injectable clock, so its states are tested headless.
ConfirmRing is the Qt widget that ticks and paints it.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Sequence

HOLD_S = 2.0


def trailing_progress(values: Sequence[float], level: float, dwell: int) -> float:
    """Fraction of the alpha switch's dwell that the latest band-power values have stayed at or
    above its level: how far an eye closure is towards confirming. Read-only: the Threshold
    still makes the decision."""
    if dwell <= 0:
        return 0.0
    run = 0
    for v in reversed(values):
        if v < level or run >= dwell:
            break
        run += 1
    return min(1.0, run / dwell)


class RingModel:
    def __init__(self, on_complete: Optional[Callable[[str], None]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.on_complete = on_complete
        self.clock = clock
        self.reset()

    def reset(self) -> None:
        self.progress = 0.0
        self.source: Optional[str] = None
        self.completed = False
        self._hold_start: Optional[float] = None
        self._hold_s = HOLD_S

    @property
    def holding(self) -> bool:
        return self._hold_start is not None

    def start_hold(self, source: str = "keyboard", seconds: float = HOLD_S) -> None:
        """Begin filling from empty over `seconds`. Ignored once complete or already holding."""
        if self.completed or self.holding:
            return
        self.source, self._hold_s = source, max(0.001, seconds)
        self._hold_start = self.clock()
        self.progress = 0.0

    def release(self) -> None:
        """Let go early: the ring empties, and nothing is confirmed."""
        if self.completed:
            return
        self._hold_start = None
        self.progress = 0.0

    def tick(self) -> None:
        if self._hold_start is None or self.completed:
            return
        self.progress = min(1.0, (self.clock() - self._hold_start) / self._hold_s)
        if self.progress >= 1.0:
            self._hold_start = None
            self.completed = True
            if self.on_complete is not None:
                self.on_complete(self.source or "keyboard")

    def set_external(self, progress: float, source: str = "eyes") -> None:
        """Eye input's own progress. The ring follows it (and empties if the eyes open) but never
        confirms: the alpha switch confirms by itself, so there's no double confirm."""
        if self.completed or self.holding:
            return
        self.source = source
        self.progress = max(0.0, min(1.0, float(progress)))

    def mark_confirmed(self, source: Optional[str] = None) -> None:
        """A confirm arrived (from any input): show the ring full, remembering what filled it."""
        if source:
            self.source = source
        self._hold_start = None
        self.progress = 1.0
        self.completed = True


def _qt_widget():
    from PySide6.QtCore import QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtWidgets import QSizePolicy, QWidget

    from . import theme as T

    class ConfirmRing(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.model = RingModel(on_complete=self._completed)
            self.handlers: dict = {}               # source -> callable when a hold completes
            self.label = ""
            self._timer = QTimer(self, interval=16)
            self._timer.timeout.connect(self._tick)
            self.setFixedSize(124, 124)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        def start_hold(self, source: str = "keyboard", seconds: float = HOLD_S) -> None:
            self.model.start_hold(source, seconds)
            if self.model.holding:
                self._timer.start()
            self.update()

        def release(self) -> None:
            self.model.release()
            self._timer.stop()
            self.update()

        def set_external(self, progress: float, source: str = "eyes") -> None:
            self.model.set_external(progress, source)
            self.update()

        def mark_confirmed(self, source=None) -> None:
            self._timer.stop()
            self.model.mark_confirmed(source)
            self.update()

        def reset(self) -> None:
            self._timer.stop()
            self.model.reset()
            self.update()

        def _tick(self) -> None:
            self.model.tick()
            if not self.model.holding:
                self._timer.stop()
            self.update()

        def _completed(self, source: str) -> None:
            fn = self.handlers.get(source)
            if fn is not None:
                fn()

        def paintEvent(self, _event) -> None:
            m = self.model
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(self.rect()).adjusted(12, 12, -12, -12)
            p.setPen(QPen(QColor(T.DIVIDER), 12))
            p.drawEllipse(r)
            cancelling = m.source == "cancel"
            if m.progress > 0:
                colour = T.MUTED if cancelling else T.SUCCESS if m.completed else T.ACCENT
                pen = QPen(QColor(colour), 12)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(r, 90 * 16, int(-360 * 16 * m.progress))
            f = QFont(self.font())
            f.setBold(True)
            if m.completed:
                text = "✕" if cancelling else "✓"
                f.setPixelSize(T.TITLE + 8)
                p.setPen(QColor(T.MUTED if cancelling else T.SUCCESS))
            elif m.holding or m.progress > 0:
                text = (f"Cancel\n{m.progress * HOLD_S:.1f} s" if cancelling else
                        f"{m.progress * HOLD_S:.1f} s" if m.source in ("keyboard", "simulated") else "eyes…")
                f.setPixelSize(T.BODY)
                p.setPen(QColor(T.TEXT))
            else:
                text = self.label or "Hold 1"
                f.setPixelSize(T.CAPTION)
                p.setPen(QColor(T.MUTED))
            p.setFont(f)
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text)
            p.end()

    return ConfirmRing


_CLASS = None


def __getattr__(name):
    global _CLASS
    if name == "ConfirmRing":
        if _CLASS is None:
            _CLASS = _qt_widget()
        return _CLASS
    raise AttributeError(name)
