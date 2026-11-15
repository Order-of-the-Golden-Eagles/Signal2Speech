"""Soak test for the judging hour (#165). Not part of the normal pytest run.

    python tests/soak/soak.py --minutes 60 --p300 --kill-at 30       # the judging-laptop run
    python tests/soak/soak.py --minutes 5 --windowed                  # a quick check

It starts the crash-safe launcher (#133, ``tools/demo_launcher.py``) on the real app with its own
simulated input (``--input simulated``, plus ``--p300`` for the live code path on the Generator).
It feeds a script long enough for the whole run: choose, preview, then confirm or cancel, over
and over. While it runs it:

- reads the app's transcript as it streams, and stamps each line when it arrives;
- checks that every confirm produced exactly one map action and one spoken line, and that no
  output appeared without a confirm (a double output);
- samples the app's memory (RSS) every minute with psutil;
- optionally kills the app once on purpose (``--kill-at``) and times how fast the launcher brings
  it back.

At the end it stops the launcher and writes ``logs/soak-<time>.md`` (the numbers and the exact
command) and ``logs/soak-<time>.log`` (the raw transcript). Both stay out of git. Every input is
labelled Simulated: this tests the app, not a brain.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
# Simulated classes, two per round: the tile to choose, then 1 = confirm or 2 = cancel.
# With --p300, "cancel" means the synthetic wearer keeps their eyes open and the confirm
# timeout clears the round, which is what really happens when a wearer doesn't confirm.
ROUND_PATTERN = ((2, 1), (1, 1), (2, 2), (1, 1))      # 3 confirms and 1 cancel per 4 rounds
LINE = re.compile(r"^(\d\d:\d\d:\d\d)  (.*)$")
STARTUP_S = 90.0        # a new app process imports, calibrates and settles; don't judge memory then
STALL_S = 180.0         # no round outcome for this long (outside a restart) means the app stalled
SLOWER = 1.5            # the last 10 minutes may be at most this much slower than the first 10


# ── Parsing (pure, unit-tested) ──────────────────────────────
@dataclass
class Tally:
    """What the transcript says happened. Times are the soak's own clock at arrival."""
    chooses: Dict[str, float] = field(default_factory=dict)       # round id -> opened at
    selection_s: List[Tuple[float, float]] = field(default_factory=list)  # (at, choose->preview)
    confirm_map_ms: List[Tuple[float, float]] = field(default_factory=list)
    previews: int = 0
    confirms: int = 0
    cancels: int = 0                 # an explicit cancel, or a round cleared by the timeout
    maps: int = 0
    speaks: int = 0
    double_outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    app_starts: List[float] = field(default_factory=list)
    app_exits: List[Tuple[float, str]] = field(default_factory=list)
    last_outcome: float = 0.0       # when the last preview, confirm, or cancel arrived
    _pending_maps: int = 0
    _pending_speaks: int = 0

    def feed(self, at: float, raw: str) -> None:
        text = raw.rstrip("\n")
        if text.startswith("[launcher]"):
            body = text.split("  ", 1)[-1]
            if "app exited with code" in body or "closed normally" in body:
                self.app_exits.append((at, body))
            return
        if "Traceback (most recent call last)" in text or text.startswith("Fatal Python error"):
            self.errors.append(text)
            return
        m = LINE.match(text)
        if not m:
            return
        body = m.group(2)
        if body.startswith("input: "):
            self.app_starts.append(at)
            self._pending_maps = self._pending_speaks = 0     # a restart: nothing carries over
        elif body.startswith("round ") and " choose:" in body:
            self.chooses[body.split()[1]] = at
        elif body.startswith("Previewed: "):
            self.previews += 1
            self.last_outcome = at
            rnd = body.split()[-1].split("->")[0]
            if rnd in self.chooses:
                self.selection_s.append((at, at - self.chooses.pop(rnd)))
        elif body.startswith("OUTPUT map: "):
            self.maps += 1
            self._pending_maps += 1
        elif body.startswith("OUTPUT speak: "):
            self.speaks += 1
            self._pending_speaks += 1
        elif body.startswith("Confirmed: "):
            self.confirms += 1
            self.last_outcome = at
            if self._pending_maps > 1 or self._pending_speaks != 1:
                self.double_outputs.append(
                    f"{body}: {self._pending_maps} map action(s), {self._pending_speaks} spoken line(s)")
            self._pending_maps = self._pending_speaks = 0
        elif body.startswith("Cancelled: ") or body.startswith("cleared (timeout)"):
            self.cancels += 1
            self.last_outcome = at
            self._check_no_output(body)
        elif body.startswith("timing: confirm→map "):
            try:
                self.confirm_map_ms.append((at, float(body.split()[-2])))
            except ValueError:
                pass

    def _check_no_output(self, body: str) -> None:
        if self._pending_maps or self._pending_speaks:
            self.double_outputs.append(f"{body}: output without a confirm")
            self._pending_maps = self._pending_speaks = 0

    def finish(self) -> None:
        """Output still waiting for its 'Confirmed' line when the run stopped is a cut, not a
        double output, unless there's more than one of a kind."""
        if self._pending_maps > 1 or self._pending_speaks > 1:
            self.double_outputs.append("at the end: more than one output without a confirm")


def script_for(minutes: float, p300: bool) -> str:
    """A --sim script that won't run out: rounds at a pace faster than the app can go."""
    per_round_s = 8.0 if p300 else 4.0                  # deliberately optimistic
    rounds = int(minutes * 60 / per_round_s) + 8
    picks = [str(c) for i in range(rounds) for c in ROUND_PATTERN[i % len(ROUND_PATTERN)]]
    return ",".join(picks)


def window_median(points: Sequence[Tuple[float, float]], start: float, end: float) -> Optional[float]:
    vals = [v for t, v in points if start <= t < end]
    return statistics.median(vals) if vals else None


# ── The run ──────────────────────────────────────────────────
@dataclass
class Sample:
    at: float
    pid: int
    rss_mb: float


class Soak:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.report_path = ROOT / "logs" / f"soak-{stamp}.md"
        self.log_path = ROOT / "logs" / f"soak-{stamp}.log"
        self.tally = Tally()
        self.samples: List[Sample] = []
        self.kill: Optional[dict] = None
        self.kill_pending: Optional[dict] = None
        self.stopping_at: Optional[float] = None
        self.interrupted = False
        self._log_open = False
        self._lock = threading.Lock()
        app_args = ["--input", "simulated", "--sim", script_for(args.minutes, args.p300)]
        if args.p300:
            app_args.append("--p300")
        if args.mute:
            app_args.append("--mute")
        if self._app_supports("--no-attract"):
            app_args.append("--no-attract")             # the idle loop (#193) would hide rounds
        self.cmd = [sys.executable, str(ROOT / "tools" / "demo_launcher.py"),
                    "--max-restarts", str(args.max_restarts)]
        if args.windowed:
            self.cmd.append("--windowed")
        self.cmd += ["--", *app_args]
        self.t0 = time.monotonic()                      # after the help check: the run starts now

    @staticmethod
    def _app_supports(flag: str) -> bool:
        try:
            out = subprocess.run([sys.executable, "-m", "signal2speech.app", "--help"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=180).stdout
        except (subprocess.SubprocessError, OSError) as err:
            print(f"soak: couldn't read the app's --help ({type(err).__name__}); "
                  f"running without {flag}", flush=True)
            return False
        return flag in out

    def now(self) -> float:
        return time.monotonic() - self.t0

    def shown_command(self) -> str:
        """The launcher command as a person would type it: no long script, no home folder."""
        script = self.cmd[self.cmd.index("--sim") + 1]
        shown = {sys.executable: "python", str(ROOT / "tools" / "demo_launcher.py"):
                 "tools/demo_launcher.py", script: f"<{len(script.split(','))} picks>"}
        return " ".join(shown.get(c, c) for c in self.cmd)

    def _read(self, stream, log) -> None:
        for raw in iter(stream.readline, ""):
            at = self.now()
            with self._lock:
                if self._log_open:
                    log.write(f"{at:9.2f}  {raw}")
                self.tally.feed(at, raw)

    def _app_process(self, launcher):
        """The app's own interpreter. On Windows a venv's python.exe is a small launcher that
        starts the real interpreter as its child, with the same command line, so take the
        innermost match: that's where the memory is, and what has to die in the kill test."""
        import psutil
        try:
            matches = [c for c in psutil.Process(launcher.pid).children(recursive=True)
                       if "signal2speech.app" in " ".join(c.cmdline())]
            pids = {m.pid for m in matches}
            inner = [m for m in matches
                     if not any(c.pid in pids for c in m.children(recursive=True))]
            return inner[0] if inner else None
        except psutil.Error:
            return None

    def run(self) -> int:
        import psutil

        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        print(f"soak: {self.shown_command()}\nsoak: {self.args.minutes:g} min, report "
              f"{self.report_path.relative_to(ROOT)}", flush=True)
        with self.log_path.open("w", encoding="utf-8") as log:
            self._log_open = True
            launcher = subprocess.Popen(self.cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                        errors="replace", bufsize=1)
            reader = threading.Thread(target=self._read, args=(launcher.stdout, log), daemon=True)
            reader.start()
            end = self.args.minutes * 60
            next_sample = 0.0
            try:
                while self.now() < end and launcher.poll() is None:
                    if self.now() >= next_sample:
                        proc = self._app_process(launcher)
                        if proc is not None:
                            try:
                                self.samples.append(Sample(self.now(), proc.pid,
                                                           proc.memory_info().rss / 2**20))
                            except psutil.Error:
                                pass
                        next_sample = max(next_sample + self.args.sample_s, self.now())
                        self._progress()
                    self._kill_step(launcher)
                    time.sleep(0.2)
            except KeyboardInterrupt:
                self.interrupted = True                 # keep what was measured: write the report
                print("soak: stopped early (Ctrl+C); writing the report", flush=True)
            finally:
                self.stopping_at = self.now()
                self._stop(launcher)
                reader.join(timeout=15)
                with self._lock:
                    self._log_open = False
        with self._lock:
            self.tally.finish()
        self.report_path.write_text(self.report(launcher.returncode), encoding="utf-8")
        print(f"soak: wrote {self.report_path.relative_to(ROOT)}", flush=True)
        return 0 if self.passed() else 1

    def _progress(self) -> None:
        with self._lock:
            t = self.tally
            rss = f"{self.samples[-1].rss_mb:.0f} MB" if self.samples else "?"
            print(f"soak: {self.now() / 60:5.1f} min · {t.confirms} confirms · {t.cancels} cancels"
                  f" · {len(t.double_outputs)} double outputs · {len(t.app_exits)} exits · {rss}",
                  flush=True)

    def _kill_step(self, launcher) -> None:
        """The kill test, one step per loop pass, so sampling and progress carry on."""
        if self.args.kill_at is None or self.kill is not None:
            return
        if self.kill_pending is None:
            if self.now() < self.args.kill_at * 60:
                return
            proc = self._app_process(launcher)
            if proc is None:
                return                                  # not up yet (restarting): try next pass
            self.kill_pending = {"at_min": self.now() / 60, "pid": proc.pid,
                                 "process_back_s": None, "window_ready_s": None}
            print(f"soak: killing the app on purpose (pid {proc.pid})", flush=True)
            proc.kill()
            return
        k = self.kill_pending
        since = self.now() - k["at_min"] * 60
        if k["process_back_s"] is None:
            new = self._app_process(launcher)
            if new is not None and new.pid != k["pid"]:
                k["process_back_s"] = since
        if k["process_back_s"] is not None and k["window_ready_s"] is None:
            with self._lock:
                starts = [s for s in self.tally.app_starts if s > k["at_min"] * 60]
            if starts:
                k["window_ready_s"] = starts[0] - k["at_min"] * 60
        if k["window_ready_s"] is not None or since > 300:
            self.kill, self.kill_pending = k, None

    def _stop(self, launcher) -> None:
        import psutil
        if launcher.poll() is not None:
            return
        try:
            top = psutil.Process(launcher.pid)
            procs = top.children(recursive=True)
        except psutil.Error:
            return                                      # the launcher already went
        for p in [top, *procs]:                         # launcher first: it mustn't restart
            try:
                p.terminate()
            except psutil.Error:
                pass
        alive = psutil.wait_procs([*procs], timeout=10)[1]
        for p in alive:
            p.kill()
        try:
            launcher.wait(timeout=10)
        except subprocess.TimeoutExpired:
            launcher.kill()

    # ── Verdict and report ───────────────────────────────────
    def crashes(self) -> List[Tuple[float, str]]:
        """App exits other than the one we caused on purpose or by stopping the run."""
        exits = list(self.tally.app_exits)
        planned = self.kill or self.kill_pending
        if planned is not None:
            k = planned["at_min"] * 60
            exits = [(t, b) for t, b in exits if not (k <= t <= k + 10)]
        if self.stopping_at is not None:
            exits = [(t, b) for t, b in exits if t < self.stopping_at]
        return exits

    def memory(self) -> List[dict]:
        """Start vs end for each app process (a restart starts a new one), after its first
        two samples: start-up (imports, calibration) allocates and frees a lot."""
        by_pid: Dict[int, List[Sample]] = {}
        for s in self.samples:
            by_pid.setdefault(s.pid, []).append(s)
        runs = []
        for run in by_pid.values():
            settled = [s for s in run if s.at - run[0].at >= STARTUP_S]
            if len(settled) < 2:                        # too short to judge growth
                runs.append({"pid": run[0].pid, "samples": len(run), "start_mb": None,
                             "end_mb": run[-1].rss_mb, "max_mb": max(s.rss_mb for s in run),
                             "growth_mb": None, "from_min": run[0].at / 60,
                             "to_min": run[-1].at / 60})
                continue
            start, end = settled[0].rss_mb, settled[-1].rss_mb
            runs.append({"pid": run[0].pid, "samples": len(run), "start_mb": start,
                         "end_mb": end, "max_mb": max(s.rss_mb for s in run),
                         "growth_mb": end - start, "from_min": settled[0].at / 60,
                         "to_min": settled[-1].at / 60})
        return runs

    @staticmethod
    def stable(run: dict) -> bool:
        """True if stable, also when a process ran too briefly to judge (see the report)."""
        if run["growth_mb"] is None:
            return True
        return run["growth_mb"] <= max(50.0, 0.15 * run["start_mb"])

    def memory_ok(self) -> bool:
        return all(self.stable(r) for r in self.memory())

    def speed(self) -> Tuple[Optional[float], Optional[float]]:
        """Median selection time in the first and the last 10 minutes."""
        span = self.stopping_at if self.stopping_at is not None else self.now()
        return (window_median(self.tally.selection_s, 0.0, min(span, 600.0)),
                window_median(self.tally.selection_s, max(0.0, span - 600.0), span + 1))

    def problems(self) -> List[str]:
        """Every reason the run fails. Empty means PASS."""
        t, out = self.tally, []
        if t.double_outputs:
            out.append(f"{len(t.double_outputs)} double output(s)")
        if t.errors:
            out.append(f"{len(t.errors)} Python error(s)")
        if self.crashes():
            out.append(f"{len(self.crashes())} unplanned app exit(s)")
        if t.confirms == 0:
            out.append("no confirms at all")
        if not self.memory_ok():
            out.append("memory grew past the limit")
        span = self.stopping_at if self.stopping_at is not None else self.now()
        # 180 s covers the slowest normal gap: a restart plus its calibration (about 90 s).
        if t.confirms and span - t.last_outcome > STALL_S:
            out.append(f"no round finished in the last {span - t.last_outcome:.0f} s (stalled)")
        first, last = self.speed()
        if first and last and last > first * SLOWER:
            out.append(f"selection got slower: {first:.2f} s -> {last:.2f} s")
        if self.args.kill_at is not None:
            if self.kill is None and self.kill_pending is None:
                out.append("the kill test was asked for but never ran")
            elif (self.kill or self.kill_pending)["process_back_s"] is None:
                out.append("the launcher didn't restart the app after the kill")
        if self.interrupted:
            out.append("stopped early")
        return out

    def passed(self) -> bool:
        return not self.problems()

    def report(self, launcher_code: Optional[int]) -> str:
        t, a = self.tally, self.args
        span = self.stopping_at if self.stopping_at is not None else self.now()
        first = (0.0, min(span, 10 * 60))
        last = (max(0.0, span - 10 * 60), span + 1)
        problems = self.problems()

        def fmt(v, unit, digits=1):
            return "—" if v is None else f"{v:.{digits}f} {unit}"
        sel = list(self.speed())
        cmap = [window_median(t.confirm_map_ms, *w) for w in (first, last)]
        lines = [
            f"# Soak run · {time.strftime('%Y-%m-%d %H:%M')}", "",
            f"**Verdict: {'PASS' if not problems else 'FAIL: ' + '; '.join(problems)}.** Input: **Simulated** "
            f"({'g.Pype Generator with the live P300 and alpha code path' if a.p300 else 'g.Pype simulated decoder'}). "
            "Nothing here is a live EEG result.", "",
            f"- **Command:** `python tests/soak/soak.py --minutes {a.minutes:g}"
            f"{' --p300' if a.p300 else ''}{' --mute' if a.mute else ''}"
            f"{f' --kill-at {a.kill_at:g}' if a.kill_at is not None else ''}"
            f"{' --windowed' if a.windowed else ''}`",
            f"- **Launcher:** `{self.shown_command()}`",
            f"- **Machine:** {platform.system()} {platform.release()}, Python {platform.python_version()}, "
            f"{os.cpu_count()} CPUs",
            f"- **Ran:** {span / 60:.1f} min (asked for {a.minutes:g}). Launcher exit code: {launcher_code}",
            "", "## Rounds", "",
            "| Previews | Confirms | Cancels (incl. timeouts) | Map actions | Spoken lines | Double outputs |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| {t.previews} | {t.confirms} | {t.cancels} | {t.maps} | {t.speaks} | {len(t.double_outputs)} |",
            "", "## Crashes and restarts", "",
            f"- **Crashes (unplanned app exits):** {len(self.crashes())}"
            + "".join(f"\n  - at {x / 60:.1f} min: {b}" for x, b in self.crashes()),
            f"- **Python errors in the output:** {len(t.errors)}",
        ]
        k = self.kill or self.kill_pending
        if k is not None:
            lines.append(f"- **Kill test:** killed the app at {k['at_min']:.1f} min. The launcher "
                         f"started a new app process after {fmt(k['process_back_s'], 's')}, and it was "
                         f"logging again after {fmt(k['window_ready_s'], 's')}.")
        elif a.kill_at is not None:
            lines.append(f"- **Kill test:** asked for at {a.kill_at:g} min, but the app was never "
                         "found to kill.")
        else:
            lines.append("- **Kill test:** not run (add `--kill-at MINUTES`).")
        lines += ["", "## Memory (app process RSS)", "",
                  f"Sampled every {a.sample_s:g} s. Each app process is judged from {STARTUP_S:.0f} s "
                  "after it started (imports and calibration come first). The limit is +50 MB or "
                  "+15%, whichever is larger.", ""]
        runs = self.memory()
        if runs:
            lines += ["| App process | Minutes | Start | End | Change | Max | |",
                      "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
            for i, r in enumerate(runs, 1):
                if r["growth_mb"] is None:
                    lines.append(f"| {i} | {r['from_min']:.0f}–{r['to_min']:.0f} | — | "
                                 f"{r['end_mb']:.0f} MB | — | {r['max_mb']:.0f} MB | "
                                 "too short to judge |")
                    continue
                lines.append(f"| {i} | {r['from_min']:.0f}–{r['to_min']:.0f} | {r['start_mb']:.0f} MB | "
                             f"{r['end_mb']:.0f} MB | {r['growth_mb']:+.0f} MB | {r['max_mb']:.0f} MB | "
                             f"{'stable' if self.stable(r) else 'GROWING'} |")
        else:
            lines.append("No samples.")
        lines += ["", "## Speed, first 10 minutes vs last 10 minutes", "",
                  "| | First 10 min | Last 10 min |", "| --- | ---: | ---: |",
                  f"| Selection time (Choose round opens → preview), median | {fmt(sel[0], 's', 2)} | {fmt(sel[1], 's', 2)} |",
                  f"| Confirm → map action, median | {fmt(cmap[0], 'ms', 0)} | {fmt(cmap[1], 'ms', 0)} |"]
        if t.double_outputs:
            lines += ["", "## Double outputs", ""] + [f"- {d}" for d in t.double_outputs[:20]]
        if t.errors:
            lines += ["", "## Errors", ""] + [f"- `{e}`" for e in t.errors[:20]]
        lines += ["", f"Raw transcript: `{self.log_path.relative_to(ROOT)}` (stays out of git).", ""]
        return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python tests/soak/soak.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--minutes", type=float, default=60.0, help="how long to run (default 60)")
    p.add_argument("--p300", action="store_true",
                   help="the live code path on the Generator (P300 choose, alpha confirm)")
    p.add_argument("--kill-at", type=float, default=None, metavar="MINUTES",
                   help="kill the app once at this minute to test the launcher's restart")
    p.add_argument("--sample-s", type=float, default=60.0, help="memory sample interval (default 60)")
    p.add_argument("--max-restarts", type=int, default=5, help="passed to the launcher")
    p.add_argument("--windowed", action="store_true", help="don't run fullscreen")
    p.add_argument("--mute", action="store_true", help="no audio")
    args = p.parse_args(argv)
    if args.kill_at is not None and not 0 < args.kill_at < args.minutes:
        p.error("--kill-at must fall inside the run")
    try:
        import psutil  # noqa: F401
    except ImportError:
        p.error("needs psutil: pip install psutil")
    return Soak(args).run()


if __name__ == "__main__":
    sys.exit(main())
