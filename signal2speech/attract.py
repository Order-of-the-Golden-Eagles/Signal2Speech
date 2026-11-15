"""Attract mode (#193): loop a narrated, clearly labelled simulated demo when the table is idle.

After IDLE_MS with no key press, mouse click, or input outcome, a second, self-contained App
runs over the main one. It uses the simulated input (the scripted g.Pype decoder when g.Pype
is installed, else the scripted fallback), so the loop goes through the same handler, preview,
confirm ring, map reveal, and AppSink as a real pick. Nothing calls a sink directly.

Isolation by construction: the loop has its own handler, sink, conversation, and log, so its
picks never reach the main session or its report counts. Any key, click, or input outcome on
the main app stops it at once: the key is swallowed (it doesn't also pick a tile), pending
speech in the loop is cancelled, the loop's widgets are deleted, and the main app is left on a
clean Choose round.

A large "Simulated demo" banner is on screen for the whole loop. Narration is on-screen
captions, so it never talks over the spoken reply.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from signal2speech.core import InputSources, Outcome, RoundKind
from signal2speech.ui import theme as T

IDLE_MS = 60_000
SCRIPT = (2, 1)          # compare counties, then confirm: the map payoff
BANNER = "SIMULATED DEMO  ·  not a live headset  ·  press any key to try it"
STEPS = {
    "choose": "1 · The tiles flash. The wearer looks at the reply they want.",
    "preview": "2 · The pick is previewed. Nothing is said yet.",
    "confirm": "3 · To say it, the wearer closes their eyes until the ring fills.",
    "said": "4 · Confirmed: the map changes and the reply is spoken, once.",
    "cleared": "Nothing was said. The next question opens in a moment.",
}
_WAKE_EVENTS = (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress)


class AttractMode(QObject):
    def __init__(self, app, *, idle_ms: int = IDLE_MS,
                 make_demo: Optional[Callable[[], object]] = None, parent: Optional[QObject] = None):
        super().__init__(parent or app.root)
        self.app = app
        self.make_demo = make_demo or self._default_demo
        self.enabled = True
        self.active = False
        self.demo = None
        self.overlay: Optional[QWidget] = None
        self.banner: Optional[QLabel] = None
        self.caption: Optional[QLabel] = None
        self.runs = 0
        self.stops: List[str] = []
        self._idle = QTimer(self, singleShot=True, interval=idle_ms)
        self._idle.timeout.connect(self.maybe_start)
        app.handler.on_handled.append(self._main_input)
        app.root.installEventFilter(self)          # keep the overlay the size of the window
        self._watch()

    # ── Idle detection ───────────────────────────────────────
    def _watch(self) -> None:
        """(Re)install the app-wide filter so it runs before every other filter, including the
        loop window's key-1 filter (Qt calls the newest filter first)."""
        qapp = QApplication.instance()
        qapp.removeEventFilter(self)
        qapp.installEventFilter(self)

    def poke(self) -> None:
        if self.enabled and not self.active:
            self._idle.start()

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if obj is self.app.root and t == QEvent.Type.Resize and self.overlay is not None:
            self.overlay.setGeometry(self.app.root.rect())
            return False
        if t == QEvent.Type.ShortcutOverride and self.active:
            event.accept()                         # no shortcut fires on the waking key
            return True
        if t in _WAKE_EVENTS:
            if self.active:
                self.stop("key" if t == QEvent.Type.KeyPress else "click")
                return True                        # the waking input doesn't also pick a tile
            self.poke()
        return False

    def _main_input(self, _e, _o) -> None:
        # A decision on the MAIN handler (keyboard, simulated, or headset) means someone's here.
        if self.active:
            self.stop("input")
        else:
            self.poke()

    def can_start(self) -> bool:
        a = self.app
        rnd = a.handler.current
        return (self.enabled and not self.active and not getattr(a, "practicing", False)
                and not a.revealing and a.handler.pending is None
                and (rnd is None or rnd.kind is RoundKind.CHOOSE))

    def maybe_start(self) -> None:
        if self.can_start():
            self.start()
        else:
            self.poke()                            # busy (preview, reveal, practice): wait again

    # ── The loop ─────────────────────────────────────────────
    def _default_demo(self):
        from signal2speech.app import App
        a = self.app
        return App(InputSources.SIMULATED, sim_script=list(SCRIPT), echo=False,
                   mute=getattr(a, "muted", False), cues=a.sink.cues is not None,
                   reopen_ms=2500, reveal_ms=7000, confirm_delay_ms=2500, attract=False)

    def start(self) -> None:
        self.active = True
        self.runs += 1
        self._idle.stop()
        demo = self.demo = self.make_demo()
        self.overlay = QWidget(self.app.root)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.overlay.setStyleSheet(f"background:{T.BG};")
        col = QVBoxLayout(self.overlay)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.banner = QLabel(BANNER)
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setStyleSheet(f"background:{T.INPUT_COLORS[InputSources.SIMULATED]}; color:{T.ON_ACCENT};"
                                  f"font-size:{T.px(T.HEADING)}px; font-weight:800; padding:{T.M}px;")
        col.addWidget(self.banner)
        self.caption = QLabel("")
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet(f"color:{T.TEXT}; font-size:{T.px(T.BODY)}px; padding:{T.S}px {T.L}px;")
        col.addWidget(self.caption)
        col.addWidget(demo.root, 1)
        self.overlay.setGeometry(self.app.root.rect())
        self.overlay.show()
        self.overlay.raise_()
        h = demo.handler
        h.on_round_opened.append(self._narrate_round)
        h.on_preview.append(lambda _c: self._say("preview"))
        h.on_handled.append(lambda _e, o: self._say("said") if o is Outcome.Confirmed else None)
        h.on_cleared.append(lambda _r: self._say("cleared"))
        self._watch()
        self.app.log(f"attract: simulated demo started (run {self.runs})")
        demo.ask()

    def _narrate_round(self, rnd) -> None:
        if rnd.kind is RoundKind.CHOOSE:
            self._refill()
            self._say("choose")
        else:
            self._say("confirm")

    def _say(self, step: str) -> None:
        if self.caption is not None:
            self.caption.setText(STEPS[step])

    def _refill(self) -> None:
        """Queue the script again for each new question, so the loop keeps going."""
        sim = getattr(self.demo, "sim", None)
        if hasattr(sim, "script"):                 # scripted fallback
            if not sim.script:
                sim.script.extend(SCRIPT)
        elif hasattr(sim, "_picks"):               # g.Pype SimulatedDecoder
            if not sim._picks:
                sim._picks.extend(SCRIPT)

    def stop(self, reason: str = "key") -> None:
        if not self.active:
            return
        self.active = False
        self.stops.append(reason)
        demo, self.demo = self.demo, None
        if demo is not None:
            demo.handler.on_round_opened.clear()   # nothing else reacts while it's torn down
            demo.handler.on_preview.clear()
            demo.handler.on_handled.clear()
            demo.handler.on_cleared.clear()
            demo.handler.disconnect("attract stopped")   # a late pick now has no round to land in
            demo.window.ring.reset()
            demo.close()
            demo.window.flasher.stop()
            demo.sink.stop_output()
        if self.overlay is not None:
            self.overlay.hide()
            self.overlay.deleteLater()
        self.overlay = self.banner = self.caption = None
        a = self.app
        a.log(f"attract: stopped ({reason}); back to a clean first round")
        if a.handler.current is None and not a._reopen.isActive():
            a.ask()
        self.poke()
