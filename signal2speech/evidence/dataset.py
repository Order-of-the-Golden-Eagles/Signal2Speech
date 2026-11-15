"""Real recorded P300 data from g.tec's hackathon P300 Speller dataset (#142).

Our headset was lost in transit, so this plays a recording that **g.tec** made (five healthy
people using a row-column P300 speller with wet electrodes, 8 channels at 250 Hz) through our own
filters and averaging. Its montage (the dataset's montage.png) is Fz, Cz, P3, Pz, P4, PO7, PO8,
Oz: the same channel count and rate as the Unicorn Hybrid Black, but not the same electrode
positions or order (the Unicorn has C3 and C4 where this has P3 and P4). It is always labelled **Recorded (g.tec dataset)**: it is
not our wearer, not our flashing tiles, and not live.

Get the data (never commit it): https://www.gtec.at/downloads_QyTs23/Hackathon/p300-speller.rar
listed at https://github.com/unicorn-bi/Hackathon. Each ``S*.mat`` holds ``fs`` (Hz), ``y``
(samples x channels, microvolts) and ``trig`` (+1 on a target flash, -1 on a non-target flash).

    python -m signal2speech.evidence --source dataset path/to/p300-speller/S1.mat
    python -m signal2speech.evidence.dataset path/to/p300-speller        # offline report
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from .synthetic import NONTARGET_CODE, TARGET_CODE

LABEL_DETAIL = "g.tec P300 Speller dataset"
#: Electrode order in the dataset's montage.png. Not the Unicorn's order.
CHANNELS = ("Fz", "Cz", "P3", "Pz", "P4", "PO7", "PO8", "Oz")


@dataclass(frozen=True)
class Session:
    """One subject's recording, ready to play."""
    name: str
    fs: float
    eeg: np.ndarray          # (samples, channels), microvolts
    codes: np.ndarray        # (samples,), TARGET_CODE / NONTARGET_CODE at flash onsets, else 0

    @property
    def targets(self) -> int:
        return int((self.codes == TARGET_CODE).sum())

    @property
    def nontargets(self) -> int:
        return int((self.codes == NONTARGET_CODE).sum())

    @property
    def seconds(self) -> float:
        return len(self.eeg) / self.fs


def resolve(path: Path | str) -> Path:
    """A ``.mat`` file, or a folder (its first ``S*.mat``)."""
    p = Path(path)
    if p.is_dir():
        files = sorted(p.glob("S*.mat"))
        if not files:
            raise FileNotFoundError(f"No S*.mat files in {p}")
        return files[0]
    if not p.is_file():
        raise FileNotFoundError(f"Dataset file not found: {p}")
    return p


def load(path: Path | str) -> Session:
    """Load one g.tec P300 Speller ``.mat`` file."""
    from scipy.io import loadmat

    f = resolve(path)
    m = loadmat(f)
    missing = [k for k in ("fs", "y", "trig") if k not in m]
    if missing:
        raise ValueError(f"{f.name} is not a g.tec P300 Speller file (missing {missing})")
    fs = float(np.ravel(m["fs"])[0])
    eeg = np.asarray(m["y"], dtype=float)
    trig = np.ravel(m["trig"]).astype(float)
    if eeg.ndim != 2 or len(trig) != len(eeg):
        raise ValueError(f"{f.name}: y must be samples x channels with one trig value per sample")
    # Keep only the first sample of each flash, in case a file holds the trigger for longer.
    onset = np.concatenate([[True], trig[1:] != trig[:-1]]) & (trig != 0)
    codes = np.zeros(len(trig), dtype=float)
    codes[onset & (trig > 0)] = TARGET_CODE
    codes[onset & (trig < 0)] = NONTARGET_CODE
    return Session(name=f.stem, fs=fs, eeg=eeg, codes=codes)


# ── offline numbers for the docs and the judges ─────────────────────────────
@dataclass(frozen=True)
class Report:
    name: str
    targets: int
    nontargets: int
    peak_uv: float           # largest |target - nontarget| difference, 200-600 ms
    peak_ms: float
    peak_channel: int        # 1-based
    lda_balanced_accuracy: float

    @property
    def peak_name(self) -> str:
        i = self.peak_channel - 1
        return CHANNELS[i] if 0 <= i < len(CHANNELS) else f"channel {self.peak_channel}"

    def line(self) -> str:
        return (f"{self.name}: {self.targets} target and {self.nontargets} non-target flashes; "
                f"target minus non-target peaks at {self.peak_uv:+.1f} uV, {self.peak_ms:.0f} ms, "
                f"{self.peak_name}; single-flash LDA balanced accuracy "
                f"{self.lda_balanced_accuracy:.2f} (chance 0.50)")


def epochs(session: Session, pre_s: float = 0.1, post_s: float = 0.7):
    """Band-pass 1-30 Hz, cut baseline-corrected epochs. Returns (epochs, labels, times_ms)."""
    from scipy.signal import butter, sosfiltfilt

    fs = session.fs
    x = sosfiltfilt(butter(4, [1, 30], btype="band", fs=fs, output="sos"), session.eeg, axis=0)
    pre, post = int(round(pre_s * fs)), int(round(post_s * fs))
    on = np.flatnonzero(session.codes != 0)
    on = on[(on - pre >= 0) & (on + post <= len(x))]
    labels = (session.codes[on] == TARGET_CODE).astype(int)
    ep = np.stack([x[i - pre:i + post] - x[i - pre:i].mean(axis=0) for i in on])
    times = np.arange(-pre, post) / fs * 1000.0
    return ep, labels, times


def analyse(session: Session, folds: int = 5) -> Report:
    """The same method as the P300 chooser (#46): binned epoch means into a shrinkage LDA,
    cross-validated. Offline, on someone else's recording: not a live result."""
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import StratifiedKFold, cross_val_score

    ep, labels, times = epochs(session)
    diff = ep[labels == 1].mean(axis=0) - ep[labels == 0].mean(axis=0)
    window = (times >= 200) & (times <= 600)
    t_idx, ch = np.unravel_index(np.abs(diff[window]).argmax(), diff[window].shape)
    post = ep[:, times >= 0, :]
    bins = max(1, int(round(0.1 * session.fs)))                 # 100 ms bins
    usable = post.shape[1] // bins * bins
    feats = post[:, :usable].reshape(len(post), usable // bins, bins, post.shape[2]).mean(axis=2)
    feats = feats.reshape(len(post), -1)
    cv = StratifiedKFold(folds, shuffle=True, random_state=0)
    acc = cross_val_score(LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"),
                          feats, labels, cv=cv, scoring="balanced_accuracy").mean()
    return Report(session.name, int(labels.sum()), int((labels == 0).sum()),
                  float(diff[window][t_idx, ch]), float(times[window][t_idx]), int(ch) + 1,
                  float(acc))


# ── g.Pype nodes: play the recording through the real-time pipeline ─────────
def make_player_nodes(session: Session):
    """Two nodes that replace a clock source's samples with the recording.

    Both take the Generator, used only as a 250 Hz clock, so they stay in lockstep. ``eeg``
    outputs the recorded EEG. ``flashes`` outputs one channel holding the recorded flash code on
    the sample each flash happened (0 otherwise); ``gp.Trigger`` fires on that edge, so epochs
    line up to the sample. Both loop when the recording ends.
    """
    import gpype as gp

    port_in = gp.Constants.Defaults.PORT_IN
    port_out = gp.Constants.Defaults.PORT_OUT
    keys = gp.Constants.Keys
    dtype = gp.Constants.DATA_TYPE

    class _Player(gp.IONode):
        def __init__(self, column_source, **kwargs):
            super().__init__(**kwargs)
            self._data = column_source          # (samples, channels)
            self._pos = 0

        def setup(self, data, port_context_in):
            out = super().setup(data, port_context_in)
            ctx = port_context_in[port_in]
            rate = ctx[keys.SAMPLING_RATE]
            if abs(rate - session.fs) > 1e-6:
                raise ValueError(f"The recording is {session.fs:g} Hz but the pipeline runs at {rate:g} Hz")
            width = self._data.shape[1]
            count = ctx[keys.CHANNEL_COUNT]
            if width > count:
                raise ValueError(f"The recording has {width} channels but the pipeline has {count}")
            if width != count:                  # the one-channel flash stream
                out[port_out][keys.CHANNEL_COUNT] = width
                for key in (keys.CHANNEL_ROLES, keys.CHANNEL_LABELS):
                    value = ctx.get(key)
                    if value:
                        out[port_out][key] = list(value)[:width]
            self._pos = 0
            return out

        def step(self, data):
            n = len(np.asarray(data[port_in]))
            idx = (self._pos + np.arange(n)) % len(self._data)
            self._pos = (self._pos + n) % len(self._data)
            return {port_out: np.array(self._data[idx], dtype=dtype)}

    eeg = _Player(session.eeg, name="recorded_eeg")
    flashes = _Player(session.codes[:, None], name="recorded_flashes")
    return eeg, flashes


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Offline report for one file or every ``S*.mat`` in a folder."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m signal2speech.evidence.dataset <S1.mat | folder>")
        return 2
    p = Path(args[0])
    files: List[Path] = sorted(p.glob("S*.mat")) if p.is_dir() else [p]
    if not files:
        print(f"No S*.mat files in {p}")
        return 1
    print(f"Recorded ({LABEL_DETAIL}). Offline analysis of g.tec's recording, not our wearer.")
    for f in files:
        print("  " + analyse(load(f)).line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
