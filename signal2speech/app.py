"""Signal2Speech integration entry point (#4, #25).

    python -m signal2speech.app --input keyboard|simulated [--sim 2,1] [--mute]

One flow: Choose -> Preview (no output) -> Confirm (one map action + one spoken line) or
Cancel (nothing). Every input goes InputAdapter -> SelectionHandler. Only AppSink.execute
produces output, and the handler calls it exactly once per confirmation.

Dependencies still missing on main are labelled, never faked:
- #30 OpenOrbit view: until signal2speech.openorbit.OpenOrbitView exists, a stand-in panel
  says which action would run.
- #21 g.Pype simulated pipeline: until signal2speech/eeg/simulated.py exists, --input simulated
  injects scripted decisions through the same arm_capture()/select_captured() path live EEG
  uses, and is labelled "Simulated".
- #23 live EEG and #48 recorded replay: refused with a clear message.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from signal2speech.core import (ActionIds, Choice, ConfirmedAction, EegClassMap, InputAdapter,
                                InputSources, Outcome, Round, RoundKind, SelectionEvent,
                                SelectionHandler, TargetIds)
from signal2speech.ui import INPUT_LABELS, SelectionWindow
from signal2speech.ui.__main__ import load_demo_choices

ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "data" / "openorbit" / "audio"   # optional bundled <action_id>.wav (#29)

BLOCKED_INPUTS = {
    InputSources.LIVE_EEG: "Live EEG is blocked: needs the P300 chooser (#46), alpha confirm "
                           "(#47), and the live run (#23).",
    InputSources.RECORDED: "Recorded replay is blocked: needs record/replay (#48).",
}


# ── Output side ──────────────────────────────────────────────
class MapView(Protocol):
    """What #30 exposes. Only AppSink calls these."""
    def show_satellite(self) -> None: ...
    def compare_air_quality(self) -> None: ...


class Speaker(Protocol):
    def say(self, text: str, clip: Optional[str] = None) -> None: ...


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


class AppSink:
    """The only place output happens. SelectionHandler calls execute once per confirm."""

    def __init__(self, view: MapView, speaker: Speaker, log: Callable[[str], None]):
        self.view = view
        self.speaker = speaker
        self.log = log

    def execute(self, action: ConfirmedAction) -> None:
        if action.action_id == ActionIds.SHOW_SATELLITE:
            self.log(f"OUTPUT map: show_satellite()  [{action.source}]")
            self.view.show_satellite()
        elif action.action_id == ActionIds.COMPARE_AIR_QUALITY:
            self.log(f"OUTPUT map: compare_air_quality()  [{action.source}]")
            self.view.compare_air_quality()
        elif action.action_id == ActionIds.SPEAK_REPLY:
            pass
        else:
            self.log(f"IGNORED unknown action {action.action_id!r}")
            return
        if action.spoken_text:
            self.log(f"OUTPUT speak: \"{action.spoken_text}\"")
            self.speaker.say(action.spoken_text, action.action_id)


class PendingMapView(QLabel):
    """Stand-in until #30 lands. Says plainly that it is not the OpenOrbit view."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.calls: List[str] = []
        self.setWordWrap(True)
        self.setMinimumSize(360, 280)
        self.setStyleSheet("background:#151a21; color:#e2e8f0; border:3px dashed #f59e0b;"
                           "border-radius:14px; font-size:22px; padding:20px;")
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


class QtSpeaker(QObject):
    """Offline speech: bundled <action_id>.wav if present, else the OS voice via QtTextToSpeech."""

    def __init__(self, log: Callable[[str], None], audio_dir: Path = AUDIO_DIR):
        super().__init__()
        from PySide6.QtTextToSpeech import QTextToSpeech
        self.log = log
        self.audio_dir = audio_dir
        self.tts = QTextToSpeech(self)
        self.tts.stateChanged.connect(lambda s: self.log(f"speech engine: {s.name}"))
        self._sound = None

    def say(self, text: str, clip: Optional[str] = None) -> None:
        wav = self.audio_dir / f"{clip}.wav" if clip else None
        if wav is not None and wav.is_file():
            from PySide6.QtMultimedia import QSoundEffect
            self._sound = QSoundEffect(self)
            self._sound.setSource(QUrl.fromLocalFile(str(wav)))
            self._sound.play()
            self.log(f"speech: bundled {wav.name}")
            return
        self.log(f"speech: OS voice ({self.tts.engine()})")
        self.tts.say(text)


class MutedSpeaker:
    def __init__(self, log: Callable[[str], None]):
        self.log = log

    def say(self, text: str, clip: Optional[str] = None) -> None:
        self.log("speech: muted (--mute), nothing audible")


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
            self._timer.start()

    def _decide(self) -> None:
        if not self.script:
            self.log("simulated: script finished, use keys 1/2")
            return
        cls = self.script.pop(0)
        self.adapter.select_captured(self.classes.target_for(cls))


# ── Wiring ───────────────────────────────────────────────────
class App:
    def __init__(self, input_source: str = InputSources.KEYBOARD, *,
                 view: Optional[MapView] = None, speaker: Optional[Speaker] = None,
                 sim_script: Optional[List[int]] = None, mute: bool = False,
                 echo: bool = True, reopen_ms: int = 2000, confirm_delay_ms: int = 2000):
        if input_source in BLOCKED_INPUTS:
            raise ValueError(BLOCKED_INPUTS[input_source])
        if input_source not in (InputSources.KEYBOARD, InputSources.SIMULATED):
            raise ValueError(f"Unknown input: {input_source}")
        self.input_source = input_source

        self.transcript_view = QPlainTextEdit(readOnly=True)
        self.transcript_view.setStyleSheet("background:#0f1318; color:#e2e8f0; font-size:15px;"
                                           "font-family: Menlo, Consolas, monospace;")
        self.log = Transcript(self.transcript_view, echo=echo)
        self.view = view if view is not None else load_view()
        if speaker is None:
            speaker = MutedSpeaker(self.log) if mute else QtSpeaker(self.log)
        self.speaker = speaker
        self.sink = AppSink(self.view, speaker, self.log)
        self.handler = SelectionHandler(self.sink)
        self.keyboard = InputAdapter(self.handler, InputSources.KEYBOARD)
        self.window = SelectionWindow(self.handler, self.keyboard, input_source=input_source,
                                      flash=input_source == InputSources.SIMULATED)
        self.choices: List[Choice] = load_demo_choices()

        h = self.handler
        h.on_round_opened.append(self._log_round)
        h.on_preview.append(lambda c: self.log(f"preview (no output): \"{c.spoken_text or c.label}\""))
        h.on_cleared.append(lambda r: self.log(f"cleared ({r}): no output"))
        h.on_handled.append(self._log_outcome)

        self.sim: Optional[InjectedSimulatedInput] = None
        if input_source == InputSources.SIMULATED:
            self.sim = InjectedSimulatedInput(h, self.window, sim_script or [2, 1], self.log,
                                              confirm_delay_ms)
            self.window.set_connection("n/a (scripted)")

        # Rule 4: the app opens the next question after a cancel, disconnect, or confirm.
        self._reopen = QTimer(singleShot=True, interval=reopen_ms)
        self._reopen.timeout.connect(self.ask)
        h.on_cleared.append(lambda _r: self._reopen.start())
        h.on_handled.append(lambda _e, o: self._reopen.start() if o is Outcome.Confirmed else None)

        self.root = QWidget()
        self.root.setWindowTitle(f"Signal2Speech · {INPUT_LABELS[input_source]}")
        self.root.setStyleSheet("background:#0b0d10;")
        right = QVBoxLayout()
        title = QLabel("Output and transcript")
        title.setStyleSheet("color:#cbd5e1; font-size:22px; font-weight:600;")
        right.addWidget(title)
        if isinstance(self.view, QWidget):
            right.addWidget(self.view, 3)
        right.addWidget(self.transcript_view, 2)
        row = QHBoxLayout(self.root)
        row.setContentsMargins(0, 0, 16, 0)
        row.addWidget(self.window, 3)
        row.addLayout(right, 2)
        self.root.resize(1700, 900)

        sc = QShortcut(QKeySequence("D"), self.root)   # rehearse a headset drop (#26)
        sc.setAutoRepeat(False)
        sc.activated.connect(lambda: h.disconnect())
        self.log(f"input: {INPUT_LABELS[input_source]}"
                 + (" (scripted, no g.Pype: #21 pending)" if self.sim else ""))

    def ask(self) -> None:
        self.handler.begin_choice_round(self.choices)

    def _log_round(self, rnd: Round) -> None:
        labels = ", ".join(f"{c.target_id}={c.label}" for c in rnd.choices)
        self.log(f"round {rnd.id} {rnd.kind.value}: {labels}")

    def _log_outcome(self, e: Optional[SelectionEvent], o: Outcome) -> None:
        ev = f"{e.source} {e.eventId} {e.roundId}->{e.targetId}" if e else "malformed"
        self.log(f"{o.value}: {ev}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.app")
    p.add_argument("--input", default=InputSources.KEYBOARD,
                   choices=["keyboard", "simulated", "recorded", "live"])
    p.add_argument("--sim", default="2,1", help="simulated classes in order, e.g. '2,1' "
                                                "(choose target-2, then confirm)")
    p.add_argument("--keys", default="", help="keyboard presses after start, e.g. '2,1'")
    p.add_argument("--mute", action="store_true", help="no audio (logs instead)")
    p.add_argument("--screenshot", type=Path, help="save a PNG after the first confirm and exit")
    args = p.parse_args(argv)
    source = InputSources.LIVE_EEG if args.input == "live" else args.input
    if source in BLOCKED_INPUTS:
        print(BLOCKED_INPUTS[source], file=sys.stderr)
        return 2

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    script = [int(s) for s in args.sim.split(",") if s.strip()]
    app = App(source, sim_script=script, mute=args.mute)
    if args.screenshot:
        def shoot(code: int) -> None:
            app.root.grab().save(str(args.screenshot))
            print(f"saved {args.screenshot}", flush=True)
            qapp.exit(code)
        # Grab before the question reopens (reopen_ms = 2000).
        app.handler.on_handled.append(
            lambda _e, o: QTimer.singleShot(1200, lambda: shoot(0)) if o is Outcome.Confirmed else None)
        QTimer.singleShot(30000, lambda: shoot(1))

    app.root.show()
    app.ask()
    keymap = {"1": TargetIds.TARGET_1, "2": TargetIds.TARGET_2}
    for k in filter(None, (s.strip() for s in args.keys.split(","))):
        app.window.press_target(keymap[k])
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
