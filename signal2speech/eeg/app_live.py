"""Live EEG inside the app (#103): P300 chooses, the alpha switch confirms, on one pipeline.

    python -m signal2speech.app --input live                        # Unicorn: calibrate, then demo
    python -m signal2speech.app --input live --arm-live-confirm     # only after #23 says it's safe
    python -m signal2speech.app --input simulated --p300 --sim 2,1  # same code path, Generator

**Live.** One ``HybridBlack(enable_oscar=True)`` pipeline from ``p300.build_pipeline`` (#46).
The app's own tiles flash through the #24 ``FlashScheduler``, and each flash emits the P300
``Marker`` on the frame the tile lights. The alpha switch (#47) hangs off the same pipeline,
because the Unicorn can be opened only once. The handler keeps live confirm **disarmed** until
#23 says it's safe. Until then key 1 confirms, and the window says so.

**Simulated.** The same class and the same hooks, on ``gp.Generator`` plus ``SyntheticP300``,
labelled Simulated. The script says which tile the "brain" attends in each Choose round and,
in each Confirm round, whether it closes its eyes (1 = close: alpha confirms; 2 = keep them
open: the app's confirm timeout cancels). The alpha branch gets its own Generator with
``AlphaBursts``, because the P300 Generator carries a constant 10 Hz sine.

Before the first question, ``calibrate()`` runs on the app's tiles: P300 sequences with the
attended tile named on screen, then eyes open and eyes closed for the alpha switch.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable, Iterable, Optional

from PySide6.QtCore import QCoreApplication, QTimer

from signal2speech.core import InputAdapter, InputSources, Round, RoundKind, TargetIds
from signal2speech.eeg import alpha_confirm as am
from signal2speech.eeg import p300

TILES = (TargetIds.TARGET_1, TargetIds.TARGET_2)
DISARMED_HINT = ("Confirm: key 1  (eye-closure confirm is off until #23 says it's safe)   ·   "
                 "Cancel: key 2 or Esc")

PAIRING_HELP = """Could not open the Unicorn Hybrid Black.
  1. Turn the headset on (LED blinking) and pair it in the OS Bluetooth settings first.
  2. Close any other app using it (Unicorn Suite, another g.Pype run, the evidence view).
  3. Check it with: python -m signal2speech.eeg.live --source hybridblack
Rehearse without it: python -m signal2speech.app --input simulated --p300"""


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


def find_unicorn(timeout_s: float = 15.0) -> list:
    """Serials of reachable Unicorns, or [] if none answer within ``timeout_s``.

    The driver's discovery is a Bluetooth scan that can take from 3 s to well over 20 s, and
    g.Pype's ``start()`` blocks indefinitely without a device. A daemon thread bounds both.
    """
    import threading
    found: list = []

    def scan():
        import gpype as gp
        found.extend(gp.HybridBlack.get_available_devices())
    th = threading.Thread(target=scan, daemon=True, name="unicorn-scan")
    th.start()
    th.join(timeout_s)
    return list(found)


class LiveEegInput:
    """P300 choose + alpha confirm feeding the app's SelectionHandler. Main thread only."""

    def __init__(self, handler, window, log: Callable[[str], None], *,
                 source: str = "hybridblack", script: Iterable[int] = (),
                 enable_oscar: bool = True, flashes: int = p300.FLASHES_PER_TILE,
                 soa_s: float = p300.SOA_S, calibration_sequences: int = 10,
                 alpha_calib_s: float = 10.0, arm_live_confirm: bool = False,
                 placeholder: Optional[p300.P300Model] = None):
        if source not in ("hybridblack", "generator"):
            raise ValueError("source is hybridblack or generator")
        self.handler, self.window, self.log = handler, window, log
        self.simulated = source == "generator"
        self.enable_oscar = enable_oscar
        self.input_source = InputSources.SIMULATED if self.simulated else InputSources.LIVE_EEG
        self.script = deque(int(s) for s in script)
        self.calibration_sequences = calibration_sequences
        self.alpha_calib_s = alpha_calib_s
        self.calibrated = False
        self.running = False
        self._closed = False
        self._calibrating = False
        self._sequence_done = False
        self.p300_calibration: dict = {}
        self.alpha_calibration: Optional[am.Calibration] = None

        # g.Pype refuses to start a realtime pipeline with an unfitted scorer, so start from a
        # small synthetic model; calibrate() refits every scorer on the wearer.
        placeholder = placeholder or p300.train_on_synthetic(n_sequences=4, seed=99)
        self.nodes = p300.build_pipeline(source, model=placeholder, enable_oscar=enable_oscar)
        self.adapter = InputAdapter(handler, self.input_source)
        self.chooser = p300.P300Chooser(self.nodes, self.adapter, flashes_per_tile=flashes)

        f = window.flasher                              # the chooser's validated timing
        f.repetitions = flashes
        f.flash_ms = int(p300.FLASH_ON_S * 1000)
        f.isi_ms = max(1, int(round((soa_s - p300.FLASH_ON_S) * 1000)))
        self.chooser.aggregator.flashes_per_tile = flashes
        f.on_sequence_started = self._sequence_started
        f.on_flash = self.chooser.on_flash
        f.on_sequence_finished = self._sequence_finished
        self._decide = QTimer(singleShot=True, interval=int((p300.TIME_POST + 0.5) * 1000))
        self._decide.timeout.connect(self.chooser.end_sequence)

        if self.simulated:
            self.bursts: Optional[am.AlphaBursts] = am.AlphaBursts()
            self.alpha = am.AlphaConfirm(handler, input_source=self.input_source,
                                         bursts=self.bursts)
        else:
            self.bursts = None
            self.alpha = am.AlphaConfirm(handler, input_source=self.input_source,
                                         pipeline=self.nodes.pipeline, upstream=self.nodes.eeg)
        handler.live_eeg_confirm_armed = bool(arm_live_confirm)
        self.live_confirm_armed = bool(arm_live_confirm) or self.simulated

        self._eyes_open_timer = QTimer(singleShot=True)
        self._eyes_open_timer.timeout.connect(self._open_eyes)
        self._eyes_close_timer = QTimer(singleShot=True)
        self._eyes_close_timer.timeout.connect(self._close_eyes)
        handler.on_round_opened.append(self._on_round_opened)
        handler.on_cleared.append(self._on_cleared)
        window.set_connection(self.connection_label())

    # ── Labels ───────────────────────────────────────────────
    def connection_label(self) -> str:
        if self.simulated:
            return "g.Pype Generator + synthetic P300 · alpha bursts"
        oscar = "OSCAR on" if self.enable_oscar else "OSCAR off"
        confirm = "eye confirm armed" if self.live_confirm_armed else "eye confirm off (#23)"
        return f"Unicorn Hybrid Black · {oscar} · {confirm}"

    # ── Lifecycle ────────────────────────────────────────────
    def start(self, no_data_s: float = 8.0) -> None:
        """Open the stream(s). Raises RuntimeError if the headset isn't there (see PAIRING_HELP).

        Live, the device list is checked first: with no Unicorn, g.Pype's ``start()`` doesn't
        fail, it blocks while it searches. After starting, the stream must deliver data within
        ``no_data_s``, so a silent headset fails here instead of during calibration.
        """
        if self.running:
            return
        if not self.simulated and not find_unicorn():
            raise RuntimeError("no Unicorn Hybrid Black found (not paired, off, or in use)")
        self.nodes.pipeline.start()
        self.alpha.start()        # its own Generator when simulated; a no-op when shared
        self.running = True
        if not pump(no_data_s, until=lambda: self.alpha.power_count() > 0):
            self.close()
            raise RuntimeError(f"the stream sent no data within {no_data_s:g} s")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for t in (self._decide, self._eyes_open_timer, self._eyes_close_timer):
            t.stop()
        for hooks, fn in ((self.handler.on_round_opened, self._on_round_opened),
                          (self.handler.on_cleared, self._on_cleared)):
            if fn in hooks:
                hooks.remove(fn)
        self.alpha.close()
        if self.running:
            self.nodes.pipeline.stop()
        self.nodes.pipeline.close()
        self.running = False

    # ── Calibration, on the app's own tiles ──────────────────
    def calibrate(self, labels: Optional[dict] = None) -> bool:
        """P300 calibration, then the alpha threshold. Blocks while keeping the UI live."""
        w = self.window
        labels = labels or {TargetIds.TARGET_1: "Tile 1", TargetIds.TARGET_2: "Tile 2"}
        for t in TILES:
            w.tiles[t].set_label(labels[t])
        w.preview.setVisible(False)
        n = self.calibration_sequences
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
                if not pump(budget, until=lambda: self._sequence_done):
                    self.log("calibration: a flash sequence didn't finish")
                pump(0.4)                                # keep sequences apart
            pump(p300.TIME_POST + 0.5)                   # last epochs arrive
            model = self.chooser.finish_calibration()
        except Exception as err:                         # no epochs, a device error, ...
            self._calibrating = False
            self.log(f"P300 calibration failed: {type(err).__name__}: {err}")
            w.prompt.setText("P300 calibration failed. Keys 1 and 2 still work.")
            return False
        self._calibrating = False
        n_t = model.n_target
        self.p300_calibration = {"sequences": n, "target_epochs": n_t,
                                 "nontarget_epochs": len(model.trials) - n_t}
        self.log(f"P300 calibrated on {n_t} target and {len(model.trials) - n_t} non-target "
                 f"epochs ({'simulated' if self.simulated else 'live EEG'})")

        s = self.alpha_calib_s
        try:
            w.prompt.setText(f"Eye-closure calibration: keep your eyes OPEN and relaxed for {s:g} s")
            w.hint.setText("")
            if self.bursts:
                self.bursts.open_eyes()
            self.alpha.collect(1.0)
            open_vals = self.alpha.collect(s)
            w.prompt.setText(f"Now CLOSE your eyes for {s:g} s. We'll say when to open them.")
            if self.bursts:
                self.bursts.close_eyes()
            self.alpha.collect(1.0)
            closed_vals = self.alpha.collect(s)
            if self.bursts:
                self.bursts.open_eyes()
            w.prompt.setText("Open your eyes.")
            self.alpha_calibration = self.alpha.calibrate(open_vals, closed_vals)
            self.alpha.collect(1.5)                      # alpha decays below release
            self.log(f"Alpha switch calibrated: ratio {self.alpha_calibration.ratio:.1f}")
        except am.CalibrationError as err:
            self.log(f"Alpha calibration failed: {err}. Key 1 still confirms.")
            w.prompt.setText("Eye-closure calibration failed. Key 1 confirms instead.")
        for t in TILES:
            w.tiles[t].set_label("")
        w.prompt.setText("Calibrated. Waiting for a question")
        self.calibrated = True
        return True

    # ── Flash hooks ──────────────────────────────────────────
    def _sequence_started(self) -> None:
        if self._calibrating:
            return                                       # begin_calibration already ran
        attended = None
        if self.simulated and self.script:
            attended = TILES[self.script.popleft() - 1]  # which tile the synthetic brain attends
        self.chooser.begin_sequence(attended_for_synthetic=attended)

    def _sequence_finished(self) -> None:
        if self._calibrating:
            self._sequence_done = True
        else:
            self._decide.start()                         # force a decision if an epoch is missing

    # ── Rounds ───────────────────────────────────────────────
    def _on_round_opened(self, rnd: Round) -> None:
        self._decide.stop()
        if rnd.kind is not RoundKind.CONFIRM:
            return
        if not self.live_confirm_armed:
            self.window.hint.setText(DISARMED_HINT)      # runs after the window's own listener
        if self.simulated and self.script:
            if self.script.popleft() == 1:               # the synthetic wearer closes their eyes
                self._eyes_close_timer.start(int((self.alpha.settle_s + 0.2) * 1000))

    def _on_cleared(self, _reason: str) -> None:
        self._decide.stop()
        self._open_eyes()

    def _close_eyes(self) -> None:
        if self.bursts:
            self.bursts.close_eyes()
            self._eyes_open_timer.start(2500)

    def _open_eyes(self) -> None:
        self._eyes_close_timer.stop()
        if self.bursts:
            self.bursts.open_eyes()
