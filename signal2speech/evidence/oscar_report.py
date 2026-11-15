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
DELAY_SEARCH_S = 60.0    # how much of the recording the delay search compares
ARTIFACT_SHARE = 0.05    # the top 5% of 1 s windows by peak-to-peak count as artifact stretches
FZ = gtec.CHANNELS.index("Fz")      # the frontal channel, where blinks are largest


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
    """Play the recording once through the evidence view's own graph (the recording plus its
    OSCAR branch, #142/#164) and return (before, after OSCAR) as (samples, channels)."""
    from signal2speech.eeg.alpha_confirm import _Tap

    from .pipeline import SourceKind, build_evidence_graph

    g = build_evidence_graph(SourceKind.GENERATOR, dataset=session, oscar=True)
    if g.oscar_node is None:
        g.pipeline.close()
        raise RuntimeError("this g.Pype has no standalone OSCAR node "
                           "(gpype.backend.core._private.oscar.Oscar), so OSCAR can't run on "
                           "replayed data here")
    got = {"before": [], "after": []}
    rows = {"before": 0, "after": 0}

    def keep(which):
        def on_rows(block):
            got[which].append(np.array(block, dtype=np.float64, copy=True))
            rows[which] += len(block)
        return on_rows

    before, after = _Tap(name="before"), _Tap(name="after")
    before.on_rows, after.on_rows = keep("before"), keep("after")
    g.pipeline.connect(g.raw, before)
    g.pipeline.connect(g.oscar_node, after)
    need = len(session.eeg) + int(extra_s * session.fs)
    g.pipeline.start()
    try:
        deadline = time.monotonic() + session.seconds * 1.5 + 30
        while min(rows.values()) < need and time.monotonic() < deadline:
            time.sleep(0.2)
    finally:
        g.pipeline.stop()
        g.pipeline.close()
    for which in ("before", "after"):
        if rows[which] < need:
            raise RuntimeError(f"{session.name}: only {rows[which]} of {need} samples came out "
                               f"{which} OSCAR in time; the replay fell behind real time")
    return np.vstack(got["before"]), np.vstack(got["after"])


# ── Offline measures (pure, unit-tested) ─────────────────────
def find_delay(before: np.ndarray, after: np.ndarray, start: int, max_lag: int = MAX_LAG,
               span: int = int(DELAY_SEARCH_S * 250)) -> int:
    """The lag (samples) where ``after`` best matches ``before``: OSCAR's processing delay.
    Raises if the best match sits at the edge of the search, where it can't be trusted."""
    n = min(len(before), len(after), start + span + max_lag) - max_lag
    seg = slice(start, n)
    errs = [np.mean(np.abs(before[seg] - after[start + k:n + k])) for k in range(max_lag)]
    lag = int(np.argmin(errs))
    # A real delay gives one lag that fits far better than the rest. If none stands out, or the
    # best is at the edge, the delay is past the search limit (or the streams don't match).
    if lag >= max_lag - 1 or errs[lag] > 0.8 * float(np.median(errs)):
        raise ValueError(f"no clear OSCAR delay within the {max_lag}-sample search limit; "
                         "raise MAX_LAG or check the streams")
    return lag


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
    delay = find_delay(before, after, start, span=int(DELAY_SEARCH_S * fs))
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


def run_one(path: str):
    """One subject. Returns a Result, or the error text, so one bad file can't lose the rest."""
    try:
        session = gtec.load(path)
        before, after = replay(session)
        return measure(session, before, after)
    except Exception as err:                       # report it and keep the other subjects
        return f"{Path(path).name}: {type(err).__name__}: {err}"


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
    paths = [str(f) for f in files]
    if args.jobs <= 1 or len(paths) == 1:
        outcomes = [run_one(p) for p in paths]
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            outcomes = list(pool.map(run_one, paths))
    results = [r for r in outcomes if isinstance(r, Result)]
    for r in outcomes:
        if isinstance(r, Result):
            print(json.dumps(asdict(r)) if args.json else r.line(), flush=True)
        else:
            print(f"FAILED {r}", file=sys.stderr, flush=True)
    if results:
        print()
        print(table(results))
    return 0 if len(results) == len(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
