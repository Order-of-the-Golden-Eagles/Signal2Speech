"""Live EEG inside the app (#103): P300 chooses, the alpha switch confirms, on one pipeline.

    python -m signal2speech.app --input live                        # Unicorn: calibrate, then demo
    python -m signal2speech.app --input live --arm-live-confirm     # only after #23 says it's safe
    python -m signal2speech.app --input simulated --p300 --sim 2,1  # same code path, Generator

**Live.** One ``HybridBlack(enable_oscar=True)`` pipeline from ``p300.build_pipeline`` (#46).
The app's own tiles flash through the #24 ``FlashScheduler``, and each flash emits the P300
``Marker`` on the frame the tile lights. The alpha switch (#47) hangs off the same pipeline,
because the Unicorn can be opened only once. The handler keeps live confirm **disarmed** until
#23 says it's safe; until then key 1 confirms, and the window's Confirm hint says so.

**Simulated.** The same class and the same hooks, on ``gp.Generator`` plus ``SyntheticP300``,
labelled Simulated. The script alternates: the tile the "brain" attends in a Choose round (1 or
2), then what it does in the Confirm round (1 = close its eyes, so the alpha switch confirms;
2 = keep them open, so the app's confirm timeout cancels). When the script runs out, the tiles
stop flashing and keys 1 and 2 take over. The alpha branch gets its own Generator with
``AlphaBursts``, because the P300 Generator carries a constant 10 Hz sine.

Before the first question, ``calibrate()`` runs on the app's tiles: P300 sequences with the
attended tile named on screen, then eyes open and eyes closed for the alpha switch. A failed
step turns that brain path off (keys still work) and the prompt and strip say which.
"""
from __future__ import annotations

import gc
import shutil
import tempfile
import threading
import time
from collections import deque
from typing import Callable, Iterable, Optional

from PySide6.QtCore import QCoreApplication, QTimer

from signal2speech.core import InputAdapter, InputSources, Round, RoundKind, TargetIds
from signal2speech.eeg import alpha_confirm as am
from signal2speech.eeg import p300

TILES = (TargetIds.TARGET_1, TargetIds.TARGET_2)
MAX_REFLASH = 2          # re-flash a Choose round this often when no decision arrives

PAIRING_HELP = """Could not open the Unicorn Hybrid Black.
  1. Turn the headset on (LED blinking) and pair it in the OS Bluetooth settings first.
  2. Close any other app using it (Unicorn Suite, another g.Pype run, the evidence view).
  3. Check it with: python -m signal2speech.eeg.live --source hybridblack
Rehearse without it: python -m signal2speech.app --input simulated --p300"""


class CalibrationAborted(Exception):
    """The operator closed the window during calibration."""


def pump(seconds: float, until: Optional[Callable[[], bool]] = None) -> bool:
    """Run the Qt event loop for up to ``seconds`` (or until ``until()`` is true)."""
    app = QCoreApplication.instance()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if until is not None and until():
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.005)
    return until() if until is not None else True


def _bounded(fn: Callable[[], object], timeout_s: float, name: str):
    """Run ``fn`` in a daemon thread. Returns (finished, result, error)."""
    box: dict = {}

    def run():
        try:
            box["result"] = fn()
        except BaseException as err:        # reported to the caller, not swallowed
            box["error"] = err
    th = threading.Thread(target=run, daemon=True, name=name)
    th.start()
    th.join(timeout_s)
    return (not th.is_alive()), box.get("result"), box.get("error")


def find_unicorn(timeout_s: float = 15.0) -> list:
    """Serials of reachable Unicorns, or [] if none answer within ``timeout_s``.

    The driver's discovery is a Bluetooth scan that can take from 3 s to well over 20 s.
    Raises RuntimeError if the scan itself fails (a missing driver is not "not paired").
    """
    def scan():
        import gpype as gp
        return gp.HybridBlack.get_available_devices()
    done, result, err = _bounded(scan, timeout_s, "unicorn-scan")
    if done and err is not None:
        raise RuntimeError(f"couldn't search for a Unicorn (driver problem?): "
                           f"{type(err).__name__}: {err}")
    return list(result or []) if done else []


_PLACEHOLDER: Optional[p300.P300Model] = None


def placeholder_model() -> p300.P300Model:
    """The synthetic stand-in LDA g.Pype needs to start; built once per process."""
    global _PLACEHOLDER
    if _PLACEHOLDER is None:
        tmp = tempfile.mkdtemp(prefix="s2s-p300-")
        try:
            _PLACEHOLDER = p300.train_on_synthetic(n_sequences=4, seed=99, workdir=tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _PLACEHOLDER


class SimulatedEyes:
    """A simulated wearer's eyes: close shortly after a Confirm round opens, reopen 2.5 s later.

    Shared by the Generator path (#103, ``AlphaBursts``) and the PiEEG self-test (#172,
    ``SelfTestStream``). ``eyes()`` returns the object with ``close_eyes``/``open_eyes``, or None
    when there is nothing simulated to drive.
    """

    HOLD_MS = 2500

    def __init__(self, eyes: Callable[[], object]):
        self._eyes = eyes
        self._close_timer = QTimer(singleShot=True)
        self._close_timer.timeout.connect(self.close_now)
        self._open_timer = QTimer(singleShot=True)
        self._open_timer.timeout.connect(self.open_now)

    def close_after(self, settle_s: float) -> None:
        """Close once the alpha switch's settle time has passed (eyes must be open first)."""
        self._close_timer.start(int((settle_s + 0.2) * 1000))

    def closing(self) -> bool:
        return self._close_timer.isActive()

    def close_now(self) -> None:
        eyes = self._eyes()
        if eyes is not None:
            eyes.close_eyes()
            self._open_timer.start(self.HOLD_MS)

    def open_now(self) -> None:
        self._close_timer.stop()
        eyes = self._eyes()
        if eyes is not None:
            eyes.open_eyes()

    def stop(self) -> None:
        self._close_timer.stop()
        self._open_timer.stop()


class LiveEegInput:
    """P300 choose + alpha confirm feeding the app's SelectionHandler. Main thread only."""

    def __init__(self, handler, window, log: Callable[[str], None], *,
                 source: str = "hybridblack", script: Iterable[int] = (),
                 enable_oscar: bool = True, flashes: int = p300.FLASHES_PER_TILE,
                 soa_s: float = p300.SOA_S, calibration_sequences: int = 10,
                 alpha_calib_s: float = 10.0, arm_live_confirm: bool = False,
                 placeholder: Optional[p300.P300Model] = None, open_timeout_s: float = 20.0):
        if source not in ("hybridblack", "generator"):
            raise ValueError("source is hybridblack or generator")
        script = [int(s) for s in script]
        if any(s not in (1, 2) for s in script):
            raise ValueError(f"script values are 1 or 2, got {script}")
        self.handler, self.window, self.log = handler, window, log
        self.simulated = source == "generator"
        self.enable_oscar = enable_oscar
        self.input_source = InputSources.SIMULATED if self.simulated else InputSources.LIVE_EEG
        self.script = deque(script)
        self.calibration_sequences = calibration_sequences
        self.alpha_calib_s = alpha_calib_s
        self.open_timeout_s = open_timeout_s
        self.calibrated = False
        self.p300_ok: Optional[bool] = None       # None until calibrate() ran
        self.alpha_ok: Optional[bool] = None
        self.running = False
        self._closed = False
        self._calibrating = False
        self._sequence_done = False
        self._got_decision = False
        self._reflashes = 0
        self._reflashing = False
        self._last_attended: Optional[str] = None
        self._start_hung = False
        self.p300_calibration: dict = {}
        self.alpha_calibration: Optional[am.Calibration] = None

        # g.Pype refuses to start a realtime pipeline with an unfitted scorer, so start from a
        # small synthetic model (in a private temp folder); calibrate() refits every scorer.
        placeholder = placeholder or placeholder_model()
        self.nodes = p300.build_pipeline(source, model=placeholder, enable_oscar=enable_oscar)
        self.adapter = InputAdapter(handler, self.input_source)
        self.chooser = p300.P300Chooser(self.nodes, self.adapter, flashes_per_tile=flashes)
        self.chooser.bridge.listeners.append(self._on_p300_decision)

        f = window.flasher                              # the chooser's validated timing
        self._saved_flasher = (f.repetitions, f.flash_ms, f.isi_ms, f.on_sequence_started,
                               f.on_flash, f.on_sequence_finished)
        f.repetitions = flashes
        f.flash_ms = int(p300.FLASH_ON_S * 1000)
        f.isi_ms = max(1, int(round((soa_s - p300.FLASH_ON_S) * 1000)))
        self.chooser.aggregator.flashes_per_tile = flashes
        f.on_sequence_started = self._sequence_started
        f.on_flash = self.chooser.on_flash
        f.on_sequence_finished = self._sequence_finished
        self._decide = QTimer(singleShot=True, interval=int((p300.TIME_POST + 0.5) * 1000))
        self._decide.timeout.connect(self._force_decision)

        if self.simulated:
            self.bursts: Optional[am.AlphaBursts] = am.AlphaBursts()
            self.alpha = am.AlphaConfirm(handler, input_source=self.input_source,
                                         bursts=self.bursts)
        else:
            self.bursts = None
            self.alpha = am.AlphaConfirm(handler, input_source=self.input_source,
                                         pipeline=self.nodes.pipeline, upstream=self.nodes.eeg)
        handler.live_eeg_confirm_armed = bool(arm_live_confirm)

        self.eyes = SimulatedEyes(lambda: self.bursts)
        handler.on_round_opened.append(self._on_round_opened)
        handler.on_cleared.append(self._on_cleared)
        window.set_connection(self.connection_label())

    @property
    def live_confirm_armed(self) -> bool:
        """Whether an eye closure can confirm: always when simulated, else the handler's flag."""
        return self.simulated or self.handler.live_eeg_confirm_armed

    # ── Labels ───────────────────────────────────────────────
    def connection_label(self) -> str:
        parts = ["g.Pype Generator + synthetic P300 · alpha bursts" if self.simulated else
                 f"Unicorn Hybrid Black · {'OSCAR on' if self.enable_oscar else 'OSCAR off'}"]
        if self.p300_ok is False:
            parts.append("P300 off (calibration failed)")
        if self.alpha_ok is False:
            parts.append("eye confirm off (calibration failed)")
        elif not self.simulated:
            parts.append("eye confirm armed" if self.live_confirm_armed else "eye confirm off (#23)")
        return " · ".join(parts)

    # ── Lifecycle ────────────────────────────────────────────
    def start(self, no_data_s: float = 8.0) -> None:
        """Open the stream(s). Raises RuntimeError if the headset can't be used.

        Live, both discovery and ``pipeline.start()`` are bounded: without a usable Unicorn,
        g.Pype's ``start()`` doesn't fail, it blocks. Then the stream must deliver data within
        ``no_data_s``, so a silent headset fails here instead of during calibration.
        """
        if self.running:
            return
        if self.simulated:
            self.nodes.pipeline.start()
        else:
            if not find_unicorn():
                raise RuntimeError("no Unicorn Hybrid Black found (not paired, off, or in use)")
            done, _r, err = _bounded(self.nodes.pipeline.start, self.open_timeout_s,
                                     "unicorn-open")
            if not done:
                # start() is still blocked in its thread: close() must not touch the pipeline
                # under it. The daemon thread dies with the process.
                self._start_hung = True
                raise RuntimeError(f"found a Unicorn but couldn't open it within "
                                   f"{self.open_timeout_s:g} s (is another app using it?)")
            if err is not None:
                raise RuntimeError(f"couldn't open the Unicorn: {type(err).__name__}: {err}")
        self.running = True       # set before anything else can fail, so close() stops it
        self.alpha.start()        # its own Generator when simulated; a no-op when shared
        if not pump(no_data_s, until=lambda: self.alpha.power_count() > 0):
            self.close()
            raise RuntimeError(f"the stream sent no data within {no_data_s:g} s")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        f = self.window.flasher
        f.stop()
        (f.repetitions, f.flash_ms, f.isi_ms, f.on_sequence_started, f.on_flash,
         f.on_sequence_finished) = self._saved_flasher
        self._decide.stop()
        self.eyes.stop()
        for hooks, fn in ((self.handler.on_round_opened, self._on_round_opened),
                          (self.handler.on_cleared, self._on_cleared)):
            if fn in hooks:
                hooks.remove(fn)
        self.alpha.close()
        if not self._start_hung:
            if self.running:
                self.nodes.pipeline.stop()
            self.nodes.pipeline.close()
        self.running = False

    # ── Calibration, on the app's own tiles ──────────────────
    def calibrate(self, labels: Optional[dict] = None) -> Optional[bool]:
        """P300 calibration, then the alpha threshold. Blocks while keeping the UI live.

        Returns True if both worked, False if either failed (that path is turned off and the
        screen says so), or None if the operator closed the window.
        """
        w = self.window
        watched = w.isVisible()                     # closing the window aborts calibration

        def wait(seconds: float, until=None) -> bool:
            ok = pump(seconds, until=lambda: (watched and not w.isVisible())
                      or (until() if until else False))
            if watched and not w.isVisible():
                raise CalibrationAborted()
            return ok if until else True

        labels = labels or {TargetIds.TARGET_1: "Tile 1", TargetIds.TARGET_2: "Tile 2"}
        for t in TILES:
            w.tiles[t].set_label(labels[t])
        w.preview.setVisible(False)
        try:
            self.p300_ok = self._calibrate_p300(labels, wait)
            self.alpha_ok = self._calibrate_alpha(wait)
        except CalibrationAborted:
            self._calibrating = False
            w.flasher.stop()
            self.log("calibration aborted: the window was closed")
            return None
        for t in TILES:
            w.tiles[t].set_label("")
        if not self.p300_ok:
            w.flash_enabled = False                 # no brain choosing; keys 1 and 2 still work
        w.eye_confirm = bool(self.alpha_ok)         # the Confirm hint follows what really works
        status = (f"P300 {'ready' if self.p300_ok else 'OFF, use keys 1 and 2'} · "
                  f"eye-closure confirm {'ready' if self.alpha_ok else 'OFF, use key 1'}")
        w.prompt.setText(f"Calibration done: {status}")
        w.set_connection(self.connection_label())
        self.log(f"calibration: {status}")
        self.calibrated = True
        return bool(self.p300_ok and self.alpha_ok)

    def _calibrate_p300(self, labels: dict, wait) -> bool:
        w, n = self.window, self.calibration_sequences
        self._calibrating = True
        try:
            for i in range(n):
                attended = TILES[i % 2]
                w.prompt.setText(f"Calibration {i + 1}/{n}: look at “{labels[attended]}” "
                                 "and silently count its flashes")
                w.hint.setText("Keep still. Don't press anything.")
                self.chooser.begin_calibration(attended)
                self._sequence_done = False
                w.flasher.start(list(TILES))
                budget = 2 * len(TILES) * w.flasher.repetitions * \
                    (w.flasher.flash_ms + w.flasher.isi_ms) / 1000 + 2
                if not wait(budget, until=lambda: self._sequence_done):
                    self.log("calibration: a flash sequence didn't finish")
                wait(0.4)                                    # keep sequences apart
            wait(p300.TIME_POST + 0.5)                       # last epochs arrive
            model = self.chooser.finish_calibration()
        except CalibrationAborted:
            raise
        except Exception as err:                             # no epochs, a device error, ...
            self.log(f"P300 calibration failed: {type(err).__name__}: {err}. Keys 1 and 2 "
                     "still choose.")
            return False
        finally:
            self._calibrating = False
        n_t = model.n_target
        self.p300_calibration = {"sequences": n, "target_epochs": n_t,
                                 "nontarget_epochs": len(model.trials) - n_t}
        self.log(f"P300 calibrated on {n_t} target and {len(model.trials) - n_t} non-target "
                 f"epochs ({'simulated' if self.simulated else 'live EEG'})")
        return True

    def _calibrate_alpha(self, wait) -> bool:
        w, s = self.window, self.alpha_calib_s

        def collect(seconds: float):
            start = self.alpha.power_count()
            wait(seconds)
            return self.alpha.power_since(start)
        try:
            w.prompt.setText(f"Eye-closure calibration: keep your eyes OPEN and relaxed for {s:g} s")
            w.hint.setText("")
            if self.bursts:
                self.bursts.open_eyes()
            collect(1.0)
            open_vals = collect(s)
            w.prompt.setText(f"Now CLOSE your eyes for {s:g} s. We'll say when to open them.")
            if self.bursts:
                self.bursts.close_eyes()
            collect(1.0)
            closed_vals = collect(s)
            if self.bursts:
                self.bursts.open_eyes()
            w.prompt.setText("Open your eyes.")
            self.alpha_calibration = self.alpha.calibrate(open_vals, closed_vals)
            collect(1.5)                                     # alpha decays below release
        except CalibrationAborted:
            raise
        except Exception as err:                             # incl. CalibrationError
            self.log(f"Eye-closure calibration failed: {type(err).__name__}: {err}. "
                     "Key 1 still confirms.")
            return False                                     # threshold stays at "never fires"
        self.log(f"Alpha switch calibrated: ratio {self.alpha_calibration.ratio:.1f}")
        return True

    # ── Flash hooks ──────────────────────────────────────────
    def _sequence_started(self) -> None:
        if self._calibrating:
            return                                       # begin_calibration already ran
        attended = None
        if self.simulated:
            if self._reflashing:                         # same question again: same attention
                attended = self._last_attended
            elif not self.script:                        # script spent: keys take over
                self.window.flasher.stop()
                self.window.hint.setText("Simulated script finished: press 1 or 2")
                return
            else:
                attended = TILES[self.script.popleft() - 1]   # tile the synthetic brain attends
            self._last_attended = attended
        self._reflashing = False
        self._got_decision = False
        self.chooser.begin_sequence(attended_for_synthetic=attended)

    def _sequence_finished(self) -> None:
        if self._calibrating:
            self._sequence_done = True
        else:
            self._decide.start()                         # force a decision if an epoch is missing

    def _on_p300_decision(self, _cls, _target, _outcome) -> None:
        self._got_decision = True

    def _force_decision(self) -> None:
        if self._got_decision:
            return
        if self.chooser.end_sequence() is not None:
            return
        rnd = self.handler.current
        if rnd is None or rnd.kind is not RoundKind.CHOOSE:
            return
        if self._reflashes < MAX_REFLASH:                # no scores at all: flash again
            self._reflashes += 1
            self.log(f"no P300 decision; flashing again ({self._reflashes}/{MAX_REFLASH})")
            self._reflashing = True
            self.window.flasher.start(list(TILES))
        else:
            self.log("no P300 decision after re-flashing; use keys 1 or 2")
            self.window.hint.setText("No brain decision: press 1 or 2")

    # ── Rounds ───────────────────────────────────────────────
    def _on_round_opened(self, rnd: Round) -> None:
        self._decide.stop()
        if rnd.kind is RoundKind.CHOOSE:
            self._reflashes = 0
            if self.simulated and not self.window.flash_enabled and self.script:
                self.script.popleft()                    # P300 off: keys choose this step
            return
        if self.simulated and self.script:
            if self.script.popleft() == 1:               # the synthetic wearer closes their eyes
                self.eyes.close_after(self.alpha.settle_s)

    def _on_cleared(self, _reason: str) -> None:
        self._decide.stop()
        self.eyes.open_now()


# ── PiEEG eye-closure confirm (#172) ─────────────────────────
PIEEG_HELP = """Could not use the PiEEG board's LSL stream.
  1. Power the board from a 5 V power bank (never the laptop's USB while it's on someone's head).
  2. In PiEEG's starter folder, run and leave running: python python_quickstart.py --lsl
  3. Check it with: python -m signal2speech.eeg.lsl_source --input live --check
Rehearse without the board: python -m signal2speech.app --input pieeg --pieeg-self-test"""

PIEEG_STREAM_IS = ("live", "simulated", "recorded")


class PiEEGConfirm:
    """Eye-closure confirm from a PiEEG Octopus 16 over LSL; the keyboard chooses (#172).

    The board is only an amplifier: ``pieeg_lsl.make_source`` puts its relayed LSL stream into the
    same ``AlphaConfirm`` (#47) the Unicorn path uses, so g.Pype stays the whole pipeline. The P300
    chooser is never wired to it: one spot on the head gives an eyes-closed signal, not a P300.

    ``stream_is`` says what is publishing, because LSL can't prove it: ``live`` (a real board on a
    person), ``simulated`` (PiEEG's simulator or our self-test), or ``recorded`` (a replayed
    session). Eye-closure confirm switches on only after this session's #150 check passes
    (``lsl_source.safe_to_arm``). Until then, and if it fails, key 1 confirms.
    """

    def __init__(self, handler, window, log: Callable[[str], None], *, stream_is: str,
                 stream: Optional[str] = None, any_host: bool = False,
                 channels: Optional[str] = None, self_test: bool = False,
                 auto_eyes: Optional[bool] = None, probe_s: float = 8.0,
                 alpha_calib_s: float = 10.0, rest_s: float = 20.0, closures: int = 3,
                 find_timeout_s: float = 5.0, no_data_s: float = 8.0):
        from signal2speech.eeg import lsl_source as lsl

        if self_test:
            stream_is = "simulated"                      # our own publisher: never Live
        if stream_is not in PIEEG_STREAM_IS:
            raise ValueError(f"stream_is is one of {', '.join(PIEEG_STREAM_IS)}")
        if closures < 2:
            raise ValueError("the #150 check needs at least 2 closures")
        self.handler, self.window, self.log = handler, window, log
        self.stream_is = stream_is
        self.input_source = {"live": InputSources.LIVE_EEG, "simulated": InputSources.SIMULATED,
                             "recorded": InputSources.RECORDED}[stream_is]
        self.self_test = self_test
        self.stream = stream or (lsl.SELF_TEST_NAME if self_test else lsl.STREAM_NAME)
        self.any_host = any_host
        self.channels_arg = channels
        # The self-test closes its simulated eyes on each Confirm round, so a rehearsal runs
        # hands-free. Tests pass auto_eyes=False and call publisher.close_eyes() themselves.
        self.auto_eyes = self_test if auto_eyes is None else auto_eyes
        self.probe_s, self.alpha_calib_s = probe_s, alpha_calib_s
        self.rest_s, self.closures = rest_s, closures
        self.find_timeout_s, self.no_data_s = find_timeout_s, no_data_s

        self.publisher = None                            # lsl_source.SelfTestStream
        self.relay = None                                # pieeg_lsl.PiEEGRelay
        self.device = None
        self.alpha: Optional[am.AlphaConfirm] = None
        self.pick = None
        self.report: dict = {}
        self.armed = False                               # eye-closure confirm on for this session
        self.reasons: list = []
        self.calibrated = False
        self.running = False
        self._closed = False
        self.eyes = SimulatedEyes(lambda: self.publisher)
        self.on_label: Optional[Callable[[str], None]] = None    # App refreshes its title
        handler.live_eeg_confirm_armed = False           # only the check below may switch it on
        handler.on_round_opened.append(self._on_round_opened)
        handler.on_cleared.append(self._on_cleared)
        window.eye_confirm = False                       # the hint says key 1 until the check passes
        window.eye_off_reason = "the eye check hasn't run yet"
        self._show_label()

    # ── Labels ───────────────────────────────────────────────
    @property
    def device_name(self) -> str:
        return self.device.name if self.device else "PiEEG Octopus 16"

    def confirm_label(self) -> str:
        """What confirms, as the strip shows it: 'Live EEG (PiEEG Octopus 16)'."""
        from signal2speech.eeg import lsl_source as lsl
        if self.stream_is == "live":
            return f"Live EEG ({self.device_name})"
        if self.stream_is == "recorded":
            return f"Recorded ({self.device_name})"
        return "Simulated (self-test LSL stream)" if self.self_test else lsl.SIMULATED_LABEL

    def strip_text(self) -> str:
        if self.armed:
            return f"Choose: Keyboard · Confirm: {self.confirm_label()}"
        state = "eye check not run yet" if not self.calibrated else "eye check failed"
        return f"Choose: Keyboard · Confirm: key 1 · {self.confirm_label()}: {state}"

    def connection_label(self) -> str:
        parts = [f"PiEEG over LSL · stream '{self.relay.name if self.relay else self.stream}'"]
        if self.pick is not None and self.device is not None:
            parts.append(f"pins {self.device.describe_channels(self.pick.channels)}")
        parts.append("eye confirm armed" if self.armed else
                     "eye confirm off (check failed)" if self.calibrated else
                     "eye confirm off until the check passes")
        return " · ".join(parts)

    def _show_label(self) -> None:
        text = self.strip_text()
        self.window.set_input_text(text, self.input_source if self.armed else InputSources.KEYBOARD)
        self.window.set_connection(self.connection_label())
        if self.on_label is not None:
            self.on_label(text)

    # ── Lifecycle ────────────────────────────────────────────
    def start(self) -> None:
        """Find this computer's stream and relay it. Raises RuntimeError if it can't be used."""
        from signal2speech.eeg import devices, pieeg_lsl
        from signal2speech.eeg import lsl_source as lsl

        if self.running:
            return
        if self.self_test:
            self.publisher = lsl.SelfTestStream(name=self.stream).start()
        try:
            info = lsl.find_stream(self.stream, any_host=self.any_host,
                                   timeout=self.find_timeout_s)
        except pieeg_lsl.PiEEGSetupError as err:
            self.close()
            raise RuntimeError(f"no LSL stream '{self.stream}' on this computer") from err
        self.relay = pieeg_lsl.PiEEGRelay(info).start()
        self.running = True
        self.device = (devices.PIEEG_OCTOPUS16 if self.self_test else
                       devices.detect(stream_name=info.name(), channel_count=info.channel_count(),
                                      rate=info.nominal_srate()))
        if not pump(self.no_data_s, until=lambda: self.relay.rows > 0):
            self.close()
            raise RuntimeError(f"the stream '{self.stream}' sent no data within {self.no_data_s:g} s")
        self.log(f"PiEEG: {self.confirm_label()}, {self.relay.channels} channels at "
                 f"{self.relay.rate:g} Hz (stream '{info.name()}' on {info.hostname()})")
        if self.stream_is == "live":
            self.log(lsl.SAFETY)
        self._show_label()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.eyes.stop()
        for hooks, fn in ((self.handler.on_round_opened, self._on_round_opened),
                          (self.handler.on_cleared, self._on_cleared)):
            if fn in hooks:
                hooks.remove(fn)
        # Nothing can confirm after this. ``armed`` keeps this session's check verdict, so the
        # session report (written on quit, after close) still says what really confirmed.
        self.handler.live_eeg_confirm_armed = False
        if self.alpha is not None:
            self.alpha.close()
        if self.relay is not None:
            self.relay.stop()
        self.alpha = self.relay = None
        # The relay and its thread reference each other, so only a collection frees its inlet.
        # Free it before the publisher's outlet goes, or the inlet logs "transmission broke off"
        # and retries. The second pass frees the publisher's outlet, so its name is free again.
        gc.collect()
        if self.publisher is not None:
            self.publisher.stop()
        self.publisher = None
        self.running = False
        gc.collect()

    # ── The #150 check, on screen ────────────────────────────
    def calibrate(self, labels: Optional[dict] = None) -> Optional[bool]:
        """Channel check, alpha calibration, rest and closures; arm only if it's clean.

        Returns True if eye-closure confirm is on, False if the check failed (key 1 confirms),
        or None if the operator closed the window.
        """
        from signal2speech.eeg import devices
        from signal2speech.eeg import lsl_source as lsl

        w = self.window
        watched = w.isVisible()

        def closed() -> bool:
            return watched and not w.isVisible()

        def tick() -> None:
            QCoreApplication.processEvents()             # keep the window live while reading
            if closed():
                raise CalibrationAborted()

        def prompt(text: str) -> None:
            w.prompt.setText(text)
            w.hint.setText("Eye-closure check (#150). Don't press anything.")
            self.log(f"check: {text}")
            tick()

        for t in TILES:
            w.tiles[t].set_label("")
        w.preview.setVisible(False)
        try:
            try:
                requested = lsl.parse_channels(self.channels_arg, self.relay.channels)
                self.pick = lsl.choose_channels(self.device, requested, self.relay.name,
                                                self.relay.rate, self.probe_s, prompt,
                                                sim=self.publisher, say=self.log, tick=tick)
            except (devices.NoAlphaResponse, ValueError) as err:
                return self._finish({"error": f"channel check: {err}"})
            except CalibrationAborted:
                raise
            except Exception as err:                     # the stream dropped, LSL errors, ...
                return self._finish({"error": f"channel check: {type(err).__name__}: {err}"})
            self.log(f"using {self.device.describe_channels(self.pick.channels)}: {self.pick.reason}")
            try:
                self.alpha = am.AlphaConfirm(
                    self.handler, input_source=self.input_source,
                    source=self._source(), channels=list(self.pick.channels),
                    sampling_rate=self.relay.rate)
                self.alpha.bursts = self.publisher       # the self-test's eyes follow the prompts
                self.alpha.start()
                pump(self.no_data_s, until=lambda: closed() or self.alpha.power_count() > 0)
                tick()
                if self.alpha.power_count() == 0:
                    return self._finish({"error": "no alpha band power from the stream"})
                report = am.measure(self.alpha, self.alpha_calib_s, self.rest_s, self.closures,
                                    prompt=prompt, tick=tick)
            except CalibrationAborted:
                raise
            except Exception as err:                     # g.Pype or the stream failed mid-check
                return self._finish({"error": f"{type(err).__name__}: {err}"})
        except CalibrationAborted:
            self.log("eye-closure check aborted: the window was closed")
            return None
        return self._finish(report)

    def _source(self):
        from signal2speech.eeg import pieeg_lsl
        return pieeg_lsl.make_source(self.relay.name, self.relay.channels, self.relay.rate)

    def _finish(self, report: dict) -> bool:
        from signal2speech.eeg import lsl_source as lsl

        self.report = report
        ok, self.reasons = lsl.safe_to_arm(report, self.closures)
        self.calibrated = True
        self.armed = ok
        if not ok and self.alpha is not None:
            self.alpha.close()                           # nothing from the board can confirm
            self.alpha = None
        # The handler gates Live EEG confirms; Simulated and Recorded confirms are gated by
        # closing the switch above, so every label follows the same rule.
        self.handler.live_eeg_confirm_armed = ok and self.input_source == InputSources.LIVE_EEG
        self.window.eye_confirm = ok
        self.window.eye_off_reason = "the eye check failed"
        verdict = (f"Eye-closure confirm ON: {self.confirm_label()} passed the check"
                   if ok else "Eye-closure confirm OFF, key 1 confirms: " + "; ".join(self.reasons))
        self.window.prompt.setText(verdict)
        self.window.hint.setText("")
        self.log(f"check: false triggers {report.get('false_triggers')}, confirms per closure "
                 f"{report.get('edges_per_closure')} -> {'armed' if ok else 'not armed'}")
        self._show_label()
        return ok

    # ── Self-test eyes ───────────────────────────────────────
    def _on_round_opened(self, rnd: Round) -> None:
        self.eyes.stop()
        if rnd.kind is RoundKind.CONFIRM and self.auto_eyes and self.armed and self.alpha:
            self.eyes.close_after(self.alpha.settle_s)

    def _on_cleared(self, _reason: str) -> None:
        self.eyes.open_now()
