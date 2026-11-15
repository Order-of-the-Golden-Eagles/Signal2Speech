"""P300 chooser (#46): flash markers -> Epochs -> LDA -> class 1/2 -> InputAdapter.

Pipeline (realtime)::

    HybridBlack(enable_oscar=True) | Generator [+ SyntheticP300]
      -> Bandpass 1-30 Hz
      -> Trigger(code of tile 1) -> P300Scorer (LDA) -+
      -> Trigger(code of tile 2) -> P300Scorer (LDA) -+-> SequenceAggregator -> class 1/2
      -> Trigger(calibration target / non-target) -> Collector (calibration only)
    Marker <- P300Chooser.on_flash(target_id), called by the UI on the frame a tile lights

Training is offline, from a calibration block: target and non-target epochs are cut, binned to
40 ms means, and fitted with a shrinkage LDA through ``gp.Sklearn.fit_offline``. Online, each
flash epoch gets an LDA score (positive = looks like a target). After a full flash sequence the
tile with the highest mean score wins, and the class index (1 or 2) is mapped by
``EegClassMap.default()`` and handed to ``InputAdapter.select_captured`` on the Qt main thread.

g.Pype's own ``gp.Sklearn`` emits only a class index per epoch. A P300 speller needs a score to
aggregate over repetitions, so ``P300Scorer`` subclasses it and emits ``decision_function``.

Verified on synthetic data only. See docs/eeg-hardware/README.md, "P300 chooser".
"""
from __future__ import annotations

import argparse
import os
import random
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

import gpype as gp
from gpype.common.constants import Constants

from signal2speech.core import EegClassMap, InputAdapter, TargetIds

KEYS = Constants.Keys
PORT_IN = Constants.Defaults.PORT_IN
PORT_OUT = Constants.Defaults.PORT_OUT

RATE = 250.0
EEG_CHANNELS = 8
#: Epoch window around each flash, in seconds. g.Pype's Trigger needs time_pre > 0.
TIME_PRE = 0.1
TIME_POST = 0.7
#: Features are per-channel means over bins of this many samples (40 ms at 250 Hz).
BIN_SAMPLES = 10

#: Marker code sent on the frame a tile lights, during online selection.
FLASH_CODES: Dict[str, int] = {TargetIds.TARGET_1: 1, TargetIds.TARGET_2: 2}
#: Class index each tile decodes to. EegClassMap.default() maps it back to the tile.
CLASS_FOR_TILE: Dict[str, int] = {TargetIds.TARGET_1: 1, TargetIds.TARGET_2: 2}
#: Calibration markers: the attended tile flashed (target) or the other one did.
CAL_TARGET = 101
CAL_NONTARGET = 100
TARGET_LABEL = str(CAL_TARGET)
NONTARGET_LABEL = str(CAL_NONTARGET)

#: Flash timing defaults: stimulus onset asynchrony and how long a tile stays lit.
SOA_S = 0.25
FLASH_ON_S = 0.10
FLASHES_PER_TILE = 5


# ── features and scoring ─────────────────────────────────────────────────────

def bin_means(block: np.ndarray, bin_samples: int = BIN_SAMPLES) -> np.ndarray:
    """Average consecutive samples. (time, channel[, trial]) -> (time // bin, channel[, trial])."""
    n = (block.shape[0] // bin_samples) * bin_samples
    shaped = block[:n].reshape((n // bin_samples, bin_samples) + block.shape[1:])
    return shaped.mean(axis=1)


class P300Scorer(gp.Sklearn):
    """gp.Sklearn with 40 ms bin features that emits an LDA score instead of a class index.

    Positive score = the epoch looks like a response to the attended tile. One instance per tile
    sits behind that tile's Trigger. ``on_score(tile_id, score)`` is called on g.Pype's worker
    thread for every epoch.
    """

    def __init__(self, estimator=None, tile_id: Optional[str] = None,
                 bin_samples: int = BIN_SAMPLES, **kwargs):
        if estimator is None:
            from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
            estimator = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
        # gp.Sklearn's default ports are Sync, which g.Pype refuses to connect to a Trigger's
        # Async epochs. Declare Async ports, as gp.EpochAverage does.
        kwargs.setdefault(KEYS.INPUT_PORTS, [
            gp.IPort.Configuration(name=PORT_IN, timing=Constants.Timing.ASYNC)])
        kwargs.setdefault(KEYS.OUTPUT_PORTS, [
            gp.OPort.Configuration(name=PORT_OUT, timing=Constants.Timing.ASYNC)])
        super().__init__(estimator, **kwargs)
        self.tile_id = tile_id
        self.bin_samples = bin_samples
        self.on_score: Optional[Callable[[Optional[str], float], None]] = None

    def fit(self, block: np.ndarray, context: dict) -> dict:
        return super().fit(bin_means(np.asarray(block), self.bin_samples), context)

    def scores(self, block: np.ndarray) -> np.ndarray:
        """Target-ness score per trial of a (time, channel, trial) block."""
        feats = bin_means(np.asarray(block, dtype=np.float64), self.bin_samples)
        x = feats.transpose(2, 0, 1).reshape(feats.shape[2], -1)
        return self._signed(self._built().decision_function(x))

    def _signed(self, raw: np.ndarray) -> np.ndarray:
        classes = [str(c) for c in self._built().classes_.tolist()]
        # Binary decision_function is positive for classes_[1].
        return raw if classes[1] == TARGET_LABEL else -raw

    def apply_block(self, block: np.ndarray) -> np.ndarray:
        return self.scores(block).reshape(-1, 1).astype(Constants.DATA_TYPE)

    def step(self, data: dict) -> dict:
        frame = np.asarray(data[PORT_IN], dtype=np.float64)
        score = float(self.scores(frame[:, :, None])[0])
        callback = self.on_score
        if callback is not None:
            callback(self.tile_id, score)
        return {PORT_OUT: np.array([[score]], dtype=Constants.DATA_TYPE)}


@dataclass
class P300Model:
    """Calibration epochs, labelled target / non-target. Fitting them is the trained model.

    A realtime ``Pipeline.start()`` refuses a Fittable node with no fitted state, and
    ``load_state()`` alone doesn't count as one (only a fit or a deserialized document does).
    So instead of copying one state into several nodes, each scorer is fitted on these epochs
    with the public ``fit_offline``; a shrinkage-LDA fit takes milliseconds.
    Keep it in memory; never commit calibration data (``models/`` is gitignored).
    """
    block: np.ndarray   # (time, channel, trial)
    trials: list        # [[index, TARGET_LABEL | NONTARGET_LABEL], ...]

    @property
    def n_target(self) -> int:
        return sum(1 for _, label in self.trials if label == TARGET_LABEL)

    def fit(self, scorer: "P300Scorer") -> "P300Scorer":
        scorer.fit_offline(self.block, {KEYS.TRIALS: self.trials, KEYS.SAMPLING_RATE: RATE})
        return scorer

    def scorer(self, tile_id: Optional[str] = None, **kwargs) -> "P300Scorer":
        return self.fit(P300Scorer(tile_id=tile_id, **kwargs))


def train_scorer(target_block: np.ndarray, nontarget_block: np.ndarray) -> P300Model:
    """Shrinkage-LDA training set from (time, channel, trial) target and non-target blocks."""
    block = np.concatenate([target_block, nontarget_block], axis=2)
    trials = ([[i, TARGET_LABEL] for i in range(target_block.shape[2])]
              + [[i, NONTARGET_LABEL] for i in range(nontarget_block.shape[2])])
    model = P300Model(block, trials)
    model.scorer(name="p300_train")   # fail early if the data can't be fitted
    return model


# ── per-sequence aggregation ─────────────────────────────────────────────────

class SequenceAggregator:
    """Collects flash scores for one sequence and decides once. Thread-safe.

    ``start()`` at sequence start. ``add()`` is called from g.Pype worker threads. When every
    tile has ``flashes_per_tile`` scores, ``on_decision(class_index, mean_scores)`` fires once.
    ``finish()`` forces a decision from whatever arrived (for dropped epochs or a timeout).
    """

    def __init__(self, tiles: Sequence[str] = tuple(FLASH_CODES),
                 flashes_per_tile: int = FLASHES_PER_TILE,
                 on_decision: Optional[Callable[[int, Dict[str, float]], None]] = None):
        self.tiles = tuple(tiles)
        self.flashes_per_tile = flashes_per_tile
        self.on_decision = on_decision
        self._lock = threading.Lock()
        self._scores: Dict[str, List[float]] = {}
        self._open = False

    @property
    def is_open(self) -> bool:
        """True while a sequence is collecting scores (between start() and finish())."""
        with self._lock:
            return self._open

    def start(self) -> None:
        with self._lock:
            self._scores = {t: [] for t in self.tiles}
            self._open = True

    def add(self, tile_id: Optional[str], score: float) -> None:
        with self._lock:
            if not self._open or tile_id not in self._scores:
                return
            self._scores[tile_id].append(float(score))
            done = all(len(v) >= self.flashes_per_tile for v in self._scores.values())
        if done:
            self.finish()

    def finish(self) -> Optional[int]:
        with self._lock:
            if not self._open:
                return None
            self._open = False
            means = {t: float(np.mean(v)) if v else float("-inf") for t, v in self._scores.items()}
        if all(np.isneginf(m) for m in means.values()):
            return None
        winner = max(means, key=means.get)
        cls = CLASS_FOR_TILE[winner]
        if self.on_decision is not None:
            self.on_decision(cls, means)
        return cls


def decide(scores_by_tile: Dict[str, Sequence[float]]) -> int:
    """Class index of the tile with the highest mean score (pure helper for offline use)."""
    winner = max(scores_by_tile, key=lambda t: float(np.mean(scores_by_tile[t])))
    return CLASS_FOR_TILE[winner]


# ── synthetic P300 ───────────────────────────────────────────────────────────

#: Per-channel P300 weight, strongest over the parietal midline (Unicorn: Fz C3 Cz C4 Pz PO7 Oz PO8).
P300_WEIGHTS = np.array([0.5, 0.6, 0.9, 0.6, 1.0, 0.8, 0.7, 0.8])


def p300_template(rate: float = RATE, amplitude: float = 5.0, latency: float = 0.30,
                  width: float = 0.06, duration: float = 0.6) -> np.ndarray:
    """(samples, 8) positive deflection peaking ``latency`` s after the flash, in microvolts."""
    t = np.arange(int(round(duration * rate))) / rate
    wave = amplitude * np.exp(-0.5 * ((t - latency) / width) ** 2)
    return wave[:, None] * P300_WEIGHTS[None, :]


def visual_template(rate: float = RATE, amplitude: float = 1.5, duration: float = 0.6) -> np.ndarray:
    """Small N1 that every flash evokes, target or not, so the classifier can't key on 'a flash'."""
    t = np.arange(int(round(duration * rate))) / rate
    wave = -amplitude * np.exp(-0.5 * ((t - 0.17) / 0.03) ** 2)
    return np.repeat(wave[:, None], EEG_CHANNELS, axis=1)


class SyntheticP300(gp.IONode):
    """Adds a P300 after every marker whose code is in ``target_codes`` (synthetic runs only).

    Sits between a ``Generator`` and the Bandpass. Ports mirror ``gp.Trigger``: EEG on ``in``,
    the Marker on ``trigger``. ``target_codes`` can be changed between sequences from any thread.
    """

    PORT_TRIGGER = "trigger"

    def __init__(self, amplitude: float = 5.0, **kwargs):
        input_ports = kwargs.pop(KEYS.INPUT_PORTS, [
            gp.IPort.Configuration(),
            gp.IPort.Configuration(name=self.PORT_TRIGGER, timing=Constants.Timing.INHERITED),
        ])
        super().__init__(input_ports=input_ports, **kwargs)
        self.amplitude = amplitude
        self.target_codes: set = set()
        self._active: List[int] = []   # per running response: next template row
        self._pending = 0              # markers seen with no data row yet
        self._template = None
        self._visual = None

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        rate = port_context_in[PORT_IN][KEYS.SAMPLING_RATE]
        self._template = p300_template(rate, self.amplitude)
        self._visual = visual_template(rate)
        self._active, self._pending, self._visual_active = [], 0, []
        return out

    def _note(self, value) -> None:
        if value is None or value == 0:
            return
        self._visual_active.append(0)
        if int(value) in self.target_codes:
            self._pending += 1

    def step(self, data):
        frame = data.get(PORT_IN)
        trig = data.get(self.PORT_TRIGGER)
        rows = frame.shape[0] if frame is not None and getattr(frame, "ndim", 0) == 2 else 0
        tarr = None if trig is None else np.asarray(trig).reshape(-1)
        if rows == 0:
            if tarr is not None and tarr.size:
                self._note(tarr[0])
            return None
        out = np.array(frame, dtype=Constants.DATA_TYPE, copy=True)
        for row in range(rows):
            if tarr is not None:
                if tarr.size == rows:
                    self._note(tarr[row])
                elif row == 0 and tarr.size:
                    self._note(tarr[0])
            while self._pending:
                self._active.append(0)
                self._pending -= 1
            for lst, tmpl in ((self._active, self._template), (self._visual_active, self._visual)):
                for i in reversed(range(len(lst))):
                    out[row, :tmpl.shape[1]] += tmpl[lst[i]]
                    lst[i] += 1
                    if lst[i] >= tmpl.shape[0]:
                        lst.pop(i)
        return {PORT_OUT: out}


#: Flash spacing when recorded responses answer the flashes. At the usual 0.25 s, three or four
#: recorded responses overlap and their background EEG adds up. Measured on g.tec's dataset: the
#: right tile was picked 95 % of the time at 0.25 s and 100 % at 0.5 s (subject S4).
RECORDED_SOA_S = 0.5


class RecordedResponses:
    """Real single-flash brain responses cut from a recording, handed out one per flash (#104).

    ``target`` are responses to the stimulus the recorded person was attending, ``nontarget`` to
    the others. Both are (trials, samples, channels) in microvolts, starting at the flash. Each is
    used once, in a shuffled order; ``reused`` counts how many had to be played a second time.
    """

    def __init__(self, target: np.ndarray, nontarget: np.ndarray, name: str = "recording",
                 seed: int = 0):
        target, nontarget = np.asarray(target, float), np.asarray(nontarget, float)
        if target.ndim != 3 or nontarget.ndim != 3 or not len(target) or not len(nontarget):
            raise ValueError("need (trials, samples, channels) target and non-target responses")
        if target.shape[2] != EEG_CHANNELS or nontarget.shape[2] != EEG_CHANNELS:
            raise ValueError(f"responses need {EEG_CHANNELS} channels")
        self.name = name
        #: A short form for the status strip, which has little room.
        self.short_name = name.replace("P300 Speller dataset, ", "dataset ")
        self.pools = {True: target, False: nontarget}
        self._rng = random.Random(seed)
        self._order = {True: [], False: []}
        self.served = {True: 0, False: 0}
        self.reused = 0
        self._lock = threading.Lock()

    @classmethod
    def from_gtec(cls, path, seed: int = 0) -> "RecordedResponses":
        """From one subject file of g.tec's P300 Speller dataset (``S4.mat``), band-passed
        1-30 Hz and baseline-corrected the way the evidence report does it."""
        from signal2speech.evidence import dataset

        session = dataset.load(path)
        if abs(session.fs - RATE) > 0.5:
            raise ValueError(f"{session.name}: {session.fs:g} Hz, the pipeline runs at {RATE:g} Hz")
        ep, labels, times = dataset.epochs(session, pre_s=TIME_PRE, post_s=TIME_POST)
        post = ep[:, times >= 0, :]
        return cls(post[labels == 1], post[labels == 0], name=f"g.tec P300 Speller dataset, {session.name}",
                   seed=seed)

    def next(self, target: bool) -> np.ndarray:
        """The next unused response of that kind."""
        with self._lock:
            if not self._order[target]:
                if self.served[target]:
                    self.reused += len(self.pools[target])
                self._order[target] = list(range(len(self.pools[target])))
                self._rng.shuffle(self._order[target])
            self.served[target] += 1
            return self.pools[target][self._order[target].pop()]


class RecordedP300(SyntheticP300):
    """Answers every flash marker with one real recorded response (#104).

    The output is the recorded EEG and nothing else: the Generator feeding this node only sets
    the clock. A marker in ``target_codes`` gets a recorded response to an attended stimulus;
    any other marker gets a recorded response to an unattended one. Which tile counts as
    attended is scripted, because the recorded person was looking at g.tec's speller, not at
    our tiles. What the classifier does with the responses is real.
    """

    def __init__(self, responses: RecordedResponses, **kwargs):
        super().__init__(**kwargs)
        self.responses = responses
        self._queued: List[bool] = []      # flashes seen, waiting for a data row: target or not
        self._playing: List[list] = []     # [response, next row]

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        self._queued, self._playing = [], []
        return out

    def _note(self, value) -> None:
        if value is None or value == 0:
            return
        self._queued.append(int(value) in self.target_codes)

    def step(self, data):
        frame = data.get(PORT_IN)
        trig = data.get(self.PORT_TRIGGER)
        rows = frame.shape[0] if frame is not None and getattr(frame, "ndim", 0) == 2 else 0
        tarr = None if trig is None else np.asarray(trig).reshape(-1)
        if rows == 0:
            if tarr is not None and tarr.size:
                self._note(tarr[0])
            return None
        out = np.zeros(frame.shape, dtype=Constants.DATA_TYPE)
        for row in range(rows):
            if tarr is not None:
                if tarr.size == rows:
                    self._note(tarr[row])
                elif row == 0 and tarr.size:
                    self._note(tarr[0])
            while self._queued:
                self._playing.append([self.responses.next(self._queued.pop(0)), 0])
            for item in reversed(self._playing):
                response, i = item
                out[row, :response.shape[1]] += response[i]
                item[1] += 1
                if item[1] >= response.shape[0]:
                    self._playing.remove(item)
        return {PORT_OUT: out}


def make_sequence(flashes_per_tile: int = FLASHES_PER_TILE, rng: Optional[random.Random] = None,
                  tiles: Sequence[str] = tuple(FLASH_CODES)) -> List[str]:
    """Shuffled flash order: each tile ``flashes_per_tile`` times, never 3 in a row."""
    rng = rng or random.Random()
    while True:
        order = [t for t in tiles for _ in range(flashes_per_tile)]
        rng.shuffle(order)
        if not any(order[i] == order[i + 1] == order[i + 2] for i in range(len(order) - 2)):
            return order


def write_synthetic_recording(path: str, attended: Sequence[str], calibration: bool,
                              flashes_per_tile: int = FLASHES_PER_TILE, soa: float = SOA_S,
                              amplitude: float = 5.0, noise: float = 10.0, alpha: float = 5.0,
                              seed: int = 0) -> List[List[str]]:
    """Write an HDF5 recording (8 EEG channels + trigger) of flash sequences with a P300.

    One sequence per entry in ``attended``. Calibration recordings mark target flashes
    ``CAL_TARGET`` and the rest ``CAL_NONTARGET``; test recordings mark the tile's
    ``FLASH_CODES`` code. Noise is white (std ``noise`` uV) plus a 10 Hz alpha of ``alpha`` uV,
    matching ``gp.Generator``. Returns the flash order of every sequence.
    """
    import h5py

    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    step = int(round(soa * RATE))
    gap = int(round(1.0 * RATE))
    orders = [make_sequence(flashes_per_tile, rng) for _ in attended]
    total = gap + sum(len(o) * step + gap for o in orders) + gap
    t = np.arange(total) / RATE
    signal = nrng.normal(0.0, noise, (total, EEG_CHANNELS))
    signal += alpha * np.sin(2 * np.pi * 10.0 * t + nrng.uniform(0, 2 * np.pi))[:, None]
    trigger = np.zeros(total)
    p3, vis = p300_template(RATE, amplitude), visual_template(RATE)
    onset = gap
    for target, order in zip(attended, orders):
        for tile in order:
            is_target = tile == target
            trigger[onset] = ((CAL_TARGET if is_target else CAL_NONTARGET) if calibration
                              else FLASH_CODES[tile])
            end = min(total, onset + p3.shape[0])
            signal[onset:end] += vis[:end - onset]
            if is_target:
                signal[onset:end] += p3[:end - onset]
            onset += step
        onset += gap
    data = np.column_stack([signal, trigger])
    with h5py.File(path, "w") as handle:
        ds = handle.create_dataset("data", data=data.T)
        ds.attrs["sampling_rate"] = RATE
        ds.attrs["channel_roles"] = np.array(["signal"] * EEG_CHANNELS + ["trigger"], dtype=object)
    return orders


def cut_epochs(path: str, condition) -> np.ndarray:
    """Batch g.Pype run: recording -> Bandpass 1-30 Hz -> Epochs(condition). (time, channel, trial)."""
    with gp.Pipeline() as p:
        reader = gp.HDF5Reader(file_name=path, mode="batch", has_time_row=False)
        signal_only = gp.ChannelSelector(roles=Constants.ChannelRoles.SIGNAL)
        bandpass = gp.Bandpass(f_lo=1, f_hi=30)
        epochs = gp.Epochs(condition=str(condition), tmin=-TIME_PRE, tmax=TIME_POST)
        collector = gp.Collector()
        p.connect(reader, signal_only)
        p.connect(signal_only, bandpass)
        p.connect(bandpass, epochs)
        p.connect(epochs, collector)
        return np.asarray(p.run().data)


def offline_accuracy(model: P300Model, path: str, attended: Sequence[str],
                     flashes_per_tile: int = FLASHES_PER_TILE) -> dict:
    """Score a test recording (``calibration=False``) and report accuracy.

    Returns single-epoch accuracy (sign of the score vs. the truth) and sequence accuracy for
    1..flashes_per_tile repetitions per tile, which is the 'trials needed' curve.
    """
    scorer = model.scorer(name="p300_offline")
    per_tile = {tile: scorer.scores(cut_epochs(path, code)) for tile, code in FLASH_CODES.items()}
    n_seq = len(attended)
    correct_epochs = total_epochs = 0
    by_reps = {}
    for reps in range(1, flashes_per_tile + 1):
        hits = 0
        for k, target in enumerate(attended):
            seq = {tile: s[k * flashes_per_tile:k * flashes_per_tile + reps]
                   for tile, s in per_tile.items()}
            hits += decide(seq) == CLASS_FOR_TILE[target]
        by_reps[reps] = hits / n_seq
    for k, target in enumerate(attended):
        for tile, s in per_tile.items():
            chunk = s[k * flashes_per_tile:(k + 1) * flashes_per_tile]
            correct_epochs += int(np.sum((chunk > 0) == (tile == target)))
            total_epochs += len(chunk)
    return {"epoch_accuracy": correct_epochs / total_epochs,
            "sequence_accuracy": by_reps[flashes_per_tile],
            "sequence_accuracy_by_reps": by_reps,
            "sequences": n_seq}


def train_on_synthetic(n_sequences: int = 20, seed: int = 1, workdir: Optional[str] = None,
                       **kwargs) -> P300Model:
    """Write a synthetic calibration recording, cut it with g.Pype, and fit the LDA."""
    workdir = workdir or tempfile.gettempdir()
    path = os.path.join(workdir, f"p300_synthetic_cal_{seed}.h5")
    attended = [list(FLASH_CODES)[i % 2] for i in range(n_sequences)]
    write_synthetic_recording(path, attended, calibration=True, seed=seed, **kwargs)
    return train_scorer(cut_epochs(path, CAL_TARGET), cut_epochs(path, CAL_NONTARGET))


# ── realtime pipeline ────────────────────────────────────────────────────────

@dataclass
class P300Nodes:
    """The realtime pipeline and the nodes other tracks attach to (#48 adds scopes here)."""
    pipeline: gp.Pipeline
    source: object                 # gp.Generator or gp.HybridBlack
    eeg: object                    # Bandpass output: 1-30 Hz EEG for scopes and Epoch averages
    marker: gp.Marker              # flash codes; connect to TimeSeriesScope markers if wanted
    synth: Optional[SyntheticP300]  # Generator runs only
    triggers: Dict[str, object]    # tile id -> Trigger
    scorers: Dict[str, P300Scorer]  # tile id -> fitted scorer
    cal_triggers: Dict[str, object]  # TARGET_LABEL / NONTARGET_LABEL -> Trigger
    cal_collectors: Dict[str, gp.Collector]
    sinks: List[object] = field(default_factory=list)


def build_pipeline(source: str = "generator", model: Optional[P300Model] = None,
                   enable_oscar: bool = True, synthetic_amplitude: float = 5.0,
                   calibration: bool = True,
                   recorded: Optional["RecordedResponses"] = None) -> P300Nodes:
    """Build (don't start) the realtime P300 pipeline.

    ``source`` is ``generator`` (simulated EEG with a synthetic P300) or ``hybridblack``
    (Unicorn Hybrid Black, pair it in the OS first). Pass a ``model`` to score online, or None
    to build a calibration-only graph you train from ``cal_collectors``. g.Pype refuses to start
    a realtime pipeline with an unfitted scorer, so to calibrate and select in one run pass a
    placeholder model and refit with ``P300Chooser.finish_calibration()``.
    """
    # Check the arguments before building anything: a half-built pipeline that is never started
    # or closed crashed the interpreter at exit on Linux (a segfault after every test had passed).
    if source not in ("generator", "recorded", "hybridblack"):
        raise ValueError(f"Unknown source {source!r}: use generator, recorded or hybridblack")
    if source == "recorded" and recorded is None:
        raise ValueError("source 'recorded' needs RecordedResponses")
    p = gp.Pipeline()
    marker = gp.Marker(name="p300_flash")
    synth = None
    if source == "generator":
        src = gp.Generator(sampling_rate=RATE, channel_count=EEG_CHANNELS, signal_frequency=10,
                           signal_amplitude=5, noise_amplitude=10, name="p300_source")
        synth = SyntheticP300(amplitude=synthetic_amplitude, name="p300_synth")
        p.connect(src, synth)
        p.connect(marker, synth[SyntheticP300.PORT_TRIGGER])
        upstream = synth
    elif source == "recorded":
        # The Generator only sets the clock: RecordedP300 replaces its output with recorded EEG.
        src = gp.Generator(sampling_rate=RATE, channel_count=EEG_CHANNELS, signal_frequency=10,
                           signal_amplitude=0, noise_amplitude=1, name="p300_source")
        synth = RecordedP300(recorded, name="p300_recorded")
        p.connect(src, synth)
        p.connect(marker, synth[SyntheticP300.PORT_TRIGGER])
        upstream = synth
    else:
        src = gp.HybridBlack(enable_oscar=enable_oscar, name="p300_source")
        upstream = src
    bandpass = gp.Bandpass(f_lo=1, f_hi=30, name="p300_bandpass")
    p.connect(upstream, bandpass)

    sinks: list = []
    triggers, scorers = {}, {}
    if model is not None:
        for tile, code in FLASH_CODES.items():
            trig = gp.Trigger(time_pre=TIME_PRE, time_post=TIME_POST, target=code,
                              name=f"p300_trigger_{code}")
            scorer = model.scorer(tile_id=tile, name=f"p300_scorer_{code}")
            sink = gp.Collector(name=f"p300_scores_{code}")
            p.connect(bandpass, trig)
            p.connect(marker, trig[gp.Trigger.PORT_TRIGGER])
            p.connect(trig, scorer)
            p.connect(scorer, sink)
            triggers[tile], scorers[tile] = trig, scorer
            sinks.append(sink)

    cal_triggers, cal_collectors = {}, {}
    if calibration:
        for label, code in ((TARGET_LABEL, CAL_TARGET), (NONTARGET_LABEL, CAL_NONTARGET)):
            trig = gp.Trigger(time_pre=TIME_PRE, time_post=TIME_POST, target=code,
                              name=f"p300_cal_trigger_{code}")
            coll = gp.Collector(name=f"p300_cal_epochs_{code}")
            p.connect(bandpass, trig)
            p.connect(marker, trig[gp.Trigger.PORT_TRIGGER])
            p.connect(trig, coll)
            cal_triggers[label], cal_collectors[label] = trig, coll
    return P300Nodes(p, src, bandpass, marker, synth, triggers, scorers, cal_triggers,
                     cal_collectors, sinks)


def p300_front_end(p: gp.Pipeline, eeg) -> object:
    """The chooser's filter chain, for ``build_evidence_graph(front_end=p300_front_end)`` (#48)."""
    bandpass = gp.Bandpass(f_lo=1, f_hi=30)
    p.connect(eeg, bandpass)
    return bandpass


def train_from_collectors(nodes: P300Nodes) -> P300Model:
    """Fit the LDA from the epochs a realtime calibration run collected."""
    target = nodes.cal_collectors[TARGET_LABEL].result
    nontarget = nodes.cal_collectors[NONTARGET_LABEL].result
    if target is None or nontarget is None:
        raise RuntimeError("Calibration collected no epochs; check the flash markers.")
    return train_scorer(np.asarray(target.data), np.asarray(nontarget.data))


# ── Qt bridge and chooser ────────────────────────────────────────────────────

_BRIDGE_CLASS = None


def _bridge_class():
    """Built lazily so importing this module (and the pytest) never needs PySide6."""
    global _BRIDGE_CLASS
    if _BRIDGE_CLASS is None:
        from PySide6.QtCore import QObject, Signal, Slot

        class QtDecisionBridge(QObject):
            """Carries a decision from a g.Pype worker thread to the Qt main thread.

            Create it on the main thread. ``decided`` is emitted from any thread; Qt queues it,
            and the slot calls ``InputAdapter.select_captured`` on the main thread.
            """
            decided = Signal(int)

            def __init__(self, adapter: Optional[InputAdapter], class_map: EegClassMap,
                         parent=None):
                super().__init__(parent)
                self.adapter = adapter
                self.class_map = class_map
                self.outcomes: list = []
                self.listeners: List[Callable[[int, Optional[str], object], None]] = []
                self.decided.connect(self._on_decided)

            @Slot(int)
            def _on_decided(self, cls: int) -> None:
                target = self.class_map.target_for(cls)
                outcome = self.adapter.select_captured(target) if self.adapter else None
                self.outcomes.append(outcome)
                for fn in self.listeners:
                    fn(cls, target, outcome)

        _BRIDGE_CLASS = QtDecisionBridge
    return _BRIDGE_CLASS


class P300Chooser:
    """Glue between the UI's flash schedule, the g.Pype pipeline, and the selection contract.

    UI (#24) usage, all on the Qt main thread::

        chooser = P300Chooser(nodes, adapter)       # adapter = InputAdapter(handler, LIVE_EEG)
        chooser.begin_sequence()                    # tiles start flashing for the open round
        chooser.on_flash("target-2")                # on the frame each tile lights
        # ... decision arrives via the Qt signal -> adapter.select_captured(target)

    Calibration: ``begin_calibration(attended)`` then ``on_flash`` as usual; markers become
    target / non-target codes. ``finish_calibration()`` fits the LDA and loads it into the
    scorers (they must exist: build the pipeline with a placeholder model).
    """

    def __init__(self, nodes: P300Nodes, adapter: Optional[InputAdapter] = None,
                 flashes_per_tile: int = FLASHES_PER_TILE,
                 class_map: Optional[EegClassMap] = None, use_qt: bool = True):
        self.nodes = nodes
        self.adapter = adapter
        self.class_map = class_map or EegClassMap.default()
        self.bridge = _bridge_class()(adapter, self.class_map) if use_qt else None
        self.decisions: list = []   # (class, mean scores), appended on the worker thread
        self.aggregator = SequenceAggregator(tuple(FLASH_CODES), flashes_per_tile,
                                             self._on_decision)
        self._calibrating_for: Optional[str] = None
        for scorer in nodes.scorers.values():
            scorer.on_score = self.aggregator.add

    def _on_decision(self, cls: int, means: Dict[str, float]) -> None:
        self.decisions.append((cls, means))
        if self.bridge is not None:
            self.bridge.decided.emit(cls)   # queued to the main thread
        elif self.adapter is not None:
            self.adapter.select_captured(self.class_map.target_for(cls))

    def begin_sequence(self, attended_for_synthetic: Optional[str] = None) -> None:
        """Call when the flash sequence for the open round starts. Stamps the round ID."""
        self._calibrating_for = None
        if self.adapter is not None:
            self.adapter.arm_capture()
        if self.nodes.synth is not None:
            self.nodes.synth.target_codes = (
                {FLASH_CODES[attended_for_synthetic]} if attended_for_synthetic else set())
        self.aggregator.start()

    def begin_calibration(self, attended: str) -> None:
        self._calibrating_for = attended
        if self.nodes.synth is not None:
            self.nodes.synth.target_codes = {CAL_TARGET}

    def on_flash(self, target_id: str, observed_at: Optional[float] = None) -> None:
        """Emit the flash Marker. Call on the frame the tile lights (pass the flip time if known)."""
        if self._calibrating_for is not None:
            code = CAL_TARGET if target_id == self._calibrating_for else CAL_NONTARGET
        else:
            code = FLASH_CODES[target_id]
        self.nodes.marker.emit(code, observed_at=observed_at)

    def end_sequence(self) -> Optional[int]:
        """Force a decision from the epochs that arrived (e.g. after a timeout)."""
        return self.aggregator.finish()

    def attach(self, scheduler) -> None:
        """Wire the UI's ``signal2speech.ui.flash.FlashScheduler`` (#24) to this chooser.

        Each repetition flashes every tile once, so flashes per tile = ``repetitions``. The
        last epoch completes ``TIME_POST`` s after the last flash; the aggregator normally
        decides then on its own, and a timeout forces a decision if an epoch went missing.
        """
        from PySide6.QtCore import QTimer
        self.aggregator.flashes_per_tile = scheduler.repetitions
        scheduler.on_sequence_started = self.begin_sequence
        scheduler.on_flash = self.on_flash
        scheduler.on_sequence_finished = lambda: QTimer.singleShot(
            int((TIME_POST + 0.5) * 1000), self.end_sequence)

    def finish_calibration(self) -> P300Model:
        """Fit the LDA on the collected calibration epochs and refit every online scorer."""
        self._calibrating_for = None
        model = train_from_collectors(self.nodes)
        for scorer in self.nodes.scorers.values():
            model.fit(scorer)
        return model


# ── CLI ──────────────────────────────────────────────────────────────────────

class _TestTiles:
    """Bare two-tile window for the CLI only, so a wearer has something to attend.

    The real tiles, preview, and judge strip are #24. The marker is emitted right after the
    tile is restyled, not at the display flip, so expect frame-level jitter (see the README).
    """

    def __init__(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
        self.window = QWidget()
        self.window.setWindowTitle("Signal2Speech P300 test tiles (#46)")
        outer = QVBoxLayout(self.window)
        # Big instruction line, so the wearer never has to read the terminal.
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setMinimumHeight(110)
        self.banner.setStyleSheet("background:#101820; color:#ffd060; font-size:26px; "
                                  "font-weight:bold; padding:12px; qproperty-alignment:AlignCenter;")
        outer.addWidget(self.banner)
        layout = QHBoxLayout()
        outer.addLayout(layout)
        self.labels = {}
        for tile in FLASH_CODES:
            lab = QLabel(tile.replace("target-", "Tile "))
            lab.setMinimumSize(300, 300)
            lab.setStyleSheet(self._style(False))
            layout.addWidget(lab)
            self.labels[tile] = lab
        self.cue = None
        self.window.show()

    @staticmethod
    def _style(lit: bool, cued: bool = False) -> str:
        border = "6px solid #e0a000" if cued else "6px solid #333"
        bg = "#ffffff" if lit else "#202020"
        fg = "#000000" if lit else "#cccccc"
        return f"background:{bg}; color:{fg}; border:{border}; font-size:28px; qproperty-alignment:AlignCenter;"

    def set_message(self, text: str) -> None:
        """Show an instruction above the tiles."""
        self.banner.setText(text)
        self.banner.repaint()

    def set_cue(self, tile: Optional[str]) -> None:
        self.cue = tile
        for t, lab in self.labels.items():
            lab.setStyleSheet(self._style(False, t == tile))

    def light(self, tile: str, lit: bool) -> None:
        lab = self.labels[tile]
        lab.setStyleSheet(self._style(lit, tile == self.cue))
        lab.repaint()   # paint now so the marker that follows is as close as Qt allows


def _run_cli(args) -> int:
    from PySide6.QtCore import QTimer

    from signal2speech.core import Choice, InputSources, SelectionHandler

    use_window = args.window or args.source == "hybridblack"
    if use_window:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        tiles_ui = _TestTiles()
    else:
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance() or QCoreApplication([])
        tiles_ui = None
    tiles = list(FLASH_CODES)
    rng = random.Random(args.seed)
    label = "simulated" if args.source == "generator" else "live-eeg"
    print(f"[p300] source={args.source} ({label}); flashes/tile={args.flashes}, SOA={args.soa}s")

    # Calibration needs scorers in the graph to load into later, so seed them with a quick
    # synthetic fit; it is replaced by the real calibration before any online sequence.
    placeholder = train_on_synthetic(n_sequences=4, seed=99)
    nodes = build_pipeline(args.source, model=placeholder, enable_oscar=not args.no_oscar)

    class Sink:
        def execute(self, action):
            print(f"[p300] confirmed: {action}")

    handler = SelectionHandler(Sink())
    source = InputSources.SIMULATED if args.source == "generator" else InputSources.LIVE_EEG
    adapter = InputAdapter(handler, source)
    chooser = P300Chooser(nodes, adapter, flashes_per_tile=args.flashes)
    choices = [Choice(TargetIds.TARGET_1, "show_satellite", "Satellite"),
               Choice(TargetIds.TARGET_2, "compare_air_quality", "Compare counties")]

    plan: List[tuple] = []  # (kind, attended)
    plan += [("cal", tiles[i % 2]) for i in range(args.calibration)]
    plan += [("sel", rng.choice(tiles)) for _ in range(args.sequences)]
    results = {"hits": 0, "n": 0}
    pending_truth: List[str] = []

    def on_result(cls, target, outcome):
        truth = pending_truth.pop(0) if pending_truth else None
        results["n"] += 1
        results["hits"] += target == truth
        print(f"[p300] decision class={cls} -> {target} (attended {truth}) -> {outcome}")
        handler.cancel("next sequence")
    chooser.bridge.listeners.append(on_result)

    def run_sequence(i: int) -> None:
        if i >= len(plan):
            QTimer.singleShot(int((TIME_POST + 0.5) * 1000), finish)
            return
        kind, attended = plan[i]
        if kind == "cal":
            if i == 0:
                print(f"[p300] calibration: {args.calibration} sequences")
            chooser.begin_calibration(attended)
        else:
            if plan[i - 1][0] == "cal":
                model = chooser.finish_calibration()
                print(f"[p300] trained LDA on {model.n_target} target and "
                      f"{len(model.trials) - model.n_target} non-target calibration epochs")
            handler.begin_choice_round(choices)
            pending_truth.append(attended)
            chooser.begin_sequence(attended_for_synthetic=attended)
        if tiles_ui is not None:
            print(f"[p300] attend {attended}")
            tiles_ui.set_cue(attended if kind == "cal" or args.source == "hybridblack" else None)
        order = make_sequence(args.flashes, rng)
        lead = 1.0 if tiles_ui is not None else 0.0   # time to look at the cued tile

        def flash(tile: str) -> None:
            if tiles_ui is not None:
                tiles_ui.light(tile, True)
                QTimer.singleShot(int(FLASH_ON_S * 1000), lambda: tiles_ui.light(tile, False))
            chooser.on_flash(tile)

        for k, tile in enumerate(order):
            QTimer.singleShot(int((lead + k * args.soa) * 1000), lambda t=tile: flash(t))
        tail = lead + len(order) * args.soa + TIME_POST + 0.4
        QTimer.singleShot(int(tail * 1000), lambda: _after(i, kind))

    def _after(i: int, kind: str) -> None:
        if kind == "sel" and chooser.aggregator._open:
            chooser.end_sequence()   # dropped epochs: decide from what arrived
        run_sequence(i + 1)

    def finish() -> None:
        if results["n"]:
            print(f"[p300] online accuracy ({label}): {results['hits']}/{results['n']}")
        app.quit()

    nodes.pipeline.start()
    QTimer.singleShot(1000, lambda: run_sequence(0))   # let Trigger buffers fill
    app.exec()
    nodes.pipeline.stop()
    nodes.pipeline.close()
    return 0


def _offline_cli(args) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        model = train_on_synthetic(n_sequences=args.calibration, seed=args.seed, workdir=tmp,
                                   flashes_per_tile=args.flashes)
        rng = random.Random(args.seed + 1)
        attended = [rng.choice(list(FLASH_CODES)) for _ in range(args.sequences)]
        path = os.path.join(tmp, "test.h5")
        write_synthetic_recording(path, attended, calibration=False, seed=args.seed + 1,
                                  flashes_per_tile=args.flashes)
        report = offline_accuracy(model, path, attended, args.flashes)
    print(f"[p300] offline synthetic: epoch accuracy {report['epoch_accuracy']:.2f}, "
          f"sequence accuracy {report['sequence_accuracy']:.2f} over {report['sequences']}")
    for reps, acc in report["sequence_accuracy_by_reps"].items():
        print(f"  {reps} flash(es)/tile: {acc:.2f}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.eeg.p300",
                                 description="P300 chooser: calibrate, then select tiles.")
    ap.add_argument("--source", choices=["generator", "hybridblack", "offline"],
                    default="generator",
                    help="generator: realtime simulated EEG; hybridblack: Unicorn headset; "
                         "offline: synthetic recordings through batch g.Pype, no clock")
    ap.add_argument("--calibration", type=int, default=10, help="calibration sequences")
    ap.add_argument("--sequences", type=int, default=6, help="online selection sequences")
    ap.add_argument("--flashes", type=int, default=FLASHES_PER_TILE, help="flashes per tile")
    ap.add_argument("--soa", type=float, default=SOA_S, help="seconds between flashes")
    ap.add_argument("--no-oscar", action="store_true", help="HybridBlack without OSCAR")
    ap.add_argument("--window", action="store_true",
                    help="show the bare test tiles (always on for hybridblack)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    if args.source == "offline":
        return _offline_cli(args)
    return _run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
