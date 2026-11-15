"""Always-available help phrase (#197).

A person who can't move needs one way to call for help from any screen. Two triggers:

- **Hold H for 2 s.** A tap does nothing, auto-repeat is ignored, and typing in a text field
  (the AI question box) is left alone.
- **A long eyes-closed hold outside a Confirm round** (opt-in, `--help-by-eyes`): the alpha
  switch's progress has to stay full for EYES_EXTRA_S more seconds after the 2 s a confirm needs.
  It never fires during a Confirm round, so a normal confirm can't trigger it.

Either way the phrase fires once, at most once every COOLDOWN_S seconds, and never touches the
selection handler, so the current round is left exactly as it was. The app sends the phrase
through AppSink, its one output path.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

HELP_TEXT = "I need help, please."
HOLD_S = 2.0
EYES_EXTRA_S = 3.0
COOLDOWN_S = 10.0
KEY = Qt.Key.Key_H


class HelpCall(QObject):
    """Turns a held key or a long eye closure into one help call. `fire(source)` does the output."""

    def __init__(self, fire: Callable[[str], None], *, hold_s: float = HOLD_S,
                 cooldown_s: float = COOLDOWN_S, eyes_extra_s: float = EYES_EXTRA_S,
                 in_confirm: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._fire = fire
        self.cooldown_s = cooldown_s
        self.eyes_extra_s = eyes_extra_s
        self.in_confirm = in_confirm
        self.clock = clock
        self.eyes_enabled = False
        self.last_fired: Optional[float] = None
        self.blocked = 0                      # holds that finished inside the cooldown
        self._eyes_full_since: Optional[float] = None
        self._hold = QTimer(self, singleShot=True, interval=int(hold_s * 1000))
        self._hold.timeout.connect(lambda: self.trigger("keyboard"))

    # ── Key ──────────────────────────────────────────────────
    def install(self) -> None:
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if t not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if event.key() != KEY or event.isAutoRepeat():
            return False
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False
        self.key(t == QEvent.Type.KeyPress)
        return True

    def key(self, pressed: bool) -> None:
        if pressed:
            if not self._hold.isActive():
                self._hold.start()
        else:
            self._hold.stop()                 # released before 2 s: a tap, nothing happens

    @property
    def holding(self) -> bool:
        return self._hold.isActive()

    # ── Eyes ─────────────────────────────────────────────────
    def feed_eyes(self, progress: float) -> None:
        """The alpha switch's progress (0-1). Full for eyes_extra_s outside a Confirm round fires."""
        if not self.eyes_enabled or self.in_confirm() or progress < 1.0:
            self._eyes_full_since = None
            return
        now = self.clock()
        if self._eyes_full_since is None:
            self._eyes_full_since = now
        elif now - self._eyes_full_since >= self.eyes_extra_s:
            self._eyes_full_since = None
            self.trigger("eyes")

    # ── Fire ─────────────────────────────────────────────────
    def trigger(self, source: str) -> bool:
        now = self.clock()
        if self.last_fired is not None and now - self.last_fired < self.cooldown_s:
            self.blocked += 1
            return False
        self.last_fired = now
        self._fire(source)
        return True
