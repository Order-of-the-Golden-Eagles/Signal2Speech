"""Confirm with a deliberate alpha switch (#47).

Closing the eyes for about 2 s raises occipital alpha (8-13 Hz). One closure in an armed
Confirm round emits exactly one ``target-1`` (Confirm). Opening the eyes or timing out does
nothing.

    source -> [AlphaBursts, simulated only] -> Bandpass 1-30 Hz
      -> ChannelSelector(PO7, Oz, PO8) -> FFT(1 s, 90 % overlap) -> BandPower(alpha)
      -> ChannelMean -> Threshold(level, release, dwell) -> _Tap       [g.Pype worker threads]
      -> AlphaConfirm.rising / .falling (queued Qt signals)             [Qt main thread]
      -> InputAdapter.select_captured("target-1"), armed Confirm round only

    python -m signal2speech.eeg.alpha_confirm                  # Generator: calibrate, measure, report
    python -m signal2speech.eeg.alpha_confirm --demo           # Generator: keyboard preview, alpha confirm
    python -m signal2speech.eeg.alpha_confirm --source hybrid-black   # live: follow the prompts

Round rules on top of the threshold:

- **Armed Confirm round only.** A Confirm round arms the adapter when it opens. Choose rounds,
  no round, and an already used confirm ignore every closure.
- **Eyes open first.** An edge counts only once the eyes have been open (state 0) for
  ``settle_s`` since arming. A closure that began in the previous round can't confirm.
- **One closure, one event.** Only a rising edge counts, and the Threshold hysteresis and dwell
  stop chatter. The adapter disarms after the decision.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

import gpype as gp
import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

from signal2speech.core import (InputAdapter, InputSources, Round, RoundKind,
                                SelectionHandler, TargetIds)

PORT_IN, PORT_OUT = "in", "out"
#: Unicorn Hybrid Black montage, 0-based: Fz C3 Cz C4 Pz PO7 Oz PO8. Alpha is occipital.
OCCIPITAL = (5, 6, 7)
SAMPLING_RATE = 250.0
FFT_WINDOW = 250          # 1 s
FFT_OVERLAP = 0.9         # a new band-power row every 0.1 s
FRAME_RATE = SAMPLING_RATE / round(FFT_WINDOW * (1 - FFT_OVERLAP))   # 10 rows/s
UNCALIBRATED_LEVEL = 1e12  # nothing crosses this until calibrate() runs


# ── g.Pype nodes ─────────────────────────────────────────────
class AlphaBursts(gp.IONode):
    """Simulated eyes-closed alpha: adds a 10 Hz sine to every signal channel while closed.

    ``close_eyes()`` and ``open_eyes()`` are safe to call from any thread. Use it only with
    ``gp.Generator``, and label that input ``simulated``.
    """

    def __init__(self, amplitude_uv: float = 8.0, frequency_hz: float = 10.0, **kwargs):
        super().__init__(**kwargs)
        self.amplitude_uv = float(amplitude_uv)
        self.frequency_hz = float(frequency_hz)
        self._closed = threading.Event()
        self.closed_at: Optional[float] = None
        self._n = 0
        self._fs = SAMPLING_RATE
        self._signal: List[int] = []

    def close_eyes(self) -> None:
        self.closed_at = time.monotonic()
        self._closed.set()

    def open_eyes(self) -> None:
        self._closed.clear()

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        ctx = port_context_in[PORT_IN]
        self._fs = float(ctx.get("sampling_rate") or SAMPLING_RATE)
        roles = ctx.get("channel_roles") or ["signal"] * int(ctx["channel_count"])
        self._signal = [i for i, r in enumerate(roles) if r == "signal"]
        return out

    def step(self, data):
        x = np.array(data[PORT_IN], copy=True)
        t = (self._n + np.arange(len(x))) / self._fs
        self._n += len(x)
        if self._closed.is_set():
            wave = self.amplitude_uv * np.sin(2 * np.pi * self.frequency_hz * t)
            x[:, self._signal] += wave[:, None].astype(x.dtype)
        return {PORT_OUT: x}


class ChannelMean(gp.IONode):
    """Averages all channels into one, so a single Threshold level fits every electrode."""

    def __init__(self, label: str = "occipital:alpha", **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        ctx = out[PORT_OUT]
        ctx["channel_count"] = 1
        ctx["channel_roles"] = ["signal"]
        ctx["channel_labels"] = [self.label]
        for key in ("channel_types", "channel_units"):
            if ctx.get(key) is not None:
                ctx[key] = [ctx[key][0]]
        return out

    def step(self, data):
        x = data[PORT_IN]
        return {PORT_OUT: x.mean(axis=1, keepdims=True).astype(x.dtype)}


class _Tap(gp.INode):
    """Hands each frame to ``on_rows`` on the g.Pype worker thread."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.on_rows: Callable[[np.ndarray], None] = lambda rows: None

    def step(self, data):
        block = data.get(PORT_IN)
        if block is not None and len(block):
            self.on_rows(np.asarray(block))
        return {}


# ── Calibration ──────────────────────────────────────────────
class CalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class Calibration:
    """Threshold levels from eyes-open and eyes-closed band power (same units as BandPower)."""
    open_p95: float
    closed_median: float
    level: float
    release: float

    @property
    def ratio(self) -> float:
        return self.closed_median / self.open_p95 if self.open_p95 > 0 else float("inf")

    @classmethod
    def from_samples(cls, open_values, closed_values, min_ratio: float = 2.0) -> "Calibration":
        """Enter at the geometric midpoint, and release halfway (geometrically) back to open.

        Raises CalibrationError when closed alpha is not at least ``min_ratio`` times the
        eyes-open 95th percentile. A switch that close would false-trigger.
        """
        o = np.asarray(open_values, dtype=float)
        c = np.asarray(closed_values, dtype=float)
        if o.size < 5 or c.size < 5:
            raise CalibrationError("need at least 5 band-power rows for each condition")
        open_p95 = float(np.percentile(o, 95))
        closed_median = float(np.median(c))
        if open_p95 <= 0 or closed_median < min_ratio * open_p95:
            raise CalibrationError(
                f"eyes-closed alpha median {closed_median:.3g} is not {min_ratio:g}x the "
                f"eyes-open 95th percentile {open_p95:.3g}. Check the occipital electrodes, "
                f"or close the eyes fully and relax.")
        level = float(np.sqrt(open_p95 * closed_median))
        release = float(np.sqrt(open_p95 * level))
        return cls(open_p95, closed_median, level, release)


# ── Decoder ──────────────────────────────────────────────────
class AlphaConfirm(QObject):
    """Alpha-switch confirm for the selection handler. Create and use it on the Qt main thread.

    Builds its own pipeline from ``source``. Alternatively, pass ``pipeline`` and ``upstream``
    to hang the branch off an existing pipeline, because one headset can only be opened once,
    so #23 shares the HybridBlack source with the P300 branch (#46).
    """

    rising = Signal(float)    # monotonic time of a 0 -> 1 Threshold edge (worker thread)
    falling = Signal(float)   # 1 -> 0

    def __init__(self, handler: SelectionHandler, *, input_source: str = InputSources.SIMULATED,
                 source=None, pipeline=None, upstream=None, bursts: Optional[AlphaBursts] = None,
                 dwell_s: float = 1.0, settle_s: float = 1.0, auto: bool = True,
                 channels=OCCIPITAL, parent: Optional[QObject] = None):
        super().__init__(parent)
        if input_source == InputSources.KEYBOARD:
            raise ValueError("alpha confirm is EEG input: simulated, recorded, or live-eeg")
        self.handler = handler
        self.input_source = input_source
        self.adapter = InputAdapter(handler, input_source)
        self.settle_s = settle_s
        self.dwell = max(1, round(dwell_s * FRAME_RATE))
        self.bursts = bursts
        self.calibration: Optional[Calibration] = None

        self._lock = threading.Lock()
        self._power: List[float] = []
        self._state = 0                      # worker-side Threshold state
        self.state = 0                       # main-thread copy
        self._armed_at: Optional[float] = None
        self._open_since: Optional[float] = None
        self.edges: List[float] = []         # every rising edge seen on the main thread
        self.log: List[tuple] = []           # (time, what, detail)
        self.decision_threads: List[str] = []

        self._owns_pipeline = pipeline is None
        if pipeline is None:
            pipeline = gp.Pipeline()
            src = source or gp.Generator(sampling_rate=SAMPLING_RATE, channel_count=8,
                                         noise_amplitude=10.0)
            if self.bursts is not None:
                pipeline.connect(src, self.bursts)
                src = self.bursts
            upstream = gp.Bandpass(f_lo=1, f_hi=30)
            pipeline.connect(src, upstream)
        elif upstream is None:
            raise ValueError("pass upstream= (a node in that pipeline) along with pipeline=")
        self.pipeline = pipeline

        select = gp.ChannelSelector(indices=list(channels))
        fft = gp.FFT(window_size=FFT_WINDOW, overlap=FFT_OVERLAP)
        power = gp.BandPower(bands=["alpha"])
        mean = ChannelMean()
        self.threshold = gp.Threshold(level=UNCALIBRATED_LEVEL, release=UNCALIBRATED_LEVEL,
                                      dwell=self.dwell)
        self._power_tap, self._state_tap = _Tap(), _Tap()
        self._power_tap.on_rows = self._on_power_rows
        self._state_tap.on_rows = self._on_state_rows
        for a, b in ((upstream, select), (select, fft), (fft, power), (power, mean),
                     (mean, self._power_tap), (mean, self.threshold),
                     (self.threshold, self._state_tap)):
            pipeline.connect(a, b)

        self.rising.connect(self._on_rising, Qt.ConnectionType.QueuedConnection)
        self.falling.connect(self._on_falling, Qt.ConnectionType.QueuedConnection)
        self.running = False
        if auto:
            handler.on_round_opened.append(self._on_round_opened)
            handler.on_cleared.append(lambda _reason: self.disarm())

    # ── Worker-thread side ───────────────────────────────────
    def _on_power_rows(self, rows: np.ndarray) -> None:
        with self._lock:
            self._power.extend(float(v) for v in rows[:, 0])

    def _on_state_rows(self, rows: np.ndarray) -> None:
        for v in rows[:, 0]:
            s = 1 if v >= 0.5 else 0
            if s != self._state:
                self._state = s
                (self.rising if s else self.falling).emit(time.monotonic())

    # ── Lifecycle ────────────────────────────────────────────
    def start(self) -> None:
        if self._owns_pipeline and not self.running:
            self.pipeline.start()
        self.running = True

    def stop(self) -> None:
        if self._owns_pipeline and self.running:
            self.pipeline.stop()
        self.running = False

    def close(self) -> None:
        self.stop()
        if self._owns_pipeline:
            self.pipeline.close()

    # ── Calibration ──────────────────────────────────────────
    def power_count(self) -> int:
        with self._lock:
            return len(self._power)

    def power_since(self, index: int) -> np.ndarray:
        with self._lock:
            return np.array(self._power[index:], dtype=float)

    def collect(self, seconds: float, tick: Optional[Callable[[], None]] = None) -> np.ndarray:
        """Band-power rows over the next ``seconds``. Keeps the Qt event loop alive."""
        start, end = self.power_count(), time.monotonic() + seconds
        app = QCoreApplication.instance()
        while time.monotonic() < end:
            if app is not None:
                app.processEvents()
            if tick:
                tick()
            time.sleep(0.01)
        return self.power_since(start)

    def apply(self, cal: Calibration) -> Calibration:
        self.threshold.set_control({"level": cal.level, "release": cal.release,
                                    "dwell": self.dwell})
        self.calibration = cal
        self._note("calibrated", asdict(cal))
        return cal

    def calibrate(self, open_values, closed_values, min_ratio: float = 2.0) -> Calibration:
        return self.apply(Calibration.from_samples(open_values, closed_values, min_ratio))

    # ── Arming (main thread) ─────────────────────────────────
    @property
    def armed(self) -> bool:
        return self._armed_at is not None

    def arm(self, now: Optional[float] = None) -> None:
        """Start the confirm window for the open Confirm round."""
        now = time.monotonic() if now is None else now
        self.adapter.arm_capture()
        self._armed_at = now
        self._open_since = now if self.state == 0 else None   # eyes must open first
        self._note("armed", self.handler.current.id if self.handler.current else None)

    def disarm(self) -> None:
        self._armed_at = self._open_since = None

    def _on_round_opened(self, rnd: Round) -> None:
        if rnd.kind is RoundKind.CONFIRM:
            self.arm()
        else:
            self.disarm()

    @Slot(float)
    def _on_falling(self, t: float) -> None:
        self.state = 0
        if self.armed and self._open_since is None:
            self._open_since = t

    @Slot(float)
    def _on_rising(self, t: float) -> None:
        self.state = 1
        self.edges.append(t)
        self.decision_threads.append(threading.current_thread().name)
        if not self.armed:
            self._note("ignored", "not armed")
            return
        if self._open_since is None or t - self._open_since < self.settle_s:
            self._note("ignored", f"eyes not open {self.settle_s:g} s since arming")
            return
        self.disarm()                                  # one closure, one event
        outcome = self.adapter.select_captured(TargetIds.TARGET_1)
        self._note("confirm", outcome.value)

    def _note(self, what: str, detail) -> None:
        self.log.append((time.monotonic(), what, detail))


# ── Standalone runs ──────────────────────────────────────────
def _prompt(text: str) -> None:
    print(f">>> {text}", flush=True)


def measure(ac: AlphaConfirm, calib_s: float, rest_s: float, closures: int,
            closure_s: float = 2.0, gap_s: float = 3.0, min_ratio: float = 2.0) -> dict:
    """Calibrate, count false triggers at rest, then time ``closures`` deliberate closures."""
    sim = ac.bursts
    report = {"input": ac.input_source, "settle_s": ac.settle_s, "dwell_rows": ac.dwell}

    _prompt(f"Calibration: keep your eyes OPEN and relaxed for {calib_s:g} s")
    if sim:
        sim.open_eyes()
    ac.collect(1.0)                                   # let the 1 s FFT window fill
    open_vals = ac.collect(calib_s)
    _prompt(f"Calibration: CLOSE your eyes for {calib_s:g} s")
    if sim:
        sim.close_eyes()
    ac.collect(1.0)
    closed_vals = ac.collect(calib_s)
    _prompt("Open your eyes")
    if sim:
        sim.open_eyes()
    try:
        cal = ac.calibrate(open_vals, closed_vals, min_ratio)
    except CalibrationError as err:
        report["error"] = str(err)
        return report
    report["calibration"] = {**asdict(cal), "ratio": round(cal.ratio, 2)}
    ac.collect(max(gap_s, 1.5))                       # settle back to open

    _prompt(f"Rest: keep your eyes OPEN for {rest_s:g} s (counting false triggers)")
    before = len(ac.edges)
    ac.collect(rest_s)
    report["rest_s"] = rest_s
    report["false_triggers"] = len(ac.edges) - before

    latencies, per_closure = [], []
    for i in range(closures):
        _prompt(f"Closure {i + 1}/{closures}: CLOSE your eyes now for {closure_s:g} s")
        before, t0 = len(ac.edges), time.monotonic()
        if sim:
            sim.close_eyes()
        ac.collect(closure_s)
        _prompt("Open")
        if sim:
            sim.open_eyes()
        ac.collect(gap_s)
        new = ac.edges[before:]
        per_closure.append(len(new))
        if new:
            latencies.append(round(new[0] - t0, 3))
    report["edges_per_closure"] = per_closure
    report["latency_s"] = latencies
    return report


def demo(ac: AlphaConfirm, choices, closure_s: float = 2.0) -> List[tuple]:
    """Keyboard preview, then an alpha confirm. Returns the handler's (event, outcome) log."""
    h, log = ac.handler, []
    h.on_handled.append(lambda e, o: log.append((e, o)))
    keyboard = InputAdapter(h, InputSources.KEYBOARD)
    h.begin_choice_round(choices)
    keyboard.select_now(TargetIds.TARGET_2)            # preview "Compare counties"
    ac.collect(ac.settle_s + 0.2)                      # eyes open while reading the preview
    _prompt(f"Confirm: CLOSE your eyes for {closure_s:g} s")
    if ac.bursts:
        ac.bursts.close_eyes()
    ac.collect(closure_s)
    if ac.bursts:
        ac.bursts.open_eyes()
    ac.collect(1.0)
    return log


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.alpha_confirm")
    p.add_argument("--source", choices=["generator", "hybrid-black"], default="generator")
    p.add_argument("--demo", action="store_true", help="keyboard preview, then alpha confirm")
    p.add_argument("--calib-s", type=float, default=10.0, help="seconds per calibration condition")
    p.add_argument("--rest-s", type=float, default=60.0, help="eyes-open false-trigger window")
    p.add_argument("--closures", type=int, default=3)
    p.add_argument("--dwell-s", type=float, default=1.0)
    p.add_argument("--settle-s", type=float, default=1.0)
    p.add_argument("--burst-uv", type=float, default=8.0, help="generator: simulated alpha amplitude")
    p.add_argument("--min-ratio", type=float, default=2.0)
    args = p.parse_args(argv)

    from signal2speech.ui.__main__ import PrintSink, load_demo_choices   # reuse #24's stubs

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    handler = SelectionHandler(PrintSink())
    if args.source == "hybrid-black":
        source, bursts, label = gp.HybridBlack(enable_oscar=True), None, InputSources.LIVE_EEG
    else:
        bursts = AlphaBursts(amplitude_uv=args.burst_uv)
        source, label = gp.Generator(sampling_rate=SAMPLING_RATE, channel_count=8,
                                     noise_amplitude=10.0), InputSources.SIMULATED
    ac = AlphaConfirm(handler, input_source=label, source=source, bursts=bursts,
                      dwell_s=args.dwell_s, settle_s=args.settle_s)
    print(f"input: {label}", flush=True)
    ac.start()
    try:
        if args.demo:
            report = measure(ac, args.calib_s, 0.0, 0, min_ratio=args.min_ratio)
            if "error" not in report:
                for e, o in demo(ac, load_demo_choices()):
                    print(json.dumps({"outcome": o.value, "source": e.source if e else None,
                                      "roundId": e.roundId if e else None,
                                      "targetId": e.targetId if e else None}), flush=True)
                if label == InputSources.LIVE_EEG and not handler.live_eeg_confirm_armed:
                    print("note: live-eeg confirm stays disarmed in the handler until #23",
                          flush=True)
        else:
            report = measure(ac, args.calib_s, args.rest_s, args.closures,
                             min_ratio=args.min_ratio)
        print(json.dumps({"report": report}), flush=True)
        return 1 if "error" in report else 0
    finally:
        ac.close()
        app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
