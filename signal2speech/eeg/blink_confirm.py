"""Double-blink confirm for the headset.

A blink is the biggest, clearest thing on a forehead EEG channel: a sharp swing of the signal,
much larger than the ongoing brain activity. Two blinks in quick succession (about 0.15 to 0.9 s
apart) are deliberate; single blinks happen all the time and never confirm.

This measures an eye movement picked up by the EEG electrodes (EOG), not a brain rhythm, and the
app labels it that way. It hands a detection to ``AlphaConfirm`` through the same path as an eye
closure, so the arming, the settle time and the one-confirm-per-round rules are unchanged.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

from .alpha_confirm import _Tap

RATE_HZ = 250.0
CHANNEL = 0                    # Fz on the Unicorn Hybrid Black: closest to the eyes
REFRACTORY_S = 0.25            # one blink is one event, however long its swing lasts
PAIR_MIN_S, PAIR_MAX_S = 0.15, 0.9
AFTER_DOUBLE_S = 1.5           # after a double blink, ignore blinks for a moment
MIN_RATIO = 2.5                # blinks must stand this far above the resting signal
SMOOTH = 25                    # 0.1 s moving average: keeps the slow blink swing, drops the
                               # faster brain activity and noise that hide it on a dry electrode


class BlinkError(ValueError):
    pass


class BlinkSwitch:
    def __init__(self, on_double: Callable[[float], None], log: Callable[[str], None] = print,
                 rate: float = RATE_HZ, channel: int = CHANNEL):
        self.on_double = on_double            # called on the g.Pype worker thread
        self.log = log
        self.rate = rate
        self.channel = channel
        self.tap = _Tap(name="blink_confirm")
        self.tap.on_rows = self._on_rows
        self.level: Optional[float] = None    # None until calibrated: nothing is detected
        self._lock = threading.Lock()
        self._samples = deque(maxlen=int(rate * 60))
        self._tail = np.zeros(0)              # last raw samples, so smoothing joins blocks up
        self._count = 0                       # samples seen, for calibration windows
        self._last_blink = -1e9               # sample index of the last blink onset
        self._prev_blink = -1e9
        self._quiet_until = -1e9
        self.doubles = 0

    # ── worker thread ──
    def _on_rows(self, rows: np.ndarray) -> None:
        block = np.asarray(rows, dtype=float)
        if block.ndim == 1:
            block = block[:, None]
        raw = block[:, min(self.channel, block.shape[1] - 1)]
        joined = np.concatenate([self._tail, raw])
        self._tail = joined[-(SMOOTH - 1):]
        smooth = np.convolve(joined, np.ones(SMOOTH) / SMOOTH, mode="full")[SMOOTH - 1:len(joined)]
        x = np.abs(smooth[-len(raw):])
        fired = False
        with self._lock:
            start = self._count
            self._samples.extend(x.tolist())
            self._count += len(x)
            level = self.level
            if level is None:
                return
            refractory = int(REFRACTORY_S * self.rate)
            for i in np.flatnonzero(x > level):
                n = start + int(i)
                if n - self._last_blink < refractory or n < self._quiet_until:
                    continue
                self._prev_blink, self._last_blink = self._last_blink, n
                gap = (n - self._prev_blink) / self.rate
                if PAIR_MIN_S <= gap <= PAIR_MAX_S:
                    self._quiet_until = n + int(AFTER_DOUBLE_S * self.rate)
                    self._last_blink = self._prev_blink = -1e9
                    self.doubles += 1
                    fired = True
        if fired:
            self.on_double(time.monotonic())

    # ── calibration (main thread) ──
    def count(self) -> int:
        with self._lock:
            return self._count

    def since(self, index: int) -> np.ndarray:
        with self._lock:
            n = self._count - index
            if n <= 0:
                return np.zeros(0)
            data = list(self._samples)[-min(n, len(self._samples)):]
        return np.asarray(data, dtype=float)

    def calibrate(self, rest: np.ndarray, blink_windows) -> float:
        """Set the detection level between the resting signal and the blinks. ``blink_windows``
        are the samples recorded while the wearer blinked twice, one array per prompt."""
        if rest.size < self.rate * 2:
            raise BlinkError("not enough resting signal")
        baseline = float(np.percentile(rest, 99))
        peaks = [float(np.max(w)) for w in blink_windows if len(w)]
        if len(peaks) < 2:
            raise BlinkError("not enough blink recordings")
        peak = float(np.median(peaks))
        if baseline <= 0 or peak < MIN_RATIO * baseline:
            raise BlinkError(f"blinks ({peak:.3g}) are not {MIN_RATIO:g}x the resting signal "
                             f"({baseline:.3g}). Check the forehead electrode, or blink firmly.")
        level = float(np.sqrt(baseline * peak))
        # Each prompt should hold two blinks above the level, or the wearer won't be detected.
        caught = sum(1 for w in blink_windows if self._onsets(np.asarray(w), level) >= 2)
        if caught < max(1, len(peaks) - 1):
            raise BlinkError(f"double blinks were found in only {caught} of {len(peaks)} tries")
        with self._lock:
            self.level = level
            self._last_blink = self._prev_blink = -1e9
        self.log(f"Blink switch calibrated: resting {baseline:.3g}, blinks {peak:.3g}, "
                 f"level {level:.3g}, double blinks found in {caught} of {len(peaks)} tries")
        return level

    def _onsets(self, x: np.ndarray, level: float) -> int:
        refractory, last, n = int(REFRACTORY_S * self.rate), -10 ** 9, 0
        for i in np.flatnonzero(x > level):
            if i - last >= refractory:
                n, last = n + 1, int(i)
        return n
