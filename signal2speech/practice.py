"""Practice round (#196): a 30-second "look here and count the flashes" warm-up.

New wearers don't know what to do when the tiles flash. The practice round lights tile 1 with
an accent outline, asks the wearer to count its flashes, and runs real flash sequences (same
timing as the demo) for about 30 s, then shows a plain "Ready" screen.

It never sends anything to output: no handler round is open during practice, so no input can
preview or confirm, and it uses its own FlashScheduler with no decoder hooks, so no input
adapter is armed and no decision is captured. It is labelled Practice for the whole round.
Live EEG calibration is not fed from it yet: that belongs to #23's owner.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from signal2speech.core import TargetIds
from signal2speech.ui.flash import FlashScheduler

PRACTICE_S = 30.0
READY_MS = 2500
GAP_MS = 400            # pause between practice sequences
TARGET = TargetIds.TARGET_1
OTHER = TargetIds.TARGET_2
PROMPT = "Practice · look at tile 1 and count its flashes"
HINT = "Practice round: nothing is sent   ·   Esc stops"


class PracticeRound(QObject):
    def __init__(self, window, *, duration_s: float = PRACTICE_S, ready_ms: int = READY_MS,
                 on_finished: Optional[Callable[[], None]] = None,
                 clock: Callable[[], float] = time.monotonic, parent: Optional[QObject] = None):
        super().__init__(parent or window)
        self.window = window
        self.duration_s = duration_s
        self.ready_ms = ready_ms
        self.on_finished = on_finished
        self.clock = clock
        self.active = False
        self.ready = False
        self.sequences = 0
        self.target_flashes = 0
        self.runs = 0
        main = window.flasher
        self.flasher = FlashScheduler(window._set_tile_lit, self._flashed,
                                      on_sequence_finished=self._sequence_done,
                                      flash_ms=main.flash_ms, isi_ms=main.isi_ms,
                                      repetitions=main.repetitions, parent=self)
        self._gap = QTimer(self, singleShot=True, interval=GAP_MS)
        self._gap.timeout.connect(self._run_sequence)
        self._ready_timer = QTimer(self, singleShot=True)
        self._ready_timer.timeout.connect(self._finish)

    def start(self) -> None:
        w = self.window
        self.active, self.ready = True, False
        self.sequences = self.target_flashes = 0
        self.runs += 1
        self._started = self.clock()
        w.flasher.stop()
        w.ring.reset()
        w.set_countdown(None)
        w.preview_box.setVisible(False)
        look, other = w.tiles[TARGET], w.tiles[OTHER]
        look.set_label("Look here")
        look.note, look.highlight = "Count its flashes", True
        other.set_label("Practice")
        other.note = "Not this one"
        look.update()
        other.update()
        w.prompt.setText(PROMPT)
        w.hint.setText(HINT)
        w.round_label.setText("Round: practice")
        self._run_sequence()

    def stop(self) -> bool:
        """Esc: end now and hand back to the app. True if a practice round was running."""
        if not self.active:
            return False
        self._finish()
        return True

    def _flashed(self, target_id: str) -> None:
        if target_id == TARGET:
            self.target_flashes += 1

    def _run_sequence(self) -> None:
        if self.active and not self.ready:
            self.flasher.start([TARGET, OTHER])

    def _sequence_done(self) -> None:
        if not self.active:
            return
        self.sequences += 1
        if self.clock() - self._started < self.duration_s:
            self._gap.start()
            return
        self._show_ready()

    def _show_ready(self) -> None:
        w = self.window
        self.ready = True
        self.flasher.stop()
        for tile in w.tiles.values():
            tile.set_label("")
        w.prompt.setText(f"Practice · Ready. Tile 1 flashed {self.target_flashes} times.")
        w.hint.setText("Practice round over. The first question opens in a moment.")
        self._ready_timer.start(self.ready_ms)

    def _finish(self) -> None:
        self.active = self.ready = False
        self.flasher.stop()
        self._gap.stop()
        self._ready_timer.stop()
        for tile in self.window.tiles.values():
            tile.set_label("")
        if self.on_finished is not None:
            self.on_finished()
