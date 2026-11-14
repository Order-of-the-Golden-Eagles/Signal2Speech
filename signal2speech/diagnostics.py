"""Demo diagnostics and the one smoke command (#41).

    python -m signal2speech.app --smoke            # dev: missing #29/#30 pieces are SKIP
    python -m signal2speech.app --smoke=judging    # judging laptop: every SKIP is a FAIL

The smoke check is hardware-independent and needs no network or display (it forces Qt
offscreen). It runs a scripted keyboard choose -> preview -> confirm and a cancel with fake
output, checks the demo numbers and the bundled OpenOrbit assets, and checks that a g.Pype
``Generator`` stream runs. It exits 0 or 1 and writes a JSON-lines log under ``logs/``,
which is gitignored. The checks that need a person are listed as MANUAL and never run here.

``Diagnostics`` is the local troubleshooting log. Attach it to a handler and it records the
input mode, the g.Pype source, the connection state, and the timing of every round, outcome,
and output. It records events and metadata only. It refuses arrays, so raw EEG can't end up
in a log (#10).
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, TextIO

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"                    # gitignored
DATA_DIR = ROOT / "data" / "openorbit"     # #29
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
# The demo's ground truth (README, MEMORY.md): EPA daily county AQI, June 26 -> June 28, 2023.
AQI = {"Washtenaw": (32, 218), "Wayne": (58, 226)}

MANUAL_CHECKS = (
    "Headset: pair the Unicorn in OS Bluetooth, check all 8 channels (#23)",
    "Live calibration: P300 chooser (#46) and alpha threshold (#47) on the demo wearer (#23)",
    "g.Pype GUI: evidence scopes open and move (python -m signal2speech.evidence, #48)",
    "Audio: the confirmed line is audible on the judging laptop speakers",
    "Offline: Wi-Fi off, then python -m signal2speech.app runs the full reveal",
)

_SCALARS = (str, int, float, bool, type(None))


# ── Diagnostics log ──────────────────────────────────────────
_NO_RAW = "diagnostics record short metadata only; raw EEG stays out of logs (#10)"
MAX_LIST = 32


def _scalar(value):
    if isinstance(value, _SCALARS):
        if isinstance(value, str) and len(value) > 500:
            raise TypeError(_NO_RAW + ": string too long")
        return value
    if type(value).__module__.startswith("numpy") and getattr(value, "ndim", None) == 0:
        return value.item()
    if isinstance(value, (Path, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    return _NOT_SCALAR


_NOT_SCALAR = object()


def _safe(value, depth: int = 0):
    """Allow-list: scalars, dicts up to 3 levels, and lists of up to 32 scalars. Else TypeError.

    Nothing is ever stringified as a fallback, so arrays, deques, tensors, bytes, and nested
    sample lists can't reach a log by accident.
    """
    s = _scalar(value)
    if s is not _NOT_SCALAR:
        return s
    if isinstance(value, dict):
        if depth >= 3:
            raise TypeError(_NO_RAW + ": nested too deep")
        return {str(k): _safe(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST:
            raise TypeError(_NO_RAW + f": list longer than {MAX_LIST}")
        out = [_scalar(v) for v in value]
        if any(v is _NOT_SCALAR for v in out):
            raise TypeError(_NO_RAW + ": lists may hold scalars only")
        return out
    raise TypeError(_NO_RAW + f": {type(value).__name__} is not allowed")


class Diagnostics:
    """Timestamped, local, metadata-only event log for a demo run."""

    def __init__(self, path: Optional[Path] = None, echo: Optional[Callable[[str], None]] = None):
        self.rows: List[dict] = []
        self.path = path
        self.echo = echo
        self._fh: Optional[TextIO] = None
        self.input_source: Optional[str] = None
        self.gpype_source: Optional[str] = None
        self.connection: Optional[str] = None
        self._round_opened: dict = {}
        self._t0 = time.monotonic()

    @classmethod
    def to_file(cls, prefix: str = "diagnostics", **kw) -> "Diagnostics":
        LOG_DIR.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        n = 1
        while True:                               # claim the name, so same-ms runs can't share it
            suffix = "" if n == 1 else f"-{n}"
            path = LOG_DIR / f"{prefix}-{stamp}-{os.getpid()}{suffix}.jsonl"
            try:
                open(path, "x", encoding="utf-8").close()
                return cls(path, **kw)
            except FileExistsError:
                n += 1

    # Context shown on every row
    def set_input(self, source: str) -> None:
        self.input_source = source
        self.record("input", source=source)

    def set_gpype_source(self, name: Optional[str]) -> None:
        self.gpype_source = name
        self.record("gpype_source", name=name)

    def set_connection(self, state: str) -> None:
        self.connection = state
        self.record("connection", state=state)

    def record(self, kind: str, **fields) -> dict:
        row = {"t": time.strftime("%H:%M:%S"), "ms": round((time.monotonic() - self._t0) * 1000, 1),
               "kind": kind, "input": self.input_source, "gpype": self.gpype_source,
               "connection": self.connection}
        row.update({k: _safe(v) for k, v in fields.items()})
        self.rows.append(row)
        if self.path is not None:
            if self._fh is None:
                self._fh = open(self.path, "a", encoding="utf-8")
            self._fh.write(json.dumps(row) + "\n")
            self._fh.flush()
        if self.echo:
            self.echo(json.dumps(row))
        return row

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # Handler wiring
    def attach(self, handler, *, input_source: Optional[str] = None,
               gpype_source: Optional[str] = None, connection: Optional[str] = None,
               sink=None) -> "Diagnostics":
        """Log rounds, previews, outcomes, and clears, plus an output row if ``sink`` is given.

        ``sink`` is the object the handler calls (``AppSink``). Its ``execute`` is wrapped once,
        however many Diagnostics attach. Each output row carries ``sink_call_ms``, the time
        spent inside ``execute``: the map update plus *starting* speech. Qt speech and sound
        play asynchronously, so audible duration is not included.
        """
        if input_source:
            self.set_input(input_source)
        if gpype_source:
            self.set_gpype_source(gpype_source)
        if connection:
            self.set_connection(connection)
        handler.on_round_opened.append(self._on_round)
        handler.on_preview.append(lambda c: self.record("preview", action=c.action_id,
                                                        text=c.spoken_text or c.label))
        handler.on_handled.append(self._on_handled)
        handler.on_cleared.append(lambda reason: self.record("cleared", reason=reason))
        if sink is not None:
            observers = getattr(sink, "_diagnostics_observers", None)
            if observers is None:                 # wrap once; later Diagnostics just listen
                observers = []
                original = sink.execute

                def timed(action):
                    t = time.monotonic()
                    original(action)
                    ms = round((time.monotonic() - t) * 1000, 1)
                    for diag in list(observers):
                        diag._on_output(action, ms)
                sink.execute = timed
                sink._diagnostics_observers = observers
            if self not in observers:
                observers.append(self)
        return self

    def _on_output(self, action, sink_call_ms: float) -> None:
        self.record("output", action=action.action_id, source=action.source,
                    preview=action.preview_event_id, confirm=action.confirm_event_id,
                    sink_call_ms=sink_call_ms)

    def _on_round(self, rnd) -> None:
        self._round_opened[rnd.id] = time.monotonic()
        self.record("round", round=rnd.id, round_kind=rnd.kind.value,
                    targets={c.target_id: c.action_id for c in rnd.choices})

    def _on_handled(self, e, outcome) -> None:
        fields = {"outcome": outcome.value}
        if e is not None:
            fields.update(source=e.source, round=e.roundId, event=e.eventId, target=e.targetId)
            opened = self._round_opened.get(e.roundId)
            if opened is not None:
                fields["since_round_ms"] = round((time.monotonic() - opened) * 1000, 1)
        self.record("handled", **fields)

    def outputs(self) -> List[dict]:
        return [r for r in self.rows if r["kind"] == "output"]


# ── Smoke check ──────────────────────────────────────────────
@dataclass
class Check:
    name: str
    status: str      # PASS, WARN, SKIP, FAIL (judging mode turns WARN and SKIP into FAIL)
    detail: str


class _FakeView:
    def __init__(self):
        self.calls: List[str] = []

    def show_satellite(self):
        self.calls.append("show_satellite")

    def compare_air_quality(self):
        self.calls.append("compare_air_quality")


class _FakeSpeaker:
    def __init__(self):
        self.said: List[str] = []

    def say(self, text, clip=None):
        self.said.append(text)


def check_environment() -> Check:
    try:
        import gpype
        import PySide6
    except ImportError as err:
        return Check("environment", "FAIL", f"import failed: {err}. Run pip install -e \".[dev]\"")
    py = platform.python_version()
    gv = str(getattr(gpype, "__version__", "unknown"))
    detail = f"Python {py}, g.Pype {gv}, PySide6 {getattr(PySide6, '__version__', 'unknown')}"
    m = re.match(r"(\d+)\.(\d+)", gv)
    if not m:
        return Check("environment", "FAIL", detail + " (can't read the g.Pype version)")
    if (int(m.group(1)), int(m.group(2))) < (4, 2):
        return Check("environment", "FAIL", detail + " (need g.Pype 4.2 or later)")
    if not py.startswith("3.12."):
        return Check("environment", "WARN", detail + " (the verified launch path pins 3.12)")
    return Check("environment", "PASS", detail)


def check_demo_numbers(text: Optional[str] = None) -> Check:
    """Each county in the spoken comparison is followed, in the same sentence, by its EPA rise."""
    if text is None:
        from signal2speech.ui.__main__ import load_demo_choices   # the app's own loader
        text = next((c.spoken_text or "" for c in load_demo_choices()
                     if c.action_id == "compare_air_quality"), "")
    missing = [f"{county} +{after - before}" for county, (before, after) in AQI.items()
               if not re.search(rf"{county}[^.]*?(?<![\d.]){after - before}(?![\d])", text)]
    if missing:
        return Check("demo numbers", "FAIL", f"spoken line {text!r} lacks {', '.join(missing)}")
    return Check("demo numbers", "PASS", f"{text!r} matches EPA " + ", ".join(
        f"{c} {b}->{a}" for c, (b, a) in AQI.items()))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_assets(data_dir: Optional[Path] = None) -> Check:
    """#29 bundle: SOURCES.md, two same-bounds MODIS images, AQI rows with the demo values."""
    data_dir = DATA_DIR if data_dir is None else data_dir
    if not data_dir.is_dir():
        return Check("openorbit assets", "SKIP", f"{_rel(data_dir)}/ not bundled yet (#29)")
    problems = []
    sources = data_dir / "SOURCES.md"
    if not sources.is_file():
        problems.append("SOURCES.md missing")
    images = sorted(p.name for p in data_dir.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    if len(images) < 2:
        problems.append(f"{len(images)} image(s), need June 26 and June 28")
    lines: List[str] = []
    for p in [sources, *data_dir.rglob("*.csv"), *data_dir.rglob("*.json")]:
        if p.is_file() and p.stat().st_size < 2_000_000:
            lines += p.read_text(encoding="utf-8", errors="ignore").splitlines()
    for county, (before, after) in AQI.items():
        # Only lines (table rows, CSV rows) that name this county count for its values.
        own = " ".join(line for line in lines if county in line)
        found = {v for v in (before, after) if re.search(rf"(?<![\d.]){v}(?!\d|\.\d)", own)}
        if found != {before, after}:
            problems.append(f"{county} {before}->{after} not found on {county}'s own rows")
    audio = sorted(p.name for p in (data_dir / "audio").glob("*.wav")) if (data_dir / "audio").is_dir() else []
    if problems:
        return Check("openorbit assets", "FAIL", "; ".join(problems))
    return Check("openorbit assets", "PASS",
                 f"{len(images)} images, SOURCES.md, AQI values; audio clips: "
                 f"{', '.join(audio) or 'none (OS voice fallback)'}")


def check_view() -> Check:
    from signal2speech.app import PendingMapView, load_view   # the app's own probe
    view = load_view()
    stand_in = isinstance(view, PendingMapView)
    view.deleteLater()
    if stand_in:
        return Check("openorbit view", "SKIP", "signal2speech.openorbit.OpenOrbitView not built yet "
                                               "(#30); the app shows a labelled stand-in")
    return Check("openorbit view", "PASS", f"{type(view).__name__} loads")


def check_confirm_flow(diag: Diagnostics) -> List[Check]:
    """Scripted keyboard choose -> preview -> confirm, then choose -> cancel, with fake output."""
    from signal2speech.app import App
    from signal2speech.core import InputSources, Outcome, TargetIds

    view, speaker = _FakeView(), _FakeSpeaker()
    app = App(InputSources.KEYBOARD, view=view, speaker=speaker, echo=False, reopen_ms=60_000)
    diag.attach(app.handler, input_source=InputSources.KEYBOARD, gpype_source="none (keyboard)",
                connection="n/a (keyboard)", sink=app.sink)
    expected = next(c.spoken_text for c in app.choices if c.action_id == "compare_air_quality")
    checks = []

    t = time.monotonic()
    app.ask()
    preview = app.window.press_target(TargetIds.TARGET_2)
    quiet = not view.calls and not speaker.said
    confirm = app.window.press_target(TargetIds.TARGET_1)
    ms = (time.monotonic() - t) * 1000
    ok = (preview is Outcome.Previewed and quiet and confirm is Outcome.Confirmed
          and view.calls == ["compare_air_quality"] and speaker.said == [expected])
    checks.append(Check("confirm flow", "PASS" if ok else "FAIL",
                        f"preview {preview.value} (silent: {quiet}), confirm {confirm.value}, "
                        f"map {view.calls}, speech {len(speaker.said)} line(s), {ms:.0f} ms"))

    app.ask()
    p2 = app.window.press_target(TargetIds.TARGET_2)
    cancel = app.window.press_target(TargetIds.TARGET_2)
    extra = app.window.press_target(TargetIds.TARGET_1)       # nothing left to confirm
    ok = (p2 is Outcome.Previewed and cancel is Outcome.Cancelled and extra.rejected
          and view.calls == ["compare_air_quality"] and len(speaker.said) == 1)
    checks.append(Check("cancel flow", "PASS" if ok else "FAIL",
                        f"preview {p2.value}, cancel {cancel.value}, late key {extra.value}, "
                        f"outputs still {len(view.calls)} map / {len(speaker.said)} speech"))
    app.root.close()
    return checks


def check_gpype_stream(seconds: float = 0.6) -> Check:
    """A g.Pype Generator pipeline delivers samples (no hardware, labelled simulated)."""
    try:
        import gpype as gp
    except ImportError as err:
        return Check("g.Pype stream", "FAIL", f"import failed: {err}")
    p = gp.Pipeline()
    collector = gp.Collector()
    p.connect(gp.Generator(sampling_rate=250, channel_count=8, noise_amplitude=10.0), collector)
    t = time.monotonic()
    try:
        p.start()
        time.sleep(seconds)
        p.stop()
    finally:
        p.close()
    result = collector.result
    rows = 0 if result is None else int(result.data.shape[0])
    ms = (time.monotonic() - t) * 1000
    if rows == 0:
        return Check("g.Pype stream", "FAIL", f"Generator delivered no samples in {ms:.0f} ms")
    return Check("g.Pype stream", "PASS", f"Generator (simulated) {rows} samples in {ms:.0f} ms")


def run_smoke(mode: str = "dev", out: Callable[[str], None] = print) -> int:
    """Run every automatic check, print a report, and return 0 (pass) or 1 (fail)."""
    if mode not in ("dev", "judging"):
        raise ValueError("mode is 'dev' or 'judging'")
    if not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"   # no display needed (CI, SSH)
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication(sys.argv[:1])   # keep a reference

    diag = Diagnostics.to_file("smoke")
    diag.record("smoke_start", mode=mode, python=platform.python_version(),
                platform=platform.platform())
    def guarded(name: str, fn) -> List[Check]:
        try:                                    # a crashing check is a failing check
            result = fn()
            return result if isinstance(result, list) else [result]
        except Exception as err:
            return [Check(name, "FAIL", repr(err))]

    checks = guarded("environment", check_environment)
    if checks[0].status != "FAIL":
        checks += guarded("demo numbers", check_demo_numbers)
        checks += guarded("openorbit assets", check_assets)
        checks += guarded("openorbit view", check_view)
        checks += guarded("confirm flow", lambda: check_confirm_flow(diag))
        checks += guarded("g.Pype stream", check_gpype_stream)
    if mode == "judging":                       # the judging build must be fully green
        checks = [Check(c.name, "FAIL", c.detail + f" [{c.status} is a FAIL in judging mode]")
                  if c.status in ("SKIP", "WARN") else c for c in checks]

    out(f"Signal2Speech smoke ({mode}) · input labels: keyboard checks use keyboard, "
        f"the stream check uses Generator (simulated); no live EEG")
    for c in checks:
        diag.record("check", name=c.name, status=c.status, detail=c.detail)
        out(f"  {c.status:<5} {c.name:<17} {c.detail}")
    for m in MANUAL_CHECKS:
        out(f"  {'MANUAL':<5} {m}")
    counts = {s: sum(c.status == s for c in checks) for s in ("PASS", "WARN", "SKIP", "FAIL")}
    verdict = "FAIL" if counts["FAIL"] else "PASS"
    diag.record("smoke_end", verdict=verdict, **counts)
    diag.close()
    log = _rel(diag.path) if diag.path else "-"
    warn = f"{counts['WARN']} warn, " if counts["WARN"] else ""
    out(f"SMOKE {verdict}: {counts['PASS']} pass, {warn}{counts['SKIP']} skip, "
        f"{counts['FAIL']} fail · log {log}")
    qapp.processEvents()
    return 1 if counts["FAIL"] else 0
