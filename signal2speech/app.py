"""Signal2Speech integration entry point (#4, #25).

    python -m signal2speech.app --input keyboard|simulated [--sim 2,1] [--mute]
    python -m signal2speech.app --input live          # Unicorn; key 1 confirms until #23
    python -m signal2speech.app --input pieeg --pieeg live   # keys choose, PiEEG eyes confirm (#172)

One flow: Choose -> Preview (no output) -> Confirm (one map action + one spoken line) or
Cancel (nothing). Every input goes InputAdapter -> SelectionHandler. Only AppSink.execute
produces output, and the handler calls it exactly once per confirmation.

Dependencies still missing on main are labelled, never faked:
- #30 OpenOrbit view: until signal2speech.openorbit.OpenOrbitView exists, a stand-in panel
  says which action would run.
- #21 g.Pype simulated pipeline: --input simulated uses signal2speech.eeg.simulated's
  SimulatedDecoder (a real g.Pype Generator stream) when it imports. Otherwise it injects
  scripted decisions through the same arm_capture()/select_captured() path and says why.
- Speech lives in signal2speech/speech/ (bundled OpenOrbit clip, else the offline OS voice).
- #103 live EEG: --input live runs signal2speech.eeg.app_live.LiveEegInput. Eye-closure
  confirm stays disarmed (key 1 confirms) until #23 passes (--arm-live-confirm).
- #172 PiEEG confirm: --input pieeg keeps the keyboard choosing and takes the eye-closure confirm
  from a PiEEG board over LSL (signal2speech.eeg.app_live.PiEEGConfirm), armed only after the
  #150 check passes in this session.
- #48 recorded replay: refused with a clear message.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from signal2speech.core import (ActionIds, Choice, ConfirmedAction, EegClassMap, InputAdapter,
                                InputSources, Outcome, Round, RoundKind, SelectionEvent,
                                SelectionHandler, TargetIds)
from signal2speech.speech import MutedSpeaker, OfflineSpeaker, Speaker
from signal2speech.speech.neural import PiperVoice
from signal2speech.ui import INPUT_LABELS, KeyHelpOverlay, SelectionWindow
from signal2speech.ui import theme as T
from signal2speech.ui.conversation import KINDS, ConversationView
from signal2speech.ui.__main__ import load_demo_choices

ROOT = Path(__file__).resolve().parents[1]

MAP_ACTIONS = frozenset({ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY})
CONFIRM_TIMEOUT_MS = 20_000   # longer than alpha calibration's ~1.5 s closure plus reading time

#: Width shared between the tiles (left) and the map with the latest line (right). The map and
#: its NASA images are what a judge should see, so the right side gets most of it.
CHOOSE_SPLIT = (2, 3)
REVEAL_SPLIT = (2, 3)     # the same on a reveal: columns that change width make the screen jump
#: Height of the one-line conversation box, before the text scale.
CONVERSATION_HEIGHT = 132      # the label line plus a reply that wraps onto two lines
PANEL_TITLE = (f"<span style='color:{T.ACTION_TINT[ActionIds.SHOW_SATELLITE]}'>OpenOrbit</span>"
               " &nbsp;·&nbsp; NASA and EPA data")

BLOCKED_INPUTS: dict = {}     # every input is wired in: recorded runs since #104

#: Where --input recorded looks for g.tec's P300 Speller dataset when --recording isn't given.
#: The dataset is for Hack the Nest projects only and is never committed.
RECORDING_ENV = "SIGNAL2SPEECH_GTEC"
DEFAULT_RECORDING = Path(__file__).resolve().parents[2] / "gtec_p300" / "p300-speller" / "S4.mat"
RECORDING_HELP = """--input recorded needs one subject file of g.tec's P300 Speller dataset.
  1. Get it from the Data Science section of https://github.com/unicorn-bi/Hackathon
  2. Unpack it outside the repo (it is for Hack the Nest projects only: never commit it).
  3. Run: python -m signal2speech.app --input recorded --recording path/to/p300-speller/S4.mat
     or set SIGNAL2SPEECH_GTEC to that file."""


# ── Output side ──────────────────────────────────────────────
class MapView(Protocol):
    """What #30 exposes. Only AppSink calls these."""
    def show_satellite(self) -> None: ...
    def compare_air_quality(self) -> None: ...


class Transcript:
    """Visible, timestamped log for judges (#4). Also mirrored to stdout."""

    def __init__(self, widget: Optional[QPlainTextEdit] = None, echo: bool = True):
        self.lines: List[str] = []
        self.widget = widget
        self.echo = echo

    def __call__(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        self.lines.append(line)
        if self.widget is not None:
            self.widget.appendPlainText(line)
        if self.echo:
            print(line, flush=True)



#: The size the window opens at when the screen has room for it.
PREFERRED_SIZE = (1700, 900)
#: Room left for the title bar and window borders, which sit outside the size we set.
FRAME_ALLOWANCE = (16, 48)


def fit_to_screen(widget, preferred=PREFERRED_SIZE, available=None) -> tuple:
    """Size ``widget`` to ``preferred``, or smaller if the screen can't hold it, and keep it on
    screen. A 1920 x 1080 laptop at 125 % scaling offers only 1536 x 864 minus the taskbar, so a
    fixed 1700 x 900 hung off the right and bottom edges. Returns the (width, height) used."""
    if available is None:
        screen = widget.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
    if available is None:
        widget.resize(*preferred)
        return tuple(preferred)
    w = max(1, min(preferred[0], available.width() - FRAME_ALLOWANCE[0]))
    h = max(1, min(preferred[1], available.height() - FRAME_ALLOWANCE[1]))
    widget.resize(w, h)
    widget.move(available.x() + (available.width() - FRAME_ALLOWANCE[0] - w) // 2 + FRAME_ALLOWANCE[0] // 2,
                available.y() + max(0, (available.height() - FRAME_ALLOWANCE[1] - h) // 2))
    return (w, h)


class AppSink:
    """The only place output happens. SelectionHandler calls execute once per confirm."""

    def __init__(self, view: MapView, speaker: Speaker, log: Callable[[str], None],
                 clock: Callable[[], float] = time.monotonic):
        self.view = view
        self.speaker = speaker
        self.log = log
        self.clock = clock
        self.last_action: Optional[str] = None
        # #130: one entry per confirm. map_ms is confirm -> map call returned; speech_ms is
        # confirm -> audio actually started (None until it does, or if nothing is audible).
        self.timings: List[dict] = []
        self.on_timing: Optional[Callable[[dict], None]] = None
        self.cues = None          # #177: a CuePlayer, or None for no sounds
        self.help_calls: List[dict] = []    # #197: one entry per help phrase spoken
        self._speech_timer = QTimer(singleShot=True)   # the reply waits for the confirm cue
        self._speech_timer.timeout.connect(self._speak_now)
        self._queued: Optional[Callable[[], None]] = None

    def execute(self, action: ConfirmedAction) -> None:
        t0 = self.clock()
        entry = {"action": action.action_id, "source": action.source, "map_ms": None,
                 "speech_ms": None}
        self.timings.append(entry)
        self.last_action = action.action_id
        if action.action_id == ActionIds.SHOW_SATELLITE:
            self.log(f"OUTPUT map: show_satellite()  [{action.source}]")
            self.view.show_satellite()
        elif action.action_id == ActionIds.COMPARE_AIR_QUALITY:
            self.log(f"OUTPUT map: compare_air_quality()  [{action.source}]")
            self.view.compare_air_quality()
        if action.action_id in MAP_ACTIONS:
            entry["map_ms"] = round((self.clock() - t0) * 1000, 1)
        if action.action_id not in MAP_ACTIONS and action.action_id != ActionIds.SPEAK_REPLY:
            self.log(f"IGNORED unknown action {action.action_id!r}")
            self.timings.remove(entry)
            return
        if action.spoken_text:
            self.log(f"OUTPUT speak: \"{action.spoken_text}\"")

            def speak(entry=entry, t0=t0):
                if hasattr(self.speaker, "on_started"):
                    def started():
                        entry["speech_ms"] = round((self.clock() - t0) * 1000, 1)
                        self._report(entry)
                    self.speaker.on_started = started
                self.speaker.say(action.spoken_text, action.action_id)
            if self.cues is not None:
                # #177: the confirm cue first, then the reply, so they never overlap.
                self._queued = speak
                self._speech_timer.start(self.cues.play("confirm") + 40)
            else:
                speak()
        self._report(entry)

    def _speak_now(self) -> None:
        fn, self._queued = self._queued, None
        if fn is not None:
            fn()

    def stop_output(self) -> None:
        """Cancel a reply still waiting for its cue, and stop audio (attract mode ending, #193)."""
        self._speech_timer.stop()
        self._queued = None
        if hasattr(self.speaker, "stop"):
            self.speaker.stop()

    def call_for_help(self, text: str, source: str, english: bool = True) -> None:
        """#197: the help phrase. Its own output, never a choice and never a round outcome."""
        from signal2speech.speech.speaker import ENGLISH_LINE
        self.help_calls.append({"time": time.strftime("%H:%M:%S"), "source": source, "text": text})
        self.log(f"OUTPUT help: \"{text}\"  [{source}]")
        self.speaker.say(text, ENGLISH_LINE if english else None)

    def _report(self, entry: dict) -> None:
        if self.on_timing is not None:
            self.on_timing(entry)


class PendingMapView(QLabel):
    """Stand-in until #30 lands. Says plainly that it is not the OpenOrbit view."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.calls: List[str] = []
        self.setWordWrap(True)
        self.setMinimumSize(360, 280)
        self.setStyleSheet(f"background:{T.SURFACE}; color:{T.STRIP_TEXT}; border:3px dashed "
                           f"{T.INPUT_COLORS[InputSources.SIMULATED]}; border-radius:{T.RADIUS_M}px;"
                           f"font-size:{T.BODY}px; padding:{T.L}px;")
        self._render()

    def show_satellite(self) -> None:
        self.calls.append(ActionIds.SHOW_SATELLITE)
        self._render()

    def compare_air_quality(self) -> None:
        self.calls.append(ActionIds.COMPARE_AIR_QUALITY)
        self._render()

    def _render(self) -> None:
        last = self.calls[-1] if self.calls else "none yet"
        self.setText("<b>OpenOrbit view not built yet (#30)</b><br><br>"
                     "This stand-in only shows which map action ran.<br><br>"
                     f"Map action: <b>{last}</b><br>Map actions run: {len(self.calls)}")


def load_view() -> QWidget:
    try:
        from signal2speech.openorbit import OpenOrbitView  # type: ignore  # provided by #30
    except ImportError:
        return PendingMapView()
    return OpenOrbitView()


# ── Input side ───────────────────────────────────────────────
class InjectedSimulatedInput(QObject):
    """Scripted simulated decisions, no g.Pype yet (#21 pending).

    Same timing contract as live EEG: arm_capture() when the tiles start flashing (Choose)
    or when the Confirm round opens (the alpha window), and select_captured() when the
    "decoder" decides. Script tokens are classifier classes: 1 -> target-1, 2 -> target-2.
    """

    def __init__(self, handler: SelectionHandler, window: SelectionWindow, script: List[int],
                 log: Callable[[str], None], confirm_delay_ms: int = 2000):
        super().__init__(window)
        self.adapter = InputAdapter(handler, InputSources.SIMULATED)
        self.classes = EegClassMap.default()
        self.script = list(script)
        self.log = log
        self.window = window
        self.confirm_delay_s = confirm_delay_ms / 1000
        # #175: a scripted confirm is a simulated eye closure: it fills the same ring as a
        # held key, and only a full ring confirms.
        window.ring.handlers["simulated"] = self._decide
        self._timer = QTimer(self, singleShot=True, interval=confirm_delay_ms)
        self._timer.timeout.connect(self._decide)
        window.flasher.on_sequence_started = self.adapter.arm_capture
        window.flasher.on_sequence_finished = self._decide
        handler.on_round_opened.append(self._round_opened)
        handler.on_cleared.append(lambda _r: self._timer.stop())

    def _round_opened(self, rnd: Round) -> None:
        self._timer.stop()
        if rnd.kind is RoundKind.CONFIRM:
            self.adapter.arm_capture()
            if self.script and self.script[0] == 1:
                self.window.ring.start_hold("simulated", self.confirm_delay_s)
            else:
                self._timer.start()

    def _decide(self) -> None:
        if not self.script:
            self.log("simulated: script finished, use keys 1/2")
            return
        cls = self.script.pop(0)
        self.adapter.select_captured(self.classes.target_for(cls))


def make_simulated_input(handler: SelectionHandler, window: SelectionWindow, script: List[int],
                         log: Callable[[str], None], confirm_delay_ms: int = 2000):
    """Return (input object, label). Prefer #21's g.Pype stream; say why when falling back."""
    try:
        from signal2speech.eeg.simulated import SimulatedDecoder
    except ImportError as e:
        missing = getattr(e, "name", "") or ""
        why = ("g.Pype not installed" if missing.startswith("gpype")
               else "#21 SimulatedDecoder not merged" if missing.startswith("signal2speech")
               else f"import failed: {missing or e}")
        return (InjectedSimulatedInput(handler, window, script, log, confirm_delay_ms),
                f"scripted, no g.Pype ({why})")
    decoder = SimulatedDecoder(handler, script, flasher=window.flasher,
                               confirm_s=confirm_delay_ms / 1000, parent=window)
    decoder.start()
    # #175: a confirm pick waits for the preview's ring, like a held key or an eye closure.
    def gate(release):
        window.ring.handlers["simulated"] = release
        window.ring.start_hold("simulated", confirm_delay_ms / 1000)
    decoder.confirm_gate = gate
    return decoder, "g.Pype Generator stream"


# ── Wiring ───────────────────────────────────────────────────
class App:
    def __init__(self, input_source: str = InputSources.KEYBOARD, *,
                 view: Optional[MapView] = None, speaker: Optional[Speaker] = None,
                 sim_script: Optional[List[int]] = None, mute: bool = False,
                 echo: bool = True, reopen_ms: int = 2000, confirm_delay_ms: int = 2000,
                 reveal_ms: int = 8000,
                 confirm_timeout_ms: int = CONFIRM_TIMEOUT_MS,
                 p300: bool = False, arm_live_confirm: bool = False,
                 live_options: Optional[dict] = None,
                 pieeg: Optional[dict] = None,
                 recording=None,
                 clock: Callable[[], float] = time.monotonic, cues: bool = False,
                 attract: bool = False, attract_idle_ms: Optional[int] = None,
                 help_by_eyes: bool = False, practice_s: Optional[float] = None):
        if pieeg is not None and input_source != InputSources.KEYBOARD:
            raise ValueError("--input pieeg chooses by keyboard: the board gives the eyes-closed "
                             "confirm only (#172)")
        if input_source in BLOCKED_INPUTS:
            raise ValueError(BLOCKED_INPUTS[input_source])
        if input_source not in InputSources.ALL:
            raise ValueError(f"Unknown input: {input_source}")
        self.input_source = input_source
        self.muted = mute

        self.transcript_view = QPlainTextEdit(readOnly=True)
        self.transcript_view.setStyleSheet(f"background:{T.SURFACE}; color:{T.STRIP_TEXT}; font-size:15px;"
                                           f"font-family: {T.MONO};")
        self.transcript_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # never swallow key 1
        # #176: what judges read. The developer log stays underneath (F2, session report).
        self.conversation = ConversationView()
        self.conversation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.options_origin = "the demo script"
        self._previewed = None
        self.log = Transcript(self.transcript_view, echo=echo)
        self.view = view if view is not None else load_view()
        own_voice = speaker is None and not mute         # False in tests and with --mute
        if speaker is None:
            speaker = (MutedSpeaker(self.log) if mute
                       else OfflineSpeaker(self.log, neural=PiperVoice.find()))
        self.speaker = speaker
        self.sink = AppSink(self.view, speaker, self.log, clock=clock)
        self.sink.on_timing = self._show_timing
        if cues and not mute:
            from signal2speech.speech.cues import CuePlayer
            self.sink.cues = CuePlayer()
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.events: List[str] = []          # #131: timeline for the session report
        self.handler = SelectionHandler(self.sink)
        self.keyboard = InputAdapter(self.handler, InputSources.KEYBOARD)
        self.window = SelectionWindow(self.handler, self.keyboard, input_source=input_source,
                                      flash=input_source in (InputSources.SIMULATED,
                                                             InputSources.RECORDED,
                                                             InputSources.LIVE_EEG))
        self.choices: List[Choice] = load_demo_choices()

        h = self.handler
        h.on_round_opened.append(self._log_round)
        h.on_preview.append(lambda c: self.log(f"preview (no output): \"{c.spoken_text or c.label}\""))
        prepare = getattr(self.speaker, "prepare", None)     # make the audio while it's previewed
        if prepare is not None:
            h.on_preview.append(lambda c: prepare(c.spoken_text) if c.spoken_text else None)
        h.on_cleared.append(lambda r: self.log(f"cleared ({r}): no output"))
        h.on_handled.append(self._log_outcome)
        h.on_round_opened.append(self._talk_round)          # #176, same events as the log
        h.on_handled.append(self._talk_outcome)
        h.on_cleared.append(self._talk_cleared)
        h.on_preview.append(self._cue_preview)               # #177
        h.on_round_opened.append(lambda r: self._event(f"round {r.id} ({r.kind.value}) opened"))
        h.on_cleared.append(lambda r: None if r in ("practice", "restart") else self._event(f"cleared ({r}), no output"))
        h.on_handled.append(lambda e, o: self._event(
            f"{o.value}" + (f" · {e.source} {e.eventId} {e.roundId}->{e.targetId}" if e else "")))

        self.sim = None
        sim_label = ""
        if input_source == InputSources.RECORDED:
            # #104: real recorded g.tec responses answer each flash; the live pipeline decides.
            from signal2speech.eeg import p300 as p300_mod
            from signal2speech.eeg.app_live import RecordedEegInput
            if recording is None:
                raise ValueError("recorded input needs a recording: pass recording=<S4.mat>")
            responses = (recording if isinstance(recording, p300_mod.RecordedResponses)
                         else p300_mod.RecordedResponses.from_gtec(recording))
            from signal2speech.speech.speaker import ENGLISH_LINE
            # Guidance lines for the walkthrough, in the app's voice. Off in tests and with --mute.
            narrator = (lambda text: self.speaker.say(text, ENGLISH_LINE)) if own_voice else None
            self.sim = RecordedEegInput(h, self.window, self.log, responses=responses,
                                        script=sim_script or [2, 1], narrator=narrator,
                                        **(live_options or {}))
            sim_label = self.sim.connection_label()
            self.window.set_input_text(self.sim.strip_text(), InputSources.RECORDED)
            if own_voice:
                # Someone with their eyes closed can't read "Open your eyes": a low beep to close,
                # a high beep to open, the same sounds as the board session's eye check.
                from signal2speech.eeg.board_session import Voice
                cue_voice = Voice(neural=PiperVoice.find())
                self.sim.eye_cue = lambda kind: cue_voice.beep("go" if kind == "close" else "stop")
                if not hasattr(self.sim, "narrator"):     # a headset: spoken calibration steps
                    self.sim.guide = cue_voice.say
            alpha = getattr(self.sim, "alpha", None)
            if alpha is not None and hasattr(alpha, "progress"):
                alpha.progress.connect(self.window.set_eye_progress, Qt.ConnectionType.QueuedConnection)
        elif input_source == InputSources.LIVE_EEG or (input_source == InputSources.SIMULATED
                                                       and p300):
            # #103: P300 chooses and the alpha switch confirms, on one g.Pype pipeline.
            from signal2speech.eeg.app_live import LiveEegInput
            self.sim = LiveEegInput(
                h, self.window, self.log,
                source="generator" if input_source == InputSources.SIMULATED else "hybridblack",
                script=sim_script or [2, 1], arm_live_confirm=arm_live_confirm,
                **(live_options or {}))
            sim_label = self.sim.connection_label()
            if own_voice:
                # Someone with their eyes closed can't read "Open your eyes": a low beep to close,
                # a high beep to open, the same sounds as the board session's eye check.
                from signal2speech.eeg.board_session import Voice
                cue_voice = Voice(neural=PiperVoice.find())
                self.sim.eye_cue = lambda kind: cue_voice.beep("go" if kind == "close" else "stop")
                if not hasattr(self.sim, "narrator"):     # a headset: spoken calibration steps
                    self.sim.guide = cue_voice.say
            alpha = getattr(self.sim, "alpha", None)
            if alpha is not None and hasattr(alpha, "progress"):
                # #175: the ring follows the alpha switch (queued: emitted on a g.Pype thread).
                alpha.progress.connect(self.window.set_eye_progress, Qt.ConnectionType.QueuedConnection)
        elif pieeg is not None:
            # #172: keys choose; a PiEEG board's eye closure confirms, after this session's check.
            # PiEEGConfirm builds its alpha switch during the check and hooks the #175 ring then.
            from signal2speech.eeg.app_live import PiEEGConfirm
            pieeg = dict(pieeg)
            if own_voice and "announce" not in pieeg:
                # A wearer with closed eyes can't read "Open your eyes": one spoken line, then beeps.
                from signal2speech.eeg.app_live import SpokenCheck
                from signal2speech.eeg.board_session import Voice
                pieeg["announce"] = SpokenCheck(Voice(neural=PiperVoice.find()))
            self.sim = PiEEGConfirm(h, self.window, self.log, **pieeg)
            sim_label = self.sim.connection_label()
        elif input_source == InputSources.SIMULATED:
            self.sim, sim_label = make_simulated_input(h, self.window, sim_script or [2, 1],
                                                       self.log, confirm_delay_ms)
            self.window.set_connection(sim_label)

        # Contract: a Confirm round with no answer cancels on timeout (#26). 0 turns it off.
        self.confirm_timeout_ms = confirm_timeout_ms
        self._confirm_timer = QTimer(singleShot=True, interval=max(1, confirm_timeout_ms))
        self._confirm_timer.timeout.connect(lambda: h.cancel("timeout"))
        h.on_round_opened.append(self._arm_confirm_timeout)
        h.on_cleared.append(lambda _r: self._stop_confirm_timeout())
        h.on_handled.append(lambda _e, o: self._stop_confirm_timeout() if o is Outcome.Confirmed else None)
        # The visible countdown reads the same timer, so it can't disagree with the cancel (#96).
        self._countdown = QTimer(interval=250)
        self._countdown.timeout.connect(self._tick_countdown)

        # Rule 4: the app opens the next question after a cancel, disconnect, or confirm.
        # A map reveal stays up longer (reveal_ms) so the audience can read it.
        self.reopen_ms, self.reveal_ms = reopen_ms, reveal_ms
        self._reopen = QTimer(singleShot=True)
        self._reopen.timeout.connect(self.ask)
        h.on_cleared.append(lambda _r: self._reopen.start(self.reopen_ms))
        h.on_handled.append(self._after_confirm)
        h.on_round_opened.append(lambda _r: self._set_reveal(False))

        self.root = QWidget()
        ui_font = QFont()
        ui_font.setFamilies(T.FONT_FAMILIES)           # one clean family across the whole app
        QApplication.instance().setFont(ui_font)
        self.root.setWindowTitle(f"Signal2Speech · {self.input_summary()}")
        if hasattr(self.sim, "on_label"):              # #172: the check changes the label
            self.sim.on_label = lambda text: self.root.setWindowTitle(f"Signal2Speech · {text}")
        self.root.setStyleSheet(f"background:{T.BG};")
        right = QVBoxLayout()
        self.panel_title = QLabel(PANEL_TITLE)
        self.panel_title.setTextFormat(Qt.TextFormat.RichText)
        self.panel_title.setWordWrap(True)
        right.addWidget(self.panel_title)
        if isinstance(self.view, QWidget):
            right.addWidget(self.view, 1)
        # The map gets the height. The conversation shows only the latest line; the developer
        # log (F2) and the session report keep everything.
        self.conversation.latest_only = True
        self.conversation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conversation.setFixedHeight(T.px(CONVERSATION_HEIGHT))
        right.addWidget(self.conversation, 0)
        right.addWidget(self.transcript_view, 2)
        self.transcript_view.setVisible(False)
        right.setContentsMargins(0, 12, 0, 12)        # the panels don't touch the window's edges
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 16, 0)
        row.addWidget(self.window, CHOOSE_SPLIT[0])
        row.addLayout(right, CHOOSE_SPLIT[1])
        self._row = row
        # The status strip spans the whole window. Inside the left column it was squeezed to a
        # third of the width whenever the map was revealed, and its text was cut off ("Last: Co").
        outer = QVBoxLayout(self.root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(row, 1)
        strip = self.window.strip
        strip.setParent(self.root)
        outer.addWidget(strip)
        strip.setStyleSheet(self.window.styleSheet())  # it left the window that styled it
        inner = self.window.centralWidget().layout()   # keep the hint line clear of the strip
        m = inner.contentsMargins()
        inner.setContentsMargins(m.left(), m.top(), m.right(), max(m.bottom(), 10))
        self.revealing = False
        fit_to_screen(self.root)

        # #196: practice round. No handler round is open while it runs, so nothing can output.
        from signal2speech.practice import PRACTICE_S, PracticeRound
        self.practice = PracticeRound(self.window, duration_s=practice_s or PRACTICE_S,
                                      on_finished=self._practice_done)
        self.window.on_escape = self.practice.stop
        # #197: help phrase from any screen.
        from signal2speech.helpcall import HELP_TEXT, HelpCall
        self.help_text = HELP_TEXT
        self.help_english = True        # the AI demo switches it with the reply language (#194)
        self.helpcall = HelpCall(self._call_for_help, parent=self.root,
                                 in_confirm=lambda: (h.current is not None
                                                     and h.current.kind is RoundKind.CONFIRM))
        self.helpcall.install()
        self.helpcall.eyes_enabled = help_by_eyes
        alpha = getattr(self.sim, "alpha", None)
        if alpha is not None and hasattr(alpha, "progress"):
            alpha.progress.connect(self.helpcall.feed_eyes, Qt.ConnectionType.QueuedConnection)
        self.help_banner = QLabel("", self.root)
        self.help_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.help_banner.setWordWrap(True)
        self.help_banner.hide()
        self._help_hide = QTimer(singleShot=True, interval=8000)
        self._help_hide.timeout.connect(self.help_banner.hide)
        # #195: text size toast.
        self.toast = QLabel("", self.root)
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        self._toast_hide = QTimer(singleShot=True, interval=1500)
        self._toast_hide.timeout.connect(self.toast.hide)
        self.on_text_scale: List[Callable[[], None]] = []
        self._restyle_overlays()

        self.restarts = 0                               # #180: R presses, for the report
        self._restarting = False
        # #180: called on R; return True if you opened the first question yourself.
        self.on_restart: List[Callable[[], bool]] = []
        restart_key = QShortcut(QKeySequence("R"), self.root)
        restart_key.setAutoRepeat(False)
        restart_key.activated.connect(self.restart)
        sc = QShortcut(QKeySequence("D"), self.root)   # rehearse a headset drop (#26)
        sc.setAutoRepeat(False)
        sc.activated.connect(lambda: h.disconnect())
        if hasattr(self.sim, "set_next"):              # #21: pick for a waiting sequence
            for seq, cls in (("Ctrl+1", 1), ("Ctrl+2", 2)):
                s2 = QShortcut(QKeySequence(seq), self.root)
                s2.setAutoRepeat(False)
                s2.activated.connect(lambda c=cls: self.sim.set_next(c))
        # Operator keys (#94). Neither touches the handler.
        rows = [("1 / 2", "Pick a tile. At the preview, hold 1 for 2 s to confirm; 2 cancels."),
                ("Esc", "Cancel and clear the screen"),
                ("R", "Restart: a fresh first question for the next visitor, nothing is said"),
                ("D", "Pretend the headset disconnected"),
                ("F11", "Fullscreen on or off"),
                ("F2", "Conversation or developer log"),
                ("P", "Practice round: 30 s of flashes, nothing is sent"),
                ("Hold H", "Say \u201cI need help, please.\u201d (2 s hold, from any screen)"),
                ("Ctrl+= / Ctrl+-", "Bigger or smaller text; Ctrl+0 resets"),
                ("F1", "Show or hide this help")]
        if hasattr(self.sim, "set_next"):
            rows.insert(3, ("Ctrl+1 / Ctrl+2", "Pick for the simulated decoder"))
        help_input = ("keyboard chooses, PiEEG eye closure confirms" if pieeg is not None
                      else INPUT_LABELS[input_source])
        self.help = KeyHelpOverlay(self.root, rows, title=f"Keys · input: {help_input}")
        for seq, fn in (("F1", self.help.toggle), ("F11", self.toggle_fullscreen),
                        ("F2", self.toggle_log), ("P", self.start_practice),
                        ("Ctrl+=", lambda: self.step_text(1)), ("Ctrl++", lambda: self.step_text(1)),
                        ("Ctrl+-", lambda: self.step_text(-1)), ("Ctrl+0", lambda: self.step_text(0))):
            s3 = QShortcut(QKeySequence(seq), self.root)
            s3.setAutoRepeat(False)
            s3.activated.connect(fn)
        self.log(f"input: {self.input_summary()}" + (f" ({sim_label})" if sim_label else ""))
        self.log(f"speech: {getattr(self.speaker, 'backend', type(self.speaker).__name__)}")
        # #193: attract mode. Off by default (tests, AI demo); main() turns it on.
        self.attract = None
        if attract:
            from signal2speech.attract import IDLE_MS, AttractMode
            self.attract = AttractMode(self, idle_ms=attract_idle_ms or IDLE_MS)
            self.attract.poke()

    # ── #180 restart ─────────────────────────────────────────
    @property
    def calibrating(self) -> bool:
        """True while a headset or board is calibrating (#103, #172): R must not interrupt it."""
        return bool(getattr(self.sim, "calibrating_now", False))

    def restart(self) -> bool:
        """R: a clean first question from any state, for the next visitor (#180).

        It goes through the contract, never around it: an open round is ended with
        ``handler.cancel("restart")``, so a decision still in flight for it arrives stale and is
        rejected, and a fresh Choose round opens with ``begin_choice_round``. Nothing new is
        shown on the map or spoken. Each restart goes in the session report. It's refused during
        a calibration. Returns True if it restarted.
        """
        h = self.handler
        if self.calibrating:
            self.log("restart (R) ignored: a calibration is running")
            return False
        attract_was_on = self.attract is not None and self.attract.active
        if attract_was_on:
            self.attract.stop("restart")             # it leaves a clean Choose round itself
        self.sink.stop_output()                      # a reply still waiting for its cue stays unsaid
        self.help_banner.hide()                      # the last visitor's help request
        self._help_hide.stop()
        if self.practice.active:
            self._restarting = True                  # _practice_done logs the end, but doesn't ask
            try:
                self.practice.stop()
            finally:
                self._restarting = False
        rnd = h.current
        fresh = rnd is not None and rnd.kind is RoundKind.CHOOSE and h.pending is None
        need_round = not (attract_was_on and fresh)  # attract already opened one: don't add another
        if need_round and rnd is not None:
            h.cancel("restart")
        self._reopen.stop()                          # the cancel scheduled a reopen; we open now
        self._stop_confirm_timeout()
        self._set_reveal(False)
        if hasattr(self.view, "reset"):
            self.view.reset()                        # no map left over from the last visitor
        self.restarts += 1
        self.log("restart (R): a fresh first question, nothing was output")
        self._event("restart (R)")
        self.conversation.add("nothing", "Restarted for the next visitor.")
        # Screens that own their own first question (the AI demo's saved phrases) open it here.
        handled = any([fn() for fn in self.on_restart])
        if need_round and not handled:
            self.ask()
        return True

    # ── #196 practice ────────────────────────────────────────
    @property
    def practicing(self) -> bool:
        return self.practice.active

    def start_practice(self) -> bool:
        """P or --practice. Not during a preview: finish or cancel that first."""
        h = self.handler
        if self.practice.active or self.revealing or h.pending is not None or (
                h.current is not None and h.current.kind is RoundKind.CONFIRM):
            return False
        if self.attract is not None and self.attract.active:
            self.attract.stop("practice")
        self._reopen.stop()
        if h.current is not None:
            h.cancel("practice")
            self._reopen.stop()
        self.log("practice: started (nothing is sent until it ends)")
        self.practice.start()
        return True

    def _practice_done(self) -> None:
        p = self.practice
        self.log(f"practice: ended after {p.sequences} sequence(s), tile 1 flashed {p.target_flashes} times")
        self.window.reset()
        if not self._restarting:                     # R opens the next question itself (#180)
            self.ask()

    # ── #197 help phrase ─────────────────────────────────────
    def _call_for_help(self, how: str) -> None:
        label = INPUT_LABELS.get(self.input_source, self.input_source)
        source = "Keyboard (held H)" if how == "keyboard" else f"{label} (long eye closure)"
        self.sink.call_for_help(self.help_text, source, self.help_english)
        self.conversation.add("help", f"“{self.help_text}”", source)
        self._event(f"help phrase · {source}")
        self.help_banner.setText(f"Help requested  ·  “{self.help_text}”")
        self._place_overlays()
        self.help_banner.show()
        self.help_banner.raise_()
        self._help_hide.start()

    # ── #195 text size ───────────────────────────────────────
    def step_text(self, direction: int) -> float:
        scale = T.step_scale(direction)
        self.apply_text_scale()
        self.toast.setText(f"Text size {round(scale * 100)}%")
        self._place_overlays()
        self.toast.show()
        self.toast.raise_()
        self._toast_hide.start()
        self.log(f"text size: {round(scale * 100)}%")
        return scale

    def apply_text_scale(self) -> None:
        self.window.apply_text_scale()
        self.window.strip.setStyleSheet(self.window.styleSheet())
        self.conversation.restyle()
        self.help.restyle()
        self._restyle_overlays()
        for fn in self.on_text_scale:
            fn()

    def _restyle_overlays(self) -> None:
        self.panel_title.setStyleSheet(f"color:{T.MUTED}; font-size:{T.px(T.BODY)}px; font-weight:600;")
        self.transcript_view.setStyleSheet(f"background:{T.SURFACE}; color:{T.STRIP_TEXT};"
                                           f"font-size:{T.px(15)}px; font-family: {T.MONO};")
        self.toast.setStyleSheet(f"background:{T.RAISED}; color:{T.TEXT}; border:2px solid {T.BORDER};"
                                 f"border-radius:{T.RADIUS_M}px; padding:{T.M}px {T.L}px;"
                                 f"font-size:{T.px(T.HEADING)}px; font-weight:700;")
        self.help_banner.setStyleSheet(f"background:{T.ACCENT}; color:{T.ON_ACCENT};"
                                       f"border-radius:{T.RADIUS_M}px; padding:{T.L}px;"
                                       f"font-size:{T.px(T.TITLE)}px; font-weight:800;")
        self._place_overlays()

    def _place_overlays(self) -> None:
        r = self.root.rect()
        self.toast.adjustSize()
        self.toast.move(max(0, (r.width() - self.toast.width()) // 2), T.L)
        w = min(r.width() - 2 * T.L, 1100)
        self.help_banner.setFixedWidth(max(200, w))
        self.help_banner.adjustSize()
        self.help_banner.move(max(0, (r.width() - self.help_banner.width()) // 2),
                              max(0, (r.height() - self.help_banner.height()) // 2))

    def input_summary(self) -> str:
        """The input as judges should read it. With a PiEEG confirm (#172), both inputs."""
        if hasattr(self.sim, "strip_text"):
            return self.sim.strip_text()
        return INPUT_LABELS[self.input_source]

    def toggle_log(self) -> None:
        """F2: swap the readable conversation and the developer log (#176)."""
        show_log = not self.transcript_view.isVisibleTo(self.root)
        self.transcript_view.setVisible(show_log)
        self.conversation.setVisible(not show_log)
        self.panel_title.setText("Developer log   ·   F2: back" if show_log else PANEL_TITLE)

    def add_question(self, text: str) -> None:
        """The conversation partner's question, shown before the options it produced."""
        self.conversation.add("question", text)

    def _talk_round(self, rnd: Round) -> None:
        if rnd.kind is RoundKind.CHOOSE:
            labels = "  ·  ".join(c.spoken_text or c.label if c.action_id == ActionIds.SPEAK_REPLY
                                  else c.label for c in rnd.choices)
            self.conversation.add("options", f"{labels}   (from {self.options_origin})")

    def _talk_outcome(self, e: Optional[SelectionEvent], o: Outcome) -> None:
        label = INPUT_LABELS.get(e.source, e.source) if e is not None else None
        if o is Outcome.Previewed and self.handler.pending is not None:
            self._previewed = self.handler.pending
            c = self._previewed
            self.conversation.add("preview", f"“{c.spoken_text or c.label}”", label)
        elif o is Outcome.Confirmed and self._previewed is not None:
            c, self._previewed = self._previewed, None
            self.conversation.add("shown" if c.action_id in MAP_ACTIONS else "said",
                                  f"“{c.spoken_text or c.label}”", label)
        elif o is Outcome.Cancelled:
            self.conversation.label_last("nothing", label)

    def _talk_cleared(self, reason: str) -> None:
        had_preview, self._previewed = self._previewed is not None, None
        if reason in ("practice", "restart"):   # practice (#196) and R (#180) say it themselves
            return
        what = "preview" if had_preview else "question"
        text = {"cancel": f"The {what} was cancelled.",
                "timeout": f"No answer in time, so the {what} was cancelled.",
                "disconnect": "The headset disconnected, so nothing was said."}.get(
                    reason, f"The {what} was cleared ({reason}).")
        self.conversation.add("nothing", text)
        if self.sink.cues is not None:
            self.sink.cues.play("cancel")

    def _cue_preview(self, _choice) -> None:
        if self.sink.cues is not None:
            self.sink.cues.play("preview")

    def toggle_fullscreen(self) -> None:
        if self.root.isFullScreen():
            self.root.showNormal()
        else:
            self.root.showFullScreen()

    def close(self) -> None:
        """Stop the g.Pype stream (#21) and this app's timers, so nothing fires after close."""
        self._confirm_timer.stop()
        self._reopen.stop()
        self._countdown.stop()
        if getattr(self, "attract", None) is not None:
            self.attract.stop("closing")
            self.attract.enabled = False
        if hasattr(self, "practice"):
            self.practice.active = False
            self.practice.flasher.stop()
        if hasattr(self.sim, "close"):
            self.sim.close()

    def ask(self) -> None:
        self.handler.begin_choice_round(self.choices)

    def _after_confirm(self, _e, outcome: Outcome) -> None:
        if outcome is not Outcome.Confirmed:
            return
        if self.sink.timings:
            # The window rewrote "Last:" after the sink measured; put the timing note back.
            self._show_timing(self.sink.timings[-1])
        if self.sink.last_action in MAP_ACTIONS and isinstance(self.view, QWidget):
            self._set_reveal(True)
            self._reopen.start(self.reveal_ms)
        else:
            self._reopen.start(self.reopen_ms)

    def _set_reveal(self, on: bool) -> None:
        """Give the map most of the width while a reveal is on screen. The empty tiles hide;
        the prompt and the judge strip (input label) stay visible."""
        if on == self.revealing:
            return
        self.revealing = on
        for tile in self.window.tiles.values():
            tile.setVisible(not on)
        self.window.hint.setVisible(not on)
        self._row.setStretch(0, REVEAL_SPLIT[0] if on else CHOOSE_SPLIT[0])
        self._row.setStretch(1, REVEAL_SPLIT[1] if on else CHOOSE_SPLIT[1])

    def _stop_confirm_timeout(self) -> None:
        self._confirm_timer.stop()
        self._countdown.stop()
        self.window.set_countdown(None)

    def _tick_countdown(self) -> None:
        if not self._confirm_timer.isActive():
            self._countdown.stop()
            self.window.set_countdown(None)
            return
        # Coarse timers can report a few ms more than the interval right after start; never
        # show more seconds than the timeout itself.
        left_ms = min(self._confirm_timer.remainingTime(), self.confirm_timeout_ms)
        self.window.set_countdown(math.ceil(left_ms / 1000))

    def _arm_confirm_timeout(self, rnd: Round) -> None:
        if rnd.kind is RoundKind.CONFIRM and self.confirm_timeout_ms > 0:
            self._confirm_timer.start()
            self._countdown.start()
            self._tick_countdown()
        else:
            self._stop_confirm_timeout()

    def _event(self, text: str) -> None:
        self.events.append(f"{time.strftime('%H:%M:%S')} {text}")

    def _show_timing(self, entry: dict) -> None:
        """Show the latest confirm-to-output times in the strip; log each one once (#130)."""
        logged = entry.setdefault("_logged", set())
        for key, label in (("map_ms", "confirm→map"), ("speech_ms", "confirm→speech")):
            if entry[key] is not None and key not in logged:
                logged.add(key)
                self.log(f"timing: {label} {entry[key]:.0f} ms")
        parts = [f"{name} {entry[key]:.0f} ms" for key, name in (("map_ms", "map"), ("speech_ms", "speech"))
                 if entry[key] is not None]
        if parts:
            self.window.add_outcome_note(" · ".join(parts))

    def report_text(self) -> str:
        """#131: a plain summary of this session. Built only from handler outcomes, the
        transcript's own words, and timings. Never EEG samples, never secrets."""
        from collections import Counter
        counts = Counter(line.split(" ", 2)[1].split(" ·")[0] for line in self.events
                         if line.split(" ", 2)[1].startswith(("Previewed", "Confirmed", "Cancelled",
                                                               "Rejected")))
        cleared = sum(1 for line in self.events if " cleared (" in line)
        try:
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit = ""
        lines = [f"# Signal2Speech session · {self.started_at}", "",
                 f"- **Commit:** `{commit or 'unknown'}`",
                 f"- **Input:** {self.input_summary()}",
                 f"- **Connection:** {self.window.connection_label.text().removeprefix('Connection: ')}"
                 if self.window.connection_label.isVisibleTo(self.window) else "- **Connection:** n/a",
                 f"- **Speech:** {getattr(self.speaker, 'backend', type(self.speaker).__name__)}",
                 "", "## Counts", "",
                 "| Previewed | Confirmed | Cancelled | Cleared (cancel, disconnect, timeout) | Rejected |",
                 "| ---: | ---: | ---: | ---: | ---: |",
                 f"| {counts['Previewed']} | {counts['Confirmed']} | {counts['Cancelled']} | {cleared} | "
                 f"{sum(v for k, v in counts.items() if k.startswith('Rejected'))} |",
                 "", "## Confirm to output", ""]
        if self.sink.timings:
            lines += ["| # | Action | Input | Confirm → map | Confirm → speech |",
                      "| ---: | --- | --- | ---: | ---: |"]
            fmt = lambda v: "—" if v is None else f"{v:.0f} ms"
            for i, t in enumerate(self.sink.timings, 1):
                lines.append(f"| {i} | {t['action']} | {t['source']} | {fmt(t['map_ms'])} | "
                             f"{fmt(t['speech_ms'])} |")
        else:
            lines.append("No confirms this session.")
        lines += ["", "## Help phrase", ""]
        lines += ([f"- {c['time']} · {c['source']}: “{c['text']}”" for c in self.sink.help_calls]
                  or ["Not used this session."])
        extra = [f"- **Practice rounds:** {self.practice.runs}",
                 f"- **Restarts (R):** {self.restarts}"]
        if hasattr(self.sim, "usage"):                 # #104: recorded responses, counted
            u = self.sim.usage()
            extra.append(f"- **Recorded responses played:** {u['target_responses']} attended and "
                         f"{u['nontarget_responses']} unattended, from {u['recording']}. "
                         f"Played more than once: {u['played_twice']}. Which tile was attended "
                         "followed the script; the classifier's picks are real.")
        if self.attract is not None:
            extra.append(f"- **Attract-mode loops:** {self.attract.runs} (simulated, left out of the counts)")
        lines += ["", "## Other", ""] + extra
        lines += ["", "## Conversation", ""] + [
            f"- **{KINDS[k][0]}**" + (f" ({src})" if src else "") + f": {text}"
            for k, text, src in self.conversation.entries]
        lines += ["", "## Timeline", ""] + [f"- {e}" for e in self.events]
        lines += ["", "## Developer log", "", "```"] + list(self.log.lines) + ["```"]
        safe = [ln for ln in lines if not _looks_like_samples(ln)]
        if len(safe) != len(lines):
            safe.append("")
            safe.append(f"_{len(lines) - len(safe) + 1} line(s) dropped: they looked like raw samples._")
        return "\n".join(safe) + "\n"

    def write_report(self, folder: Optional[Path] = None) -> Path:
        folder = folder or (ROOT / "logs")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"session-{time.strftime('%Y%m%d-%H%M%S')}.md"
        path.write_text(self.report_text(), encoding="utf-8")
        return path

    def _log_round(self, rnd: Round) -> None:
        labels = ", ".join(f"{c.target_id}={c.label}" for c in rnd.choices)
        self.log(f"round {rnd.id} {rnd.kind.value}: {labels}")

    def _log_outcome(self, e: Optional[SelectionEvent], o: Outcome) -> None:
        ev = f"{e.source} {e.eventId} {e.roundId}->{e.targetId}" if e else "malformed"
        self.log(f"{o.value}: {ev}")


def _looks_like_samples(line: str) -> bool:
    """A run of 20+ numbers in one line looks like signal data, which never goes in a report."""
    return len(re.findall(r"-?\d+\.\d+", line)) >= 20


def _timeout_seconds(text: str) -> float:
    """0 (off) or 0.1-3600 s. Rejects values that would silently round to 0 or overflow QTimer."""
    try:
        s = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}")
    if s != 0 and not 0.1 <= s <= 3600:
        raise argparse.ArgumentTypeError("use 0 (never) or 0.1 to 3600 seconds")
    return s


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.app")
    p.add_argument("--input", default=InputSources.KEYBOARD,
                   choices=["keyboard", "simulated", "recorded", "live", "pieeg"])
    p.add_argument("--recording", type=Path, default=None,
                   help="--input recorded: a subject file of g.tec's P300 Speller dataset, e.g. "
                        "S4.mat (or set SIGNAL2SPEECH_GTEC). Real recorded responses answer the flashes")
    p.add_argument("--sim", default="2,1", help="simulated classes in order, e.g. '2,1' "
                                                "(choose target-2, then confirm)")
    p.add_argument("--keys", default="", help="keyboard presses after start, e.g. '2,1'")
    p.add_argument("--mute", action="store_true", help="no audio (logs instead)")
    p.add_argument("--no-cues", action="store_true",
                   help="no preview/confirm/cancel sounds (#177); --mute also turns them off")
    p.add_argument("--confirm-timeout", type=_timeout_seconds, default=CONFIRM_TIMEOUT_MS / 1000,
                   help="seconds before an unanswered Confirm round cancels (0 = never)")
    p.add_argument("--fullscreen", action="store_true", help="start fullscreen (F11 toggles, F1 shows keys)")
    p.add_argument("--no-report", action="store_true",
                   help="don't write logs/session-<time>.md on exit (#131)")
    p.add_argument("--p300", action="store_true",
                   help="with --input simulated: run the live path (#103) on the Generator")
    p.add_argument("--arm-live-confirm", action="store_true",
                   help="live: let eye closure confirm. Only after #23 says it's safe")
    p.add_argument("--calibration", type=int, default=10,
                   help="live/--p300: P300 calibration sequences before the demo")
    p.add_argument("--alpha-calib-s", type=float, default=10.0,
                   help="live/--p300: seconds of eyes open, then closed, for the alpha switch")
    p.add_argument("--practice", action="store_true",
                   help="start with the 30 s practice round (#196); P starts it any time")
    p.add_argument("--no-gaze-mark", action="store_true",
                   help="--input recorded: don't outline the card the wearer would be looking at")
    p.add_argument("--no-narration", action="store_true",
                   help="--input recorded: don't speak the walkthrough's guidance lines")
    p.add_argument("--no-intro", action="store_true",
                   help="skip the opening animation of the two cards")
    p.add_argument("--no-attract", action="store_true",
                   help="don't loop the simulated demo after 60 s idle (#193)")
    p.add_argument("--help-by-eyes", action="store_true",
                   help="a long eye closure outside a Confirm round also says the help phrase (#197)")
    p.add_argument("--text-scale", type=float, default=1.0,
                   help="start at this text size, 0.8 to 1.6 (#195); Ctrl+= / Ctrl+- / Ctrl+0 change it")
    g = p.add_argument_group("PiEEG eye-closure confirm (--input pieeg, #172)")
    g.add_argument("--pieeg", choices=["live", "simulated", "recorded"],
                   help="what is publishing the board's LSL stream: a real board on a person, "
                        "a simulator, or a replayed recording. Required: LSL can't prove it")
    g.add_argument("--pieeg-self-test", action="store_true",
                   help="publish our own simulated 16-pin stream (no board), labelled Simulated")
    g.add_argument("--stream", default=None, help="LSL stream name (PiEEG: Octopus16)")
    g.add_argument("--any-host", action="store_true",
                   help="accept the stream from another computer (default: this computer only)")
    g.add_argument("--channels", default="auto",
                   help="'auto' picks the pins that respond; or 1-based pins, e.g. 3,7")
    g.add_argument("--probe-s", type=float, default=8.0, help="seconds per eye state in the channel check")
    g.add_argument("--rest-s", type=float, default=20.0, help="eyes-open false-trigger window")
    g.add_argument("--closures", type=int, default=3, help="deliberate closures in the check")
    p.add_argument("--screenshot", type=Path, help="save a PNG after the first confirm and exit")
    p.add_argument("--smoke", nargs="?", const="dev", choices=["dev", "judging"],
                   help="hardware-free smoke check, exit 0/1 (#41); 'judging' fails on any SKIP")
    args = p.parse_args(argv)
    if args.smoke:
        from signal2speech.diagnostics import run_smoke
        return run_smoke(args.smoke)
    pieeg = None
    pieeg_only = {"--pieeg": args.pieeg is not None, "--pieeg-self-test": args.pieeg_self_test,
                  "--stream": args.stream is not None, "--any-host": args.any_host,
                  "--channels": args.channels != "auto", "--probe-s": args.probe_s != 8.0,
                  "--rest-s": args.rest_s != 20.0, "--closures": args.closures != 3}
    if args.input != "pieeg" and any(pieeg_only.values()):
        given = ", ".join(k for k, v in pieeg_only.items() if v)
        print(f"{given}: only for --input pieeg", file=sys.stderr)
        return 2
    if args.input == "pieeg":
        if not (args.pieeg or args.pieeg_self_test):
            print("--input pieeg: say what is publishing the stream with --pieeg live, simulated, "
                  "or recorded (or use --pieeg-self-test)", file=sys.stderr)
            return 2
        if args.pieeg_self_test and args.pieeg == "live":
            print("--pieeg-self-test is a simulator: it can't be labelled live", file=sys.stderr)
            return 2
        if args.arm_live_confirm:
            print("--arm-live-confirm doesn't apply to --input pieeg: the #150 check in this "
                  "session decides", file=sys.stderr)
            return 2
        if args.p300:
            print("--p300 doesn't apply to --input pieeg: keys choose, the board only confirms",
                  file=sys.stderr)
            return 2
        if args.closures < 2:
            print("--closures: the #150 check needs at least 2", file=sys.stderr)
            return 2
        pieeg = {"stream_is": args.pieeg or "simulated", "self_test": args.pieeg_self_test,
                 "stream": args.stream, "any_host": args.any_host, "channels": args.channels,
                 "probe_s": args.probe_s, "alpha_calib_s": args.alpha_calib_s,
                 "rest_s": args.rest_s, "closures": args.closures}
    source = {"live": InputSources.LIVE_EEG, "pieeg": InputSources.KEYBOARD}.get(args.input,
                                                                                  args.input)
    if source in BLOCKED_INPUTS:
        print(BLOCKED_INPUTS[source], file=sys.stderr)
        return 2
    recording = None
    if source == InputSources.RECORDED:
        import os
        recording = args.recording or os.environ.get(RECORDING_ENV) or DEFAULT_RECORDING
        if not Path(recording).is_file():
            print(f"No recording at {recording}\n{RECORDING_HELP}", file=sys.stderr)
            return 2
    elif args.recording is not None:
        print("--recording: only for --input recorded", file=sys.stderr)
        return 2

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    if args.screenshot:
        from signal2speech.ui import fade
        fade.ENABLED = False                       # a picture taken mid-fade would be wrong
    script = [int(s) for s in args.sim.split(",") if s.strip()]
    if any(s not in (1, 2) for s in script):
        print(f"--sim takes 1s and 2s, e.g. 2,1; got {args.sim!r}", file=sys.stderr)
        return 2
    live_path = (source in (InputSources.LIVE_EEG, InputSources.RECORDED) or pieeg is not None
                 or (source == InputSources.SIMULATED and args.p300))

    def setup_help() -> str:
        from signal2speech.eeg.app_live import PAIRING_HELP, PIEEG_HELP
        return PIEEG_HELP if pieeg is not None else PAIRING_HELP
    try:
        T.set_scale(args.text_scale)
        app = App(source, sim_script=script, mute=args.mute, cues=not args.no_cues,
                  # Never over a board session: the eye check runs 90 s with no key presses, and a
                  # simulated demo must not start on top of a wearer's calibration or live input.
                  attract=not (args.no_attract or args.screenshot or args.keys
                               or args.input in ("pieeg", "live", "recorded")),
                  help_by_eyes=args.help_by_eyes,
                  confirm_timeout_ms=int(args.confirm_timeout * 1000),
                  p300=args.p300, arm_live_confirm=args.arm_live_confirm,
                  live_options={"calibration_sequences": args.calibration,
                                "alpha_calib_s": args.alpha_calib_s},
                  pieeg=pieeg, recording=recording)
    except Exception as err:
        if not live_path:
            raise
        print(f"Couldn't set up the EEG pipeline: {type(err).__name__}: {err}\n{setup_help()}",
              file=sys.stderr)
        return 3
    if source == InputSources.RECORDED:
        app.sim.mark_gaze = not args.no_gaze_mark
        if args.no_narration:
            app.sim.narrator = None
    qapp.aboutToQuit.connect(app.close)
    if not args.no_report:
        qapp.aboutToQuit.connect(lambda: print(f"session report: {app.write_report()}", flush=True))
    def opening() -> None:
        """The two cards alone, then they settle on the left and the panels fade in."""
        if args.screenshot or args.keys or args.no_intro:
            return
        from signal2speech.ui.intro import play_intro
        qapp.processEvents()                       # the tiles need their final places first
        play_intro(app.root, app.window, app.choices,
                   reveal=[w for w in (app.view, app.conversation, app.window.strip)
                           if isinstance(w, QWidget)])

    if hasattr(app.sim, "calibrate"):          # #103: open the stream and calibrate first
        app.root.showFullScreen() if args.fullscreen else app.root.show()
        opening()
        try:
            app.sim.start()
        except Exception as err:               # g.Pype raises various errors for a missing device
            print(f"{type(err).__name__}: {err}\n{setup_help()}", file=sys.stderr)
            app.close()
            return 3
        try:
            ok = app.sim.calibrate({c.target_id: c.label for c in app.choices})
        except Exception as err:               # release the headset, then report
            app.close()
            print(f"Calibration crashed: {type(err).__name__}: {err}", file=sys.stderr)
            return 1
        if ok is None:
            app.close()                        # window closed during calibration
            return 0
        from signal2speech.eeg.app_live import pump
        pump(2.0 if ok else 6.0)               # let the operator read the calibration result
    guards: List[QTimer] = []   # stopped on return, so a later event loop in this process can't fire them
    if args.screenshot:
        def shoot(code: int) -> None:
            app.root.grab().save(str(args.screenshot))
            print(f"saved {args.screenshot}", flush=True)
            qapp.exit(code)
        # Grab while the reveal is still up (reveal_ms = 8000).
        after_confirm = QTimer(singleShot=True, interval=1200)
        after_confirm.timeout.connect(lambda: shoot(0))
        guards.append(after_confirm)
        app.handler.on_handled.append(
            lambda _e, o: after_confirm.start() if o is Outcome.Confirmed else None)
        guard = QTimer(singleShot=True, interval=30000)
        guard.timeout.connect(lambda: shoot(1))
        guard.start()
        guards.append(guard)

    app.root.showFullScreen() if args.fullscreen else app.root.show()
    if not hasattr(app.sim, "calibrate"):
        opening()
    if not (args.practice and app.start_practice()):
        app.ask()
    keymap = {"1": TargetIds.TARGET_1, "2": TargetIds.TARGET_2}
    for k in filter(None, (s.strip() for s in args.keys.split(","))):
        app.window.press_target(keymap[k])
    try:
        return qapp.exec()
    finally:
        for g in guards:
            g.stop()


if __name__ == "__main__":
    sys.exit(main())
