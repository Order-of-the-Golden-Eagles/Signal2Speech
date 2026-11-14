"""P300 flash scheduler for the choice tiles (#24, consumed by #46).

The scheduler lights one tile at a time. On each flash it lights the tile, forces a synchronous
repaint, and then calls ``on_flash(target_id)`` in the same event-loop tick, so #46 can emit a
g.Pype ``Marker`` on the frame the tile changes. It never reorders, relabels, or moves tiles.
"""
from __future__ import annotations

import random
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import QObject, Qt, QTimer

SetLit = Callable[[str, bool], None]


class FlashScheduler(QObject):
    def __init__(self, set_lit: SetLit, on_flash: Optional[Callable[[str], None]] = None, *,
                 flash_ms: int = 100, isi_ms: int = 75, repetitions: int = 10,
                 on_sequence_started: Optional[Callable[[], None]] = None,
                 on_sequence_finished: Optional[Callable[[], None]] = None,
                 rng: Optional[random.Random] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._set_lit = set_lit          # must light/unlight the tile and repaint synchronously
        self.on_flash = on_flash         # called right after the lit frame is painted
        self.on_sequence_started = on_sequence_started    # e.g. eeg.arm_capture()
        self.on_sequence_finished = on_sequence_finished  # e.g. let the classifier decide
        self.flash_ms = flash_ms
        self.isi_ms = isi_ms
        self.repetitions = repetitions
        self._rng = rng or random.Random()
        self._order: List[str] = []
        self._lit: Optional[str] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)

    @property
    def running(self) -> bool:
        return bool(self._order) or self._lit is not None

    def build_order(self, target_ids: Sequence[str]) -> List[str]:
        """Each repetition flashes every target once, shuffled, with no target twice in a row."""
        targets = list(target_ids)
        order: List[str] = []
        for _ in range(self.repetitions):
            block = targets[:]
            self._rng.shuffle(block)
            if order and len(block) > 1 and block[0] == order[-1]:
                block[0], block[-1] = block[-1], block[0]
            order.extend(block)
        return order

    def start(self, target_ids: Sequence[str]) -> None:
        self.stop()
        if not target_ids or self.repetitions < 1:
            return
        self._order = self.build_order(target_ids)
        if self.on_sequence_started:
            self.on_sequence_started()
        self._tick()

    def stop(self) -> None:
        """Abort without calling on_sequence_finished (round closed or decision arrived)."""
        self._timer.stop()
        self._order = []
        if self._lit is not None:
            lit, self._lit = self._lit, None
            self._set_lit(lit, False)

    def _tick(self) -> None:
        if self._lit is not None:               # end of a flash: unlight, wait the ISI
            lit, self._lit = self._lit, None
            self._set_lit(lit, False)
            if self._order:
                self._timer.start(self.isi_ms)
            elif self.on_sequence_finished:
                self.on_sequence_finished()
            return
        if not self._order:
            return
        target = self._order.pop(0)              # start of a flash
        self._lit = target
        self._set_lit(target, True)              # repaints before returning
        if self.on_flash:
            self.on_flash(target)
        self._timer.start(self.flash_ms)
