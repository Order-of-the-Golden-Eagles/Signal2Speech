"""One entry point: python -m signal2speech (#136). No real tools are started, except a tiny
inline process for the smoke-check path."""
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import signal2speech.__main__ as entry  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def have(_name):
    return object()


def lack(_name):
    return None


def test_every_tool_names_its_input_and_uses_this_python():
    for t in entry.TOOLS:
        assert t.command()[0] == sys.executable
    titles = {t.key: t.title for t in entry.TOOLS}
    assert titles["demo-keyboard"].endswith("Keyboard") and titles["demo-simulated"].endswith("Simulated")
    assert titles["evidence"].endswith("Simulated") and titles["ai"].endswith("Keyboard")


def test_fullscreen_only_applies_to_demos():
    assert "--fullscreen" in entry.BY_KEY["demo-keyboard"].command(fullscreen=True)
    assert "--fullscreen" not in entry.BY_KEY["ai"].command(fullscreen=True)
    assert "--fullscreen" not in entry.BY_KEY["demo-keyboard"].command(fullscreen=False)


def test_missing_dependency_is_explained():
    assert entry.missing(entry.BY_KEY["evidence"], find_spec=lack).startswith("needs gpype")
    assert entry.missing(entry.BY_KEY["evidence"], find_spec=have) is None
    assert entry.missing(entry.BY_KEY["demo-keyboard"], find_spec=lack) is None


def test_window_buttons_launch_and_gray_out(qapp):
    spawned = []
    win = entry.run_window(spawn=lambda cmd: spawned.append(cmd) or True, find_spec=lack)
    assert set(win.buttons) == set(entry.BY_KEY)
    assert not win.buttons["evidence"].isEnabled() and win.buttons["demo-keyboard"].isEnabled()
    win.fullscreen_box.setChecked(True)
    win.buttons["demo-simulated"].click()
    assert spawned[-1][1:] == ["-m", "signal2speech.app", "--input", "simulated", "--sim", "2,1",
                               "--fullscreen"]
    assert win.status.text() == "Started: NASA example · Simulated"
    win.close()


def test_window_reports_a_failed_start(qapp):
    win = entry.run_window(spawn=lambda cmd: False, find_spec=have)
    assert win.buttons["evidence"].isEnabled()
    win.buttons["ai"].click()
    assert win.status.text() == "Couldn't start Signal2Speech · Keyboard"
    win.close()


@pytest.mark.parametrize("code,expect", [(0, "PASS"), (3, "FAIL (exit 3)")])
def test_inline_tool_shows_output_and_result(qapp, monkeypatch, code, expect):
    fake = entry.Tool("smoke", "Smoke check", "test", ["-c", f"print('hello from smoke'); raise SystemExit({code})"],
                      inline=True)
    monkeypatch.setattr(entry, "TOOLS", [fake])
    win = entry.run_window(spawn=lambda cmd: True, find_spec=have)
    win.buttons["smoke"].click()
    end = time.monotonic() + 15
    while time.monotonic() < end and "running" in win.status.text():
        qapp.processEvents()
        time.sleep(0.02)
    assert win.status.text() == f"Smoke check: {expect}"
    assert "hello from smoke" in win.output.toPlainText()
    win.close()


def test_help_lists_every_tool(capsys):
    with pytest.raises(SystemExit):
        entry.main(["--help"])
    out = capsys.readouterr().out
    assert all(key in out for key in entry.BY_KEY)


def test_running_one_tool_directly(monkeypatch):
    calls = []
    monkeypatch.setattr(entry.subprocess, "call", lambda cmd, cwd=None: calls.append(cmd) or 0)
    assert entry.main(["demo-keyboard", "--fullscreen"]) == 0
    assert calls[-1][1:] == ["-m", "signal2speech.app", "--input", "keyboard", "--fullscreen"]
    monkeypatch.setattr(entry, "missing", lambda tool: "needs gpype")
    assert entry.main(["evidence"]) == 2
