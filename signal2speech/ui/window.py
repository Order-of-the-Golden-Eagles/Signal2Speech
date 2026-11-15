"""PySide6 selection window (#24).

The window only renders SelectionHandler events and calls InputAdapter / handler.cancel().
It never maps targets to actions, plays audio, or changes the map. Call everything on the Qt
main thread: SelectionHandler is not thread-safe.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QSizePolicy,
                               QVBoxLayout, QWidget)

from signal2speech.core import (Choice, InputAdapter, InputSources, Outcome, Round, RoundKind,
                                SelectionEvent, SelectionHandler, TargetIds)

from .fit import fit_pixel_size
from .flash import FlashScheduler

INPUT_LABELS = {InputSources.KEYBOARD: "Keyboard", InputSources.SIMULATED: "Simulated",
                InputSources.RECORDED: "Recorded", InputSources.LIVE_EEG: "Live EEG"}
_INPUT_COLORS = {InputSources.KEYBOARD: "#3b82f6", InputSources.SIMULATED: "#f59e0b",
                 InputSources.RECORDED: "#a855f7", InputSources.LIVE_EEG: "#22c55e"}
_TILE_ORDER = (TargetIds.TARGET_1, TargetIds.TARGET_2)

_STYLE = """
QMainWindow, QWidget#root { background: #0b0d10; }
QLabel { color: #f5f7fa; }
QLabel#prompt { font-size: 32px; font-weight: 600; color: #cbd5e1; }
QLabel#preview { font-size: 44px; font-weight: 700; color: #ffe066; padding: 16px; }
QLabel#hint { font-size: 24px; color: #cbd5e1; }
QLabel#countdown { font-size: 22px; color: #94a3b8; }
QFrame#strip { background: #151a21; border-top: 2px solid #2a3340; }
QLabel.strip { font-size: 20px; font-family: Menlo, Consolas, monospace; color: #e2e8f0; }
"""


class Tile(QLabel):
    """One frozen choice tile. Flashing changes colour only: no resize, move, or relabel.

    Long labels shrink to fit (56 px down to 32 px, #95). The size is chosen on relabel and
    resize only, never on a flash, so flash timing stays steady.
    """

    MAX_PX = 56
    INSET = 28   # 4 px border + 24 px padding, each side

    def __init__(self, target_id: str, key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.target_id = target_id
        self.key = key
        self.lit = False
        self._label = ""
        self.font_px = self.MAX_PX
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(300, 220)   # fits two tiles plus the map at 1280x720 (#94)
        self._apply()

    @property
    def label(self) -> str:
        return self._label

    def set_label(self, label: str) -> None:
        self._label = label
        self.setText(f"{label}\n [{self.key}]" if label else "")
        self._fit()
        self._apply()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit():
            self._apply()

    def _fit(self) -> bool:
        """Recompute font_px for the current text and size. True if it changed."""
        font = QFont(self.font())
        font.setBold(True)
        px = fit_pixel_size(self.text(), font, self.width() - 2 * self.INSET,
                            self.height() - 2 * self.INSET, self.MAX_PX)
        changed, self.font_px = px != self.font_px, px
        return changed

    def set_lit(self, lit: bool) -> None:
        self.lit = lit
        self._apply()

    def _apply(self) -> None:
        if not self._label:
            bg, fg, border = "#11151a", "#11151a", "#1f2630"
        elif self.lit:
            bg, fg, border = "#ffffff", "#000000", "#ffffff"
        else:
            bg, fg, border = "#1e2630", "#ffffff", "#475569"
        self.setStyleSheet(f"background:{bg}; color:{fg}; border:4px solid {border};"
                           f"border-radius:18px; font-size:{self.font_px}px; font-weight:700;"
                           "padding:24px;")


class SelectionWindow(QMainWindow):
    def __init__(self, handler: SelectionHandler, keyboard: InputAdapter, *,
                 input_source: str = InputSources.KEYBOARD, flash: bool = False,
                 on_flash: Optional[Callable[[str], None]] = None,
                 on_sequence_started: Optional[Callable[[], None]] = None,
                 on_sequence_finished: Optional[Callable[[], None]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        if keyboard.source != InputSources.KEYBOARD:
            raise ValueError("Keys 1/2 need a keyboard InputAdapter.")
        self.handler = handler
        self.keyboard = keyboard
        self.flash_enabled = flash
        self._preview: Optional[Choice] = None
        self.setWindowTitle("Signal2Speech")
        self.setStyleSheet(_STYLE)
        self.resize(1280, 800)

        root = QWidget(objectName="root")
        col = QVBoxLayout(root)
        col.setContentsMargins(32, 24, 32, 0)
        col.setSpacing(20)

        self.prompt = QLabel("Waiting for a round", objectName="prompt")
        self.preview = QLabel("", objectName="preview")
        self.preview.setWordWrap(True)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setVisible(False)
        col.addWidget(self.prompt)
        col.addWidget(self.preview)
        # Seconds left before an unanswered Confirm round cancels (#26, #96). App drives it.
        self.countdown = QLabel("", objectName="countdown")
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown.setVisible(False)
        col.addWidget(self.countdown)

        row = QHBoxLayout()
        row.setSpacing(32)
        self.tiles: Dict[str, Tile] = {}
        for key, target in zip("12", _TILE_ORDER):
            tile = Tile(target, key)
            self.tiles[target] = tile
            row.addWidget(tile, 1)
        col.addLayout(row, 1)

        self.hint = QLabel("", objectName="hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.hint)

        strip = QFrame(objectName="strip")
        srow = QHBoxLayout(strip)
        srow.setContentsMargins(16, 10, 16, 10)
        srow.setSpacing(28)
        self.input_label = self._strip_label()
        self.connection_label = self._strip_label()
        self.round_label = self._strip_label()
        self.outcome_label = self._strip_label()
        srow.addWidget(self.input_label)
        srow.addWidget(self.round_label)
        # The last outcome can be long; let it clip instead of forcing the window wide.
        # The transcript and the tooltip keep the full text.
        self.outcome_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # The connection text can be long ("scripted, no g.Pype (...)"); let it clip too.
        # The input label never clips: it's what keeps simulated input from looking live.
        self.connection_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        srow.addWidget(self.connection_label, 1)
        srow.addWidget(self.outcome_label, 1)
        col.addWidget(strip)
        self.setCentralWidget(root)

        self.set_input_source(input_source)
        self.set_connection("n/a" if input_source == InputSources.KEYBOARD else "unknown")
        self._set_round_text(None)
        self.outcome_label.setText("Last: —")

        self.flasher = FlashScheduler(self._set_tile_lit, on_flash,
                                      on_sequence_started=on_sequence_started,
                                      on_sequence_finished=on_sequence_finished, parent=self)

        # Ambient keys; auto-repeat off so a held "2" can't preview and then cancel.
        for seq, fn in (("1", lambda: self.press_target(TargetIds.TARGET_1)),
                        ("2", lambda: self.press_target(TargetIds.TARGET_2)),
                        ("Esc", self.press_cancel)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setAutoRepeat(False)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

        handler.on_round_opened.append(self.show_round)
        handler.on_preview.append(self.show_preview)
        handler.on_cleared.append(self.reset)
        handler.on_handled.append(self.show_outcome)

    # ── Judge strip ──────────────────────────────────────────
    def _strip_label(self) -> QLabel:
        lbl = QLabel()
        lbl.setProperty("class", "strip")
        return lbl

    def set_input_source(self, source: str) -> None:
        """Label the decoder actually feeding the handler, so Simulated never reads as Live."""
        self.input_source = source
        self.input_label.setText(f"Input: {INPUT_LABELS.get(source, source)}")
        self.input_label.setStyleSheet(f"color:{_INPUT_COLORS.get(source, '#e2e8f0')};"
                                       "font-weight:700;")

    def set_connection(self, state: str) -> None:
        self.connection_label.setText(f"Connection: {state}")
        self.connection_label.setToolTip(self.connection_label.text())
        # Keyboard has no connection to report; hide "n/a" so small screens keep room (#94).
        self.connection_label.setVisible(state != "n/a")

    def _set_round_text(self, rnd: Optional[Round]) -> None:
        self.round_label.setText(f"Round: {rnd.id} ({rnd.kind.value})" if rnd else "Round: —")

    # ── Keys (the only calls into core) ──────────────────────
    def press_target(self, target_id: str) -> Outcome:
        outcome = self.keyboard.select_now(target_id)
        if outcome is Outcome.RejectedNoOpenRound:   # select_now returns before handle()
            self.outcome_label.setText(f"Last: {outcome.value} · keyboard {target_id}")
        return outcome

    def press_cancel(self) -> None:
        self.handler.cancel()

    # ── Handler listeners ────────────────────────────────────
    def confirm_hint(self) -> str:
        """The Confirm-round hint. Live EEG eye confirm stays off until #23 arms it (#103)."""
        if (self.input_source == InputSources.LIVE_EEG
                and not self.handler.live_eeg_confirm_armed):
            return ("Confirm: key 1  (eye-closure confirm is off until #23 says it's safe)   ·   "
                    "Cancel: key 2 or Esc")
        return "Confirm: close your eyes for 2 s, or key 1   ·   Cancel: key 2 or Esc"

    def show_round(self, rnd: Round) -> None:
        self.flasher.stop()
        for target, tile in self.tiles.items():
            c = rnd.find(target)
            tile.set_label(c.label if c else "")
        self._set_round_text(rnd)
        if rnd.kind is RoundKind.CONFIRM:
            self.prompt.setText("Say this?")
            self.preview.setText(self._preview_text())
            self._fit_preview()
            self.preview.setVisible(True)
            self.hint.setText(self.confirm_hint())
        else:
            self._preview = None
            self.prompt.setText("Choose a reply")
            self.set_countdown(None)
            self.preview.setVisible(False)
            self.hint.setText("Look at a tile, or press 1 or 2   ·   Esc clears")
            if self.flash_enabled:
                self.flasher.start([t for t in _TILE_ORDER if rnd.find(t)])

    def show_preview(self, choice: Choice) -> None:
        """No audio and no map change. The Confirm round opens right after this."""
        self.flasher.stop()
        self._preview = choice

    def reset(self, reason: str = "") -> None:
        self.set_countdown(None)
        self.flasher.stop()
        self._preview = None
        for tile in self.tiles.values():
            tile.set_label("")
        self.preview.setVisible(False)
        self.preview.setText("")
        self.hint.setText("")
        self.prompt.setText("Waiting for a round")
        self._set_round_text(None)
        if reason:
            self.outcome_label.setText(f"Last: Cleared ({reason})")

    def show_outcome(self, e: Optional[SelectionEvent], outcome: Outcome) -> None:
        detail = f" · {e.source} {e.eventId} {e.roundId}→{e.targetId}" if e else ""
        self.outcome_label.setText(f"Last: {outcome.value}{detail}")
        self.outcome_label.setToolTip(self.outcome_label.text())
        if outcome is Outcome.Confirmed:   # handler closed the round without on_cleared
            self.reset()
            self.prompt.setText("Confirmed · sent to output")

    # ── Helpers ──────────────────────────────────────────────
    PREVIEW_MAX_PX = 44

    def set_countdown(self, seconds) -> None:
        """Show "Cancels in N s" under the preview, or hide it with None."""
        if seconds is None:
            self.countdown.setVisible(False)
            self.countdown.setText("")
            return
        self.countdown.setText(f"No answer cancels in {int(seconds)} s")
        self.countdown.setVisible(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_preview()

    def _fit_preview(self) -> None:
        """Shrink long preview text (44 px down to 32 px) so it leaves room for the tiles."""
        if not hasattr(self, "preview"):
            return
        font = QFont(self.preview.font())
        font.setBold(True)
        width = max(self.width() - 64 - 32, 1)      # window margins, then label padding
        height = max(int(self.height() * 0.28), 80)
        self.preview_px = fit_pixel_size(self.preview.text(), font, width, height,
                                         self.PREVIEW_MAX_PX)
        self.preview.setStyleSheet(f"font-size: {self.preview_px}px;")

    def _preview_text(self) -> str:
        c = self._preview
        return (c.spoken_text or c.label) if c else ""

    def _set_tile_lit(self, target_id: str, lit: bool) -> None:
        tile = self.tiles.get(target_id)
        if tile is not None:
            tile.set_lit(lit)
            tile.repaint()   # synchronous, so on_flash fires after the lit frame is painted
