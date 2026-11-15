"""AI Answering demo (#5): typed question -> two reply tiles -> preview -> confirm -> spoken once.

    python -m signal2speech.ai [--provider auto|claude|stub|slow-stub|saved] [--question "..."]

Reuses the #4 App (same handler, adapters, sink, transcript, and the real OpenOrbit view).
A confirmed speak_reply is spoken once with no map change. A confirmed map suggestion
(show_satellite or compare_air_quality, #106) reveals the map and speaks its line once, the
same as in `python -m signal2speech.app`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from signal2speech.app import App
from signal2speech.ui import theme as T
from signal2speech.core import InputSources, Outcome, TargetIds

from .qt import AsyncSuggester, QuestionPanel
from .replies import (HELP_PHRASES, TIMEOUT_S, ReplySet, ReplySuggester, language_code,
                      language_name, make_provider, saved_phrases_from_file)


#: The main screen: the reply cards get more of the width than the conversation beside them.
CHAT_SPLIT = (3, 2)
CHAT_TILE_HEIGHT = 300
CHAT_TILE_PX = (30, 20)        # title size on the reply cards: from, and down to for long replies
CHAT_LOG_HEIGHT = 300          # the conversation box: room for one question and its answer
SUITE_HELP = "\n".join([
    "Could not read the headset from Unicorn Suite.",
    "  1. Open Unicorn Suite, then Unicorn Recorder, and connect the headset there.",
    "  2. In Unicorn Recorder, switch on its LSL output and start the acquisition.",
    "  3. Run this again. A stream with another name: set SIGNAL2SPEECH_LSL_NAME to it."])
READ_S = 17                     # headset: seconds to read the replies before the cards flash
NASA_QUESTION = "Which county's AQI rose more when wildfire smoke reached southeast Michigan?"


class AnsweringDemo:
    def __init__(self, input_source: str = InputSources.KEYBOARD, provider_kind: str = "auto", *,
                 provider=None, provider_note: Optional[str] = None, speaker=None, view=None,
                 cues: bool = False, reply_language: str = "en",
                 mute: bool = False, echo: bool = True, deadline_s: float = TIMEOUT_S + 1,
                 recording=None, p300: bool = False, arm_live_confirm: bool = False,
                 live_options: Optional[dict] = None):
        if provider is None and provider_note is None:
            provider, provider_note = make_provider(provider_kind)
        self.provider_note = provider_note or ""
        # view=None gives the real OpenOrbit view, so map suggestions (#106) reveal the map.
        self.app = App(input_source, view=view, speaker=speaker, mute=mute, echo=echo, cues=cues,
                       recording=recording, p300=p300, arm_live_confirm=arm_live_confirm,
                       live_options=live_options)
        # The built-in NASA question (the app's own demo round), kept as an example to ask.
        self.nasa_choices = list(self.app.choices)
        self.nasa_origin = self.app.options_origin
        # Recorded brain data (#104): it answers only a question that was asked. Which reply the
        # scripted wearer attends alternates, or the operator sets it with Ctrl+1 / Ctrl+2.
        self.recorded = input_source == InputSources.RECORDED
        # A headset (or its simulated rehearsal): the cards flash only for a question that was
        # asked. Flashing straight after calibration made a pick before anyone had asked anything.
        self.live = input_source == InputSources.LIVE_EEG or p300
        self._pending = False
        #: Seconds the wearer gets to read both replies and choose one before the cards flash.
        self.read_s = READ_S
        self._read_left = 0
        self._read_round = None
        self._read_timer = QTimer(interval=1000)
        self.next_pick = 1
        self._asked = False
        if self.recorded:
            self.app.sim.script.clear()
            self.app.sim.idle_hint = ("Type a question above and press Enter (or click Saved phrases). "
                                      "The recorded brain data will pick a reply.")
        self.suggester = ReplySuggester(provider, saved_phrases_from_file())   # #134
        self.async_ = AsyncSuggester(self.suggester, deadline_s, parent=self.app.window)
        self.panel = QuestionPanel()
        self.question = ""
        self.current: Optional[ReplySet] = None

        self.root = QWidget()
        self.root.setWindowTitle(f"Signal2Speech · {self.app.input_summary()}")
        self.root.setStyleSheet("background:#0b0d10;")
        col = QVBoxLayout(self.root)
        col.setContentsMargins(16, 8, 16, 0)
        col.setSpacing(6)
        # What this is and how to use it, readable at a glance by someone who just sat down.
        self.banner = QLabel()
        self.banner.setTextFormat(Qt.TextFormat.RichText)
        self.banner.setWordWrap(True)
        col.addWidget(self.banner)
        self._style_banner()
        col.addWidget(self.panel)
        col.addWidget(self.app.root, 1)
        from signal2speech.app import fit_to_screen
        fit_to_screen(self.root, (1700, 1000))            # never larger than the screen it is on

        self.panel.ask_requested.connect(self.ask)
        self.panel.alternatives_requested.connect(self.alternatives)
        self.panel.saved_requested.connect(self.saved)
        self.panel.nasa_requested.connect(lambda: self.back() if self._map_on else self.nasa())
        self.app.handler.on_round_opened.append(self._fit_side_panel)
        self.app.handler.on_round_opened.append(self._read_then_flash)
        self._read_timer.timeout.connect(self._read_tick)
        tap = getattr(self.app.sim, "trace_tap", None)
        if tap is not None:                    # an EEG input: show what the pipeline receives
            tap.on_rows = self.panel.trace.feed
            if input_source == InputSources.RECORDED:
                self.panel.trace.idle_note = "plays when the cards flash"
            self.panel.trace.set_source({
                InputSources.LIVE_EEG: "Live EEG, headset",
                InputSources.RECORDED: "Recorded g.tec EEG",
            }.get(input_source, "Simulated, not a brain"))
        self.app.on_text_scale.append(self._style_banner)
        self._map_on = True
        self._show_map(False)
        self.async_.ready.connect(self._show)
        # After a confirm the app reopens a round: offer saved phrases, not the spoken pair.
        self.app.handler.on_handled.append(self._after_handled)
        self.app.on_restart.append(self._on_restart)            # #180: R starts a new visitor
        self.app.log(f"replies provider: {self.provider_note}")
        self.app.log(f"saved phrases: {self.suggester.saved.source}")
        # #194: F3 switches between English and the chosen reply language.
        self.language = "en"
        self.other_language = reply_language if reply_language != "en" else "es"
        if reply_language != "en":
            self.set_language(reply_language)
        else:
            self._label_language()
        from PySide6.QtGui import QKeySequence, QShortcut
        sc = QShortcut(QKeySequence("F3"), self.root)
        sc.setAutoRepeat(False)
        sc.activated.connect(self.toggle_language)
        if self.recorded:
            for n in (1, 2):
                pick = QShortcut(QKeySequence(f"Ctrl+{n}"), self.root)
                pick.setAutoRepeat(False)
                pick.activated.connect(lambda n=n: self.attend(n))
            self.app.help.rows.insert(-1, ("Ctrl+1 / Ctrl+2", "Which reply the scripted wearer looks at next"))
        self.app.help.rows.insert(-1, ("F3", f"Replies in English or {language_name(self.other_language)}"))
        self.app.help.restyle()
        self.app.on_text_scale.append(self.panel.restyle)

    def set_language(self, code: str) -> bool:
        """Switch the reply language (#194). Checks the OS voice first: with no voice for the
        language it says so and stays in English, so a reply is never read in the wrong accent."""
        speaker = self.app.speaker
        has_voice = speaker.set_language(code) if hasattr(speaker, "set_language") else code == "en"
        if not has_voice:
            msg = f"No {language_name(code)} voice is installed, so replies stay in English."
            self.app.log(f"reply language: {msg}")
            self.app.conversation.add("note", msg)
            if hasattr(speaker, "set_language"):
                speaker.set_language("en")
            code = "en"
        note = self.suggester.set_language(code)
        self.language = code
        self.app.help_text = HELP_PHRASES.get(code, HELP_PHRASES["en"])
        self.app.help_english = code not in HELP_PHRASES or code == "en"
        self.app.log(f"reply language: {language_name(code)}" + (f" ({note})" if note else ""))
        self._label_language(note if has_voice else f"no {language_name(self.other_language)} voice installed")
        return has_voice

    def toggle_language(self) -> None:
        self.set_language(self.other_language if self.language == "en" else "en")
        if not self.async_.pending:            # show the offline replies in the new language now
            if self.question:
                self._request(())
            else:
                self._show(self.suggester.saved.current("language changed"))

    def _label_language(self, note: str = "") -> None:
        other = language_name("en" if self.language != "en" else self.other_language)
        self.panel.set_language(f"Reply language: {language_name(self.language)}"
                                + (f" ({note})" if note else "") + f"   ·   F3: {other}")

    def _style_banner(self) -> None:
        step = (f"<span style='color:{T.ON_ACCENT};background:{T.ACCENT};font-weight:800'>&nbsp;%d&nbsp;</span>"
                f"&nbsp;<span style='color:{T.TEXT}'>%s</span>")
        steps = " &nbsp;&nbsp;→&nbsp;&nbsp; ".join(step % pair for pair in (
            (1, "Someone asks a question"),
            (2, "Look at the reply you want"),
            (3, "Close your eyes for 2 seconds to say it")))
        self.banner.setText(
            f"<span style='color:{T.ACCENT};font-size:{T.px(T.TITLE - 4)}px;font-weight:800'>Signal2Speech</span>"
            f"&nbsp;&nbsp;<span style='color:{T.TEXT};font-size:{T.px(T.HEADING)}px'>"
            "Answer any question without speaking or typing, using brain signals</span><br>"
            f"<span style='font-size:{T.px(T.CAPTION + 2)}px;color:{T.MUTED}'>{steps}</span>")

    def _show_map(self, on: bool) -> None:
        """The side panel is the conversation. The NASA map takes it over only for a NASA choice."""
        if on == self._map_on:
            return
        self._map_on = on
        app = self.app
        conv = app.conversation
        conv.latest_only = on
        conv.current_question_only = not on
        # Replies are the main thing on the main screen: wider column, taller cards, and a title
        # size that lets a whole sentence fit. The NASA screens keep their own proportions.
        from signal2speech.app import CHOOSE_SPLIT
        split = CHOOSE_SPLIT if on else CHAT_SPLIT
        app._row.setStretch(0, split[0])
        app._row.setStretch(1, split[1])
        for tile in app.window.tiles.values():
            tile.HEIGHT = type(tile).HEIGHT if on else CHAT_TILE_HEIGHT
            tile.MAX_PX = type(tile).MAX_PX if on else CHAT_TILE_PX[0]
            tile.MIN_PX = type(tile).MIN_PX if on else CHAT_TILE_PX[1]
            tile.setMaximumHeight(tile.HEIGHT)
            tile.updateGeometry()
            tile._fit()
            tile.update()
        side = app._row.itemAt(1).layout()
        # Hide before showing: if both sets were visible for a moment, the window would grow
        # past the screen and stay there.
        if not on and isinstance(app.view, QWidget):
            app.view.setVisible(False)
        # With the map up, the chosen words are already on the left; the map gets the height.
        conv.setVisible(not on and not app.transcript_view.isVisibleTo(app.root))
        self.banner.setVisible(not on)        # the NASA screens need the banner's height too
        # The same button leads into the example and back out of it.
        self.panel.nasa_btn.setText("←  Back to the main screen" if on else "Example: NASA air quality")
        self.panel.nasa_btn.setStyleSheet(
            f"background:{T.ACCENT};color:{T.ON_ACCENT};font-weight:700;" if on else "")
        if on and isinstance(app.view, QWidget):
            app.view.setVisible(True)
        if on:
            from signal2speech.app import CONVERSATION_HEIGHT, PANEL_TITLE
            conv.setFixedHeight(T.px(CONVERSATION_HEIGHT))
            side.setStretchFactor(conv, 0)
            side.setAlignment(conv, Qt.AlignmentFlag(0))
            conv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            app.panel_title.setText(PANEL_TITLE)
        else:
            conv.setFixedHeight(T.px(CHAT_LOG_HEIGHT))        # one exchange, not a history
            side.setStretchFactor(conv, 1)
            side.setAlignment(conv, Qt.AlignmentFlag.AlignTop)
            conv.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            app.panel_title.setText(f"<span style='color:{T.TEXT};font-weight:700'>Conversation</span>")
        conv.restyle()

    def _fit_side_panel(self, rnd) -> None:
        from signal2speech.app import MAP_ACTIONS
        from signal2speech.core import RoundKind
        if rnd.kind is RoundKind.CHOOSE:
            self._show_map(any(c.action_id in MAP_ACTIONS for c in rnd.choices))

    def _read_then_flash(self, rnd) -> None:
        """Headset: give the wearer time to read both replies, then flash. Every choose round of
        an asked question gets it, including one reopened after a timeout."""
        from signal2speech.core import RoundKind
        self._read_timer.stop()
        if not (self.live and self._pending and rnd.kind is RoundKind.CHOOSE
                and getattr(self.app.sim, "p300_ok", True)):
            return
        self._read_round, self._read_left = rnd.id, int(self.read_s)
        self._read_tick(first=True)
        if self._read_left > 0:
            self._read_timer.start()

    def _read_tick(self, first: bool = False) -> None:
        current = self.app.handler.current
        if current is None or current.id != self._read_round:
            self._read_timer.stop()             # the round changed: never flash an old one
            return
        if not first:
            self._read_left -= 1
        w = self.app.window
        if self._read_left > 0:
            w.hint.setText(f"Read both replies and choose one in your head. "
                           f"Flashing starts in {self._read_left} s")
            return
        self._read_timer.stop()
        w.hint.setText("Look at your reply and count its flashes")
        w.flasher.start([c.target_id for c in current.choices])

    def _idle_hint(self) -> None:
        if self.live and not self._pending:
            self.app.window.hint.setText(
                "Type a question above and press Enter. The cards flash once it is asked.")

    def _arm_recorded(self) -> None:
        """Recorded input: one scripted look and one confirm, then the script is empty again."""
        if self.live:
            if self._asked:
                self._asked, self._pending = False, True
            # The window doesn't start flashing on its own here (flash_hold): _read_then_flash
            # does, after the wearer has had time to read the replies and pick one in their head.
            self.app.window.flash_hold = True
            self.app.window.flash_enabled = bool(self._pending and getattr(self.app.sim, "p300_ok", True))
        if not self.recorded:
            return
        self.app.sim.script.clear()            # a look left over from a replaced round never carries on
        if self._asked:
            self._asked = False
            self.app.sim.script.extend([self.next_pick, 1])
            self.next_pick = 2 if self.next_pick == 1 else 1

    def back(self) -> None:
        """Leave the NASA example: the main screen again, with the saved phrases on the cards."""
        self.app.log("judge: back to the main screen")
        self.question = ""
        self.panel.question.clear()
        self._show(self.suggester.saved.current("back from the NASA example"))

    def nasa(self) -> None:
        """Ask the built-in NASA question: the same two map choices as the stand-alone demo."""
        self._asked = True
        self.question = ""
        self.current = None
        self.app.log("judge: NASA example")
        self.panel.set_busy(False)
        self.panel.origin.setText("Replies: built-in NASA and EPA data")
        self.panel.question.setText(NASA_QUESTION)     # the question box shows what was asked
        self.panel.question.setCursorPosition(0)
        self.panel.question.clearFocus()               # keys 1 and 2 go to the cards
        self.app.add_question(NASA_QUESTION)
        self.app.choices = list(self.nasa_choices)
        self.app.options_origin = self.nasa_origin
        self._arm_recorded()
        self.app.ask()
        self._idle_hint()

    def attend(self, n: int) -> None:
        """Recorded input: the reply (1 or 2) the scripted wearer will look at for the next question."""
        self.next_pick = n
        self.app.log(f"walkthrough: for the next question the wearer looks at reply {n}")

    def start(self) -> None:
        self._show(self.suggester.saved.current("waiting for a question"))

    def ask(self, question: str) -> None:
        self._asked = True
        self.question = question
        self.app.add_question(question)
        self.app.log(f"question: \"{question}\"")
        self._request(())

    def alternatives(self) -> None:
        if self.question:
            self._asked = True
            avoid = self.current.texts if self.current and self.current.origin != "Saved phrases" else ()
            self.app.log("judge: other replies")
            self._request(avoid)

    def saved(self) -> None:
        self._asked = True                     # a deliberate request: recorded data may answer it
        self.app.log("judge: saved phrases")
        self._show(self.suggester.saved.next_page("chosen by judge"))

    def _request(self, avoid) -> None:
        self.panel.set_busy(True, self.provider_note)
        self.async_.request(self.question, avoid)

    def _show(self, rs: ReplySet) -> None:
        self.panel.set_busy(False)
        self.current = rs
        self.panel.show_origin(rs)
        note = f" ({rs.note})" if rs.note else ""
        self.app.log(f"replies from {rs.origin}{note}: " + " | ".join(rs.texts))
        self.app.choices = list(rs.choices)
        self.app.options_origin = rs.origin.lower() if rs.origin != "Claude" else "Claude"
        self._arm_recorded()
        self.app.ask()
        self._idle_hint()

    def _on_restart(self) -> bool:
        """R (#180): forget the last visitor's question and replies, drop a pending AI request,
        and open the first question with saved phrases."""
        self.async_.cancel()
        self.question = ""
        self.panel.question.clear()
        self._show(self.suggester.saved.current("restarted"))      # opens the round itself
        return True

    def _after_handled(self, _e, outcome: Outcome) -> None:
        if outcome is Outcome.Confirmed:
            rs = self.suggester.saved.current("after confirm")
            self.current = rs
            self.panel.show_origin(rs)
            self.app.choices = list(rs.choices)
            self.app.options_origin = rs.origin.lower()      # never "from Claude" for saved phrases
            if self.live:                                    # answered: no flashing until the next question
                self._pending = False
                self.app.window.flash_enabled = False
                self._read_timer.stop()
            # The question is answered: empty the box for the next one.
            self.question = ""
            self.panel.question.clear()
            self.panel.alt_btn.setEnabled(False)


def bring_to_front(window) -> None:
    """Put the window on top of the others. Windows ignores a plain raise from a background
    process, so it is pinned on top for a moment and then released."""
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.show()
    window.raise_()
    window.activateWindow()

    def release() -> None:
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        window.show()
        window.raise_()
        window.activateWindow()
    QTimer.singleShot(1500, release)


def wait_for_start(window, source: str) -> bool:
    """A Start button over the window: calibration begins when the people at the table are
    ready, not when the program happens to open. False if the window was closed instead."""
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QPushButton
    live = source == InputSources.LIVE_EEG
    veil = QWidget(window)
    veil.setStyleSheet("background: rgba(11, 13, 16, 235);")
    veil.setGeometry(window.rect())
    col = QVBoxLayout(veil)
    col.addStretch(1)
    note = QLabel(("Put the headset on and sit comfortably. " if live else "")
                  + "Calibration takes about 90 seconds. "
                  + ("The wearer looks at one card and counts its flashes, then closes their eyes on the low beep "
                     "and opens them on the high beep." if live else
                     "It runs by itself on the recorded brain data."))
    note.setAlignment(Qt.AlignmentFlag.AlignCenter)
    note.setWordWrap(True)
    note.setStyleSheet(f"color:{T.TEXT};font-size:{T.px(T.HEADING)}px;background:transparent;")
    button = QPushButton("Start")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(f"QPushButton{{background:{T.ACCENT};color:{T.ON_ACCENT};font-size:{T.px(T.TITLE)}px;"
                         f"font-weight:800;padding:{T.M}px {T.px(64)}px;border-radius:{T.RADIUS_M}px;}}")
    col.addWidget(note)
    col.addSpacing(T.L)
    col.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
    col.addStretch(1)
    veil.show()
    veil.raise_()
    button.setFocus()
    loop, started = QEventLoop(), {"ok": False}

    def go() -> None:
        started["ok"] = True
        loop.quit()
    button.clicked.connect(go)
    watch = QTimer(interval=200)
    watch.timeout.connect(lambda: (veil.setGeometry(window.rect()), None if window.isVisible() else loop.quit()))
    watch.start()
    loop.exec()
    watch.stop()
    veil.hide()                 # gone now: a deferred delete alone waits for the main event loop,
    veil.setParent(None)        # which doesn't run until calibration is over
    veil.deleteLater()
    window.repaint()
    return started["ok"]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.ai")
    p.add_argument("--input", default="keyboard", choices=["keyboard", "simulated", "recorded", "live"],
                   help="live: the Unicorn Hybrid Black headset chooses (P300); see --arm-live-confirm")
    p.add_argument("--p300", action="store_true",
                   help="with --input simulated: rehearse the headset path on simulated signals")
    p.add_argument("--via-suite", action="store_true",
                   help="live: read the headset from Unicorn Suite's Unicorn Recorder over LSL (start its "
                        "LSL output first) instead of opening it directly")
    p.add_argument("--arm-live-confirm", action="store_true",
                   help="live: let eye closure confirm. Only after the guided check "
                        "(python -m signal2speech.eeg.live --source hybridblack) says it's safe")
    p.add_argument("--recording", type=Path, default=None,
                   help="--input recorded: a subject file of g.tec's P300 Speller dataset, e.g. S4.mat "
                        "(or set SIGNAL2SPEECH_GTEC). Real recorded responses answer the flashes")
    p.add_argument("--calibration", type=int, default=10,
                   help="recorded, live, --p300: calibration sequences before the first question")
    p.add_argument("--provider", default="auto",
                   choices=["auto", "claude", "stub", "slow-stub", "saved"])
    p.add_argument("--question", default="", help="ask this question at start")
    p.add_argument("--keys", default="", help="keys after the replies arrive, e.g. '1,1'")
    p.add_argument("--mute", action="store_true")
    p.add_argument("--read-seconds", type=int, default=READ_S,
                   help="headset: seconds to read the two replies before the cards start flashing")
    p.add_argument("--no-start-button", action="store_true",
                   help="EEG inputs: begin calibration at once instead of waiting for the Start button")
    p.add_argument("--windows-voice", action="store_true",
                   help="speak with the Windows voice instead of the natural (Piper) voice")
    p.add_argument("--no-cues", action="store_true", help="no preview/confirm/cancel sounds")
    p.add_argument("--reply-language", default="en",
                   help="suggest and speak replies in this language, e.g. es or Spanish (#194); F3 switches")
    p.add_argument("--deadline", type=float, default=TIMEOUT_S + 1,
                   help="seconds before falling back to saved phrases")
    p.add_argument("--screenshot", type=Path, help="save a PNG after --keys (or replies) and exit")
    args = p.parse_args(argv)

    try:
        reply_language = language_code(args.reply_language)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if args.windows_voice:
        import os
        os.environ["SIGNAL2SPEECH_VOICE"] = "off"       # read when the app builds its speaker
    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        provider, note = make_provider(args.provider)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    recording = None
    source = InputSources.LIVE_EEG if args.input == "live" else args.input
    eeg_path = source in (InputSources.LIVE_EEG, InputSources.RECORDED) or args.p300
    if args.input == InputSources.RECORDED:
        import os
        from signal2speech.app import DEFAULT_RECORDING, RECORDING_ENV, RECORDING_HELP
        recording = args.recording or os.environ.get(RECORDING_ENV) or DEFAULT_RECORDING
        if not Path(recording).is_file():
            print(f"No recording at {recording}\n{RECORDING_HELP}", file=sys.stderr)
            return 2
    try:
        demo = AnsweringDemo(source, provider=provider, provider_note=note, mute=args.mute,
                             cues=not args.no_cues, reply_language=reply_language,
                             deadline_s=args.deadline, recording=recording,
                             p300=args.p300, arm_live_confirm=args.arm_live_confirm,
                             live_options={"calibration_sequences": args.calibration,
                                           **({"source": "unicorn-lsl"} if args.via_suite else {})})
    except Exception as err:
        if not eeg_path:
            raise
        from signal2speech.eeg.app_live import PAIRING_HELP
        print(f"Couldn't set up the EEG pipeline: {type(err).__name__}: {err}"
              + (f"\n{SUITE_HELP if args.via_suite else PAIRING_HELP}" if source == InputSources.LIVE_EEG else ""), file=sys.stderr)
        return 3
    demo.read_s = max(0, args.read_seconds)
    demo.root.show()
    bring_to_front(demo.root)
    if hasattr(demo.app.sim, "calibrate") and not (args.no_start_button or args.question or args.screenshot
                                                    or args.keys or args.mute):
        if not wait_for_start(demo.root, source):  # the window was closed before Start
            demo.app.close()
            return 0
    if hasattr(demo.app.sim, "calibrate"):         # EEG inputs: open the stream and calibrate first
        qapp.aboutToQuit.connect(demo.app.close)
        demo.app.sim.calibration_sequences = args.calibration
        try:
            demo.app.sim.start()
        except Exception as err:                   # no headset, not paired, or in use
            from signal2speech.eeg.app_live import PAIRING_HELP
            demo.app.close()
            print(f"{type(err).__name__}: {err}"
                  + (f"\n{SUITE_HELP if args.via_suite else PAIRING_HELP}" if source == InputSources.LIVE_EEG else ""), file=sys.stderr)
            return 3
        try:
            ok = demo.app.sim.calibrate({TargetIds.TARGET_1: "Reply 1", TargetIds.TARGET_2: "Reply 2"})
        except Exception as err:
            demo.app.close()
            print(f"Calibration failed: {type(err).__name__}: {err}", file=sys.stderr)
            return 1
        if ok is None:                             # the window was closed during calibration
            demo.app.close()
            return 0
    demo.start()

    keymap = {"1": TargetIds.TARGET_1, "2": TargetIds.TARGET_2}
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    def after_replies(_rs=None) -> None:
        for k in keys:
            demo.app.window.press_target(keymap[k])
        if args.screenshot:
            QTimer.singleShot(400, shoot)

    def shoot() -> None:
        demo.root.grab().save(str(args.screenshot))
        print(f"saved {args.screenshot}", flush=True)
        qapp.exit(0)

    if args.screenshot:
        QTimer.singleShot(int((args.deadline + 10) * 1000), shoot)   # never hang
    if args.question:
        once = {"done": False}

        def first(rs) -> None:
            if not once["done"]:
                once["done"] = True
                QTimer.singleShot(0, after_replies)
        demo.async_.ready.connect(first)
        demo.panel.question.setText(args.question)
        demo.ask(args.question)
    elif args.screenshot or keys:
        QTimer.singleShot(0, after_replies)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
