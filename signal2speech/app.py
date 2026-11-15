"""Signal2Speech integration entry point (#4, #25).

    python -m signal2speech.app --input keyboard|simulated [--sim 2,1] [--mute]

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
- #23 live EEG and #48 recorded replay: refused with a clear message.
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

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from signal2speech.core import (ActionIds, Choice, ConfirmedAction, EegClassMap, InputAdapter,
                                InputSources, Outcome, Round, RoundKind, SelectionEvent,
                                SelectionHandler, TargetIds)
from signal2speech.speech import MutedSpeaker, OfflineSpeaker, Speaker
from signal2speech.ui import INPUT_LABELS, KeyHelpOverlay, SelectionWindow
from signal2speech.ui.__main__ import load_demo_choices

ROOT = Path(__file__).resolve().parents[1]

MAP_ACTIONS = frozenset({ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY})
CONFIRM_TIMEOUT_MS = 15_000   # longer than alpha calibration's ~1.5 s closure plus reading time

BLOCKED_INPUTS = {
    InputSources.RECORDED: "Recorded replay is blocked: it isn't wired into the app yet. Record "
                           "and replay work in the evidence view (python -m signal2speech.evidence, #48).",
}


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
            if hasattr(self.speaker, "on_started"):
                def started(entry=entry, t0=t0):
                    entry["speech_ms"] = round((self.clock() - t0) * 1000, 1)
                    self._report(entry)
                self.speaker.on_started = started
            self.speaker.say(action.spoken_text, action.action_id)
        self._report(entry)

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
                 clock: Callable[[], float] = time.monotonic):
        if input_source in BLOCKED_INPUTS:
            raise ValueError(BLOCKED_INPUTS[input_source])
        if input_source not in (InputSources.KEYBOARD, InputSources.SIMULATED,
                                InputSources.LIVE_EEG):
            raise ValueError(f"Unknown input: {input_source}")
        self.input_source = input_source

        self.transcript_view = QPlainTextEdit(readOnly=True)
        self.transcript_view.setStyleSheet("background:#0f1318; color:#e2e8f0; font-size:15px;"
                                           "font-family: Menlo, Consolas, monospace;")
        self.log = Transcript(self.transcript_view, echo=echo)
        self.view = view if view is not None else load_view()
        if speaker is None:
            speaker = MutedSpeaker(self.log) if mute else OfflineSpeaker(self.log)
        self.speaker = speaker
        self.sink = AppSink(self.view, speaker, self.log, clock=clock)
        self.sink.on_timing = self._show_timing
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.events: List[str] = []          # #131: timeline for the session report
        self.handler = SelectionHandler(self.sink)
        self.keyboard = InputAdapter(self.handler, InputSources.KEYBOARD)
        self.window = SelectionWindow(self.handler, self.keyboard, input_source=input_source,
                                      flash=input_source in (InputSources.SIMULATED,
                                                             InputSources.LIVE_EEG))
        self.choices: List[Choice] = load_demo_choices()

        h = self.handler
        h.on_round_opened.append(self._log_round)
        h.on_preview.append(lambda c: self.log(f"preview (no output): \"{c.spoken_text or c.label}\""))
        h.on_cleared.append(lambda r: self.log(f"cleared ({r}): no output"))
        h.on_handled.append(self._log_outcome)
        h.on_round_opened.append(lambda r: self._event(f"round {r.id} ({r.kind.value}) opened"))
        h.on_cleared.append(lambda r: self._event(f"cleared ({r}), no output"))
        h.on_handled.append(lambda e, o: self._event(
            f"{o.value}" + (f" · {e.source} {e.eventId} {e.roundId}->{e.targetId}" if e else "")))

        self.sim = None
        sim_label = ""
        if input_source == InputSources.LIVE_EEG or (input_source == InputSources.SIMULATED
                                                     and p300):
            # #103: P300 chooses and the alpha switch confirms, on one g.Pype pipeline.
            from signal2speech.eeg.app_live import LiveEegInput
            self.sim = LiveEegInput(
                h, self.window, self.log,
                source="generator" if input_source == InputSources.SIMULATED else "hybridblack",
                script=sim_script or [2, 1], arm_live_confirm=arm_live_confirm,
                **(live_options or {}))
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
        self._row = row
        self.revealing = False
        self.root.resize(1700, 900)

        sc = QShortcut(QKeySequence("D"), self.root)   # rehearse a headset drop (#26)
        sc.setAutoRepeat(False)
        sc.activated.connect(lambda: h.disconnect())
        if hasattr(self.sim, "set_next"):              # #21: pick for a waiting sequence
            for seq, cls in (("Ctrl+1", 1), ("Ctrl+2", 2)):
                s2 = QShortcut(QKeySequence(seq), self.root)
                s2.setAutoRepeat(False)
                s2.activated.connect(lambda c=cls: self.sim.set_next(c))
        # Operator keys (#94). Neither touches the handler.
        rows = [("1 / 2", "Pick a tile. At the preview, 1 confirms and 2 cancels."),
                ("Esc", "Cancel and clear the screen"),
                ("D", "Pretend the headset disconnected"),
                ("F11", "Fullscreen on or off"),
                ("F1", "Show or hide this help")]
        if hasattr(self.sim, "set_next"):
            rows.insert(3, ("Ctrl+1 / Ctrl+2", "Pick for the simulated decoder"))
        self.help = KeyHelpOverlay(self.root, rows, title=f"Keys · input: {INPUT_LABELS[input_source]}")
        for seq, fn in (("F1", self.help.toggle), ("F11", self.toggle_fullscreen)):
            s3 = QShortcut(QKeySequence(seq), self.root)
            s3.setAutoRepeat(False)
            s3.activated.connect(fn)
        self.log(f"input: {INPUT_LABELS[input_source]}" + (f" ({sim_label})" if sim_label else ""))
        self.log(f"speech: {getattr(self.speaker, 'backend', type(self.speaker).__name__)}")

    def toggle_fullscreen(self) -> None:
        if self.root.isFullScreen():
            self.root.showNormal()
        else:
            self.root.showFullScreen()

    def close(self) -> None:
        """Stop the g.Pype stream (#21) and this app's timers, so nothing fires after close."""
        self._confirm_timer.stop()
        self._reopen.stop()
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
        self._row.setStretch(0, 1 if on else 3)
        self._row.setStretch(1, 3 if on else 2)

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
                 f"- **Input:** {INPUT_LABELS[self.input_source]}",
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
        lines += ["", "## Timeline", ""] + [f"- {e}" for e in self.events]
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
                   choices=["keyboard", "simulated", "recorded", "live"])
    p.add_argument("--sim", default="2,1", help="simulated classes in order, e.g. '2,1' "
                                                "(choose target-2, then confirm)")
    p.add_argument("--keys", default="", help="keyboard presses after start, e.g. '2,1'")
    p.add_argument("--mute", action="store_true", help="no audio (logs instead)")
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
    p.add_argument("--screenshot", type=Path, help="save a PNG after the first confirm and exit")
    p.add_argument("--smoke", nargs="?", const="dev", choices=["dev", "judging"],
                   help="hardware-free smoke check, exit 0/1 (#41); 'judging' fails on any SKIP")
    args = p.parse_args(argv)
    if args.smoke:
        from signal2speech.diagnostics import run_smoke
        return run_smoke(args.smoke)
    source = InputSources.LIVE_EEG if args.input == "live" else args.input
    if source in BLOCKED_INPUTS:
        print(BLOCKED_INPUTS[source], file=sys.stderr)
        return 2

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    script = [int(s) for s in args.sim.split(",") if s.strip()]
    if any(s not in (1, 2) for s in script):
        print(f"--sim takes 1s and 2s, e.g. 2,1; got {args.sim!r}", file=sys.stderr)
        return 2
    live_path = source == InputSources.LIVE_EEG or (source == InputSources.SIMULATED and args.p300)
    try:
        app = App(source, sim_script=script, mute=args.mute,
                  confirm_timeout_ms=int(args.confirm_timeout * 1000),
                  p300=args.p300, arm_live_confirm=args.arm_live_confirm,
                  live_options={"calibration_sequences": args.calibration,
                                "alpha_calib_s": args.alpha_calib_s})
    except Exception as err:
        if not live_path:
            raise
        from signal2speech.eeg.app_live import PAIRING_HELP   # driver or pipeline setup failed
        print(f"Couldn't set up the EEG pipeline: {type(err).__name__}: {err}\n{PAIRING_HELP}",
              file=sys.stderr)
        return 3
    qapp.aboutToQuit.connect(app.close)
    if not args.no_report:
        qapp.aboutToQuit.connect(lambda: print(f"session report: {app.write_report()}", flush=True))
    if hasattr(app.sim, "calibrate"):          # #103: open the stream and calibrate first
        app.root.showFullScreen() if args.fullscreen else app.root.show()
        try:
            app.sim.start()
        except Exception as err:               # g.Pype raises various errors for a missing device
            from signal2speech.eeg.app_live import PAIRING_HELP
            print(f"{type(err).__name__}: {err}\n{PAIRING_HELP}", file=sys.stderr)
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
