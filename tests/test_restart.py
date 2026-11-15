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

    def reset(self):
        self.calls.append("reset")


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


def outputs(a):
    """Map actions only; the view's reset on R isn't an output."""
    return [c for c in a.view.calls if c != "reset"]


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
    assert outputs(app) == [] and app.speaker.said == []


def test_a_late_decision_from_before_the_restart_is_stale(app):
    """An EEG flash sequence was armed on the old round; its decision lands after R."""
    eeg = InputAdapter(app.handler, InputSources.SIMULATED)
    eeg.arm_capture()                               # the sequence started on the old round
    app.restart()
    assert eeg.select_captured(T2) is Outcome.RejectedStaleRound
    assert fresh_choose(app) and outputs(app) == [] and app.speaker.said == []


def test_restart_during_a_reveal_cuts_it_short_without_a_second_output(app):
    app.window.press_target(T2)
    assert app.window.press_target(T1) is Outcome.Confirmed
    assert app.revealing and len(app.view.calls) == 1
    app.restart()
    assert not app.revealing and fresh_choose(app)
    assert app.view.calls[-1] == "reset"                 # the last visitor's map is cleared
    pump(0.8)
    outputs = [c for c in app.view.calls if c != "reset"]
    assert len(outputs) == 1 and len(app.speaker.said) == 1


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
    assert any(line.split("  ", 1)[1].startswith("practice: ended") for line in app.log.lines)


def test_restart_is_refused_during_a_calibration(app):
    class Calibrating:
        calibrating_now = True
    app.sim = Calibrating()
    rnd = app.handler.current
    assert app.restart() is False
    assert app.handler.current is rnd and app.restarts == 0
    assert any("restart (R) ignored" in line for line in app.log.lines)


def test_restart_hides_the_last_visitors_help_banner(app):
    app._call_for_help("keyboard")
    assert app.help_banner.isVisibleTo(app.root)
    app.restart()
    assert not app.help_banner.isVisibleTo(app.root)


def test_r_during_attract_restarts_once(app):
    """Attract swallows the waking key; R still restarts, and opens exactly one round."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from signal2speech.attract import AttractMode

    def make_demo():
        return App(InputSources.KEYBOARD, view=FakeView(), speaker=FakeSpeaker(), echo=False)
    app.root.show()
    mode = app.attract = AttractMode(app, make_demo=make_demo)
    mode.start()
    assert mode.active
    before = len(app.opened)
    QApplication.sendEvent(app.root, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R,
                                               Qt.KeyboardModifier.NoModifier, "r"))
    pump(0.3)
    assert not mode.active and app.restarts == 1 and fresh_choose(app)
    assert len(app.opened) - before <= 1                  # attract's own round, or one from R


def test_the_ai_demo_starts_the_next_visitor_on_saved_phrases(qapp):
    """R forgets the question and the AI replies; a reply still on its way is dropped."""
    from signal2speech.ai.__main__ import AnsweringDemo
    from signal2speech.ai.replies import StubProvider

    demo = AnsweringDemo(provider=StubProvider(), provider_note="test", speaker=FakeSpeaker(),
                         echo=False, view=FakeView())
    demo.start()
    slow = demo.suggester.suggest

    def late(question, avoid=()):
        time.sleep(0.4)
        return slow(question, avoid)
    demo.suggester.suggest = late
    demo.panel.question.setText("Where is Detroit?")
    demo.ask("Where is Detroit?")                          # still in flight when R comes
    assert demo.app.restart()
    pump(1.0)                                              # the late reply arrives, stale
    assert demo.question == "" and demo.panel.question.text() == ""
    assert demo.current.origin == "Saved phrases"
    assert demo.app.choices == list(demo.current.choices)
    assert fresh_choose(demo.app)
    demo.app.close()
    demo.root.close()
