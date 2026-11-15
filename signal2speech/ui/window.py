"""PySide6 selection window (#24).

The window only renders SelectionHandler events and calls InputAdapter / handler.cancel().
It never maps targets to actions, plays audio, or changes the map. Call everything on the Qt
main thread: SelectionHandler is not thread-safe.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QSizePolicy,
                               QVBoxLayout, QWidget)

from signal2speech.core import (Choice, InputAdapter, InputSources, Outcome, Round, RoundKind,
                                SelectionEvent, SelectionHandler, TargetIds)

from .fit import fit_pixel_size
from .flash import FlashScheduler
from .icons import draw_icon
from . import theme as P

INPUT_LABELS = {InputSources.KEYBOARD: "Keyboard", InputSources.SIMULATED: "Simulated",
                InputSources.RECORDED: "Recorded", InputSources.LIVE_EEG: "Live EEG"}
_INPUT_COLORS = P.INPUT_COLORS
_TILE_ORDER = (TargetIds.TARGET_1, TargetIds.TARGET_2)

_STYLE = P.window_qss()


class Tile(QLabel):
    """One frozen choice tile, drawn by hand (#174): icon, title, one-line description, and
    the key as a corner badge.

    States: idle, flashing (lit), selected (the confirmed choice), and waiting (no round open).
    Flashing looks exactly as before: plain white with black content, so the stimulus the
    P300 classifier sees is unchanged. Flashing never relabels, moves, or resizes a tile.
    Long titles shrink to fit (56 px down to 32 px, #95), recomputed on relabel and resize only.
    """

    MAX_PX = P.DISPLAY
    INSET = P.BORDER_W + P.L          # border + padding, each side
    TOP = 64                          # icon and key badge row
    BOTTOM = 40                       # one-line description

    def __init__(self, target_id: str, key: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.target_id = target_id
        self.key = key
        self.lit = False
        self.selected = False
        self._label = ""
        self.action_id: Optional[str] = None
        self.icon: Optional[str] = None
        self.description = ""
        self.font_px = self.MAX_PX
        self.setMinimumSize(300, 220)   # fits two tiles plus the map at 1280x720 (#94)

    @property
    def label(self) -> str:
        return self._label

    @property
    def state(self) -> str:
        if not self._label:
            return "waiting"
        if self.lit:
            return "lit"
        return "selected" if self.selected else "idle"

    def set_label(self, label: str, action_id: Optional[str] = None) -> None:
        self._label = label
        self.action_id = action_id
        self.icon, self.description = P.ACTION_INFO.get(action_id, (None, "")) if label else (None, "")
        self.selected = False
        self.setText(label)
        self._fit()
        self.update()

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def set_lit(self, lit: bool) -> None:
        self.lit = lit
        self.update()

    def title_rect(self) -> QRectF:
        r = QRectF(self.rect()).adjusted(self.INSET, self.INSET, -self.INSET, -self.INSET)
        return r.adjusted(0, self.TOP, 0, -self.BOTTOM)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> bool:
        """Recompute font_px for the current title and size. True if it changed."""
        font = QFont(self.font())
        font.setBold(True)
        r = self.title_rect()
        px = fit_pixel_size(self._label, font, int(r.width()), int(max(r.height(), 40)),
                            self.MAX_PX, P.TILE_TITLE_MIN)
        changed, self.font_px = px != self.font_px, px
        return changed

    def paintEvent(self, event) -> None:
        state = self.state
        bg, fg, border, sub = {
            "waiting": (P.TILE_DISABLED_BG, P.TILE_DISABLED_TEXT, P.TILE_DISABLED_BORDER, P.TILE_DISABLED_TEXT),
            "lit": (P.TILE_LIT_BG, P.TILE_LIT_TEXT, P.TILE_LIT_BG, P.TILE_LIT_TEXT),
            "selected": (P.TILE_SELECTED_BG, P.TILE_SELECTED_TEXT, P.TILE_SELECTED_BORDER, P.TILE_SELECTED_TEXT),
            "idle": (P.TILE_BG, P.TILE_TEXT, P.TILE_BORDER, P.MUTED),
        }[state]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = P.BORDER_W / 2
        body = QRectF(self.rect()).adjusted(half, half, -half, -half)
        path = QPainterPath()
        path.addRoundedRect(body, P.RADIUS_L, P.RADIUS_L)
        p.fillPath(path, QColor(bg))
        p.setPen(QPen(QColor(border), P.BORDER_W))
        p.drawPath(path)
        inner = QRectF(self.rect()).adjusted(self.INSET, self.INSET, -self.INSET, -self.INSET)
        if state == "waiting":
            p.setPen(QColor(fg))
            f = QFont(self.font())
            f.setPixelSize(P.BODY)
            p.setFont(f)
            p.drawText(inner, int(Qt.AlignmentFlag.AlignCenter), "Waiting for the next question")
            p.end()
            return
        # Top row: icon on the left, key badge on the right.
        if self.icon:
            draw_icon(p, "check" if state == "selected" else self.icon,
                      QRectF(inner.left(), inner.top(), 48, 48), fg)
        badge = QRectF(inner.right() - 48, inner.top(), 48, 48)
        if state == "lit":     # keep the flash plain white: outline only, no filled block
            p.setPen(QPen(QColor(P.TILE_LIT_TEXT), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P.ACCENT))
        p.drawRoundedRect(badge, P.RADIUS_S, P.RADIUS_S)
        p.setPen(QColor(P.TILE_LIT_TEXT if state == "lit" else P.ON_ACCENT))
        f = QFont(self.font())
        f.setPixelSize(P.CAPTION + 8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), self.key)
        # Title, centred and fitted.
        f = QFont(self.font())
        f.setPixelSize(self.font_px)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(self.title_rect(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                   self._label)
        # One-line description at the bottom, elided if too long.
        description = "Sent to output" if state == "selected" else self.description
        if description:
            f = QFont(self.font())
            for px in range(P.CAPTION + 2, 14, -1):        # shrink a little before eliding
                f.setPixelSize(px)
                if QFontMetrics(f).horizontalAdvance(description) <= inner.width():
                    break
            p.setFont(f)
            p.setPen(QColor(sub))
            text = QFontMetrics(f).elidedText(description, Qt.TextElideMode.ElideRight,
                                              int(inner.width()))
            p.drawText(QRectF(inner.left(), inner.bottom() - self.BOTTOM + 8, inner.width(), self.BOTTOM - 8),
                       int(Qt.AlignmentFlag.AlignCenter), text)
        p.end()


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
        self.eye_confirm: Optional[bool] = None   # False once eye-closure calibration failed (#103)
        self.eye_off_reason = "its calibration failed"   # shown when eye_confirm is False (#172)
        self._preview: Optional[Choice] = None
        self.setWindowTitle("Signal2Speech")
        self.setStyleSheet(_STYLE)
        self.resize(1280, 800)

        root = QWidget(objectName="root")
        col = QVBoxLayout(root)
        col.setContentsMargins(P.XL, P.L, P.XL, 0)
        col.setSpacing(P.M)

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
        row.setSpacing(P.XL)
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
        srow.setContentsMargins(P.M, P.S + 2, P.M, P.S + 2)
        srow.setSpacing(P.L)
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
        self.input_label.setStyleSheet(f"color:{_INPUT_COLORS.get(source, P.STRIP_TEXT)};"
                                       "font-weight:700;")

    def set_input_text(self, text: str, color_source: str) -> None:
        """Name two inputs at once, e.g. 'Choose: Keyboard · Confirm: Live EEG (PiEEG Octopus 16)'
        (#172). ``input_source`` stays the chooser's; the colour is the confirm's when it's on."""
        self.input_label.setText(text)
        self.input_label.setToolTip(text)
        self.input_label.setStyleSheet(f"color:{_INPUT_COLORS.get(color_source, P.STRIP_TEXT)};"
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
        """The Confirm-round hint, matching what really confirms (#103)."""
        if self.eye_confirm is False:
            return (f"Confirm: key 1  (eye-closure confirm is off: {self.eye_off_reason})   ·   "
                    "Cancel: key 2 or Esc")
        if (self.input_source == InputSources.LIVE_EEG
                and not self.handler.live_eeg_confirm_armed):
            return ("Confirm: key 1  (eye-closure confirm is off until #23 says it's safe)   ·   "
                    "Cancel: key 2 or Esc")
        return "Confirm: close your eyes for 2 s, or key 1   ·   Cancel: key 2 or Esc"

    def show_round(self, rnd: Round) -> None:
        self.flasher.stop()
        for target, tile in self.tiles.items():
            c = rnd.find(target)
            tile.set_label(c.label if c else "", c.action_id if c else None)
        self._set_round_text(rnd)
        self._last_round = rnd
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
            self.hint.setText("Look at a tile, or press 1 or 2   ·   Esc clears" if self.flash_enabled
                              else "Press 1 or 2   ·   Esc clears")
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
            last = getattr(self, "_last_round", None)
            self.reset()
            self.prompt.setText("Confirmed · sent to output")
            chosen = last.find(e.targetId) if (last is not None and e is not None) else None
            tile = self.tiles.get(e.targetId) if e is not None else None
            if chosen is not None and tile is not None:
                tile.set_label(chosen.label, chosen.action_id)
                tile.set_selected(True)

    # ── Helpers ──────────────────────────────────────────────
    PREVIEW_MAX_PX = P.PREVIEW

    def add_outcome_note(self, note: str) -> None:
        """Append e.g. "map 3 ms · speech 180 ms" to the last outcome in the strip (#130)."""
        base = self.outcome_label.text().split("  ⏱ ")[0]
        self.outcome_label.setText(f"{base}  ⏱ {note}")
        self.outcome_label.setToolTip(self.outcome_label.text())

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
        width = max(self.width() - 2 * P.XL - 2 * P.M - 6, 1)   # margins, padding, accent bar
        height = max(int(self.height() * 0.28), 80)
        self.preview_px = fit_pixel_size(self.preview.text(), font, width, height,
                                         self.PREVIEW_MAX_PX, P.TILE_TITLE_MIN)
        self.preview.setStyleSheet(f"font-size: {self.preview_px}px;")

    def _preview_text(self) -> str:
        c = self._preview
        return (c.spoken_text or c.label) if c else ""

    def _set_tile_lit(self, target_id: str, lit: bool) -> None:
        tile = self.tiles.get(target_id)
        if tile is not None:
            tile.set_lit(lit)
            tile.repaint()   # synchronous, so on_flash fires after the lit frame is painted
