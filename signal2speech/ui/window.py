"""PySide6 selection window (#24).

The window only renders SelectionHandler events and calls InputAdapter / handler.cancel().
It never maps targets to actions, plays audio, or changes the map. Call everything on the Qt
main thread: SelectionHandler is not thread-safe.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPlainTextEdit, QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

from signal2speech.core import (ActionIds, Choice, InputAdapter, InputSources, Outcome, Round, RoundKind,
                                SelectionEvent, SelectionHandler, TargetIds)

from .confirm_ring import HOLD_S, ConfirmRing
from .fit import fit_pixel_size
from .flash import FlashScheduler
from .icons import draw_icon
from . import theme as P

INPUT_LABELS = {InputSources.KEYBOARD: "Keyboard", InputSources.SIMULATED: "Simulated",
                InputSources.RECORDED: "Recorded", InputSources.LIVE_EEG: "Live EEG"}
_INPUT_COLORS = P.INPUT_COLORS
_TILE_ORDER = (TargetIds.TARGET_1, TargetIds.TARGET_2)

_STYLE = P.window_qss()


_MAP_ACTIONS = {ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY}


class _KeyOne(QObject):
    """App-wide filter for key 1, so a hold can be told apart from a tap (#175). Typing a 1 in a
    text field (the AI question box) is left alone."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if t not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if event.key() != Qt.Key.Key_1 or event.isAutoRepeat() or event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier:
            return False
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False
        if not self.window.isVisible() and not getattr(self.window, "_test_keys", False):
            return False
        self.window.key_one(t == QEvent.Type.KeyPress)
        return True


CAPTION_ROW = 40


class Tile(QLabel):
    """One frozen choice tile, drawn by hand (#174): icon, title, one-line description, and
    the key as a corner badge.

    States: idle, flashing (lit), selected (the confirmed choice), and waiting (no round open).
    Flashing looks exactly as before: plain white with black content, so the stimulus the
    P300 classifier sees is unchanged. Flashing never relabels, moves, or resizes a tile.
    Long titles shrink to fit (56 px down to 32 px, #95), recomputed on relabel and resize only.
    """

    INSET = P.BORDER_W + P.L          # border + padding, each side
    TOP = 64                          # icon and key badge row

    MAX_PX = P.DISPLAY                # tile titles at full size, before the text scale (#195)

    @property
    def BOTTOM(self) -> int:          # one-line description row
        return max(40, P.px(CAPTION_ROW))

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
        self.note: Optional[str] = None   # replaces the description (practice round, #196)
        self.highlight = False            # accent outline: "look here" (practice round, #196)
        self.font_px = self.MAX_PX
        self.setMinimumSize(300, 210)   # fits two tiles plus the map at 1280x720 (#94, #195)

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
        self.note = None
        self.highlight = False
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
                            P.px(self.MAX_PX), P.TILE_TITLE_MIN)
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
        if self.highlight and state == "idle":
            border = P.ACCENT
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
            f.setPixelSize(P.px(P.BODY))
            p.setFont(f)
            p.drawText(inner, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       "Waiting for the next question")
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
        f.setPixelSize(P.px(P.CAPTION + 8))
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
        description = ("Sent to output" if state == "selected"
                       else self.note if self.note is not None else self.description)
        if description:
            f = QFont(self.font())
            for px in range(P.px(P.CAPTION + 2), 14, -1):  # shrink a little before eliding
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


class WrapWhenLong(QLabel):
    """A label that wraps only when its text is long. Short text keeps the height it always had;
    long text wraps instead of forcing the window wider than the screen."""

    def __init__(self, text: str = "", limit: int = 44, **kwargs):
        super().__init__(**kwargs)
        self.limit = limit
        self.setText(text)

    def setText(self, text: str) -> None:
        self.setWordWrap(len(text) > self.limit)
        super().setText(text)


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
        self.on_escape: Optional[Callable[[], bool]] = None   # return True to consume Esc
        self.setWindowTitle("Signal2Speech")
        self.setStyleSheet(_STYLE)
        self.resize(1280, 800)

        root = QWidget(objectName="root")
        col = QVBoxLayout(root)
        col.setContentsMargins(P.XL, P.L, P.XL, 0)
        col.setSpacing(P.M)

        # A long prompt wraps, so it can never widen the window past the screen. Short ones
        # don't: a wrapping label asks for more height, and that pushed the preview screen over
        # 720 at the largest text size.
        self.prompt = WrapWhenLong("Waiting for a round", objectName="prompt")
        col.addWidget(self.prompt)
        # #175: the consent screen. What will happen, the exact words, and the confirm ring.
        self.preview_box = QWidget()
        pcol = QVBoxLayout(self.preview_box)
        pcol.setContentsMargins(0, 0, 0, 0)
        pcol.setSpacing(P.S)
        self.preview_header = QLabel("", objectName="previewHeader")
        pcol.addWidget(self.preview_header)
        prow = QHBoxLayout()
        prow.setSpacing(P.L)
        self.preview = QLabel("", objectName="preview")
        self.preview.setWordWrap(True)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prow.addWidget(self.preview, 1)
        self.ring = ConfirmRing()
        self.ring.handlers["keyboard"] = lambda: self.press_target(TargetIds.TARGET_1)
        prow.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)
        pcol.addLayout(prow)
        self.preview_box.setVisible(False)
        col.addWidget(self.preview_box)
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
        self.hint.setWordWrap(True)       # large text (#195) must wrap, not widen the window
        col.addWidget(self.hint)

        strip = QFrame(objectName="strip")
        srow = QHBoxLayout(strip)
        srow.setContentsMargins(P.M, P.S + 2, P.M, P.S + 2)
        srow.setSpacing(P.L)
        # Two inputs, a device name and a status make a long line (PiEEG, #172). Then it wraps,
        # so the window never has to grow past the screen to fit it.
        self.input_label = WrapWhenLong(limit=60)
        self.input_label.setProperty("class", "strip")
        self.connection_label = self._strip_label()
        self.round_label = self._strip_label()
        self.outcome_label = self._strip_label()
        srow.addWidget(self.input_label)
        # At large text sizes (#195) the round id may clip; the input label never does.
        self.round_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.round_label.setMinimumWidth(1)
        srow.addWidget(self.round_label, 1)
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
        for seq, fn in (("2", lambda: self.press_target(TargetIds.TARGET_2)),
                        ("Esc", self.press_cancel)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setAutoRepeat(False)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

        # Key 1: a tap picks in a Choose round; in a Confirm round it must be HELD for HOLD_S
        # seconds (#175), so it needs press and release events, not a shortcut.
        self._key_filter = _KeyOne(self)
        QApplication.instance().installEventFilter(self._key_filter)

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
        if self.on_escape is not None and self.on_escape():
            return                         # e.g. Esc ended a practice round (#196)
        self.handler.cancel()

    # ── Handler listeners ────────────────────────────────────
    def confirm_hint(self) -> str:
        """The Confirm-round hint, matching what really confirms (#103)."""
        if self.eye_confirm is False:
            return (f"Confirm: hold 1  (eye-closure confirm is off: {self.eye_off_reason})   ·   "
                    "Cancel: key 2 or Esc")
        if (self.input_source == InputSources.LIVE_EEG
                and not self.handler.live_eeg_confirm_armed):
            return ("Confirm: hold 1  (eye-closure confirm is off until #23 says it's safe)   ·   "
                    "Cancel: key 2 or Esc")
        return "Confirm: close your eyes for 2 s, or hold 1   ·   Cancel: key 2 or Esc"

    def eyes_can_confirm(self) -> bool:
        """Whether an eye closure can confirm right now (mirrors confirm_hint)."""
        if self.eye_confirm is False or self.input_source == InputSources.KEYBOARD:
            return False
        if self.input_source == InputSources.LIVE_EEG and not self.handler.live_eeg_confirm_armed:
            return False
        return True

    def set_eye_progress(self, progress: float, source: str = "eyes") -> None:
        """The alpha switch's progress towards a confirm (0-1), on the main thread (#175)."""
        rnd = self.handler.current
        if rnd is not None and rnd.kind is RoundKind.CONFIRM and self.eyes_can_confirm():
            self.ring.set_external(progress, source)

    def key_one(self, pressed: bool) -> None:
        """Physical key 1. Choose round: a tap picks. Confirm round: hold to fill the ring."""
        rnd = self.handler.current
        if rnd is not None and rnd.kind is RoundKind.CONFIRM:
            if pressed:
                self.ring.start_hold("keyboard", HOLD_S)
            else:
                self.ring.release()
        elif pressed:
            self.press_target(TargetIds.TARGET_1)

    def show_round(self, rnd: Round) -> None:
        self.flasher.stop()
        self.prompt.setVisible(True)
        for target, tile in self.tiles.items():
            c = rnd.find(target)
            tile.set_label(c.label if c else "", c.action_id if c else None)
        self._set_round_text(rnd)
        self._last_round = rnd
        if rnd.kind is RoundKind.CONFIRM:
            self.prompt.setText("Say this?")
            self.preview_header.setText(self._preview_header())
            self.preview.setText(f"“{self._preview_text()}”")
            self.ring.reset()
            self.ring.label = "Hold 1\nor close eyes" if self.eyes_can_confirm() else "Hold 1"
            self.preview_box.setVisible(True)
            self._fit_preview()
            self.hint.setText(self.confirm_hint())
        else:
            self._preview = None
            self.prompt.setText("Choose a reply")
            self.set_countdown(None)
            self.ring.reset()
            self.preview_box.setVisible(False)
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
        self.ring.reset()
        self.preview_box.setVisible(False)
        self.preview.setText("")
        self.preview.setMinimumHeight(0)
        self.preview_header.setText("")
        self.hint.setText("")
        self.prompt.setText("Waiting for a round")
        self.prompt.setVisible(True)
        self._set_round_text(None)
        if reason:
            self.outcome_label.setText(f"Last: Cleared ({reason})")

    def show_outcome(self, e: Optional[SelectionEvent], outcome: Outcome) -> None:
        detail = f" · {e.source} {e.eventId} {e.roundId}→{e.targetId}" if e else ""
        self.outcome_label.setText(f"Last: {outcome.value}{detail}")
        self.outcome_label.setToolTip(self.outcome_label.text())
        if outcome is Outcome.Confirmed:   # handler closed the round without on_cleared
            last = getattr(self, "_last_round", None)
            spoken = self._preview
            filled_by = self.ring.model.source or (e.source if e is not None else None)
            self.reset()
            if spoken is not None:
                self.preview_header.setText("✓ Shown and spoken" if spoken.action_id in _MAP_ACTIONS
                                            else "✓ Spoken")
                self.preview.setText(f"“{spoken.spoken_text or spoken.label}”")
                self.ring.mark_confirmed(filled_by)
                self.preview_box.setVisible(True)
            self.prompt.setText("Confirmed · sent to output")
            chosen = last.find(e.targetId) if (last is not None and e is not None) else None
            tile = self.tiles.get(e.targetId) if e is not None else None
            if chosen is not None and tile is not None:
                tile.set_label(chosen.label, chosen.action_id)
                tile.set_selected(True)

    # ── Helpers ──────────────────────────────────────────────
    PREVIEW_MAX_PX = P.PREVIEW        # before the text scale (#195)

    def apply_text_scale(self) -> None:
        """Re-style after theme.set_scale (#195). Tiles and preview refit; flashing is untouched."""
        self.setStyleSheet(P.window_qss())
        for tile in self.tiles.values():
            tile._fit()
            tile.update()
        self._fit_preview()

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
        width = max(self.width() - 2 * P.XL - 2 * P.M - 6 - 150 - P.L, 1)   # margins, accent bar, ring
        height = max(int(self.height() * 0.28), 80)
        self.preview_px = fit_pixel_size(self.preview.text(), font, width, height,
                                         P.px(self.PREVIEW_MAX_PX), P.TILE_TITLE_MIN)
        self.preview.setStyleSheet(f"font-size: {self.preview_px}px;")
        # Reserve the fitted text's height, so the layout squeezes the tiles, never the words.
        font.setPixelSize(self.preview_px)
        text = QFontMetrics(font).boundingRect(0, 0, width, 10_000, int(Qt.TextFlag.TextWordWrap),
                                               self.preview.text())
        rnd = self.handler.current
        confirming = rnd is not None and rnd.kind is RoundKind.CONFIRM and bool(self.preview.text())
        self.preview.setMinimumHeight(text.height() + 2 * P.M + 4 if confirming else 0)
        # At large text sizes (#195) the header already says what's happening; drop the
        # "Say this?" prompt during a preview so everything fits a 1280x720 screen.
        if self.preview_box.isVisibleTo(self) and self.prompt.text() == "Say this?":
            self.prompt.setVisible(P.SCALE <= 1.2)
        elif not self.prompt.isVisibleTo(self):
            self.prompt.setVisible(True)

    def _preview_header(self) -> str:
        c = self._preview
        if c is not None and c.action_id in _MAP_ACTIONS:
            return "This will show the map and say:"
        return "This will be said aloud:"

    def _preview_text(self) -> str:
        c = self._preview
        return (c.spoken_text or c.label) if c else ""

    def _set_tile_lit(self, target_id: str, lit: bool) -> None:
        tile = self.tiles.get(target_id)
        if tile is not None:
            tile.set_lit(lit)
            tile.repaint()   # synchronous, so on_flash fires after the lit frame is painted
