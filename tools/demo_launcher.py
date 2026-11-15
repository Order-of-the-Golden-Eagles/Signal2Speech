"""Crash-safe launcher for the judging table (#133).

    python tools/demo_launcher.py                          # keyboard, fullscreen
    python tools/demo_launcher.py --input simulated --sim 2,1
    python tools/demo_launcher.py --windowed --max-restarts 3 -- --mute

Runs `python -m signal2speech.app --fullscreen <your flags>` with this same Python. If the app
exits with an error, it restarts it after 1 s, then 2 s, up to --max-restarts times, and logs each
start and exit to logs/launcher-<time>.log. Closing the window normally (exit code 0) ends the
launcher, with no restart. Ctrl+C stops the app and the launcher.

Any flag the launcher doesn't know is passed through to the app. Put app flags after `--` if
they clash with a launcher flag.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
BACKOFF_S = (1.0, 2.0)          # first restart after 1 s, then every 2 s: always within 2 s


def app_command(app_args: Sequence[str], fullscreen: bool = True,
                python: str = sys.executable) -> List[str]:
    cmd = [python, "-m", "signal2speech.app"]
    if fullscreen and "--fullscreen" not in app_args:
        cmd.append("--fullscreen")
    return cmd + list(app_args)


class Launcher:
    def __init__(self, cmd: List[str], max_restarts: int = 5, log_path: Optional[Path] = None,
                 popen: Callable = subprocess.Popen, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, echo: Callable[[str], None] = print):
        self.cmd = cmd
        self.max_restarts = max_restarts
        self.log_path = log_path
        self.popen, self.sleep, self.clock, self.echo = popen, sleep, clock, echo
        self.restarts = 0
        self.exits: List[int] = []

    def log(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        self.echo(f"[launcher] {line}")
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def run(self) -> int:
        """Return 0 after a clean quit, 1 after giving up on repeated crashes, 130 on Ctrl+C."""
        self.log(f"start: {' '.join(self.cmd)}")
        while True:
            started = self.clock()
            proc = self.popen(self.cmd, cwd=str(ROOT))
            try:
                code = proc.wait()
            except KeyboardInterrupt:
                self.log("Ctrl+C: stopping the app")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                return 130
            ran = self.clock() - started
            self.exits.append(code)
            if code == 0:
                self.log(f"app closed normally after {ran:.0f} s. Not restarting.")
                return 0
            if self.restarts >= self.max_restarts:
                self.log(f"app exited with code {code} after {ran:.0f} s. Gave up after "
                         f"{self.restarts} restart{'' if self.restarts == 1 else 's'}. Switch to the fallback build "
                         "(docs/devops/judging-build.md).")
                return 1
            delay = BACKOFF_S[min(self.restarts, len(BACKOFF_S) - 1)]
            self.restarts += 1
            self.log(f"app exited with code {code} after {ran:.0f} s. Restart "
                     f"{self.restarts}/{self.max_restarts} in {delay:.0f} s.")
            self.sleep(delay)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python tools/demo_launcher.py",
                                description="Start the demo fullscreen and restart it if it crashes.")
    p.add_argument("--windowed", action="store_true", help="don't add --fullscreen")
    p.add_argument("--max-restarts", type=int, default=5, help="give up after this many crashes")
    p.add_argument("--no-log", action="store_true", help="don't write logs/launcher-<time>.log")
    args, app_args = p.parse_known_args(argv)
    if app_args and app_args[0] == "--":
        app_args = app_args[1:]
    log = None if args.no_log else ROOT / "logs" / f"launcher-{time.strftime('%Y%m%d-%H%M%S')}.log"
    return Launcher(app_command(app_args, fullscreen=not args.windowed),
                    max_restarts=max(0, args.max_restarts), log_path=log).run()


if __name__ == "__main__":
    sys.exit(main())
