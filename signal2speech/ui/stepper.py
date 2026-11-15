"""Where we are: Choose · Preview · Confirm · Spoken (#178).

A judge who walks up mid-demo sees which of the four steps is happening. The steps follow the
selection handler's own events, never a timer of their own:

- a Choose round opens -> **Choose**
- a preview is shown (the Confirm round opens) -> **Preview**
- while that round's confirm ring fills to confirm (key 1 held, or the eyes closing; not
  key 2 held to cancel) -> **Confirm**
- the handler confirms and the output runs -> **Spoken**
- a cancel, timeout, or disconnect clears the round -> no step until the next question
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from signal2speech.core import Outcome, Round, RoundKind

from . import theme as P

STEPS = ("Choose", "Preview", "Confirm", "Spoken")


def step_for(kind: Optional[RoundKind], confirmed: bool, ring_active: bool) -> Optional[str]:
    """The current step from the handler state, or None when no question is open."""
    if confirmed:
        return "Spoken"
    if kind is RoundKind.CHOOSE:
        return "Choose"
    if kind is RoundKind.CONFIRM:
        return "Confirm" if ring_active else "Preview"
    return None


class StepBar(QWidget):
    """Four labels; the current one is highlighted, earlier ones are marked done."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(P.XS)
        self.labels: List[QLabel] = []
        self.separators: List[QLabel] = []
        for i, name in enumerate(STEPS):
            if i:
                sep = QLabel("›")
                self.separators.append(sep)
                row.addWidget(sep)
            lbl = QLabel(f"{i + 1} {name}")
            self.labels.append(lbl)
            row.addWidget(lbl)
        self.current: Optional[str] = None
        self.restyle()

    def set_step(self, step: Optional[str]) -> None:
        if step == self.current:
            return                                  # nothing to redraw
        self.current = step
        self.restyle()

    def restyle(self) -> None:
        """Colours for the current step, sizes for the current text scale (#195)."""
        for sep in self.separators:
            sep.setStyleSheet(f"color:{P.QUIET}; font-size:{P.px(P.CAPTION + 2)}px;")
        at = STEPS.index(self.current) if self.current in STEPS else -1
        for i, lbl in enumerate(self.labels):
            base = f"font-size:{P.px(P.CAPTION + 2)}px; padding:2px {P.S}px; border-radius:{P.RADIUS_S}px;"
            if i == at:
                lbl.setStyleSheet(base + f"background:{P.ACCENT}; color:{P.ON_ACCENT}; font-weight:700;")
            elif i < at:
                lbl.setStyleSheet(base + f"color:{P.MUTED};")
            else:
                lbl.setStyleSheet(base + f"color:{P.QUIET};")


class StepTracker:
    """Moves a StepBar along with the handler (#178). ``ring`` is the window's confirm ring;
    its model tells us when it starts or stops filling, so nothing polls."""

    def __init__(self, handler, bar: StepBar, ring=None):
        self.bar, self.ring = bar, ring
        self.kind: Optional[RoundKind] = None
        self.confirmed = False
        handler.on_round_opened.append(self._opened)
        handler.on_preview.append(lambda _c: self._update())
        handler.on_handled.append(self._handled)
        handler.on_cleared.append(self._cleared)
        self._model = getattr(ring, "model", None)
        if self._model is not None and hasattr(self._model, "listeners"):
            self._model.listeners.append(self._update)

    def _ring_active(self) -> bool:
        m = self._model
        if m is None or m.source == "cancel":        # holding 2 to cancel isn't confirming
            return False
        return bool(m.holding or m.progress > 0)

    def _opened(self, rnd: Round) -> None:
        self.kind, self.confirmed = rnd.kind, False
        self._update()

    def _handled(self, _e, outcome: Outcome) -> None:
        if outcome is Outcome.Confirmed:
            self.confirmed, self.kind = True, None
            self._update()

    def _cleared(self, _reason: str) -> None:
        self.kind, self.confirmed = None, False
        self._update()

    def clear(self) -> None:
        """No step: a practice round or another screen that isn't a question (#196)."""
        self.kind, self.confirmed = None, False
        self._update()

    def _update(self) -> None:
        self.bar.set_step(step_for(self.kind, self.confirmed, self._ring_active()))

    def stop(self) -> None:
        if self._model is not None and self._update in getattr(self._model, "listeners", []):
            self._model.listeners.remove(self._update)
