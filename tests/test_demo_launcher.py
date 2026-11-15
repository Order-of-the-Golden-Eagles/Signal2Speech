"""Crash-safe launcher (#133). No real app is started: the process runner is a fake."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo_launcher", ROOT / "tools" / "demo_launcher.py")
dl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dl)


class FakeProc:
    def __init__(self, code, interrupt=False):
        self.code, self.interrupt, self.terminated = code, interrupt, False

    def wait(self, timeout=None):
        if self.interrupt and not self.terminated:
            raise KeyboardInterrupt
        return self.code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def make(codes, max_restarts=5, tmp_path=None, interrupt_at=None):
    procs = [FakeProc(c, interrupt=(i == interrupt_at)) for i, c in enumerate(codes)]
    started, sleeps = [], []

    def popen(cmd, cwd=None):
        started.append(cmd)
        return procs[len(started) - 1]
    log = tmp_path / "launcher.log" if tmp_path else None
    launcher = dl.Launcher(["python", "-m", "signal2speech.app"], max_restarts=max_restarts,
                           log_path=log, popen=popen, sleep=sleeps.append, echo=lambda s: None)
    return launcher, started, sleeps, procs, log


def test_clean_quit_does_not_restart(tmp_path):
    launcher, started, sleeps, _, log = make([0], tmp_path=tmp_path)
    assert launcher.run() == 0
    assert len(started) == 1 and sleeps == []
    assert "closed normally" in log.read_text()


def test_crash_restarts_within_two_seconds_until_clean_quit(tmp_path):
    launcher, started, sleeps, _, log = make([1, -11, 0], tmp_path=tmp_path)
    assert launcher.run() == 0
    assert len(started) == 3 and launcher.exits == [1, -11, 0]
    assert sleeps == [1.0, 2.0] and all(s <= 2.0 for s in sleeps)
    text = log.read_text()
    assert "code 1" in text and "code -11" in text and "Restart 2/5" in text


def test_gives_up_after_the_limit(tmp_path):
    launcher, started, sleeps, _, log = make([1] * 10, max_restarts=3, tmp_path=tmp_path)
    assert launcher.run() == 1
    assert len(started) == 4 and sleeps == [1.0, 2.0, 2.0]       # 1 start + 3 restarts
    assert "Gave up after 3 restarts" in log.read_text()


def test_ctrl_c_stops_the_app_without_restarting():
    launcher, started, sleeps, procs, _ = make([0], interrupt_at=0)
    assert launcher.run() == 130
    assert procs[0].terminated and len(started) == 1 and sleeps == []


def test_command_is_fullscreen_by_default_and_passes_flags_through():
    cmd = dl.app_command(["--input", "simulated", "--sim", "2,1"])
    assert cmd[:3] == [sys.executable, "-m", "signal2speech.app"]
    assert "--fullscreen" in cmd and cmd[-4:] == ["--input", "simulated", "--sim", "2,1"]
    assert "--fullscreen" not in dl.app_command(["--input", "keyboard"], fullscreen=False)
    assert dl.app_command(["--fullscreen"]).count("--fullscreen") == 1


def test_main_parses_launcher_and_app_flags(monkeypatch):
    seen = {}

    class Spy(dl.Launcher):
        def run(self):
            seen.update(cmd=self.cmd, max_restarts=self.max_restarts, log=self.log_path)
            return 0
    monkeypatch.setattr(dl, "Launcher", Spy)
    assert dl.main(["--windowed", "--max-restarts", "2", "--no-log", "--", "--input", "simulated"]) == 0
    assert seen["max_restarts"] == 2 and seen["log"] is None
    assert "--fullscreen" not in seen["cmd"] and seen["cmd"][-2:] == ["--input", "simulated"]
