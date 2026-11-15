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
WIDTH, HEIGHT = 540, 104       # before the text scale: small, and the same on every screen
#: The Unicorn Hybrid Black's electrodes, in its channel order (as Unicorn Recorder lists them).
UNICORN_CHANNELS = ("Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8")
REDRAW_MS = 80                 # about 12 pictures a second: steady, and cheap next to the flashes


class BrainTrace(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.caption = "No EEG: keyboard"
        self.idle_note = "no signal right now"
        self.active = False
        self._lock = threading.Lock()
        self._samples: deque = deque(maxlen=int(RATE_HZ * SECONDS))   # rows of all channels
        self._scales: list = []
        self.channel_names: tuple = ()
        self.setFixedSize(T.px(WIDTH), T.px(HEIGHT))
        self.setToolTip("The last four seconds of every EEG channel going into the chooser, after its 1 to 30 Hz filter, laid out like Unicorn Recorder")
        self._timer = QTimer(self, interval=REDRAW_MS)
        self._timer.timeout.connect(self.update)

    # ── fed from the g.Pype worker thread ──
    def feed(self, rows: np.ndarray) -> None:
        """Rows of samples (time, channels). Every channel is kept, one lane each."""
        block = np.asarray(rows, dtype=float)
        if block.ndim == 1:
            block = block[:, None]
        if not block.size:
            return
        with self._lock:
            self._samples.extend(block.tolist())

    def set_source(self, caption: str, channel_names: tuple = ()) -> None:
        self.caption = caption
        self.channel_names = tuple(channel_names)
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
        label_w = T.px(118)
        left = QRectF(box.left() + 10, box.top() + 8, label_w, box.height() - 16)
        p.drawText(left, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), "Brain Activity")
        small = QFont(self.font())
        small.setPixelSize(T.px(T.CAPTION - 7))
        p.setFont(small)
        p.setPen(QColor(T.MUTED))
        p.drawText(left.adjusted(0, T.px(22), 0, 0),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self.caption)

        names_w = T.px(30)
        plot = QRectF(left.right() + 6 + names_w, box.top() + 5, box.right() - left.right() - 16 - names_w,
                      box.height() - 10)
        with self._lock:
            rows = np.asarray(list(self._samples), dtype=float)
        if not self.active or rows.ndim != 2 or len(rows) < 2:
            p.setPen(QPen(QColor(T.BORDER), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), plot.center().y()), QPointF(plot.right(), plot.center().y()))
            return
        if float(np.ptp(rows)) < 1e-9:
            # Nothing is arriving: with recorded data the EEG plays only while the cards flash.
            # Say so, and never draw a made-up signal in the gap.
            p.setPen(QColor(T.MUTED))
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), self.idle_note)
            return
        lanes = rows.shape[1]
        lane_h = plot.height() / lanes
        if len(self._scales) != lanes:
            self._scales = [0.0] * lanes
        full = self._samples.maxlen
        step = plot.width() / (full - 1)
        decim = 2                                          # half the points: the same picture, cheaper
        x0 = plot.right() - (len(rows) - 1) * step         # newest sample at the right edge
        tiny = QFont(self.font())
        tiny.setPixelSize(max(8, T.px(T.CAPTION - 9)))
        colour = QColor(T.ACTION_TINT.get("show_satellite", T.ACCENT))
        for c in range(lanes):
            top = plot.top() + c * lane_h
            mid = top + lane_h / 2
            p.setFont(tiny)
            p.setPen(QColor(T.QUIET))
            name = self.channel_names[c] if c < len(self.channel_names) else str(c + 1)
            p.drawText(QRectF(plot.left() - names_w - 2, top, names_w, lane_h),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), name)
            data = rows[:, c] - np.median(rows[:, c])
            spread = float(np.percentile(np.abs(data), 98)) or 1.0
            # Each lane keeps its own scale, which follows the signal slowly so it doesn't jump.
            prev = self._scales[c]
            self._scales[c] = max(spread, prev * 0.97) if prev > 1e-9 else spread
            gain = (lane_h / 2 - 0.5) / max(self._scales[c], 1e-9)
            ys = np.clip(mid - data * gain, top, top + lane_h)
            idx = range(0, len(ys), decim)
            p.setPen(QPen(colour, 1.0))
            p.drawPolyline(QPolygonF([QPointF(x0 + i * step, float(ys[i])) for i in idx]))
