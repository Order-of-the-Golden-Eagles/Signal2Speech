"""#180: R gives the next visitor a fresh first question from any state, with no output.

The restart goes through the contract (handler.cancel, then begin_choice_round), so a decision
still in flight for the old round is rejected as stale. Offscreen, keyboard and simulated only.
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import (ActionIds, InputAdapter, InputSources, Outcome,  # noqa: E402
                                RoundKind, TargetIds)

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeView(QWidget):
    """A widget, so the app runs its real map reveal."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def show_satellite(self):
        self.calls.append(ActionIds.SHOW_SATELLITE)

    def compare_air_quality(self):
        self.calls.append(ActionIds.COMPARE_AIR_QUALITY)


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, clip=None):
        self.said.append(text)


@pytest.fixture
def app(qapp):
    a = App(InputSources.KEYBOARD, view=FakeView(), speaker=FakeSpeaker(), echo=False,
            reopen_ms=300, reveal_ms=300, confirm_timeout_ms=0)
    opened = []
    a.handler.on_round_opened.append(lambda r: opened.append(r))
    a.opened = opened
    a.ask()
    yield a
    a.close()
    a.root.close()


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)


def fresh_choose(a):
    rnd = a.handler.current
    return rnd is not None and rnd.kind is RoundKind.CHOOSE and a.handler.pending is None


def test_restart_during_a_preview_outputs_nothing_and_opens_one_fresh_round(app):
    assert app.window.press_target(T2) is Outcome.Previewed
    before = len(app.opened)
    app.restart()
    assert fresh_choose(app) and not app.window.preview_box.isVisible()
    pump(0.8)                                       # past reopen_ms: no second round sneaks in
    assert len(app.opened) == before + 1
    assert app.view.calls == [] and app.speaker.said == []


def test_a_late_decision_from_before_the_restart_is_stale(app):
    """An EEG flash sequence was armed on the old round; its decision lands after R."""
    eeg = InputAdapter(app.handler, InputSources.SIMULATED)
    eeg.arm_capture()                               # the sequence started on the old round
    app.restart()
    assert eeg.select_captured(T2) is Outcome.RejectedStaleRound
    assert fresh_choose(app) and app.view.calls == [] and app.speaker.said == []


def test_restart_during_a_reveal_cuts_it_short_without_a_second_output(app):
    app.window.press_target(T2)
    assert app.window.press_target(T1) is Outcome.Confirmed
    assert app.revealing and len(app.view.calls) == 1
    app.restart()
    assert not app.revealing and fresh_choose(app)
    pump(0.8)
    assert len(app.view.calls) == 1 and len(app.speaker.said) == 1


def test_the_r_key_restarts_and_the_report_counts_it(app):
    app.window.press_target(T2)
    key_r = [s for s in app.root.findChildren(QShortcut) if s.key().toString() == "R"]
    assert len(key_r) == 1
    key_r[0].activated.emit()                         # the real R wiring
    assert fresh_choose(app)
    report = app.report_text()
    assert "- **Restarts (R):** 1" in report and "restart (R)" in report
    timeline = report.split("## Timeline")[1].split("## Developer log")[0]
    assert "restart (R)" in timeline and "cleared (restart)" not in timeline   # counted once
    assert ("nothing", "Restarted for the next visitor.", None) in app.conversation.entries


def test_restart_ends_a_practice_round_with_one_fresh_question(app):
    assert app.start_practice()
    before = len(app.opened)
    app.restart()
    assert not app.practicing and fresh_choose(app) and len(app.opened) == before + 1
