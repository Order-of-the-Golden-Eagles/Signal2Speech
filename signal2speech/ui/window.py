"""PySide6 selection window (#24).

The window only renders SelectionHandler events and calls InputAdapter / handler.cancel().
It never maps targets to actions, plays audio, or changes the map. Call everything on the Qt
main thread: SelectionHandler is not thread-safe.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPlainTextEdit, QSizePolicy, QTextEdit, QVBoxLayout, QWidget)

from signal2speech.core import (ActionIds, Choice, InputAdapter, InputSources, Outcome, Round, RoundKind,
                                SelectionEvent, SelectionHandler, TargetIds)

from .confirm_ring import HOLD_S, ConfirmRing
from .fit import fit_pixel_size
from .flash import FlashScheduler
from .fade import fade_in
from .icons import draw_emoji, draw_icon
from . import theme as P

INPUT_LABELS = {InputSources.KEYBOARD: "Keyboard", InputSources.SIMULATED: "Simulated",
                InputSources.RECORDED: "Recorded", InputSources.LIVE_EEG: "Live EEG"}

# What judges read in the strip (#179): one plain sentence per outcome. The exact outcome name,
# event and round go to the developer log and the tooltip. tests/ check every Outcome is here.
# At most ~29 characters: the strip shares one line with the input badge at 1280 x 720.
SENTENCE_MAX = 29
OUTCOME_SENTENCES = {
    Outcome.Previewed: "Preview shown. Nothing said.",
    Outcome.Confirmed: "Confirmed: shown, said once.",
    Outcome.Cancelled: "Nothing said: cancelled.",
    Outcome.RejectedNoOpenRound: "Ignored: no question open.",
    Outcome.RejectedStaleRound: "Ignored a late signal.",
    Outcome.RejectedDuplicateEvent: "Ignored a repeated signal.",
    Outcome.RejectedRoundConsumed: "Ignored: already answered.",
    Outcome.RejectedUnknownTarget: "Ignored: not on screen.",
    Outcome.RejectedUnknownSource: "Ignored an unknown input.",
    Outcome.RejectedMalformed: "Ignored a broken signal.",
    Outcome.RejectedLiveConfirmDisarmed: "Eye closure off: hold 1.",
}
CLEARED_SENTENCES = {
    "cancel": "Nothing said: cancelled.",
    "timeout": "Nothing said: timed out.",
    "disconnect": "Nothing said: disconnected.",
    "restart": "Restarted for a new visitor.",
    "practice": "Practice: nothing is sent.",
}


def plain_outcome(outcome: Outcome) -> str:
    return OUTCOME_SENTENCES.get(outcome, outcome.value)


def plain_cleared(reason: str) -> str:
    return CLEARED_SENTENCES.get(reason, f"Nothing said: cleared ({reason}).")


def badge_style(source: str) -> str:
    """The strip's pill filled with the input's colour (#179), the same colour as the evidence
    banner. Shape and padding come from the strip's pill style (``QLabel.strip``)."""
    bg = P.BADGE_COLORS.get(source, P.RAISED)
    fg = P.BADGE_TEXT.get(source, P.TEXT)
    return f"background:{bg}; color:{fg}; border:1px solid {bg}; font-weight:700;"

_TILE_ORDER = (TargetIds.TARGET_1, TargetIds.TARGET_2)

_STYLE = P.window_qss()


_MAP_ACTIONS = {ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY}


class _KeyOne(QObject):
    """App-wide filter for keys 1 and 2, so a hold can be told apart from a tap (#175). Typing a
    1 or 2 in a text field (the AI question box) is left alone."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if t not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        if (event.key() not in (Qt.Key.Key_1, Qt.Key.Key_2) or event.isAutoRepeat()
                or event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier):
            return False
        if isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QPlainTextEdit)):
            return False
        if not self.window.isVisible() and not getattr(self.window, "_test_keys", False):
            return False
        pressed = t == QEvent.Type.KeyPress
        if event.key() == Qt.Key.Key_1:
            self.window.key_one(pressed)
        else:
            self.window.key_two(pressed)
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

    MAX_PX = P.TILE_TITLE             # tile titles at full size, before the text scale (#195)
    HEIGHT = 250                      # a tile is a target to look at, not a poster

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
        self.setMinimumSize(240, 190)   # fits two tiles plus the map at 1280x720 (#94, #195)
        self.setMaximumHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def sizeHint(self) -> QSize:      # the height it takes when there's room; it never grows past it
        return QSize(300, self.HEIGHT)

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
        tint = P.ACTION_TINT.get(self.action_id) if state == "idle" else None
        if tint:
            border = tint
        if self.highlight and state == "idle":
            border = P.ACCENT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = P.BORDER_W / 2
        body = QRectF(self.rect()).adjusted(half, half, -half, -half)
        path = QPainterPath()
        path.addRoundedRect(body, P.RADIUS_L, P.RADIUS_L)
        p.fillPath(path, QColor(bg))
        if tint:                                   # a faint wash of the tile's own colour
            wash = QColor(tint)
            wash.setAlphaF(P.TINT_BG_ALPHA)
            p.fillPath(path, wash)
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
            box = QRectF(inner.left(), inner.top(), 48, 48)
            if state == "lit":      # the flash stays plain black on white, exactly as before
                draw_icon(p, self.icon, box, fg)
            else:
                draw_emoji(p, "check" if state == "selected" else self.icon, box)
        badge = QRectF(inner.right() - 48, inner.top(), 48, 48)
        if state == "lit":     # keep the flash plain white: outline only, no filled block
            p.setPen(QPen(QColor(P.TILE_LIT_TEXT), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(tint or P.ACCENT))
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


class ElidedLabel(QLabel):
    """Shows as much of its text as fits, ending in "…", never a word cut in half (#179)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._full = ""

    def setText(self, text: str) -> None:
        self._full = text
        self._elide()

    def fullText(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width()
        shown = self._full if width <= 0 else self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, width)
        super().setText(shown)

    def _hint_for(self, hint, text: str):
        # Qt's hint is for the text shown now, plus the pill's padding and border. Swap the text.
        fm = self.fontMetrics()
        hint.setWidth(hint.width() - fm.horizontalAdvance(super().text()) + fm.horizontalAdvance(text))
        return hint

    def minimumSizeHint(self):
        return self._hint_for(super().minimumSizeHint(), "● …")

    def sizeHint(self):
        return self._hint_for(super().sizeHint(), self._full)


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
        # Three bands. The tiles sit in the middle one and never move: the prompt and the preview
        # live above them, the countdown and the hint below, and the two outer bands share the
        # spare height equally, which keeps the tiles centred.
        top = QVBoxLayout()
        top.setSpacing(P.M)
        col.addLayout(top, 1)
        top.addWidget(self.prompt)
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
        # Cancelling takes the same deliberate hold as confirming: a stray tap on 2 must not
        # throw away what the wearer just chose.
        self.ring.handlers["cancel"] = lambda: self.press_target(TargetIds.TARGET_2)
        self._held_key: Optional[int] = None       # which key is filling the ring: 1 or 2
        prow.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)
        pcol.addLayout(prow)
        self.preview_box.setVisible(False)
        top.addWidget(self.preview_box)
        top.addStretch(1)
        # Seconds left before an unanswered Confirm round cancels (#26, #96). App drives it.
        self.countdown = QLabel("", objectName="countdown")
        self.countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown.setVisible(False)

        row = QHBoxLayout()
        row.setSpacing(P.XL)
        self.tiles: Dict[str, Tile] = {}
        for key, target in zip("12", _TILE_ORDER):
            tile = Tile(target, key)
            self.tiles[target] = tile
            row.addWidget(tile, 1)
        col.addLayout(row, 0)

        self.hint = QLabel("", objectName="hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)       # large text (#195) must wrap, not widen the window
        bottom = QVBoxLayout()
        bottom.setSpacing(P.M)
        bottom.addWidget(self.countdown)
        bottom.addWidget(self.hint)
        bottom.addStretch(1)
        col.addLayout(bottom, 1)
        for held in (*self.tiles.values(), self.hint, self.countdown):   # hidden, but keep their place
            policy = held.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            held.setSizePolicy(policy)

        strip = QFrame(objectName="strip")
        srow = QVBoxLayout(strip)
        srow.setContentsMargins(P.L, P.S, P.L, P.M)
        srow.setSpacing(P.S)
        self._strip_rows = (QHBoxLayout(), QHBoxLayout())
        for r in self._strip_rows:
            r.setSpacing(P.M)
            srow.addLayout(r)
        self._strip_long: Optional[bool] = None
        self._connection_on = False        # an EEG input has a connection to show (#179)
        # Two inputs, a device name and a status make a long line (recorded input #104, PiEEG
        # #172). Long input badges get a line of their own across the strip (see _layout_strip);
        # they still wrap as a last resort, so the window never grows past the screen to fit them.
        self.input_label = WrapWhenLong(limit=110)
        self.input_label.setProperty("class", "strip")
        # #179: a second badge when choose and confirm use different inputs (PiEEG, #172).
        self.confirm_badge = WrapWhenLong(limit=60)
        self.confirm_badge.setProperty("class", "strip")
        self.confirm_badge.setVisible(False)
        self.connection_label = ElidedLabel()
        self.connection_label.setProperty("class", "strip")
        self.round_label = self._strip_label()
        self.outcome_label = self._strip_label()
        # Badges hug their text and never clip: they are what keeps simulated input from
        # looking live (#179). A long one wraps as a last resort.
        for badge in (self.input_label, self.confirm_badge):
            badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        # #179: round ids live in the developer log and the outcome's tooltip. The label stays
        # (practice and tests read it) but isn't shown to judges.
        self.round_label.setVisible(False)
        # The plain sentence never shrinks below its text: fonts differ by machine, so it can't
        # rely on a fixed width. The connection state gives way instead, down to "● …".
        self.outcome_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.connection_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.connection_label.setMaximumWidth(P.px(self.CONNECTION_MAX_PX))
        self._layout_strip(False)
        col.addWidget(strip)
        self.strip = strip                 # App moves it to span the whole window
        self.setCentralWidget(root)

        self.set_input_source(input_source)
        self.set_connection("n/a" if input_source == InputSources.KEYBOARD else "unknown")
        self._set_round_text(None)
        self._set_sentence("", "")

        self.flasher = FlashScheduler(self._set_tile_lit, on_flash,
                                      on_sequence_started=on_sequence_started,
                                      on_sequence_finished=on_sequence_finished, parent=self)

        # Esc is the operator's instant cancel. Keys 1 and 2 go through the key filter below,
        # because in a Confirm round both must be held.
        for seq, fn in (("Esc", self.press_cancel),):
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

    #: Input badges longer than this (together) get their own line in the strip.
    STRIP_LONG_LABEL = 40

    def _layout_strip(self, long_label: bool) -> None:
        """One row when the input badges are short. When they are long, they take the first row
        to themselves and the sentence and connection go on the second."""
        if long_label == self._strip_long:
            return
        self._strip_long = long_label
        first, second = self._strip_rows
        for row in (first, second):
            while row.count():
                row.takeAt(0)
        first.addWidget(self.input_label)
        first.addWidget(self.confirm_badge)
        rest = second if long_label else first
        for pill in (self.round_label, self.outcome_label, self.connection_label):
            rest.addWidget(pill)
        first.addStretch(1)                # keeps the pills on the left, not spread out
        second.addStretch(1)

    def set_input_source(self, source: str) -> None:
        """Label the decoder actually feeding the handler, so Simulated never reads as Live."""
        self.input_source = source
        self._layout_strip(False)
        self.input_label.setText(f"Input: {INPUT_LABELS.get(source, source)}")
        self.input_label.setToolTip(self.input_label.text())
        self.input_label.setStyleSheet(badge_style(source))
        self.confirm_badge.setVisible(False)

    def set_two_inputs(self, choose_text: str, choose_source: str,
                       confirm_text: str, confirm_source: str) -> None:
        """Both badges when choose and confirm use different inputs, each in its own colour
        (#172, #179, #104), e.g. [Choose: Keyboard] [Confirm: Live EEG (PiEEG Octopus 16)].
        ``input_source`` stays the chooser's."""
        self._layout_strip(len(choose_text) + len(confirm_text) > self.STRIP_LONG_LABEL)
        self.input_label.setText(choose_text)
        self.input_label.setToolTip(choose_text)
        self.input_label.setStyleSheet(badge_style(choose_source))
        self.confirm_badge.setText(confirm_text)
        self.confirm_badge.setToolTip(confirm_text)
        self.confirm_badge.setStyleSheet(badge_style(confirm_source))
        self.confirm_badge.setVisible(True)

    def _set_sentence(self, text: str, tip: str) -> None:
        """The plain sentence judges read, and the exact outcome for developers (#179). An
        empty pill would look like a broken badge, so there's no pill until something happens."""
        self.outcome_label.setText(text)
        self.outcome_label.setToolTip(tip)
        self.outcome_label.setVisible(bool(text))

    @property
    def has_connection(self) -> bool:
        """An EEG input reported a connection (keyboard has none)."""
        return self._connection_on

    def set_connection(self, state: str) -> None:
        """A short state in the strip (the part before the first " · ", shortened with "…" if it
        still doesn't fit); the full text is in the tooltip and the session report (#179)."""
        self.connection_label.setText(f"● {state.split(' · ')[0]}")
        self.connection_label.setToolTip(f"Connection: {state}")
        # Keyboard has no connection to report; hide "n/a" so small screens keep room (#94).
        self._connection_on = state != "n/a"
        self.connection_label.setVisible(self._connection_on)

    def _set_round_text(self, rnd: Optional[Round]) -> None:
        self.round_label.setText(f"Round: {rnd.id} ({rnd.kind.value})" if rnd else "Round: —")

    # ── Keys (the only calls into core) ──────────────────────
    def press_target(self, target_id: str) -> Outcome:
        outcome = self.keyboard.select_now(target_id)
        if outcome is Outcome.RejectedNoOpenRound:   # select_now returns before handle()
            self._set_sentence(plain_outcome(outcome), f"{outcome.value} · keyboard {target_id}")
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
                    "Cancel: hold 2, or Esc")
        if (self.input_source == InputSources.LIVE_EEG
                and not self.handler.live_eeg_confirm_armed):
            return ("Confirm: hold 1  (eye-closure confirm is off until #23 says it's safe)   ·   "
                    "Cancel: hold 2, or Esc")
        return "Confirm: close your eyes for 2 s, or hold 1   ·   Cancel: hold 2, or Esc"

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
        self._hold_or_tap(1, pressed, "keyboard", TargetIds.TARGET_1)

    def key_two(self, pressed: bool) -> None:
        """Physical key 2. Choose round: a tap picks. Confirm round: hold to cancel."""
        self._hold_or_tap(2, pressed, "cancel", TargetIds.TARGET_2)

    def _hold_or_tap(self, key: int, pressed: bool, ring_source: str, target: str) -> None:
        if not pressed:
            if self._held_key == key:               # letting go early empties the ring
                self._held_key = None
                self.ring.release()
            return
        rnd = self.handler.current
        if rnd is not None and rnd.kind is RoundKind.CONFIRM:
            if self._held_key is None:              # the first key down owns the ring
                self._held_key = key
                self.ring.start_hold(ring_source, HOLD_S)
        else:
            self.press_target(target)

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
            was_hidden = self.preview_box.isHidden()
            self.preview_box.setVisible(True)
            if was_hidden:
                fade_in(self.preview_box, P.BG)       # the words arrive, they don't pop
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
            self._set_sentence(plain_cleared(reason), f"Cleared ({reason})")

    def show_outcome(self, e: Optional[SelectionEvent], outcome: Outcome) -> None:
        detail = f" · {e.source} {e.eventId} {e.roundId}→{e.targetId}" if e else ""
        self._set_sentence(plain_outcome(outcome), f"{outcome.value}{detail}")   # exact in the tip
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
                was_hidden = self.preview_box.isHidden()
                self.preview_box.setVisible(True)
                if was_hidden:
                    fade_in(self.preview_box, P.BG)       # the words arrive, they don't pop
            self.prompt.setText("Confirmed · sent to output")
            chosen = last.find(e.targetId) if (last is not None and e is not None) else None
            tile = self.tiles.get(e.targetId) if e is not None else None
            if chosen is not None and tile is not None:
                tile.set_label(chosen.label, chosen.action_id)
                tile.set_selected(True)

    # ── Helpers ──────────────────────────────────────────────
    PREVIEW_MAX_PX = P.PREVIEW        # before the text scale (#195)
    PREVIEW_MIN_PX = P.PREVIEW_MIN
    CONNECTION_MAX_PX = 240           # the strip's connection state, before the text scale

    def apply_text_scale(self) -> None:
        """Re-style after theme.set_scale (#195). Tiles and preview refit; flashing is untouched."""
        self.setStyleSheet(P.window_qss())
        self.connection_label.setMaximumWidth(P.px(self.CONNECTION_MAX_PX))   # #179
        for tile in self.tiles.values():
            tile._fit()
            tile.update()
        self._fit_preview()

    def add_outcome_note(self, note: str) -> None:
        """Append e.g. "map 3 ms · speech 180 ms" to the last outcome in the strip (#130)."""
        base = self.outcome_label.text().split("  ⏱ ")[0]
        self.outcome_label.setText(f"{base}  ⏱ {note}")
        tip = self.outcome_label.toolTip().split("  ⏱ ")[0]
        self.outcome_label.setToolTip(f"{tip}  ⏱ {note}")

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
        width = max(self.width() - 2 * P.XL - 2 * P.M - 6 - self.ring.width() - P.L, 1)   # margins, accent bar, ring
        height = max(int(self.height() * 0.28), 80)
        self.preview_px = fit_pixel_size(self.preview.text(), font, width, height,
                                         P.px(self.PREVIEW_MAX_PX), self.PREVIEW_MIN_PX)
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
