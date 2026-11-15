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
from signal2speech.eeg.devices import GTEC_P300_DATASET  # noqa: E402

CHANNELS = GTEC_P300_DATASET.channel_names


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


# ── #151: how many flashes does the chooser need? ────────────────────────────
CURVE_FLASHES = (1, 2, 3, 5, 10)


def curve(session: Session, flashes: Sequence[int] = CURVE_FLASHES, folds: int = 5,
          draws: int = 400, seed: int = 0) -> dict:
    """How often our chooser picks the attended item out of two, by flashes averaged.

    Cross-validated in blocks of time: the recording is cut into five consecutive stretches, the
    LDA is fitted on four and tested on the fifth, five times over. Blocks matter. Flashes come
    faster than an epoch lasts, so neighbouring epochs share samples, and a random split would
    test on EEG the classifier had nearly seen (it scored 88-98 % on one flash that way, which is
    too good). In each test, ``n`` held-out responses to the attended stimulus and ``n`` to an
    unattended one are scored, and the pick is right when the attended ones score higher on
    average. That is the two-tile decision ``signal2speech.eeg.p300`` makes, with its features
    (40 ms bin means over the epoch). Offline, on someone else's recording: not a live result.
    """
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import KFold

    from signal2speech.eeg import p300

    ep, labels, _ = epochs(session, pre_s=p300.TIME_PRE, post_s=p300.TIME_POST)
    feats = np.stack([p300.bin_means(e).reshape(-1) for e in ep])
    rng = np.random.default_rng(seed)
    right = {n: [] for n in flashes}
    for train, test in KFold(folds, shuffle=False).split(feats):          # consecutive blocks
        lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(feats[train], labels[train])
        scores = lda.decision_function(feats[test])
        t, nt = scores[labels[test] == 1], scores[labels[test] == 0]
        for n in flashes:
            if len(t) < n or len(nt) < n:
                continue
            for _ in range(draws):
                a = rng.choice(t, n, replace=False).mean()
                b = rng.choice(nt, n, replace=False).mean()
                right[n].append(a > b)
    return {n: float(np.mean(v)) for n, v in right.items() if v}


def curve_svg(curves: dict, flashes: Sequence[int] = CURVE_FLASHES) -> str:
    """The curves as a small SVG line chart (no plotting library needed)."""
    w, h, left, top, bottom = 640, 360, 64, 28, 52
    pw, ph = w - left - 24, h - top - bottom
    xs = {n: left + pw * i / (len(flashes) - 1) for i, n in enumerate(flashes)}
    y = lambda acc: top + ph * (1.0 - (acc - 0.5) / 0.5)
    colours = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="13">',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>']
    for acc in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        out.append(f'<line x1="{left}" x2="{left + pw}" y1="{y(acc):.1f}" y2="{y(acc):.1f}" stroke="#dddddd"/>')
        out.append(f'<text x="{left - 8}" y="{y(acc) + 4:.1f}" text-anchor="end" fill="#333">{acc:.0%}</text>')
    for n in flashes:
        out.append(f'<text x="{xs[n]:.1f}" y="{top + ph + 20}" text-anchor="middle" fill="#333">{n}</text>')
    out.append(f'<text x="{left + pw / 2}" y="{h - 10}" text-anchor="middle" fill="#333">flashes averaged per tile</text>')
    out.append(f'<text x="16" y="{top + ph / 2}" text-anchor="middle" fill="#333" transform="rotate(-90 16 {top + ph / 2})">right tile picked</text>')
    out.append(f'<text x="{left}" y="18" fill="#333" font-weight="bold">Recorded (g.tec P300 Speller dataset): two-tile accuracy, tested on separate blocks of time</text>')
    for i, (name, c) in enumerate(curves.items()):
        pts = " ".join(f"{xs[n]:.1f},{y(c[n]):.1f}" for n in flashes if n in c)
        col = colours[i % len(colours)]
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        for n in flashes:
            if n in c:
                out.append(f'<circle cx="{xs[n]:.1f}" cy="{y(c[n]):.1f}" r="3.5" fill="{col}"/>')
        out.append(f'<rect x="{left + pw - 70}" y="{top + ph - 22 - 18 * (len(curves) - 1 - i)}" width="12" height="12" fill="{col}"/>')
        out.append(f'<text x="{left + pw - 52}" y="{top + ph - 11 - 18 * (len(curves) - 1 - i)}" fill="#333">{name}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Offline report for one file or every ``S*.mat`` in a folder. ``--curve`` adds accuracy by
    number of flashes (#151); ``--plot FILE.svg`` also saves that as a chart."""
    args = list(sys.argv[1:] if argv is None else argv)
    want_curve = "--curve" in args
    plot = None
    if "--plot" in args:
        i = args.index("--plot")
        if i + 1 >= len(args):
            print("--plot needs a file name, e.g. --plot flashes.svg")
            return 2
        plot = Path(args[i + 1])
        del args[i:i + 2]
        want_curve = True
    args = [a for a in args if a != "--curve"]
    if len(args) != 1:
        print("usage: python -m signal2speech.evidence.dataset <S1.mat | folder> [--curve] [--plot FILE.svg]")
        return 2
    p = Path(args[0])
    files: List[Path] = sorted(p.glob("S*.mat")) if p.is_dir() else [p]
    if not files:
        print(f"No S*.mat files in {p}")
        return 1
    print(f"Recorded ({LABEL_DETAIL}). Offline analysis of g.tec's recording, not our wearer.")
    sessions = [load(f) for f in files]
    for s in sessions:
        print("  " + analyse(s).line())
    if want_curve:
        print("\nRight tile picked out of two, by flashes averaged per tile (cross-validated on 5 separate blocks of time; chance 50 %):")
        print("  subject | " + " | ".join(f"{n:>3} flash{'es' if n > 1 else '  '}" for n in CURVE_FLASHES))
        curves = {}
        for s in sessions:
            curves[s.name] = curve(s)
            print(f"  {s.name:7} | " + " | ".join(f"{curves[s.name].get(n, float('nan')):>10.0%}" for n in CURVE_FLASHES))
        if len(curves) > 1:
            mean = {n: float(np.mean([c[n] for c in curves.values() if n in c])) for n in CURVE_FLASHES}
            print("  mean    | " + " | ".join(f"{mean[n]:>10.0%}" for n in CURVE_FLASHES))
        if plot is not None:
            plot.write_text(curve_svg(curves), encoding="utf-8")
            print(f"saved {plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
