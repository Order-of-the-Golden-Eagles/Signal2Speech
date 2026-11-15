"""What OSCAR changes on g.tec's recorded P300 data (#164).

    python -m signal2speech.evidence.oscar_report path/to/p300-speller          # all subjects
    python -m signal2speech.evidence.oscar_report path/to/p300-speller/S1.mat   # one

g.Pype's OSCAR (online artifact removal) normally runs inside the Unicorn source. Our evidence
view also runs it as a branch, so the same EEG can be seen before and after. Here each subject of
g.tec's P300 Speller dataset (#142) plays through a real g.Pype pipeline, in real time:

    Generator (clock) -> recorded EEG -> tap "before"
                                      -> Oscar -> tap "after"

Then, offline, on the two streams it measures:

1. **OSCAR's delay**, the lag that best lines "after" up with "before".
2. **Artifact amplitude:** peak-to-peak in 1 s windows, 1-30 Hz, at Fz (the frontal channel, where
   blinks are largest). It compares the 5% of windows with the largest swings before OSCAR (the
   blink and movement stretches) and the rest, before vs after.
3. **Single-flash classification:** the same shrinkage LDA as the P300 chooser
   (``dataset.analyse``), cross-validated, on the EEG before vs after OSCAR (delay removed).

Everything is labelled Recorded (g.tec dataset): someone else's recording, not our wearer and not
live. A subject takes as long as its recording (about 4 minutes). ``--jobs`` runs several at once.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from . import dataset as gtec

WARMUP_S = 10.0          # OSCAR adapts at the start; leave it out of every number
MAX_LAG = 250            # samples (1 s): the delay search range
ARTIFACT_SHARE = 0.05    # the top 5% of 1 s windows by peak-to-peak count as artifact stretches
FZ = 0


@dataclass
class Result:
    subject: str
    seconds: float
    delay_ms: float
    fz_artifact_uv_before: float      # median peak-to-peak, artifact windows
    fz_artifact_uv_after: float
    fz_clean_uv_before: float         # median peak-to-peak, the other windows
    fz_clean_uv_after: float
    artifact_windows: int
    accuracy_before: float            # single-flash LDA balanced accuracy, chance 0.50
    accuracy_after: float
    accuracy_after_unshifted: float   # OSCAR's output epoched on the flashes as-is (no delay fix)
    peak_uv_before: float             # target minus non-target, 200-600 ms
    peak_uv_after: float

    def line(self) -> str:
        change = self.fz_artifact_uv_after / self.fz_artifact_uv_before - 1
        return (f"{self.subject}: OSCAR delay {self.delay_ms:.0f} ms; Fz artifact stretches "
                f"{self.fz_artifact_uv_before:.0f} -> {self.fz_artifact_uv_after:.0f} uV "
                f"({change:+.0%}), clean stretches {self.fz_clean_uv_before:.0f} -> "
                f"{self.fz_clean_uv_after:.0f} uV; single-flash accuracy "
                f"{self.accuracy_before:.2f} -> {self.accuracy_after:.2f} "
                f"({self.accuracy_after_unshifted:.2f} without the delay fix)")


# ── Replay through g.Pype ────────────────────────────────────
def replay(session: gtec.Session, extra_s: float = 3.0):
    """Play the recording once through g.Pype; return (before, after) as (samples, channels)."""
    import gpype as gp

    from signal2speech.eeg.alpha_confirm import _Tap

    from .pipeline import oscar_node

    osc = oscar_node()
    if osc is None:
        raise RuntimeError("this g.Pype has no standalone OSCAR node "
                           "(gpype.backend.core._private.oscar.Oscar)")
    got = {"before": [], "after": []}
    rows = {"before": 0, "after": 0}

    def keep(which):
        def on_rows(block):
            got[which].append(np.array(block, dtype=np.float64, copy=True))
            rows[which] += len(block)
        return on_rows

    p = gp.Pipeline()
    clock = gp.Generator(name="eeg", sampling_rate=session.fs, channel_count=session.eeg.shape[1],
                         noise_amplitude=0.0, signal_amplitude=0.0)
    eeg, _flashes = gtec.make_player_nodes(session)
    before, after = _Tap(name="before"), _Tap(name="after")
    before.on_rows, after.on_rows = keep("before"), keep("after")
    p.connect(clock, eeg)
    p.connect(eeg, before)
    p.connect(eeg, osc)
    p.connect(osc, after)
    need = len(session.eeg) + int(extra_s * session.fs)
    p.start()
    try:
        deadline = time.monotonic() + session.seconds * 1.5 + 30
        while min(rows.values()) < need and time.monotonic() < deadline:
            time.sleep(0.2)
    finally:
        p.stop()
        p.close()
    b, a = np.vstack(got["before"]), np.vstack(got["after"])
    if len(b) < len(session.eeg):
        raise RuntimeError(f"only {len(b)} of {len(session.eeg)} samples arrived")
    return b, a


# ── Offline measures (pure, unit-tested) ─────────────────────
def find_delay(before: np.ndarray, after: np.ndarray, start: int, max_lag: int = MAX_LAG) -> int:
    """The lag (samples) where ``after`` best matches ``before``: OSCAR's processing delay."""
    n = min(len(before), len(after)) - max_lag
    seg = slice(start, n)
    errs = [np.mean(np.abs(before[seg] - after[start + k:n + k])) for k in range(max_lag)]
    return int(np.argmin(errs))


def bandpass(x: np.ndarray, fs: float) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    return sosfiltfilt(butter(4, [1, 30], btype="band", fs=fs, output="sos"), x, axis=0)


def window_ptp(x: np.ndarray, fs: float) -> np.ndarray:
    w = int(round(fs))
    usable = len(x) // w * w
    return np.ptp(x[:usable].reshape(-1, w), axis=1)


def measure(session: gtec.Session, before: np.ndarray, after: np.ndarray) -> Result:
    fs = session.fs
    start = int(WARMUP_S * fs)
    delay = find_delay(before, after, start)
    n = min(len(session.eeg), len(after) - delay)
    raw = before[start:n]
    clean = after[start + delay:n + delay]
    codes = session.codes[start:n]

    ptp_b = window_ptp(bandpass(raw, fs)[:, FZ], fs)
    ptp_a = window_ptp(bandpass(clean, fs)[:, FZ], fs)
    cut = np.quantile(ptp_b, 1 - ARTIFACT_SHARE)
    art = ptp_b >= cut

    rep_b = gtec.analyse(gtec.Session(session.name, fs, raw, codes))
    rep_a = gtec.analyse(gtec.Session(session.name, fs, clean, codes))
    # What a pipeline gets if it epochs OSCAR's output on the flashes without the delay fix.
    rep_u = gtec.analyse(gtec.Session(session.name, fs, after[start:n], codes))
    return Result(session.name, round(len(raw) / fs, 1), delay / fs * 1000,
                  float(np.median(ptp_b[art])), float(np.median(ptp_a[art])),
                  float(np.median(ptp_b[~art])), float(np.median(ptp_a[~art])), int(art.sum()),
                  rep_b.lda_balanced_accuracy, rep_a.lda_balanced_accuracy,
                  rep_u.lda_balanced_accuracy, rep_b.peak_uv, rep_a.peak_uv)


def run_one(path: str) -> Result:
    session = gtec.load(path)
    before, after = replay(session)
    return measure(session, before, after)


def table(results: List[Result]) -> str:
    rows = ["| Subject | OSCAR delay | Fz, blink/artifact stretches | Fz, the rest | "
            "Single-flash accuracy | Same, without the delay fix | P300 peak (target − non-target) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in results:
        rows.append(f"| {r.subject} | {r.delay_ms:.0f} ms | {r.fz_artifact_uv_before:.0f} → "
                    f"{r.fz_artifact_uv_after:.0f} µV | {r.fz_clean_uv_before:.0f} → "
                    f"{r.fz_clean_uv_after:.0f} µV | {r.accuracy_before:.2f} → "
                    f"{r.accuracy_after:.2f} | {r.accuracy_after_unshifted:.2f} | "
                    f"{r.peak_uv_before:+.1f} → {r.peak_uv_after:+.1f} µV |")
    return "\n".join(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.evidence.oscar_report",
                                 description="What OSCAR changes on g.tec's recorded P300 data (#164)")
    ap.add_argument("path", help="the p300-speller folder, or one S*.mat")
    ap.add_argument("--jobs", type=int, default=1, help="subjects to replay at once")
    ap.add_argument("--json", action="store_true", help="print one JSON line per subject")
    args = ap.parse_args(argv)
    root = Path(args.path)
    files = sorted(root.glob("S*.mat")) if root.is_dir() else [root]
    if not files:
        ap.error(f"no S*.mat in {root}")
    print(f"Recorded ({gtec.LABEL_DETAIL}): {len(files)} subject(s), replayed through g.Pype in "
          f"real time, about {len(files) * 4 / max(1, args.jobs):.0f} min", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(run_one, [str(f) for f in files]))
    for r in results:
        print(json.dumps(asdict(r)) if args.json else r.line(), flush=True)
    print()
    print(table(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
