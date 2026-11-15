"""Voice-guided test and data-collection session for an EEG board over LSL (#150, #170, #171).

One command runs the whole library session on the PiEEG Octopus 16. The wearer only listens and
does what the voice says; every timed part starts on a beep, so timing never depends on reading
speed. Raw data is recorded from the first second and saved after every phase.

    # PiEEG's starter running in another window:  python python_quickstart.py --lsl
    python -m signal2speech.eeg.board_session --input live --consent
    python -m signal2speech.eeg.board_session --self-test          # full dry run, no board

Phases:
  1. Contact      which pins are touching (repeats with spoken advice until enough are)
  2. Channel pick eyes open, then closed: which pins respond
  3. Calibration  open/closed blocks: sets the switch threshold
  4. Rest         eyes open: counts false triggers
  5. Switch test  close on the low beep, open on the high beep: hit rate and delay
  6. Scan test    the app reads numbered choices in turn; close your eyes on your target, then
                  once more to confirm: accuracy and seconds per selection

g.tec's g.Pype does the signal processing (the alpha switch, #47). The board is an amplifier.
Raw EEG is saved only with ``--consent`` (live) and never belongs in git.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from signal2speech.core import InputSources
from signal2speech.eeg import devices

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = ("Yes", "No", "Compare counties", "Satellite view")
NUMBER_WORDS = ("One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight")


# ── voice and beeps ─────────────────────────────────────────────────────────
class Voice:
    """Blocking speech and beeps. ``say`` returns only when the words are finished, so a beep
    that follows it marks a clean start. Falls back to printing if no voice is available."""

    def __init__(self, enabled: bool = True, rate: int = 3, simulate_timing: bool = False):
        self.enabled = enabled
        self.simulate_timing = simulate_timing      # silent, but take as long as speech would
        self._sapi = None
        self._beep = None
        self.log: List[str] = []
        if not enabled:
            return
        try:                                   # Windows: SAPI speaks every call reliably
            import win32com.client
            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self._sapi.Rate = rate
        except Exception:
            self._sapi = None
        try:
            import winsound
            self._beep = winsound.Beep
        except Exception:
            self._beep = None

    @property
    def audible(self) -> bool:
        return self._sapi is not None

    def say(self, text: str) -> None:
        self.log.append(text)
        print(f">>> {text}", flush=True)
        if not self.enabled and self.simulate_timing:
            time.sleep(self.estimate_s(text))
            return
        if self._sapi is not None:
            try:
                self._sapi.Speak(text)
                return
            except Exception:
                self._sapi = None
        if self.enabled:
            try:                               # other platforms: a fresh engine per utterance
                import pyttsx3
                eng = pyttsx3.init()
                eng.say(text)
                eng.runAndWait()
                eng.stop()
            except Exception:
                pass

    @staticmethod
    def estimate_s(text: str) -> float:
        """Roughly how long the Windows voice takes at our rate (measured: 1.1 to 2.2 s)."""
        return min(8.0, 0.9 + 0.045 * len(text))

    def beep(self, kind: str = "go") -> None:
        """'go' (low): do it now. 'stop' (high): stop. 'ok' (double): registered."""
        if not self.enabled:
            return
        tones = {"go": [(660, 180)], "stop": [(990, 180)], "ok": [(880, 90), (1320, 120)]}[kind]
        for freq, ms in tones:
            if self._beep is not None:
                try:
                    self._beep(freq, ms)
                    continue
                except Exception:
                    self._beep = None
            sys.stdout.write("\a")
            sys.stdout.flush()


# ── raw recording, independent of the processing pipeline ───────────────────
class Recorder:
    """Pulls raw samples straight from the LSL stream on its own thread, so the data is kept
    even if a later step fails."""

    def __init__(self, stream_name: str, timeout: float = 5.0):
        import pylsl

        found = pylsl.resolve_byprop("name", stream_name, 1, timeout)
        if not found:
            raise RuntimeError(f"LSL stream '{stream_name}' not found")
        info = max(found, key=lambda s: s.created_at())
        self.channels = info.channel_count()
        self.nominal_rate = float(info.nominal_srate())
        self._inlet = pylsl.StreamInlet(info, max_buflen=120)
        self._inlet.open_stream(timeout=timeout)
        self._clock = pylsl.local_clock
        self._rows: list = []
        self._times: list = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.last_rx = time.monotonic()
        self.started = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="board-recorder", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            chunk, stamps = self._inlet.pull_chunk(timeout=0.2)
            if chunk:
                with self._lock:
                    self._rows.extend(chunk)
                    self._times.extend(stamps)
                self.last_rx = time.monotonic()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._rows)

    def now(self) -> float:
        return float(self._clock())

    def silent_for(self) -> float:
        return time.monotonic() - self.last_rx

    def block(self, start: int, end: Optional[int] = None) -> np.ndarray:
        with self._lock:
            rows = self._rows[start:end]
        return np.asarray(rows, dtype=float).reshape(-1, self.channels)

    def measured_rate(self) -> float:
        elapsed = max(1e-6, self.last_rx - self.started)
        return self.count / elapsed

    def save(self, path: Path) -> None:
        with self._lock:
            eeg = np.asarray(self._rows, dtype=np.float32).reshape(-1, self.channels)
            stamps = np.asarray(self._times, dtype=np.float64)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, eeg=eeg, lsl_time=stamps)
        tmp.replace(path)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        try:
            self._inlet.close_stream()
        except Exception:
            pass


# ── pure logic, unit-tested without hardware ────────────────────────────────
#: The measured delay runs from a beep to the switch firing, so it already includes the
#: wearer's reaction time. Looking back by exactly that much lands on the instant the choice
#: began, and timing jitter could tip it into the previous choice. Nobody reacts to a choice
#: before hearing it, so lean this far towards the later one.
GRACE_S = 0.5


def attribute(edge_t: float, highlights: Sequence[Tuple[float, str]], latency_s: float,
              grace_s: float = GRACE_S) -> Optional[str]:
    """Which option was the wearer answering? The switch fires ``latency_s`` after the wearer
    hears what they want (reaction plus detection), so look back by that much."""
    decided = edge_t - latency_s + grace_s
    chosen = None
    for start, option in highlights:
        if start <= decided:
            chosen = option
        else:
            break
    return chosen if chosen is not None else (highlights[0][1] if highlights else None)


def spoken_option(index: int, option: str) -> str:
    return f"{NUMBER_WORDS[index]}: {option}."


@dataclass
class Verdict:
    ready: bool
    reasons: List[str] = field(default_factory=list)


def judge(report: dict) -> Verdict:
    """Is the eyes-closed switch good enough to use live? Strict on purpose."""
    reasons = []
    rest = report.get("rest", {})
    if rest.get("false_triggers", 1) > 0:
        reasons.append(f"{rest.get('false_triggers')} false trigger(s) during eyes-open rest")
    sw = report.get("switch_test", {})
    if sw.get("cued", 0) < 3 or sw.get("hits", 0) < sw.get("cued", 1):
        reasons.append(f"switch test caught {sw.get('hits', 0)} of {sw.get('cued', 0)} closures")
    if sw.get("extra_triggers", 0) > 0:
        reasons.append(f"{sw.get('extra_triggers')} extra trigger(s) in the switch test")
    scan = report.get("scan_test", {})
    if scan.get("trials"):
        if scan.get("correct", 0) < scan.get("trials"):
            reasons.append(f"scan test picked the right choice {scan.get('correct')} of "
                           f"{scan.get('trials')} times")
    if "calibration" not in report:
        reasons.append("calibration did not finish")
    return Verdict(not reasons, reasons)


class SessionAbort(RuntimeError):
    """The session can't continue. Whatever was recorded is still saved."""


# ── simulated wearer for the dry run ────────────────────────────────────────
class SimWearer:
    """Opens and closes the self-test stream's 'eyes' the way a person would: a reaction delay
    after each cue."""

    def __init__(self, publisher, reaction_s: float = 0.45, jitter_s: float = 0.0, seed: int = 0):
        import random

        self.pub, self._base, self._jitter = publisher, reaction_s, jitter_s
        self._rng = random.Random(seed)
        self._timers: List[threading.Timer] = []

    @property
    def reaction(self) -> float:
        """This reaction's delay: people aren't metronomes."""
        return self._base + self._rng.uniform(0.0, self._jitter)

    def _later(self, delay: float, fn: Callable[[], None]) -> None:
        t = threading.Timer(delay, fn)
        t.daemon = True
        self._timers.append(t)
        t.start()

    def close(self, hold_s: Optional[float] = None) -> None:
        delay = self.reaction
        self._later(delay, self.pub.close_eyes)
        if hold_s is not None:
            self._later(delay + hold_s, self.pub.open_eyes)

    def open(self) -> None:
        self._later(self.reaction, self.pub.open_eyes)

    def cancel(self) -> None:
        for t in self._timers:
            t.cancel()
        self.pub.open_eyes()


class NoWearer:
    """A real person is wearing the board: nothing to simulate."""
    def close(self, hold_s: Optional[float] = None) -> None: ...
    def open(self) -> None: ...
    def cancel(self) -> None: ...


# ── the session ─────────────────────────────────────────────────────────────
@dataclass
class Options:
    block_s: float = 7.0            # seconds per eyes-open or eyes-closed block
    settle_s: float = 2.0           # start of each block that doesn't count: reaction time, and
                                    # the alpha rhythm takes a moment to rise or fall
    calib_reps: int = 3
    rest_s: float = 30.0
    switches: int = 5
    scan_trials: int = 4
    dwell_s: float = 1.2            # silence after each spoken choice
    confirm_s: float = 5.0
    min_good_pins: int = 3
    channels: Optional[List[int]] = None
    record: bool = True


class BoardSession:
    def __init__(self, relay, device: devices.Device, label: str, input_source: str,
                 opts: Options, voice: Voice, wearer, out_dir: Path, make_source):
        self.relay, self.device, self.label = relay, device, label
        self.input_source, self.opts, self.voice, self.wearer = input_source, opts, voice, wearer
        self.out_dir, self._make_source = out_dir, make_source
        self.rec = Recorder(relay.name)
        self.rate = float(relay.rate)
        self.events: List[dict] = []
        self.report: dict = {"label": label, "device": device.key, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
        self.ac = None
        self.app = None
        self.pick: Optional[devices.ChannelPick] = None
        self.latency_s = 1.3

    # -- helpers --
    def mark(self, name: str, **extra) -> dict:
        e = {"event": name, "t": round(time.monotonic(), 4), "lsl_time": round(self.rec.now(), 4),
             "sample": self.rec.count, **extra}
        self.events.append(e)
        return e

    def cue(self, name: str, text: Optional[str] = None, beep: Optional[str] = "go", **extra) -> dict:
        """Speak, then beep. The event is stamped at the beep: that's when the timed part starts."""
        if text:
            self.voice.say(text)
        if beep:
            self.voice.beep(beep)
        return self.mark(name, **extra)

    def wait(self, seconds: float) -> np.ndarray:
        """Wait while keeping Qt alive. Returns alpha-power rows once the switch exists."""
        if self.rec.silent_for() > 3.0:
            raise SessionAbort("No data from the board for 3 seconds. Is it still connected "
                               "(LED solid) and PiEEG's script still running?")
        if self.ac is not None:
            return self.ac.collect(seconds)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.app is not None:
                self.app.processEvents()
            time.sleep(0.01)
        return np.array([])

    def save(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "events.json").write_text(json.dumps(self.events, indent=1), encoding="utf-8")
        (self.out_dir / "report.json").write_text(json.dumps(self.report, indent=1), encoding="utf-8")
        if self.opts.record:
            self.rec.save(self.out_dir / "eeg.npz")

    # -- phases --
    def contact(self) -> None:
        for attempt in range(1, 5):
            self.wait(4.0)
            n = int(4.0 * self.rate)
            block = self.rec.block(max(0, self.rec.count - n))
            if len(block) < self.rate:
                raise SessionAbort("The stream is there but almost no samples arrived.")
            ok = devices.contact_ok(block, self.rate, self.device.contact_rms_uv)
            rms = devices.band_rms(block, self.rate)
            good = int(ok.sum())
            self.report["contact"] = {"good_pins": good, "of": int(len(ok)), "attempt": attempt,
                                      "rms_uv": [round(float(r), 1) for r in rms],
                                      "measured_rate": round(self.rec.measured_rate(), 1)}
            print(f"contact: {good} of {len(ok)} pins good; measured {self.rec.measured_rate():.1f} "
                  f"samples per second", flush=True)
            self.mark("contact", good=good, attempt=attempt)
            if good >= self.opts.min_good_pins:
                return
            if attempt == 4:
                break
            self.voice.say(f"Only {good} pins are touching. Part the hair, press the sensor "
                           "straight down, and hold it snug. Checking again.")
        if self.report["contact"]["good_pins"] == 0:
            raise SessionAbort("No pin has good contact after four tries.")
        self.voice.say("Contact is weak, but continuing.")

    def channel_pick(self) -> None:
        if self.opts.channels or self.device.fixed_montage:
            self.pick = devices.resolve_alpha_channels(self.device, self.opts.channels)
        else:
            T = self.opts.block_s
            for attempt in (1, 2):
                self.voice.say("First, keep your eyes open and look straight ahead, until the next beep.")
                a = self.cue("pick_open")["sample"]
                self.wearer.open()
                self.wait(T)
                self.voice.say("Now close your eyes and relax, until the high beep.")
                b = self.cue("pick_closed")["sample"]
                self.wearer.close()
                self.wait(T)
                c = self.cue("pick_end", beep="stop")["sample"]
                self.wearer.open()
                self.voice.say("Open your eyes.")
                skip = int(self.opts.settle_s * self.rate)     # drop the settling time
                try:
                    self.pick = devices.resolve_alpha_channels(
                        self.device, None, self.rec.block(a + skip, b), self.rec.block(b + skip, c),
                        self.rate)
                    break
                except devices.NoAlphaResponse as err:
                    print(f"channel pick, try {attempt}: {err}", flush=True)
                    if attempt == 2:
                        raise SessionAbort(str(err))
                    self.voice.say("I could not see a change. Move the sensor a little lower on "
                                   "the back of the head, and relax. Trying once more.")
        self.report["channels_1based"] = [c + 1 for c in self.pick.channels]
        self.report["channel_ratios"] = [round(r, 2) for r in self.pick.ratios]
        print(f"using {self.device.describe_channels(self.pick.channels)}: {self.pick.reason}", flush=True)

    def build_switch(self) -> None:
        from signal2speech.core import SelectionHandler
        from signal2speech.eeg import alpha_confirm as alpha

        class _Sink:
            def execute(self, action) -> None: ...

        self.ac = alpha.AlphaConfirm(SelectionHandler(_Sink()), input_source=self.input_source,
                                     source=self._make_source(), channels=list(self.pick.channels),
                                     sampling_rate=self.rate, auto=False)
        self.ac.start()
        self.wait(2.0)

    def calibrate(self) -> None:
        from signal2speech.eeg import alpha_confirm as alpha

        T, settle = self.opts.block_s, self.opts.settle_s
        self.voice.say(f"Calibration. {self.opts.calib_reps} rounds. Eyes open on the low beep, "
                       "eyes closed on the high beep.")
        cal = None
        for attempt in (1, 2):
            opens, closeds = [], []
            for rep in range(self.opts.calib_reps):
                self.cue("cal_open", "Eyes open.", rep=rep, attempt=attempt)
                self.wearer.open()
                self.wait(settle)
                opens.extend(self.wait(T - settle).tolist())
                self.cue("cal_closed", "Eyes closed.", beep="stop", rep=rep, attempt=attempt)
                self.wearer.close()
                self.wait(settle)
                closeds.extend(self.wait(T - settle).tolist())
            self.cue("cal_end", "Open your eyes.", beep=None)
            self.wearer.open()
            try:
                cal = self.ac.calibrate(opens, closeds)
                break
            except alpha.CalibrationError as err:
                print(f"calibration, try {attempt}: {err}", flush=True)
                self.report.setdefault("calibration_failures", []).append(str(err))
                if attempt == 2:
                    raise SessionAbort(f"Calibration failed twice: {err}")
                self.wait(2.0)
                self.voice.say("The difference was too small. This time, close your eyes fully, "
                               "let your face go slack, and stay still. Trying again.")
        self.report["calibration"] = {"ratio": round(cal.ratio, 2), "level": round(cal.level, 3),
                                      "release": round(cal.release, 3), "attempts": attempt,
                                      "open_rows": len(opens), "closed_rows": len(closeds)}
        print(f"calibration: closed is x{cal.ratio:.1f} the open level", flush=True)
        self.wait(2.0)

    def rest(self) -> None:
        self.voice.say(f"Rest for {self.opts.rest_s:g} seconds. Keep your eyes open. Blink normally.")
        before = self.ac.edge_count
        self.cue("rest_start")
        self.wait(self.opts.rest_s)
        self.cue("rest_end", beep="stop")
        n = self.ac.edge_count - before
        self.report["rest"] = {"seconds": self.opts.rest_s, "false_triggers": n}
        print(f"rest: {n} false trigger(s) in {self.opts.rest_s:g} s", flush=True)

    def _wait_edge(self, since_count: int, timeout: float) -> Optional[float]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.wait(0.05)
            new = self.ac.edges_since(since_count)
            if new:
                return new[0]
        return None

    def _wait_open(self, timeout: float = 4.0) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end and self.ac.state == 1:
            self.wait(0.05)
        self.wait(1.2)                                         # settle with eyes open

    def switch_test(self) -> None:
        self.voice.say("Switch test. Each time you hear the low beep, close your eyes. "
                       "Open them on the high beep.")
        hits, latencies, extra = 0, [], 0
        import random
        rng = random.Random(1)
        for k in range(self.opts.switches):
            idle = self.ac.edge_count
            self.wait(rng.uniform(2.0, 3.5))
            extra += self.ac.edge_count - idle                 # triggers with eyes open
            count = self.ac.edge_count
            t0 = self.cue("switch_close", k=k)["t"]
            self.wearer.close()
            edge = self._wait_edge(count, 4.0)
            self.cue("switch_open", beep="stop", k=k, detected=edge is not None)
            self.wearer.open()
            if edge is not None:
                hits += 1
                latencies.append(edge - t0)
            self._wait_open()
        if latencies:
            self.latency_s = float(statistics.median(latencies))
        self.report["switch_test"] = {
            "cued": self.opts.switches, "hits": hits, "extra_triggers": extra,
            "latency_s": [round(x, 2) for x in latencies],
            "median_latency_s": round(self.latency_s, 2) if latencies else None}
        print(f"switch test: {hits}/{self.opts.switches} closures caught, median delay "
              f"{self.latency_s:.2f} s, {extra} extra", flush=True)

    def scan_test(self) -> None:
        opts = list(OPTIONS)
        self.voice.say(f"Choice test. I will read {len(opts)} numbered choices, again and again. "
                       "As soon as you hear your target, close your eyes until the double beep, "
                       "then open them. I will say what you picked and ask: confirm? "
                       "Close your eyes again to confirm, or keep them open to cancel.")
        trials = []
        for i in range(self.opts.scan_trials):
            target = opts[(i * 3 + 1) % len(opts)]             # 2, 1, 4, 3: every position once
            self.voice.say(f"Your target is {NUMBER_WORDS[opts.index(target)]}: {target}.")
            self.wait(1.0)
            count, highlights, selected, edge = self.ac.edge_count, [], None, None
            t_start = self.cue("scan_start", beep="go", trial=i, target=target)["t"]
            for step in range(len(opts) * 2):                  # at most two passes
                option = opts[step % len(opts)]
                highlights.append((self.mark("scan_offer", trial=i, option=option)["t"], option))
                if option == target:
                    self.wearer.close()
                self.voice.say(spoken_option(opts.index(option), option))
                edge = self._wait_edge(count, self.opts.dwell_s)
                if edge is None and self.ac.edges_since(count):
                    edge = self.ac.edges_since(count)[0]
                if edge is not None:
                    selected = attribute(edge, highlights, self.latency_s)
                    break
            self.cue("scan_selected", beep="ok", trial=i, selected=selected)
            self.wearer.open()
            t_select = (edge - t_start) if edge is not None else None
            confirmed = False
            if selected is not None:
                self._wait_open()                              # the double beep means: open
                count = self.ac.edge_count
                self.voice.say(f"{selected}. Confirm?")
                t_c = self.cue("confirm_window", trial=i)["t"]
                if selected == target:
                    self.wearer.close(hold_s=2.2)
                c_edge = self._wait_edge(count, self.opts.confirm_s)
                confirmed = c_edge is not None
                self.cue("confirm_result", "Confirmed." if confirmed else "Cancelled.",
                         beep="ok" if confirmed else "stop", trial=i, confirmed=confirmed)
                self.wearer.open()
                self._wait_open()
                total = (time.monotonic() - t_start)
            else:
                self.voice.say("No choice was made.")
                total = time.monotonic() - t_start
            trials.append({"target": target, "selected": selected, "correct": selected == target,
                           "confirmed": confirmed,
                           "seconds_to_select": round(t_select, 2) if t_select else None,
                           "seconds_total": round(total, 2)})
            print(f"scan {i + 1}: target {target!r}, picked {selected!r}, confirmed {confirmed}, "
                  f"{total:.1f} s", flush=True)
        done = [t for t in trials if t["correct"] and t["confirmed"]]
        self.report["scan_test"] = {
            "options": opts, "trials": len(trials),
            "correct": sum(t["correct"] for t in trials),
            "confirmed_correct": len(done),
            "mean_seconds_to_select": round(statistics.mean(
                [t["seconds_to_select"] for t in trials if t["seconds_to_select"]]), 2)
            if any(t["seconds_to_select"] for t in trials) else None,
            "mean_seconds_total": round(statistics.mean([t["seconds_total"] for t in done]), 2)
            if done else None,
            "detail": trials}

    def run(self) -> int:
        from PySide6.QtCore import QCoreApplication

        self.app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
        phases = [("contact", self.contact), ("channel pick", self.channel_pick),
                  ("switch", self.build_switch), ("calibration", self.calibrate),
                  ("rest", self.rest), ("switch test", self.switch_test),
                  ("scan test", self.scan_test)]
        code = 0
        try:
            self.voice.say("Starting. Sit comfortably and keep still. Follow my voice.")
            self.mark("session_start")
            for name, phase in phases:
                print(f"--- {name} ---", flush=True)
                phase()
                self.report.setdefault("phases_done", []).append(name)
                self.save()
        except SessionAbort as err:
            self.report["aborted"] = str(err)
            print(f"STOPPED: {err}", flush=True)
            self.voice.say("The session stopped early. What was recorded is saved.")
            code = 2
        except KeyboardInterrupt:
            self.report["aborted"] = "interrupted by the operator"
            print("STOPPED by the operator.", flush=True)
            code = 130
        finally:
            self.wearer.cancel()
            verdict = judge(self.report)
            self.report["ready_for_live_confirm"] = verdict.ready
            self.report["reasons"] = verdict.reasons
            self.report["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.report["seconds"] = round(time.monotonic() - self.rec.started, 1)
            self.mark("session_end")
            try:
                self.save()
            finally:
                if self.ac is not None:
                    self.ac.close()
                self.rec.stop()
        if code == 0:
            self.voice.say("All done. Thank you." if verdict.ready else
                           "All done. Some checks did not pass. Thank you.")
        print(json.dumps({"summary": {k: v for k, v in self.report.items() if k != "contact"}}), flush=True)
        print(f"saved to {self.out_dir}" + ("" if self.opts.record else " (report only, no raw EEG)"),
              flush=True)
        return code if code else (0 if verdict.ready else 1)


def verify_recording(folder: Path, say=print) -> bool:
    """Is a saved session complete and usable? Run this before leaving the board.

    Recomputes, from the raw file alone, how much the alpha rose in each eyes-closed block."""
    folder = Path(folder)
    missing = [n for n in ("report.json", "events.json") if not (folder / n).is_file()]
    if missing:
        say(f"NOT USABLE: missing {', '.join(missing)} in {folder}")
        return False
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    events = json.loads((folder / "events.json").read_text(encoding="utf-8"))
    say(f"{report.get('label')} | started {report.get('started')} | {report.get('seconds')} s | "
        f"phases: {', '.join(report.get('phases_done', [])) or 'none'}")
    if report.get("aborted"):
        say(f"stopped early: {report['aborted']}")
    raw = folder / "eeg.npz"
    if not raw.is_file():
        say("no raw EEG was saved (run with --consent to record it). Report only.")
        return False
    data = np.load(raw)
    eeg, stamps = data["eeg"], data["lsl_time"]
    if len(eeg) < 250 or len(eeg) != len(stamps):
        say(f"NOT USABLE: {len(eeg)} samples, {len(stamps)} time stamps")
        return False
    span = float(stamps[-1] - stamps[0])
    rate = (len(eeg) - 1) / span if span > 0 else 0.0
    gaps = int((np.diff(stamps) > 0.5).sum())
    say(f"raw EEG: {len(eeg)} samples x {eeg.shape[1]} channels, {span:.0f} s, "
        f"{rate:.1f} samples per second, {gaps} gap(s) over half a second")
    chans = [c - 1 for c in report.get("channels_1based", [])] or list(range(eeg.shape[1]))
    nominal = 250.0
    settle = int(2.0 * nominal)
    ratios = []
    cal = [e for e in events if e["event"] in ("cal_open", "cal_closed", "cal_end")]
    for a, b, c in zip(cal, cal[1:], cal[2:]):
        if a["event"] == "cal_open" and b["event"] == "cal_closed":
            o = eeg[a["sample"] + settle:b["sample"], :][:, chans]
            cl = eeg[b["sample"] + settle:c["sample"], :][:, chans]
            if len(o) >= nominal and len(cl) >= nominal:
                ratios.append(float(devices.alpha_power(cl, nominal).mean()
                                    / max(devices.alpha_power(o, nominal).mean(), 1e-12)))
    if ratios:
        say("eyes-closed alpha vs eyes-open, per calibration round: "
            + ", ".join(f"x{r:.1f}" for r in ratios))
    else:
        say("no complete calibration round in the recording")
    ok = bool(ratios) and gaps == 0
    say("USABLE: the recording is complete." if ok else
        "CHECK: the recording has gaps or no calibration round. Consider recording again.")
    return ok


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.board_session",
                                description="Voice-guided test and recording session (#150)")
    p.add_argument("--input", choices=["live", "simulated"])
    p.add_argument("--self-test", action="store_true", help="full dry run on our simulated stream")
    p.add_argument("--self-test-rate", type=float, default=250.0)
    p.add_argument("--self-test-closed-uv", type=float, default=25.0,
                   help="self-test: eyes-closed alpha size (try 4 for a wearer with almost no response)")
    p.add_argument("--self-test-reaction", type=float, nargs=2, default=[0.45, 0.0],
                   metavar=("BASE", "JITTER"), help="self-test: reaction time and its random extra")
    p.add_argument("--self-test-drop-after", type=float, default=None,
                   help="self-test: the board 'disconnects' after this many seconds")
    p.add_argument("--stream", default="Octopus16")
    p.add_argument("--any-host", action="store_true")
    p.add_argument("--consent", action="store_true",
                   help="the wearer agreed to their raw EEG being recorded (needed to save it live)")
    p.add_argument("--channels", default="auto")
    p.add_argument("--quick", action="store_true", help="shorter blocks and fewer trials")
    p.add_argument("--no-voice", action="store_true", help="print the cues, don't speak or beep")
    p.add_argument("--out", default=None, help="folder for this session (default: recordings/...)")
    p.add_argument("--verify", metavar="FOLDER", default=None,
                   help="check a saved session is complete and usable, then exit")
    p.add_argument("--fast-silent", action="store_true", help=argparse.SUPPRESS)   # tests only
    args = p.parse_args(argv)
    if args.verify:
        return 0 if verify_recording(Path(args.verify)) else 1
    if args.self_test:
        args.input = "simulated"
    if args.input is None:
        p.error("say what is publishing the stream: --input live, --input simulated, or --self-test")

    import gpype as gp  # noqa: F401

    from signal2speech.eeg import lsl_source, pieeg_lsl

    opts = Options()
    if args.quick:
        opts = Options(block_s=6.0, calib_reps=2, rest_s=15.0, switches=3, scan_trials=2)
    live = args.input == "live"
    opts.record = (not live) or args.consent
    publisher = relay = None
    try:
        if args.self_test:
            publisher = lsl_source.SelfTestStream(actual_rate=args.self_test_rate,
                                                  alpha_closed_uv=args.self_test_closed_uv).start()
            args.stream = lsl_source.SELF_TEST_NAME
            if args.self_test_drop_after:
                t = threading.Timer(args.self_test_drop_after, publisher.stop)
                t.daemon = True
                t.start()
        try:
            info = lsl_source.find_stream(args.stream, any_host=args.any_host)
        except pieeg_lsl.PiEEGSetupError as err:
            print(str(err).replace("--sim --lsl", "--lsl   (add --sim for PiEEG's simulator)"), flush=True)
            return 1
        relay = pieeg_lsl.PiEEGRelay(info).start()
        device = devices.detect(stream_name=info.name(), channel_count=info.channel_count(),
                                rate=info.nominal_srate())
        if args.self_test:
            device = devices.PIEEG_OCTOPUS16
        label = lsl_source.live_label(device) if live else lsl_source.SIMULATED_LABEL
        opts.channels = lsl_source.parse_channels(args.channels, relay.channels)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = Path(args.out) if args.out else ROOT / "recordings" / f"{stamp}_{device.key}_{args.input}"
        print(f"input: {label}\ndevice: {device.name}, {relay.channels} channels at {relay.rate:g} Hz\n"
              f"saving to: {out}", flush=True)
        if live:
            print(lsl_source.SAFETY, flush=True)
            if not args.consent:
                print("No --consent: the session runs, but raw EEG is NOT saved (report only).", flush=True)
        silent = args.no_voice or args.fast_silent
        voice = Voice(enabled=not silent, simulate_timing=args.no_voice and not args.fast_silent)
        wearer = (SimWearer(publisher, args.self_test_reaction[0], args.self_test_reaction[1])
                  if publisher is not None else NoWearer())
        session = BoardSession(
            relay, device, label, InputSources.LIVE_EEG if live else InputSources.SIMULATED, opts,
            voice, wearer, out,
            make_source=lambda: pieeg_lsl.make_source(relay.name, relay.channels, relay.rate))
        session.report["consent"] = bool(args.consent) if live else "n/a (simulated)"
        code = session.run()
        if opts.record:
            verify_recording(out)
        return code
    finally:
        if relay is not None:
            relay.stop()
        if publisher is not None:
            publisher.stop()
        relay = publisher = None
        import gc
        gc.collect()


if __name__ == "__main__":
    sys.exit(main())
