"""Flash-to-marker timing check for the P300 chooser (#46).

The P300 is time-locked to the moment a tile actually lights on the monitor, but the chooser
emits its g.Pype Marker right after Qt repaints the tile. A constant gap between the two is
harmless (calibration learns it). Jitter in that gap smears every epoch and costs accuracy.

This tool flashes tiles with the same ``FlashScheduler`` the chooser uses and records, per
lit flash:

* ``marker_t``  - when ``on_flash`` runs (where the chooser emits the Marker)
* ``present_t`` - the best available "frame is on screen" time:
    - ``--tiles widget`` (default, same QLabel + repaint path as the real tiles): the next
      display vblank after the repaint flushed, from the Windows DWM composition clock
      (``DwmGetCompositionTimingInfo``). This is an estimate, not a measurement.
    - ``--tiles gl``: Qt's ``QOpenGLWidget.frameSwapped`` with vsync on (swap-interval 1).

It reports offset (present minus marker) mean / p95 / max, jitter, and the refresh rate, then
prints PASS or WARN. Run it on the judging laptop with the real display:

    python -m signal2speech.eeg.flash_timing --seconds 30
    python -m signal2speech.eeg.flash_timing --seconds 30 --tiles gl
    python -m signal2speech.eeg.flash_timing --seconds 30 --csv logs/flash_timing.csv
    python -m signal2speech.eeg.flash_timing --compare logs/flash_timing.csv onsets.txt --tile target_1

Software timestamps cannot see the panel's own scan-out or response time. For ground truth use
the photodiode / slow-motion camera procedure in docs/eeg-hardware/README.md ("Flash timing").
Under ``QT_QPA_PLATFORM=offscreen`` nothing reaches a screen, so the numbers are meaningless
and the verdict is always WARN.
"""
from __future__ import annotations

import argparse
import ctypes
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

#: WARN when the marker-to-present jitter (p95 - p5 spread of the offset) is above this.
JITTER_WARN_MS = 20.0
#: WARN when more than this fraction of flashes have no present timestamp.
MISSING_WARN_FRACTION = 0.10
#: WARN when fewer lit flashes than this were measured.
MIN_FLASHES = 20

SOURCE_DWM = "dwm-vblank-estimate"
SOURCE_GL = "qt-frameswapped"
SOURCE_NONE = "none"


# ── Clock ────────────────────────────────────────────────────────────────────

class Clock:
    """Seconds on one monotonic clock. On Windows this is QueryPerformanceCounter, the same
    clock the DWM composition timing uses, so vblank times compare directly."""

    def __init__(self):
        self._qpc = None
        self.freq = 0
        if sys.platform == "win32":
            try:
                k32 = ctypes.windll.kernel32
                f = ctypes.c_int64()
                if k32.QueryPerformanceFrequency(ctypes.byref(f)) and f.value > 0:
                    self.freq = f.value
                    self._qpc = k32.QueryPerformanceCounter
            except (AttributeError, OSError):
                self._qpc = None

    @property
    def is_qpc(self) -> bool:
        return self._qpc is not None

    def now(self) -> float:
        if self._qpc is not None:
            c = ctypes.c_int64()
            self._qpc(ctypes.byref(c))
            return c.value / self.freq
        return time.perf_counter()


# ── DWM composition timing (Windows) ─────────────────────────────────────────

class _Ratio(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("num", ctypes.c_uint32), ("den", ctypes.c_uint32)]


_U32, _U64 = ctypes.c_uint32, ctypes.c_uint64


class _DwmTimingInfo(ctypes.Structure):
    """DWM_TIMING_INFO from dwmapi.h (declared with pack(1))."""
    _pack_ = 1
    _fields_ = [
        ("cbSize", _U32), ("rateRefresh", _Ratio), ("qpcRefreshPeriod", _U64),
        ("rateCompose", _Ratio), ("qpcVBlank", _U64), ("cRefresh", _U64), ("cDXRefresh", _U32),
        ("qpcCompose", _U64), ("cFrame", _U64), ("cDXPresent", _U32), ("cRefreshFrame", _U64),
        ("cFrameSubmitted", _U64), ("cDXPresentSubmitted", _U32), ("cFrameConfirmed", _U64),
        ("cDXPresentConfirmed", _U32), ("cRefreshConfirmed", _U64), ("cDXRefreshConfirmed", _U32),
        ("cFramesLate", _U64), ("cFramesOutstanding", _U32), ("cFrameDisplayed", _U64),
        ("qpcFrameDisplayed", _U64), ("cRefreshFrameDisplayed", _U64), ("cFrameComplete", _U64),
        ("qpcFrameComplete", _U64), ("cFramePending", _U64), ("qpcFramePending", _U64),
        ("cFramesDisplayed", _U64), ("cFramesComplete", _U64), ("cFramesPending", _U64),
        ("cFramesAvailable", _U64), ("cFramesDropped", _U64), ("cFramesMissed", _U64),
        ("cRefreshNextDisplayed", _U64), ("cRefreshNextPresented", _U64),
        ("cRefreshesDisplayed", _U64), ("cRefreshesPresented", _U64), ("cRefreshStarted", _U64),
        ("cPixelsReceived", _U64), ("cPixelsDrawn", _U64), ("cBuffersEmpty", _U64),
    ]


def next_vblank(t: float, vblank: float, period: float) -> float:
    """First vblank at or after ``t``, given any known vblank time and the refresh period."""
    if period <= 0:
        raise ValueError("period must be positive")
    k = math.ceil((t - vblank) / period - 1e-9)
    return vblank + k * period


class DwmTiming:
    """Reads the desktop compositor's vblank clock. ``available`` is False off Windows."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self._fn = None
        if sys.platform == "win32" and clock.is_qpc:
            try:
                self._fn = ctypes.windll.dwmapi.DwmGetCompositionTimingInfo
            except (AttributeError, OSError):
                self._fn = None
        self.available = self._read() is not None

    def _read(self) -> Optional[_DwmTimingInfo]:
        if self._fn is None:
            return None
        info = _DwmTimingInfo()
        info.cbSize = ctypes.sizeof(_DwmTimingInfo)
        try:
            if self._fn(None, ctypes.byref(info)) != 0:   # S_OK
                return None
        except OSError:
            return None
        return info if info.qpcRefreshPeriod else None

    def refresh_hz(self) -> Optional[float]:
        info = self._read()
        if info is None:
            return None
        if info.rateRefresh.den:
            return info.rateRefresh.num / info.rateRefresh.den
        return self.clock.freq / info.qpcRefreshPeriod

    def frames_missed(self) -> Optional[int]:
        info = self._read()
        return None if info is None else int(info.cFramesMissed)

    def present_after(self, t: float) -> Optional[float]:
        """Estimated scan-out start of a frame flushed at ``t``: the next vblank after it."""
        info = self._read()
        if info is None:
            return None
        f = self.clock.freq
        return next_vblank(t, info.qpcVBlank / f, info.qpcRefreshPeriod / f)


# ── Records and statistics (pure, unit-tested) ───────────────────────────────

@dataclass
class FlashSample:
    tile: str
    start_t: float                       # set_lit(True) called
    flushed_t: Optional[float] = None    # repaint() returned
    marker_t: Optional[float] = None     # on_flash ran (the chooser emits its Marker here)
    present_t: Optional[float] = None    # best available on-screen time

    @property
    def offset_ms(self) -> Optional[float]:
        if self.marker_t is None or self.present_t is None:
            return None
        return (self.present_t - self.marker_t) * 1000.0


@dataclass
class TimingStats:
    n: int
    mean_ms: float
    p95_ms: float
    max_ms: float
    min_ms: float
    std_ms: float
    jitter_ms: float     # p95 - p5 spread of the offset


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (same as numpy's default), q in [0, 100]."""
    if not values:
        raise ValueError("no values")
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


def summarize(offsets_ms: Sequence[float]) -> Optional[TimingStats]:
    xs = [float(x) for x in offsets_ms if x is not None]
    if not xs:
        return None
    mean = sum(xs) / len(xs)
    std = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    return TimingStats(n=len(xs), mean_ms=mean, p95_ms=percentile(xs, 95), max_ms=max(xs),
                       min_ms=min(xs), std_ms=std,
                       jitter_ms=percentile(xs, 95) - percentile(xs, 5))


@dataclass
class TimingReport:
    source: str
    tiles: str
    platform: str
    refresh_hz: Optional[float]
    flashes: int
    stats: Optional[TimingStats]
    interval: Optional[TimingStats] = None     # flash-onset-to-onset, ms (scheduler timing)
    repaint: Optional[TimingStats] = None      # set_lit -> repaint returned, ms
    frames_missed: Optional[int] = None
    threshold_ms: float = JITTER_WARN_MS
    verdict: str = "WARN"
    reasons: List[str] = field(default_factory=list)
    samples: List[FlashSample] = field(default_factory=list, repr=False)


def evaluate(report: TimingReport) -> TimingReport:
    """Fill in ``verdict`` (PASS/WARN) and ``reasons``."""
    reasons: List[str] = []
    if report.platform in ("offscreen", "minimal"):
        reasons.append(f"Qt platform '{report.platform}' never presents to a screen; "
                       "timings are not meaningful")
    if report.source == SOURCE_NONE or report.stats is None:
        reasons.append("no present timestamp available; only the marker time was recorded")
    else:
        s = report.stats
        missing = report.flashes - s.n
        if report.flashes and missing / report.flashes > MISSING_WARN_FRACTION:
            reasons.append(f"{missing}/{report.flashes} flashes had no present timestamp")
        if s.n < MIN_FLASHES:
            reasons.append(f"only {s.n} flashes measured (want >= {MIN_FLASHES}); run longer")
        if s.jitter_ms > report.threshold_ms:
            reasons.append(f"jitter {s.jitter_ms:.1f} ms > {report.threshold_ms:.0f} ms")
    if report.frames_missed:
        reasons.append(f"compositor missed {report.frames_missed} frames during the run")
    report.reasons = reasons
    report.verdict = "WARN" if reasons else "PASS"
    return report


def _fmt(s: Optional[TimingStats]) -> str:
    if s is None:
        return "n/a"
    return (f"mean {s.mean_ms:7.2f}  p95 {s.p95_ms:7.2f}  max {s.max_ms:7.2f}  "
            f"min {s.min_ms:7.2f}  std {s.std_ms:6.2f}  (n={s.n})")


def format_report(r: TimingReport) -> str:
    hz = f"{r.refresh_hz:.2f} Hz ({1000.0 / r.refresh_hz:.2f} ms/frame)" if r.refresh_hz else "unknown"
    lines = [
        "Flash timing (#46) - marker vs on-screen frame",
        f"  tiles: {r.tiles}   Qt platform: {r.platform}   present source: {r.source}",
        f"  display refresh: {hz}",
        f"  lit flashes: {r.flashes}",
        f"  offset present-marker ms: {_fmt(r.stats)}",
    ]
    if r.stats is not None:
        lines.append(f"  jitter (p95-p5 spread):   {r.stats.jitter_ms:.2f} ms "
                     f"(threshold {r.threshold_ms:.0f} ms)")
    lines.append(f"  repaint duration ms:      {_fmt(r.repaint)}")
    lines.append(f"  flash onset interval ms:  {_fmt(r.interval)}")
    if r.frames_missed is not None:
        lines.append(f"  compositor frames missed: {r.frames_missed}")
    if r.source == SOURCE_DWM:
        lines.append("  note: dwm-vblank-estimate assumes the frame scans out at the next vblank "
                     "after the flush; check absolute latency with the photodiode procedure.")
    lines.append("  positive offset = frame reached the screen after the marker.")
    lines.append(f"{r.verdict}" + (": " + "; ".join(r.reasons) if r.reasons else
                                    f": jitter within {r.threshold_ms:.0f} ms"))
    return "\n".join(lines)


def build_report(samples: Sequence[FlashSample], *, source: str, tiles: str, platform: str,
                 refresh_hz: Optional[float], frames_missed: Optional[int] = None,
                 threshold_ms: float = JITTER_WARN_MS) -> TimingReport:
    offsets = [s.offset_ms for s in samples if s.offset_ms is not None]
    starts = [s.start_t for s in samples]
    intervals = [(b - a) * 1000.0 for a, b in zip(starts, starts[1:])]
    repaints = [(s.flushed_t - s.start_t) * 1000.0 for s in samples if s.flushed_t is not None]
    r = TimingReport(source=source,
                     tiles=tiles, platform=platform, refresh_hz=refresh_hz,
                     flashes=len(samples), stats=summarize(offsets),
                     interval=summarize(intervals), repaint=summarize(repaints),
                     frames_missed=frames_missed, threshold_ms=threshold_ms,
                     samples=list(samples))
    return evaluate(r)


# ── Ground-truth comparison (photodiode / slow-motion camera) ────────────────

CSV_HEADER = "index,tile,start_s,flushed_s,marker_s,present_s,offset_ms"


def write_csv(path: str, samples: Sequence[FlashSample]) -> None:
    """Per-flash timestamps (seconds on the tool's clock). Timing only, no EEG."""
    def f(x):
        return "" if x is None else f"{x:.6f}"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CSV_HEADER + "\n")
        for i, s in enumerate(samples):
            off = s.offset_ms
            fh.write(f"{i},{s.tile},{f(s.start_t)},{f(s.flushed_t)},{f(s.marker_t)},"
                     f"{f(s.present_t)},{'' if off is None else f'{off:.3f}'}\n")


def read_marker_times(path: str, tile: Optional[str] = None) -> List[float]:
    """Marker times from a ``--csv`` file, optionally only one tile's flashes."""
    out: List[float] = []
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
        col, tcol = header.index("marker_s"), header.index("tile")
        for row in fh:
            cells = row.strip().split(",")
            if len(cells) > col and cells[col] and (tile is None or cells[tcol] == tile):
                out.append(float(cells[col]))
    return out


def read_onsets(path: str) -> List[float]:
    """One light-onset time per line, in seconds on any clock (camera, sensor). '#' = comment."""
    out: List[float] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip().replace(",", " ")
            if line:
                out.append(float(line.split()[0]))
    return out


@dataclass
class GroundTruth:
    pairs: int
    count_mismatch: int              # onsets minus markers; should be 0
    diff: Optional[TimingStats]      # (onset interval - marker interval), ms
    jitter_std_ms: Optional[float]   # estimated per-flash std = std(diff) / sqrt(2)
    verdict: str = "WARN"
    reasons: List[str] = field(default_factory=list)


def compare_ground_truth(marker_times: Sequence[float], onset_times: Sequence[float],
                         threshold_ms: float = JITTER_WARN_MS) -> GroundTruth:
    """Jitter of real light onsets vs markers, with no shared clock needed.

    For consecutive flashes i, i+1: (onset[i+1] - onset[i]) - (marker[i+1] - marker[i]) is the
    change in marker-to-light delay. A constant delay cancels; jitter does not. Both lists must
    start at the same flash (trim the onset list to the first flash the tool made).
    """
    n = min(len(marker_times), len(onset_times))
    diffs = [((onset_times[i + 1] - onset_times[i]) - (marker_times[i + 1] - marker_times[i]))
             * 1000.0 for i in range(n - 1)]
    stats = summarize(diffs)
    gt = GroundTruth(pairs=n, count_mismatch=len(onset_times) - len(marker_times), diff=stats,
                     jitter_std_ms=None if stats is None else stats.std_ms / math.sqrt(2))
    if gt.count_mismatch:
        gt.reasons.append(f"{len(onset_times)} light onsets vs {len(marker_times)} markers; "
                          "check for missed or extra flashes before trusting this")
    if stats is None or n < MIN_FLASHES:
        gt.reasons.append(f"only {n} flashes paired (want >= {MIN_FLASHES})")
    elif stats.jitter_ms > threshold_ms:
        gt.reasons.append(f"interval error spread {stats.jitter_ms:.1f} ms > {threshold_ms:.0f} ms")
    gt.verdict = "WARN" if gt.reasons else "PASS"
    return gt


def format_ground_truth(gt: GroundTruth) -> str:
    lines = ["Flash timing ground truth (#46) - light onsets vs markers",
             f"  paired flashes: {gt.pairs}   onset-marker count difference: {gt.count_mismatch}",
             f"  interval error ms: {_fmt(gt.diff)}"]
    if gt.diff is not None:
        lines.append(f"  interval error spread (p95-p5): {gt.diff.jitter_ms:.2f} ms; "
                     f"estimated per-flash jitter std: {gt.jitter_std_ms:.2f} ms")
    lines.append(gt.verdict + (": " + "; ".join(gt.reasons) if gt.reasons else ""))
    return "\n".join(lines)


# ── Qt measurement ───────────────────────────────────────────────────────────

LIT, UNLIT = "#ffffff", "#202020"


def _make_widget_tile(name: str):
    from PySide6.QtWidgets import QLabel
    lab = QLabel(name)
    lab.setMinimumSize(300, 300)

    def set_lit(lit: bool) -> None:
        bg, fg = (LIT, "#000000") if lit else (UNLIT, "#cccccc")
        lab.setStyleSheet(f"background:{bg}; color:{fg}; border:6px solid #333; "
                          "font-size:28px; qproperty-alignment:AlignCenter;")
    set_lit(False)
    lab.set_lit = set_lit
    return lab


def _make_gl_tile(name: str):
    from PySide6.QtGui import QColor
    from PySide6.QtOpenGLWidgets import QOpenGLWidget

    class GLTile(QOpenGLWidget):
        def __init__(self):
            super().__init__()
            self.setMinimumSize(300, 300)
            self._color = QColor(UNLIT)

        def set_lit(self, lit: bool) -> None:
            self._color = QColor(LIT if lit else UNLIT)

        def paintGL(self) -> None:
            f = self.context().functions()
            c = self._color
            f.glClearColor(c.redF(), c.greenF(), c.blueF(), 1.0)
            f.glClear(0x00004000)   # GL_COLOR_BUFFER_BIT

    return GLTile()


class FlashTimingProbe:
    """Two flashing tiles driven by the chooser's ``FlashScheduler``; records FlashSamples."""

    def __init__(self, tiles: str = "widget", *, flash_ms: int = 100, isi_ms: int = 75,
                 clock: Optional[Clock] = None):
        from PySide6.QtWidgets import QHBoxLayout, QWidget

        from signal2speech.ui.flash import FlashScheduler

        if tiles not in ("widget", "gl"):
            raise ValueError("tiles must be 'widget' or 'gl'")
        self.tiles_kind = tiles
        self.clock = clock or Clock()
        self.dwm = DwmTiming(self.clock)
        self.samples: List[FlashSample] = []
        self._current: Optional[FlashSample] = None
        self._awaiting_swap: Optional[FlashSample] = None

        if tiles == "gl":
            from PySide6.QtGui import QSurfaceFormat
            fmt = QSurfaceFormat.defaultFormat()
            fmt.setSwapInterval(1)                 # vsync, so the swap tracks the flip
            QSurfaceFormat.setDefaultFormat(fmt)

        self.window = QWidget()
        self.window.setWindowTitle("Signal2Speech flash timing (#46)")
        self.window.setStyleSheet("background:#0b0d10;")
        layout = QHBoxLayout(self.window)
        make = _make_gl_tile if tiles == "gl" else _make_widget_tile
        self.tiles = {}
        for name in ("target_1", "target_2"):
            t = make(name)
            layout.addWidget(t)
            self.tiles[name] = t
            if tiles == "gl":
                t.frameSwapped.connect(self._on_swapped)

        self.scheduler = FlashScheduler(self._set_lit, self._on_flash,
                                        flash_ms=flash_ms, isi_ms=isi_ms, repetitions=10)

    @property
    def source(self) -> str:
        if self.tiles_kind == "gl":
            return SOURCE_GL
        return SOURCE_DWM if self.dwm.available else SOURCE_NONE

    def _set_lit(self, tile: str, lit: bool) -> None:
        w = self.tiles[tile]
        if lit:
            self._current = FlashSample(tile=tile, start_t=self.clock.now())
            self.samples.append(self._current)
            self._awaiting_swap = self._current
        else:
            self._awaiting_swap = None   # a swap of the unlit frame must not count
        w.set_lit(lit)
        w.repaint()            # same synchronous repaint as the real tiles
        if lit and self._current is not None:
            s = self._current
            s.flushed_t = self.clock.now()
            if self.tiles_kind == "widget" and self.dwm.available:
                s.present_t = self.dwm.present_after(s.flushed_t)

    def _on_flash(self, tile: str) -> None:
        if self._current is not None and self._current.tile == tile:
            self._current.marker_t = self.clock.now()

    def _on_swapped(self) -> None:
        s = self._awaiting_swap
        if s is not None and s.present_t is None:
            s.present_t = self.clock.now()

    def run(self, seconds: float) -> List[FlashSample]:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        deadline = self.clock.now() + seconds

        def next_sequence():
            if self.clock.now() >= deadline:
                QTimer.singleShot(200, loop.quit)   # let the last swap arrive
            else:
                self.scheduler.start(list(self.tiles))

        self.scheduler.on_sequence_finished = next_sequence
        self.window.show()
        QTimer.singleShot(500, next_sequence)        # let the window map first
        QTimer.singleShot(int((seconds + 5) * 1000), loop.quit)   # safety net
        loop.exec()
        self.scheduler.stop()
        self.window.close()
        return self.samples


def measure(seconds: float = 30.0, tiles: str = "widget", *, flash_ms: int = 100,
            isi_ms: int = 75, threshold_ms: float = JITTER_WARN_MS) -> TimingReport:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    probe = FlashTimingProbe(tiles, flash_ms=flash_ms, isi_ms=isi_ms)
    missed0 = probe.dwm.frames_missed()
    samples = probe.run(seconds)
    missed1 = probe.dwm.frames_missed()
    platform = QGuiApplication.platformName()
    hz = probe.dwm.refresh_hz()
    if not hz:
        screen = app.primaryScreen()
        hz = screen.refreshRate() if screen is not None else None
    missed = (missed1 - missed0) if (missed0 is not None and missed1 is not None) else None
    return build_report(samples, source=probe.source, tiles=tiles, platform=platform,
                        refresh_hz=hz, frames_missed=missed, threshold_ms=threshold_ms)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.eeg.flash_timing",
                                 description="Measure P300 flash marker vs on-screen frame timing.")
    ap.add_argument("--seconds", type=float, default=30.0, help="how long to flash (default 30)")
    ap.add_argument("--tiles", choices=("widget", "gl"), default="widget",
                    help="widget = the real QLabel tiles + DWM vblank estimate (default); "
                         "gl = QOpenGLWidget tiles + Qt frameSwapped")
    ap.add_argument("--flash-ms", type=int, default=100)
    ap.add_argument("--isi-ms", type=int, default=75)
    ap.add_argument("--threshold-ms", type=float, default=JITTER_WARN_MS,
                    help=f"WARN above this jitter (default {JITTER_WARN_MS:.0f})")
    ap.add_argument("--csv", metavar="PATH", help="also write per-flash timestamps to PATH")
    ap.add_argument("--compare", nargs=2, metavar=("CSV", "ONSETS"),
                    help="no flashing: compare a --csv run with light-onset times from a "
                         "photodiode or slow-motion video (one time in seconds per line)")
    ap.add_argument("--tile", choices=("target_1", "target_2"),
                    help="with --compare: only that tile's markers (the one the sensor watched)")
    args = ap.parse_args(argv)
    if args.compare:
        gt = compare_ground_truth(read_marker_times(args.compare[0], args.tile),
                                  read_onsets(args.compare[1]), args.threshold_ms)
        print(format_ground_truth(gt))
        return 0 if gt.verdict == "PASS" else 1
    if args.seconds <= 0:
        ap.error("--seconds must be positive")
    report = measure(args.seconds, args.tiles, flash_ms=args.flash_ms, isi_ms=args.isi_ms,
                     threshold_ms=args.threshold_ms)
    print(format_report(report))
    if args.csv:
        write_csv(args.csv, report.samples)
        print(f"  per-flash timestamps written to {args.csv}")
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
