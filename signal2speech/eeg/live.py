"""Guided live run (#23): device check -> signal quality -> P300 + confirm calibration ->
N choose+confirm attempts -> a summary that says whether live EEG confirm can be armed.

    python -m signal2speech.eeg.live --source hybridblack   # Live EEG, Unicorn Hybrid Black, OSCAR on
    python -m signal2speech.eeg.live --source generator     # dry run, no hardware, labelled Simulated

Steps:

1. **Device check.** Opens the headset through the #46 P300 pipeline (one headset can be
   opened once, so every branch shares that pipeline). If it isn't paired, it prints how to
   pair it and exits with code 3.
2. **Signal quality.** About 10 s of the stream with OSCAR on. Per channel: 1-30 Hz RMS
   (flat or noisy means no-go) and 50/60 Hz line noise (a warning). Go / no-go.
3. **P300 calibration.** ``P300Chooser.begin_calibration`` / ``finish_calibration`` from
   ``signal2speech/eeg/p300.py``, plus a cross-validated accuracy on the calibration epochs.
4. **Confirm calibration.** The #47 alpha switch if ``signal2speech/eeg/alpha_confirm.py`` is
   importable (PR #58), otherwise keyboard confirm.
5. **Attempts.** N choose+confirm attempts through ``SelectionHandler`` and ``InputAdapter``.
   Every handler ``Outcome``, every P300 decision, accuracy, and time per selection go to
   ``logs/`` (gitignored). No raw EEG is written, ever.
6. **Summary.** Safe to set ``live_eeg_confirm_armed = True`` only if live EEG confirm was
   exercised on a live run, no ``RejectedStaleRound`` was seen, and false confirms are 0.

The step logic (quality, scoring, arming) is pure Python so ``tests/test_live.py`` runs it
headless. g.Pype and Qt are imported only when the harness runs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import itertools
import json
import os
import random
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from signal2speech.core import (Choice, ConfirmedAction, InputAdapter, InputSources, Outcome,
                                RoundKind, SelectionHandler, TargetIds)

RATE = 250.0
CHANNELS = ("Fz", "C3", "Cz", "C4", "Pz", "PO7", "Oz", "PO8")   # Unicorn Hybrid Black order

#: Quality thresholds (starting heuristics, tune on the first live run).
FLAT_RMS_UV = 0.5     # 1-30 Hz RMS below this: electrode not touching / channel dead
NOISY_RMS_UV = 50.0   # above this: poor contact, movement, or muscle
LINE_RMS_UV = 10.0    # 50/60 Hz RMS above this (and above the EEG band): warn

#: Arming needs at least this many attempts that reached a live-EEG confirm round.
MIN_ARMING_ATTEMPTS = 5

EXIT_OK, EXIT_ERROR, EXIT_NO_DEVICE, EXIT_NO_GO, EXIT_CALIBRATION = 0, 1, 3, 4, 5

PAIRING_HELP = (
    "Unicorn Hybrid Black not available. Check:\n"
    "  1. The headset is switched on (LED blinking) and charged.\n"
    "  2. It is paired in the OS Bluetooth settings (Windows: Settings > Bluetooth & devices >\n"
    "     Add device). Pair it there first; g.Pype does not pair it.\n"
    "  3. No other app (another g.Pype run, the evidence view, Unicorn Suite) has it open.\n"
    "Then run this again. Use --source generator for a dry run without hardware.")

CHOICES = (Choice(TargetIds.TARGET_1, "show_satellite", "Satellite"),
           Choice(TargetIds.TARGET_2, "compare_air_quality", "Compare counties"))


# ── step 2: signal quality (pure) ────────────────────────────────────────────

@dataclass
class ChannelQuality:
    name: str
    rms_uv: float        # 1-30 Hz
    line_uv: float       # max of 48-52 Hz and 58-62 Hz
    status: str          # ok | flat | noisy
    line_warning: bool


@dataclass
class QualityReport:
    channels: List[ChannelQuality]
    seconds: float

    @property
    def go(self) -> bool:
        return bool(self.channels) and all(c.status == "ok" for c in self.channels)

    @property
    def bad(self) -> List[str]:
        return [c.name for c in self.channels if c.status != "ok"]


def _band_rms(psd: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    sel = (freqs >= lo) & (freqs <= hi)
    df = freqs[1] - freqs[0]
    return np.sqrt(psd[sel].sum(axis=0) * df)


def assess_quality(samples: np.ndarray, rate: float = RATE,
                   names: Sequence[str] = CHANNELS) -> QualityReport:
    """Per-channel quality from a (time, channel) block in microvolts.

    Uses an averaged 1 s Hann periodogram, so DC offsets and slow drift don't count.
    """
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] < int(rate):
        return QualityReport([], x.shape[0] / rate if x.ndim == 2 else 0.0)
    n = int(rate)
    win = np.hanning(n)
    segs = [x[i:i + n] for i in range(0, x.shape[0] - n + 1, n // 2)]
    psd = np.mean([np.abs(np.fft.rfft((s - s.mean(axis=0)) * win[:, None], axis=0)) ** 2
                   for s in segs], axis=0)
    psd *= 2.0 / (rate * (win ** 2).sum())   # one-sided PSD in uV^2/Hz
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    eeg = _band_rms(psd, freqs, 1.0, 30.0)
    line = np.maximum(_band_rms(psd, freqs, 48.0, 52.0), _band_rms(psd, freqs, 58.0, 62.0))
    out = []
    for i in range(x.shape[1]):
        status = "flat" if eeg[i] < FLAT_RMS_UV else "noisy" if eeg[i] > NOISY_RMS_UV else "ok"
        name = names[i] if i < len(names) else f"ch{i + 1}"
        out.append(ChannelQuality(name, round(float(eeg[i]), 2), round(float(line[i]), 2),
                                  status, bool(line[i] > LINE_RMS_UV and line[i] > eeg[i])))
    return QualityReport(out, x.shape[0] / rate)


def format_quality(report: QualityReport) -> str:
    rows = [f"  {'ch':<4} {'1-30 Hz RMS':>12} {'50/60 Hz':>9}  status"]
    for c in report.channels:
        flag = c.status.upper() if c.status != "ok" else "ok"
        rows.append(f"  {c.name:<4} {c.rms_uv:>9.1f} uV {c.line_uv:>6.1f} uV  {flag}"
                    + ("  (line noise)" if c.line_warning else ""))
    verdict = "GO" if report.go else f"NO-GO ({', '.join(report.bad) or 'no data'})"
    rows.append(f"  {report.seconds:.1f} s analysed -> {verdict}")
    return "\n".join(rows)


# ── step 5: attempts and scoring (pure) ──────────────────────────────────────

@dataclass
class Attempt:
    index: int
    intended: str                       # tile the wearer attended
    decoded: Optional[str] = None       # tile the P300 previewed (None: no decision)
    preview_outcome: Optional[str] = None
    confirm_method: Optional[str] = None   # alpha | keyboard
    confirm_source: Optional[str] = None   # source of the event that ended the confirm round
    confirm_outcome: Optional[str] = None  # Confirmed | Cancelled | Timeout | ...
    seconds: Optional[float] = None     # Choose round opened -> confirm round ended

    @property
    def p300_correct(self) -> bool:
        return self.decoded is not None and self.decoded == self.intended

    @property
    def false_confirm(self) -> bool:
        """A Confirmed after a wrong preview: the wearer meant to let it time out or cancel."""
        return self.confirm_outcome == Outcome.Confirmed.value and not self.p300_correct


@dataclass
class RunStats:
    label: str                          # Simulated | Live EEG
    source: str                         # InputSources value of the EEG adapters
    confirm_method: str
    attempts: List[Attempt] = field(default_factory=list)
    outcomes: Dict[str, int] = field(default_factory=dict)
    late_p300_decisions: int = 0        # decisions that arrived after their round closed

    def note_outcome(self, outcome: Outcome) -> None:
        self.outcomes[outcome.value] = self.outcomes.get(outcome.value, 0) + 1

    @property
    def stale_round_rejections(self) -> int:
        return self.outcomes.get(Outcome.RejectedStaleRound.value, 0)

    @property
    def false_confirms(self) -> int:
        return sum(a.false_confirm for a in self.attempts)

    @property
    def eeg_confirm_rounds(self) -> int:
        """Attempts whose confirm round was decided by EEG (alpha), not the keyboard."""
        return sum(1 for a in self.attempts
                   if a.confirm_method == "alpha" and a.preview_outcome == "Previewed")

    def summary(self) -> dict:
        n = len(self.attempts)
        times = [a.seconds for a in self.attempts if a.seconds is not None]
        right = [a for a in self.attempts if a.p300_correct]
        return {
            "label": self.label, "source": self.source, "confirm_method": self.confirm_method,
            "attempts": n,
            "p300_correct": len(right),
            "p300_accuracy": round(len(right) / n, 3) if n else None,
            "confirmed_correct": sum(1 for a in right
                                     if a.confirm_outcome == Outcome.Confirmed.value),
            "false_confirms": self.false_confirms,
            "stale_round_rejections": self.stale_round_rejections,
            "late_p300_decisions": self.late_p300_decisions,
            "eeg_confirm_rounds": self.eeg_confirm_rounds,
            "mean_seconds_per_selection": round(sum(times) / len(times), 2) if times else None,
            "outcomes": dict(self.outcomes),
        }


# ── step 6: arming decision (pure) ───────────────────────────────────────────

@dataclass
class ArmingDecision:
    safe: bool                  # safe to set live_eeg_confirm_armed = True
    rule_passed: bool           # the evidence rule passed, whatever the label
    reasons: List[str]

    def text(self) -> str:
        head = ("SAFE to set live_eeg_confirm_armed = True" if self.safe else
                "NOT safe to set live_eeg_confirm_armed = True")
        return head + "".join(f"\n  - {r}" for r in self.reasons)


def decide_arming(stats: RunStats, min_attempts: int = MIN_ARMING_ATTEMPTS) -> ArmingDecision:
    """Arm only on live evidence: alpha confirms seen, no stale crossings, no false confirms."""
    reasons, ok = [], True
    if stats.stale_round_rejections:
        ok = False
        reasons.append(f"{stats.stale_round_rejections} RejectedStaleRound seen: a late decision "
                       "reached a newer round")
    else:
        reasons.append("no RejectedStaleRound seen")
    if stats.false_confirms:
        ok = False
        reasons.append(f"{stats.false_confirms} false confirm(s): Confirmed after a wrong preview")
    else:
        reasons.append("false confirms = 0")
    if stats.eeg_confirm_rounds < min_attempts:
        ok = False
        why = ("confirm was by keyboard, so live EEG confirm was not exercised"
               if stats.confirm_method != "alpha" else
               f"only {stats.eeg_confirm_rounds} EEG confirm round(s), need {min_attempts}")
        reasons.append(why)
    else:
        reasons.append(f"{stats.eeg_confirm_rounds} EEG confirm rounds")
    live = stats.source == InputSources.LIVE_EEG
    if not live:
        reasons.append(f"input was {stats.label}, not Live EEG: a dry run never arms anything")
    return ArmingDecision(ok and live, ok, reasons)


# ── logging (no raw EEG) ─────────────────────────────────────────────────────

class RunLog:
    """JSON lines under ``logs/``. Only events, outcomes, and summaries: never samples."""

    #: Values allowed in a record: scalars, short lists of scalars, and nested dicts of those.
    MAX_LIST = 16

    def __init__(self, directory: str, label: str):
        os.makedirs(directory, exist_ok=True)
        # Milliseconds and the PID keep two runs started in the same second apart.
        # Mode "x" never shares a file: on a collision, add a counter and try again.
        now = _dt.datetime.now()
        stamp = now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"
        tag = label.lower().replace(" ", "-")
        base = os.path.join(directory, f"live_{stamp}_{os.getpid()}")
        for n in itertools.count():
            self.path = f"{base}{'' if n == 0 else f'-{n}'}_{tag}.jsonl"
            try:
                with open(self.path, "x", encoding="utf-8"):
                    break
            except FileExistsError:
                continue
        self.label = label
        self._lock = threading.Lock()

    @classmethod
    def _check(cls, value, where: str) -> None:
        if isinstance(value, np.ndarray):
            raise TypeError(f"refusing to log an array at {where}: no raw EEG in logs")
        if isinstance(value, dict):
            for k, v in value.items():
                cls._check(v, f"{where}.{k}")
        elif isinstance(value, (list, tuple)):
            if len(value) > cls.MAX_LIST:
                raise TypeError(f"refusing to log a {len(value)}-item list at {where}")
            for v in value:
                cls._check(v, where)

    def write(self, kind: str, **fields) -> dict:
        record = {"t": round(time.time(), 3), "label": self.label, "kind": kind, **fields}
        self._check(record, kind)
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record


# ── console ──────────────────────────────────────────────────────────────────

class Console:
    """Operator prompts. ``scripted`` answers every question with its default (dry runs, tests)."""

    def __init__(self, scripted: bool = False, out=None, inp: Callable[[str], str] = input):
        self.scripted = scripted
        self.out = out or sys.stdout
        self.inp = inp

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def ask(self, question: str, default: str = "") -> str:
        if self.scripted:
            self.say(f"{question} [{default}] (scripted)")
            return default
        try:
            ans = self.inp(f"{question} [{default}] ").strip()
        except EOFError:
            ans = ""
        return ans or default

    def yes(self, question: str, default: bool = False) -> bool:
        return self.ask(question + " (y/n)", "y" if default else "n").lower().startswith("y")


# ── harness (g.Pype + Qt) ────────────────────────────────────────────────────

def alpha_module():
    """``signal2speech.eeg.alpha_confirm`` (#47) if it is on this checkout, else None."""
    try:
        from signal2speech.eeg import alpha_confirm   # noqa: F401
        return alpha_confirm
    except ImportError:
        return None


class TaggedAdapter(InputAdapter):
    """InputAdapter whose event IDs carry a branch tag (``s1-p300``, ``e3-alpha``).

    Two adapters with the same source on one handler both count from 1, so the P300 branch's
    ``s1`` and the alpha branch's ``s1`` collide and the second is ``RejectedDuplicateEvent``.
    Found by this harness; the tag keeps every event ID unique per run.
    """

    def __init__(self, handler: SelectionHandler, source: str, tag: str):
        super().__init__(handler, source)
        self.tag = tag

    def create(self, round_id: str, target_id: str):
        e = super().create(round_id, target_id)
        return type(e)(e.source, e.roundId, f"{e.eventId}-{self.tag}", e.targetId)


class _LogSink:
    """Harness-only sink: logs the confirmed action. No speech, no map."""

    def __init__(self, log: RunLog):
        self.log = log
        self.executed: List[ConfirmedAction] = []

    def execute(self, action: ConfirmedAction) -> None:
        self.executed.append(action)
        self.log.write("effect", action=asdict(action))


@dataclass
class Options:
    source: str = "generator"           # generator | hybridblack
    attempts: int = 10
    quality_s: float = 10.0
    calibration: int = 10
    flashes: int = 5
    soa: float = 0.25
    confirm_timeout_s: float = 8.0
    alpha_calib_s: float = 10.0
    alpha_rest_s: float = 20.0
    enable_oscar: bool = True
    confirm: str = "auto"               # auto | alpha | keyboard
    seed: int = 0
    logs_dir: str = "logs"


class LiveHarness:
    """Runs the six steps. ``run()`` returns a process exit code."""

    def __init__(self, opts: Options, console: Optional[Console] = None):
        self.opts = opts
        self.simulated = opts.source == "generator"
        self.label = "Simulated" if self.simulated else "Live EEG"
        self.console = console or Console(scripted=self.simulated)
        self.eeg_source = InputSources.SIMULATED if self.simulated else InputSources.LIVE_EEG
        self.log = RunLog(opts.logs_dir, self.label)
        self.rng = random.Random(opts.seed)
        self.alpha_mod = alpha_module() if opts.confirm in ("auto", "alpha") else None
        self.confirm_method = "alpha" if self.alpha_mod is not None else "keyboard"
        self.stats = RunStats(self.label, self.eeg_source, self.confirm_method)
        self.sink = _LogSink(self.log)
        self.handler = SelectionHandler(self.sink)
        self.handler.on_handled.append(self._on_handled)
        self.p300_adapter = TaggedAdapter(self.handler, self.eeg_source, "p300")
        self.keyboard = InputAdapter(self.handler, InputSources.KEYBOARD)
        self.app = self.nodes = self.chooser = self.alpha = self.tiles = None
        self._ring: deque = deque(maxlen=int(RATE * max(opts.quality_s, 1.0) * 1.5))
        self._ring_lock = threading.Lock()
        self._samples_seen = 0
        self._last_event_source: Optional[str] = None
        self._awaiting_decision = False

    # ── plumbing ──
    def say(self, text: str) -> None:
        self.console.say(f"[live:{self.label}] {text}")

    @property
    def oscar(self) -> str:
        if self.simulated:
            return "OSCAR n/a (Generator)"
        return "OSCAR on" if self.opts.enable_oscar else "OSCAR off"

    def step(self, n: int, title: str) -> None:
        self.say(f"Step {n}/6: {title}")
        self.log.write("step", step=n, title=title)

    def pump(self, seconds: float, until: Optional[Callable[[], bool]] = None) -> bool:
        """Keep Qt events flowing for ``seconds``, or until ``until()`` is true."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.app is not None:
                self.app.processEvents()
            if until is not None and until():
                return True
            time.sleep(0.005)
        return until() if until is not None else True

    def _on_handled(self, event, outcome: Outcome) -> None:
        self.stats.note_outcome(outcome)
        self._last_event_source = event.source if event is not None else None
        self.log.write("outcome", outcome=outcome.value,
                       event=None if event is None else asdict(event),
                       round=self.handler.current.id if self.handler.current else None)

    def _on_p300(self, cls, target, outcome) -> None:
        late = not self._awaiting_decision
        if late:
            self.stats.late_p300_decisions += 1
        self._awaiting_decision = False
        self.log.write("p300_decision", cls=int(cls), target=target, late=late,
                       outcome=None if outcome is None else outcome.value)

    def _on_rows(self, rows: np.ndarray) -> None:   # g.Pype worker thread
        with self._ring_lock:
            self._ring.extend(np.asarray(rows, dtype=np.float64)[:, :len(CHANNELS)])
            self._samples_seen += len(rows)

    # ── step 1 ──
    def build(self):
        """Build the shared pipeline: P300 branch, a quality tap, and the alpha branch."""
        import gpype as gp
        from gpype.common.constants import Constants

        from signal2speech.eeg import p300

        if self.app is None:
            from PySide6.QtWidgets import QApplication
            self.app = QApplication.instance() or QApplication([])
        placeholder = p300.train_on_synthetic(n_sequences=4, seed=99)   # replaced in step 3
        self.nodes = p300.build_pipeline(self.opts.source, model=placeholder,
                                         enable_oscar=self.opts.enable_oscar)
        port_in = Constants.Defaults.PORT_IN

        class _QualityTap(gp.INode):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.on_rows: Callable[[np.ndarray], None] = lambda rows: None

            def step(self, data):
                block = data.get(port_in)
                if block is not None and len(block):
                    self.on_rows(np.asarray(block))
                return {}

        upstream = self.nodes.synth or self.nodes.source
        signal_only = gp.ChannelSelector(roles=Constants.ChannelRoles.SIGNAL, name="live_signal")
        tap = _QualityTap(name="live_quality_tap")
        tap.on_rows = self._on_rows
        self.nodes.pipeline.connect(upstream, signal_only)
        self.nodes.pipeline.connect(signal_only, tap)

        self.chooser = p300.P300Chooser(self.nodes, self.p300_adapter,
                                        flashes_per_tile=self.opts.flashes)
        self.chooser.bridge.listeners.append(self._on_p300)
        if self.alpha_mod is not None:
            self.alpha = self._build_alpha()
        if not self.simulated:
            self.tiles = p300._TestTiles()

    def _build_alpha(self):
        """AlphaConfirm (#47). Live: hang its branch off the shared headset pipeline.
        Simulated: its own Generator with scripted eye closures."""
        am = self.alpha_mod
        if self.simulated:
            ac = am.AlphaConfirm(self.handler, input_source=self.eeg_source,
                                 bursts=am.AlphaBursts())
        else:
            ac = am.AlphaConfirm(self.handler, input_source=self.eeg_source,
                                 pipeline=self.nodes.pipeline, upstream=self.nodes.eeg)
        ac.adapter = TaggedAdapter(self.handler, self.eeg_source, "alpha")
        return ac

    def device_check(self) -> bool:
        self.step(1, f"device check ({'Generator' if self.simulated else 'HybridBlack'}, "
                     f"{self.oscar})")
        try:
            self.build()
            self.nodes.pipeline.start()
            if self.alpha is not None and self.simulated:
                self.alpha.start()
        except Exception as err:   # g.Pype raises various errors for a missing device
            self.log.write("device", ok=False, error=f"{type(err).__name__}: {err}")
            self.say(f"Could not open the source: {type(err).__name__}: {err}")
            if not self.simulated:
                self.say(PAIRING_HELP)
            return False
        if not self.pump(5.0, until=lambda: self._samples_seen >= RATE):
            self.log.write("device", ok=False, error="no samples within 5 s")
            self.say("The source opened but sent no samples within 5 s.")
            if not self.simulated:
                self.say(PAIRING_HELP)
            return False
        self.log.write("device", ok=True, samples=self._samples_seen)
        self.say(f"Stream is up ({self._samples_seen} samples so far).")
        return True

    # ── step 2 ──
    def signal_quality(self) -> QualityReport:
        self.step(2, f"signal quality for {self.opts.quality_s:g} s, {self.oscar}")
        if not self.simulated:
            self.say("Sit still, eyes open, relaxed jaw.")
        with self._ring_lock:
            self._ring.clear()
        self.pump(self.opts.quality_s)
        with self._ring_lock:
            block = np.array(self._ring)
        report = assess_quality(block)
        self.say("\n" + format_quality(report))
        self.log.write("quality", go=report.go, seconds=round(report.seconds, 1),
                       channels=[asdict(c) for c in report.channels])
        return report

    # ── flashing ──
    def _flash_sequence(self, cue: Optional[str]) -> None:
        from PySide6.QtCore import QTimer

        from signal2speech.eeg import p300
        if self.tiles is not None:
            self.tiles.set_cue(cue)
        lead = 1.0 if self.tiles is not None else 0.0
        order = p300.make_sequence(self.opts.flashes, self.rng)
        t0 = time.monotonic() + lead
        for k, tile in enumerate(order):
            self.pump(max(0.0, t0 + k * self.opts.soa - time.monotonic()))
            if self.tiles is not None:
                self.tiles.light(tile, True)
                QTimer.singleShot(int(p300.FLASH_ON_S * 1000),
                                  lambda t=tile: self.tiles.light(t, False))
            self.chooser.on_flash(tile)
        self.pump(self.opts.soa)   # keep the next sequence's first marker off this sample

    # ── step 3 ──
    def calibrate_p300(self) -> bool:
        from signal2speech.eeg import p300
        self.step(3, f"P300 calibration, {self.opts.calibration} sequences")
        if not self.simulated:
            self.say("Look at the tile with the yellow border and silently count its flashes.")
        t0 = time.monotonic()
        tiles = list(p300.FLASH_CODES)
        for i in range(self.opts.calibration):
            attended = tiles[i % 2]
            self.chooser.begin_calibration(attended)
            self._flash_sequence(attended)
        self.pump(p300.TIME_POST + 0.5)
        try:
            model = self.chooser.finish_calibration()
        except Exception as err:
            self.log.write("p300_calibration", ok=False, error=f"{type(err).__name__}: {err}")
            self.say(f"P300 calibration failed: {err}")
            return False
        cv = calibration_cv_accuracy(model)
        n_t = model.n_target
        self.log.write("p300_calibration", ok=True, target_epochs=n_t,
                       nontarget_epochs=len(model.trials) - n_t, cv_epoch_accuracy=cv,
                       seconds=round(time.monotonic() - t0, 1))
        self.say(f"Trained LDA on {n_t} target and {len(model.trials) - n_t} non-target epochs; "
                 f"cross-validated epoch accuracy {cv if cv is None else f'{cv:.2f}'} "
                 f"(chance 0.50), {time.monotonic() - t0:.0f} s.")
        return True

    # ── step 4 ──
    def calibrate_confirm(self) -> bool:
        if self.alpha is None:
            self.step(4, "confirm: keyboard (alpha_confirm.py not on this checkout)")
            how = ("scripted keys: 1 confirms a correct preview, 2 cancels a wrong one"
                   if self.simulated else "type y + Enter to confirm, Enter alone to cancel")
            self.say(f"Keyboard confirm: {how}.")
            self.log.write("confirm_calibration", method="keyboard")
            return True
        self.step(4, f"alpha-switch calibration ({self.opts.alpha_calib_s:g} s open, "
                     f"{self.opts.alpha_calib_s:g} s closed, {self.opts.alpha_rest_s:g} s rest)")
        report = self.alpha_mod.measure(self.alpha, self.opts.alpha_calib_s,
                                        self.opts.alpha_rest_s, closures=2)
        self.log.write("confirm_calibration", method="alpha", report=_scalars(report))
        if "error" in report:
            self.say(f"Alpha calibration failed: {report['error']}")
            return False
        self.say(f"Alpha calibration: {report.get('calibration')}; "
                 f"false triggers at rest: {report.get('false_triggers')}; "
                 f"edges per closure: {report.get('edges_per_closure')}.")
        return True

    # ── step 5 ──
    def attempts(self) -> None:
        from signal2speech.eeg import p300
        self.step(5, f"{self.opts.attempts} choose+confirm attempts ({self.confirm_method} "
                     "confirm)")
        if self.alpha is not None and not self.simulated:
            # Harness-only handler with a logging sink, so a live confirm can be measured.
            # The app's handler stays disarmed until the summary says otherwise.
            self.handler.live_eeg_confirm_armed = True
        tiles = list(p300.FLASH_CODES)
        for i in range(self.opts.attempts):
            a = Attempt(i + 1, self.rng.choice(tiles), confirm_method=self.confirm_method)
            self._run_attempt(a)
            self.stats.attempts.append(a)
            self.log.write("attempt", **asdict(a), p300_correct=a.p300_correct,
                           false_confirm=a.false_confirm)
            mark = "ok" if a.p300_correct else "MISS"
            self.say(f"  #{a.index}: attend {a.intended} -> preview {a.decoded} ({mark}) -> "
                     f"{a.confirm_outcome} via {a.confirm_source or '-'} in {a.seconds} s")
            self.pump(0.5)
        self.pump(p300.TIME_POST + 0.5)   # catch any late decision

    def _run_attempt(self, a: Attempt) -> None:
        from signal2speech.eeg import p300
        if not self.simulated:
            self.say(f"Attempt {a.index}: attend {a.intended}.")
        t0 = time.monotonic()
        self.handler.begin_choice_round(list(CHOICES))
        outcomes_before = len(self.chooser.bridge.outcomes)
        self._awaiting_decision = True
        self.chooser.begin_sequence(attended_for_synthetic=a.intended)
        self._flash_sequence(a.intended if not self.simulated else None)
        got = self.pump(p300.TIME_POST + 1.5,
                        until=lambda: len(self.chooser.bridge.outcomes) > outcomes_before)
        if not got:
            self.chooser.end_sequence()   # decide from the epochs that arrived
            got = self.pump(0.5, until=lambda: len(self.chooser.bridge.outcomes) > outcomes_before)
        if got:
            outcome = self.chooser.bridge.outcomes[outcomes_before]
            a.preview_outcome = outcome.value if outcome is not None else None
            if outcome is Outcome.Previewed and self.handler.pending is not None:
                a.decoded = self.handler.pending.target_id
        else:
            self._awaiting_decision = False
            a.preview_outcome = "NoDecision"
        if a.preview_outcome != Outcome.Previewed.value:
            self.handler.cancel("no preview")
            a.confirm_outcome = "Skipped"
            a.seconds = round(time.monotonic() - t0, 2)
            return
        confirm_round = self.handler.current
        intend_confirm = a.p300_correct
        before = dict(self.stats.outcomes)
        if self.alpha is not None:
            self._alpha_confirm(intend_confirm, confirm_round)
        else:
            self._keyboard_confirm(a, intend_confirm)
        if self.handler.current is confirm_round:   # nobody decided: timeout cancels
            self.handler.cancel("timeout")
            a.confirm_outcome, a.confirm_source = "Timeout", None
        else:
            a.confirm_outcome = _first_new(before, self.stats.outcomes,
                                           (Outcome.Confirmed, Outcome.Cancelled))
            a.confirm_source = self._last_event_source
        a.seconds = round(time.monotonic() - t0, 2)

    def _alpha_confirm(self, intend: bool, confirm_round) -> None:
        bursts = getattr(self.alpha, "bursts", None)
        if not self.simulated:
            self.say("  Correct preview? Close your eyes ~2 s to confirm. Wrong? Keep them open.")
        elif bursts is not None:
            self.pump(self.alpha.settle_s + 0.3)   # eyes open after arming, as a wearer would
            if intend:
                bursts.close_eyes()
        self.pump(self.opts.confirm_timeout_s,
                  until=lambda: self.handler.current is not confirm_round)
        if bursts is not None:
            bursts.open_eyes()

    def _keyboard_confirm(self, a: Attempt, intend: bool) -> None:
        if self.simulated:
            self.keyboard.select_now(TargetIds.TARGET_1 if intend else TargetIds.TARGET_2)
            return
        ans = self.console.ask(f"  Preview is {a.decoded}. Confirm? y=confirm, Enter=cancel", "")
        self.pump(0.05)
        self.keyboard.select_now(TargetIds.TARGET_1 if ans.lower().startswith("y")
                                 else TargetIds.TARGET_2)

    # ── step 6 ──
    def finish(self) -> ArmingDecision:
        self.step(6, "summary")
        summary = self.stats.summary()
        decision = decide_arming(self.stats)
        self.log.write("summary", **summary, arming_safe=decision.safe,
                       arming_rule_passed=decision.rule_passed, arming_reasons=decision.reasons)
        s = summary
        self.say(f"Input: {self.label}. Confirm: {self.confirm_method}.")
        self.say(f"P300: {s['p300_correct']}/{s['attempts']} correct previews"
                 f" (accuracy {s['p300_accuracy']}); correct+confirmed {s['confirmed_correct']};"
                 f" mean {s['mean_seconds_per_selection']} s per selection.")
        self.say(f"False confirms {s['false_confirms']}; RejectedStaleRound "
                 f"{s['stale_round_rejections']}; late P300 decisions {s['late_p300_decisions']}.")
        self.say(f"Outcomes: {s['outcomes']}")
        self.say(decision.text())
        self.say(f"Log: {self.log.path}")
        return decision

    def close(self) -> None:
        for fn in (getattr(self.alpha, "close", None),):
            if fn:
                try:
                    fn()
                except Exception:
                    pass
        if self.nodes is not None:
            for fn in (self.nodes.pipeline.stop, self.nodes.pipeline.close):
                try:
                    fn()
                except Exception:
                    pass

    def run(self) -> int:
        self.say(f"Signal2Speech live run (#23). Input is labelled {self.label}."
                 + (" Dry run: no headset." if self.simulated else ""))
        try:
            if not self.device_check():
                return EXIT_NO_DEVICE
            report = self.signal_quality()
            if not report.go and not self.console.yes("Signal quality is NO-GO. Continue anyway?",
                                                      default=self.simulated):
                self.say("Stopped at signal quality. Re-seat the electrodes and run again.")
                return EXIT_NO_GO
            if not self.calibrate_p300() or not self.calibrate_confirm():
                return EXIT_CALIBRATION
            self.attempts()
            self.finish()
            return EXIT_OK
        finally:
            self.close()


def _first_new(before: Dict[str, int], after: Dict[str, int], wanted) -> Optional[str]:
    for o in wanted:
        if after.get(o.value, 0) > before.get(o.value, 0):
            return o.value
    return None


def _scalars(d: dict) -> dict:
    """Keep a report loggable: drop arrays and long lists."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _scalars(v)
        elif isinstance(v, (list, tuple)) and len(v) <= RunLog.MAX_LIST and not any(
                isinstance(x, (list, tuple, dict, np.ndarray)) for x in v):
            out[k] = [float(x) if isinstance(x, (np.floating,)) else x for x in v]
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, np.generic):
            out[k] = v.item()
    return out


def calibration_cv_accuracy(model, folds: int = 5) -> Optional[float]:
    """Cross-validated single-epoch accuracy of the calibration LDA (chance 0.5)."""
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import cross_val_score

    from signal2speech.eeg import p300
    feats = p300.bin_means(np.asarray(model.block, dtype=np.float64))
    x = feats.transpose(2, 0, 1).reshape(feats.shape[2], -1)
    y = np.array([label == p300.TARGET_LABEL for _, label in model.trials])
    k = min(folds, int(y.sum()), int((~y).sum()))
    if k < 2:
        return None
    lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    return round(float(cross_val_score(lda, x, y, cv=k).mean()), 3)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.eeg.live",
                                 description="Guided live run (#23): device, quality, "
                                             "calibration, attempts, arming summary.")
    ap.add_argument("--source", choices=["hybridblack", "generator"], default="generator",
                    help="hybridblack: Unicorn headset (Live EEG); generator: dry run (Simulated)")
    ap.add_argument("--attempts", type=int, default=10, help="live choose+confirm attempts")
    ap.add_argument("--quality-s", type=float, default=10.0, help="signal quality seconds")
    ap.add_argument("--calibration", type=int, default=10, help="P300 calibration sequences")
    ap.add_argument("--flashes", type=int, default=5, help="flashes per tile per sequence")
    ap.add_argument("--soa", type=float, default=0.25, help="seconds between flashes")
    ap.add_argument("--confirm-timeout", type=float, default=8.0,
                    help="seconds before an unanswered confirm round cancels")
    ap.add_argument("--confirm", choices=["auto", "alpha", "keyboard"], default="auto",
                    help="auto: alpha switch if alpha_confirm.py exists, else keyboard")
    ap.add_argument("--alpha-calib-s", type=float, default=10.0)
    ap.add_argument("--alpha-rest-s", type=float, default=20.0)
    ap.add_argument("--no-oscar", action="store_true", help="HybridBlack without OSCAR")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--logs", default="logs", help="log directory (gitignored)")
    args = ap.parse_args(argv)
    opts = Options(source=args.source, attempts=args.attempts, quality_s=args.quality_s,
                   calibration=args.calibration, flashes=args.flashes, soa=args.soa,
                   confirm_timeout_s=args.confirm_timeout, alpha_calib_s=args.alpha_calib_s,
                   alpha_rest_s=args.alpha_rest_s, enable_oscar=not args.no_oscar,
                   confirm=args.confirm, seed=args.seed, logs_dir=args.logs)
    harness = LiveHarness(opts)
    if args.confirm == "alpha" and harness.alpha_mod is None:
        harness.say("--confirm alpha needs signal2speech/eeg/alpha_confirm.py (#47); "
                    "falling back to keyboard confirm.")
    return harness.run()


if __name__ == "__main__":
    raise SystemExit(main())
