"""Headless pipeline monitor behind the MCP server (#110). g.Pype only, no Qt, no raw EEG out.

The monitor runs the same P300 evidence pipeline as ``python -m signal2speech.evidence --p300``
(#76): the chooser's front end, its LDA scorers, and the calibration Triggers whose epochs the
averages are built from. Beside it, a quality tap keeps the last 10 s of signal in memory (it
never leaves the process), and an alpha branch tracks occipital alpha power like the eye-closure
switch (#47).

**Generator (Simulated).** A session thread flashes the two tiles itself: first ``calibration``
cued sequences, which fill the target / non-target averages and train the LDA, then one online
sequence every ``period`` seconds with a random attended tile, so ``latest_decisions`` shows
real classifier output against a known answer.

**Headset (Live EEG).** No tiles are on screen in a headless process, so nobody has anything to
look at: the monitor doesn't flash, the P300 average stays empty, and the tools say so. Quality
and alpha are live. Run the app or the evidence view for P300 with a wearer.

Everything returned is a summary: per-channel RMS, averaged waveforms downsampled to 20 ms
bins, band power, decision outcomes. Raw samples stay in this process.
"""
from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

import gpype as gp
import numpy as np
from gpype.common.constants import Constants

from signal2speech.eeg import alpha_confirm as am
from signal2speech.eeg import p300
from signal2speech.eeg.live import CHANNELS, assess_quality
from signal2speech.evidence.p300_mode import build_p300_evidence
from signal2speech.evidence.pipeline import InputLabel, SourceKind

RATE = p300.RATE
QUALITY_SECONDS = 10.0
BIN_MS = 20
P300_WINDOW_MS = (250, 500)       # where a P300 peaks after the flash


class _Tap(gp.INode):
    """Hands each frame (or event) to ``on_rows`` on the g.Pype worker thread.

    The input inherits its timing, like ``gp.Collector``, so it can follow a stream or an
    event node such as ``EpochAverage``.
    """

    def __init__(self, **kwargs):
        from gpype.backend.core.i_port import IPort
        kwargs.setdefault("input_ports", [IPort.Configuration(
            name=Constants.Defaults.PORT_IN, timing=Constants.Timing.INHERITED)])
        super().__init__(**kwargs)
        self.on_rows = lambda rows: None

    def step(self, data):
        block = data.get(Constants.Defaults.PORT_IN)
        if block is not None and len(block):
            self.on_rows(np.asarray(block))
        return {}


@dataclass
class Decision:
    t: float
    attended: Optional[str]           # what the synthetic brain looked at (Generator only)
    decided: Optional[str]
    scores: dict = field(default_factory=dict)

    @property
    def correct(self) -> Optional[bool]:
        return None if self.attended is None or self.decided is None \
            else self.attended == self.decided


class Monitor:
    """Builds and runs the pipeline; thread-safe read-only snapshots for the MCP tools."""

    def __init__(self, source: str = "generator", calibration: int = 6, period: float = 6.0,
                 seed: Optional[int] = None):
        self.kind = SourceKind(source)
        self.simulated = self.kind is SourceKind.GENERATOR
        self.calibration_sequences = calibration
        self.period = period
        self.rng = random.Random(seed)
        from signal2speech.eeg.app_live import placeholder_model
        self.ev = build_p300_evidence(self.kind, model=placeholder_model())
        self.graph = self.ev.graph
        self.label: InputLabel = self.graph.label
        # No adapter and no Qt: decisions are recorded here, never sent to a handler.
        self.chooser = p300.P300Chooser(self.ev.nodes, adapter=None, use_qt=False)

        self._lock = threading.Lock()
        self._ring: Deque[np.ndarray] = deque()
        self._ring_rows = 0
        self._avg = {"target": None, "nontarget": None}
        self._avg_n = {"target": 0, "nontarget": 0}
        self._alpha: Deque[tuple] = deque(maxlen=int(am.FRAME_RATE * 120))
        self.decisions: Deque[Decision] = deque(maxlen=200)
        self.state = "built"
        self.calibrated = False
        self.p300_note = ("" if self.simulated else
                          "No P300 in headless live mode: there are no tiles for the wearer to "
                          "look at. Use the app (--input live) or the evidence view (--p300).")
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._wire()

    # ── Graph additions ──────────────────────────────────────
    def _wire(self) -> None:
        p, g = self.graph.pipeline, self.graph
        quality = _Tap(name="mcp_quality")
        quality.on_rows = self._on_quality_rows
        signal = gp.ChannelSelector(roles=Constants.ChannelRoles.SIGNAL, name="mcp_signal")
        p.connect(g.raw, signal)
        p.connect(signal, quality)
        for which, node in (("target", g.target_average), ("nontarget", g.nontarget_average)):
            tap = _Tap(name=f"mcp_{which}_avg")
            tap.on_rows = lambda rows, w=which: self._on_average(w, rows)
            p.connect(node, tap)
        sel = gp.ChannelSelector(indices=list(am.OCCIPITAL), name="mcp_occipital")
        fft = gp.FFT(window_size=am.FFT_WINDOW, overlap=am.FFT_OVERLAP, name="mcp_alpha_fft")
        power = gp.BandPower(bands=["alpha"], name="mcp_alpha_power")
        mean = am.ChannelMean(expect_rate=am.FRAME_RATE, name="mcp_alpha_mean")
        tap = _Tap(name="mcp_alpha")
        tap.on_rows = self._on_alpha_rows
        for a, b in ((g.epoch_input, sel), (sel, fft), (fft, power), (power, mean), (mean, tap)):
            p.connect(a, b)

    def _on_quality_rows(self, rows: np.ndarray) -> None:
        keep = int(QUALITY_SECONDS * RATE)
        with self._lock:
            self._ring.append(rows.astype(np.float32, copy=True))
            self._ring_rows += len(rows)
            while self._ring and self._ring_rows - len(self._ring[0]) >= keep:
                self._ring_rows -= len(self._ring.popleft())

    def _on_average(self, which: str, block: np.ndarray) -> None:
        avg = np.asarray(block)
        if avg.ndim == 3:                               # (samples, channels, n): last = all
            avg = avg[..., -1]
        with self._lock:
            self._avg[which] = avg.astype(np.float64, copy=True)
            self._avg_n[which] += 1

    def _on_alpha_rows(self, rows: np.ndarray) -> None:
        now = time.monotonic()
        with self._lock:
            for v in rows[:, 0]:
                self._alpha.append((now, float(v)))

    # ── Lifecycle ────────────────────────────────────────────
    def start(self) -> None:
        self.graph.pipeline.start()
        self.state = "running"
        if self.simulated:
            self._thread = threading.Thread(target=self._session, daemon=True, name="mcp-session")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.state == "running":
            self.graph.pipeline.stop()
        self.graph.pipeline.close()
        self.state = "stopped"

    def wait(self, until, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end and not until():
            time.sleep(0.05)
        return until()

    # ── Session (Generator only) ─────────────────────────────
    def _flash_sequence(self) -> None:
        start = time.monotonic()
        for k, tile in enumerate(p300.make_sequence(self.chooser.aggregator.flashes_per_tile,
                                                    self.rng)):
            delay = start + k * p300.SOA_S - time.monotonic()
            if delay > 0 and self._stop.wait(delay):
                return
            self.chooser.on_flash(tile)

    def _session(self) -> None:
        tiles = list(p300.FLASH_CODES)
        for i in range(self.calibration_sequences):
            if self._stop.is_set():
                return
            self.chooser.begin_calibration(tiles[i % 2])
            self._flash_sequence()
            self._stop.wait(0.4)
        self._stop.wait(p300.TIME_POST + 0.5)
        try:
            self.chooser.finish_calibration()
            self.calibrated = True
        except Exception as err:                        # surfaced through the tools
            self.p300_note = f"P300 calibration failed: {type(err).__name__}: {err}"
            return
        while not self._stop.is_set():
            attended = self.rng.choice(tiles)
            before = len(self.chooser.decisions)
            self.chooser.begin_sequence(attended_for_synthetic=attended)
            self._flash_sequence()
            end = time.monotonic() + p300.TIME_POST + 1.0
            while len(self.chooser.decisions) == before and time.monotonic() < end:
                if self._stop.wait(0.05):
                    return
            if len(self.chooser.decisions) == before:
                self.chooser.end_sequence()
            decided, scores = None, {}
            if len(self.chooser.decisions) > before:
                cls, means = self.chooser.decisions[-1]
                decided = EEG_TARGET.get(cls)
                scores = {k: round(float(v), 3) for k, v in means.items()}
            self.decisions.append(Decision(time.time(), attended, decided, scores))
            self._stop.wait(max(0.0, self.period))

    # ── Snapshots for the tools ──────────────────────────────
    def quality_block(self) -> np.ndarray:
        with self._lock:
            if not self._ring:
                return np.empty((0, len(CHANNELS)))
            return np.concatenate(list(self._ring))[:, :len(CHANNELS)]

    def averages(self):
        with self._lock:
            return ({k: (None if v is None else v.copy()) for k, v in self._avg.items()},
                    dict(self._avg_n))

    def alpha_history(self, seconds: float = 30.0) -> List[float]:
        now = time.monotonic()
        with self._lock:
            return [v for t, v in self._alpha if now - t <= seconds]


EEG_TARGET = {1: "target-1", 2: "target-2"}


def summarize_quality(monitor: Monitor) -> dict:
    block = monitor.quality_block()
    if len(block) < RATE:
        return {"ready": False, "seconds": round(len(block) / RATE, 1),
                "note": "Collecting: need at least 1 s of signal."}
    report = assess_quality(block)
    return {"ready": True, "seconds": round(report.seconds, 1), "go": report.go,
            "channels": [{"name": c.name, "rms_uv_1_30hz": round(c.rms_uv, 2),
                          "line_noise_uv": round(c.line_uv, 2), "status": c.status,
                          "line_warning": c.line_warning} for c in report.channels]}


def summarize_average(monitor: Monitor, channel: str = "Pz") -> dict:
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
    ci = CHANNELS.index(channel)
    avgs, counts = monitor.averages()
    if avgs["target"] is None or avgs["nontarget"] is None:
        return {"ready": False, "channel": channel, "epochs": counts,
                "note": monitor.p300_note or "No calibration epochs yet; wait for calibration."}
    pre = int(round(p300.TIME_PRE * RATE))
    t_ms = (np.arange(avgs["target"].shape[0]) - pre) / RATE * 1000.0

    def binned(avg):
        y = avg[:, ci]
        edges = np.arange(t_ms[0], t_ms[-1] + BIN_MS, BIN_MS)
        idx = np.digitize(t_ms, edges)
        return [round(float(y[idx == k].mean()), 2) for k in range(1, len(edges)) if
                np.any(idx == k)], [int(e) for e in edges[:-1]]

    tgt, bins_ms = binned(avgs["target"])
    non, _ = binned(avgs["nontarget"])
    win = (t_ms >= P300_WINDOW_MS[0]) & (t_ms <= P300_WINDOW_MS[1])
    diff = avgs["target"][:, ci] - avgs["nontarget"][:, ci]
    peak_i = int(np.argmax(np.where(win, diff, -np.inf)))
    base = (t_ms < 0)
    noise = float(np.std(diff[base])) if base.any() else 0.0
    peak = float(diff[peak_i])
    visible = bool(peak > max(1.0, 3 * noise))
    return {"ready": True, "channel": channel, "epochs": counts,
            "bin_ms": BIN_MS, "bin_start_ms": bins_ms,
            "target_uv": tgt, "nontarget_uv": non,
            "p300_window_ms": list(P300_WINDOW_MS),
            "peak_difference_uv": round(peak, 2), "peak_latency_ms": int(round(t_ms[peak_i])),
            "baseline_noise_uv": round(noise, 2),
            "p300_visible": visible,
            "rule": "visible if the target minus non-target peak in 250-500 ms is above 1 µV "
                    "and above 3x the pre-flash noise"}


def summarize_alpha(monitor: Monitor) -> dict:
    hist = monitor.alpha_history(30.0)
    if not hist:
        return {"ready": False, "note": "Collecting alpha power (needs about 1 s)."}
    arr = np.asarray(hist)
    return {"ready": True, "band_hz": [8, 13], "channels": [CHANNELS[i] for i in am.OCCIPITAL],
            "latest_power": round(float(arr[-1]), 3),
            "median_30s": round(float(np.median(arr)), 3),
            "p10_30s": round(float(np.percentile(arr, 10)), 3),
            "p90_30s": round(float(np.percentile(arr, 90)), 3),
            "rows_30s": int(len(arr)),
            "note": ("The Generator adds a constant 10 Hz sine, so simulated alpha is always "
                     "high; it shows the branch works, not eye state." if monitor.simulated else
                     "Eyes closed raise this power; compare against the 30 s median.")}
