"""Simulated stimulus markers and a synthetic P300 for the Generator source.

``Generator`` produces noise and sine waves with no evoked response, so an
average of target and non-target epochs would look the same. To show what
the evidence view is for, ``SyntheticP300`` adds a positive deflection
about 300 ms after every target marker. It is labelled Simulated
everywhere it appears and never runs on live EEG.
"""

from __future__ import annotations

import random
import threading

import numpy as np
import gpype as gp

KEYS = gp.Constants.Keys
PORT_IN = gp.Constants.Defaults.PORT_IN
PORT_OUT = gp.Constants.Defaults.PORT_OUT

#: Marker code for a flash of the attended tile.
TARGET_CODE = 1
#: Marker code for a flash of any other tile.
NONTARGET_CODE = 2


def p300_waveform(sampling_rate: float, amplitude: float = 10.0,
                  latency: float = 0.3, width: float = 0.08,
                  length: float = 0.8) -> np.ndarray:
    """A Gaussian bump peaking ``latency`` seconds after the marker.

    Args:
        sampling_rate: Samples per second.
        amplitude: Peak height in microvolts.
        latency: Peak time after the marker, in seconds.
        width: Standard deviation of the bump, in seconds.
        length: Total length of the waveform, in seconds.

    Returns:
        One-dimensional array, ``length * sampling_rate`` samples long.
    """
    t = np.arange(int(round(length * sampling_rate))) / sampling_rate
    return amplitude * np.exp(-0.5 * ((t - latency) / width) ** 2)


class SyntheticP300(gp.IONode):
    """Adds a simulated P300 to the EEG after each target marker.

    Input: the EEG channels with the marker channel appended last (a
    ``Router`` of the source and a ``Marker``). Output: the EEG channels
    only, with the deflection added. Non-target markers add nothing.
    """

    class Configuration(gp.IONode.Configuration):
        class Keys(gp.IONode.Configuration.Keys):
            AMPLITUDE = "amplitude"
            TARGET = "target"

    def __init__(self, amplitude: float = 10.0, target: int = TARGET_CODE,
                 **kwargs):
        super().__init__(amplitude=amplitude, target=target, **kwargs)
        self._wave = None
        self._pending = None

    def setup(self, data, port_context_in):
        port_context_out = super().setup(data, port_context_in)
        context = port_context_in[PORT_IN]
        out = port_context_out[PORT_OUT]
        count = context[KEYS.CHANNEL_COUNT]
        out[KEYS.CHANNEL_COUNT] = count - 1
        for key in (KEYS.CHANNEL_ROLES, KEYS.CHANNEL_LABELS):
            value = context.get(key)
            if value:
                out[key] = list(value)[:-1]
        amplitude = self.config[self.Configuration.Keys.AMPLITUDE]
        self._wave = p300_waveform(context[KEYS.SAMPLING_RATE], amplitude)
        self._pending = np.zeros(0, dtype=gp.Constants.DATA_TYPE)
        return port_context_out

    def step(self, data):
        frame = np.asarray(data[PORT_IN])
        eeg = np.array(frame[:, :-1], dtype=gp.Constants.DATA_TYPE)
        add = inject(frame[:, -1], self._wave, self._pending,
                     self.config[self.Configuration.Keys.TARGET])
        self._pending = add[len(frame):]
        eeg += add[:len(frame), None]
        return {PORT_OUT: eeg}


def inject(markers: np.ndarray, wave: np.ndarray, pending: np.ndarray,
           target: int) -> np.ndarray:
    """The deflection for one frame, plus what spills into later frames.

    Args:
        markers: The marker channel of this frame, one value per sample.
        wave: The waveform started at each target marker.
        pending: Spill-over from earlier frames.
        target: The marker code that starts a waveform.

    Returns:
        At least ``len(markers)`` samples; the tail belongs to later frames.
    """
    starts = np.flatnonzero(np.isclose(markers, target))
    length = max([len(markers), len(pending)]
                 + [int(s) + len(wave) for s in starts])
    out = np.zeros(length, dtype=float)
    out[:len(pending)] += pending
    for s in starts:
        out[s:s + len(wave)] += wave
    return out


class Flasher:
    """Emits target and non-target codes on a ``Marker``, like flashing tiles.

    Stands in for the P300 chooser's tiles (#46) so the average fills up
    without a person. One flash in ``1 / target_ratio`` is a target.
    """

    def __init__(self, marker: "gp.Marker", interval: float = 0.35,
                 target_ratio: float = 0.33, seed: int | None = None):
        self._marker = marker
        self._interval = interval
        self._ratio = target_ratio
        self._random = random.Random(seed)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def next_code(self) -> int:
        return TARGET_CODE if self._random.random() < self._ratio \
            else NONTARGET_CODE

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="evidence-flasher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        self._stop.wait(1.0)  # let the pipeline settle
        while not self._stop.is_set():
            self._marker.emit(self.next_code())
            jitter = self._random.uniform(-0.05, 0.05)
            self._stop.wait(self._interval + jitter)
