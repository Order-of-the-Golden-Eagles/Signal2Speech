"""A small, fixed "Brain Activity" graph: the last few seconds of the EEG the pipeline is using.

It draws what the chooser's pipeline actually receives after its 1-30 Hz filter, and its caption
names where that signal comes from (live headset, g.tec recording, or simulator). With keyboard
input there is no EEG, and it says so instead of drawing anything.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme as T

RATE_HZ = 250
SECONDS = 4.0
WIDTH, HEIGHT = 430, 56        # before the text scale: small, and the same on every screen
REDRAW_MS = 80                 # about 12 pictures a second: steady, and cheap next to the flashes


class BrainTrace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.caption = "No EEG: keyboard"
        self.idle_note = "no signal right now"
        self.active = False
        self._lock = threading.Lock()
        self._samples: deque = deque(maxlen=int(RATE_HZ * SECONDS))
        self._scale = 1.0
        self.setFixedSize(T.px(WIDTH), T.px(HEIGHT))
        self.setToolTip("The last four seconds of EEG going into the chooser, after its 1 to 30 Hz filter")
        self._timer = QTimer(self, interval=REDRAW_MS)
        self._timer.timeout.connect(self.update)

    # ── fed from the g.Pype worker thread ──
    def feed(self, rows: np.ndarray) -> None:
        """Rows of samples (time, channels). One channel is kept: a single readable line."""
        block = np.asarray(rows, dtype=float)
        if block.ndim == 1:
            block = block[:, None]
        if not block.size:
            return
        with self._lock:
            self._samples.extend(block[:, block.shape[1] // 2].tolist())

    def set_source(self, caption: str) -> None:
        self.caption = caption
        self.active = True
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.setBrush(QColor(T.SURFACE))
        p.drawRoundedRect(box, T.RADIUS_S, T.RADIUS_S)

        title = QFont(self.font())
        title.setPixelSize(T.px(T.CAPTION - 3))
        title.setBold(True)
        p.setFont(title)
        p.setPen(QColor(T.TEXT))
        label_w = T.px(136)
        left = QRectF(box.left() + 10, box.top(), label_w, box.height())
        p.drawText(left.adjusted(0, 6, 0, -box.height() / 2), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
                   "Brain Activity")
        small = QFont(self.font())
        small.setPixelSize(T.px(T.CAPTION - 7))
        p.setFont(small)
        p.setPen(QColor(T.MUTED))
        p.drawText(left.adjusted(0, box.height() / 2, 0, -4),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self.caption)

        plot = QRectF(left.right() + 6, box.top() + 6, box.right() - left.right() - 14, box.height() - 12)
        mid = plot.center().y()
        p.setPen(QPen(QColor(T.BORDER), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(plot.left(), mid), QPointF(plot.right(), mid))
        with self._lock:
            data = np.fromiter(self._samples, dtype=float, count=len(self._samples))
        if not self.active or data.size < 2:
            return
        if float(np.ptp(data)) < 1e-9:
            # Nothing is arriving: with recorded data the EEG plays only while the cards flash.
            # Say so, and never draw a made-up signal in the gap.
            p.setPen(QColor(T.MUTED))
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), self.idle_note)
            return
        data = data - np.median(data)
        spread = float(np.percentile(np.abs(data), 98)) or 1.0
        # The scale follows the signal slowly, so the line doesn't jump when a response arrives.
        self._scale = max(spread, self._scale * 0.97) if self._scale > 1e-9 else spread
        full = self._samples.maxlen
        step = plot.width() / (full - 1)
        x0 = plot.right() - (data.size - 1) * step         # newest sample at the right edge
        gain = (plot.height() / 2 - 1) / max(self._scale, 1e-9)
        ys = np.clip(mid - data * gain, plot.top(), plot.bottom())
        points = QPolygonF([QPointF(x0 + i * step, float(y)) for i, y in enumerate(ys)])
        p.setPen(QPen(QColor(T.ACTION_TINT.get("show_satellite", T.ACCENT)), 1.4))
        p.drawPolyline(points)
