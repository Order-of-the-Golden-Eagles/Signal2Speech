"""#178: the header, the partner's question, and the Choose · Preview · Confirm · Spoken steps."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import ActionIds, InputSources, RoundKind, TargetIds  # noqa: E402
from signal2speech.ui.__main__ import DEMO_QUESTION  # noqa: E402
from signal2speech.ui.stepper import STEPS, step_for  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class View(QWidget):
    def __init__(self):
        super().__init__()
        self.calls = []

    def show_satellite(self):
        self.calls.append(ActionIds.SHOW_SATELLITE)

    def compare_air_quality(self):
        self.calls.append(ActionIds.COMPARE_AIR_QUALITY)


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text, clip=None):
        self.said.append(text)


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture
def app(qapp):
    a = App(InputSources.KEYBOARD, view=View(), speaker=Speaker(), echo=False,
            reveal_ms=60000, confirm_timeout_ms=0)
    a.root.show()
    a.root.resize(1280, 720)
    yield a
    a.close()
    a.root.close()


def test_step_rule_covers_every_state():
    assert step_for(RoundKind.CHOOSE, False, False) == "Choose"
    assert step_for(RoundKind.CONFIRM, False, False) == "Preview"
    assert step_for(RoundKind.CONFIRM, False, True) == "Confirm"
    assert step_for(None, True, False) == "Spoken"
    assert step_for(None, False, False) is None
    assert STEPS == ("Choose", "Preview", "Confirm", "Spoken")


def test_steps_follow_a_round_from_choose_to_spoken(app):
    app.ask()
    assert app.steps.current == "Choose"
    app.window.press_target(T2)
    assert app.steps.current == "Preview"
    app.window.ring.start_hold("keyboard", 5.0)        # key 1 held: the ring starts filling
    pump(0.3)
    assert app.steps.current == "Confirm"
    app.window.ring.release()
    pump(0.3)
    assert app.steps.current == "Preview"              # let go: back to the preview
    app.window.press_target(T1)
    assert app.steps.current == "Spoken"
    assert app.view.calls == [ActionIds.COMPARE_AIR_QUALITY] and len(app.speaker.said) == 1


def test_a_cancel_clears_the_steps_until_the_next_question(app):
    app.ask()
    app.window.press_target(T2)
    app.window.press_cancel()
    assert app.steps.current is None
    app.ask()
    assert app.steps.current == "Choose"


def test_the_question_replaces_choose_a_reply(app):
    w = app.window
    app.ask()
    assert w.question_label.isVisibleTo(w) and w.question_label.text() == DEMO_QUESTION
    assert not w.prompt.isVisibleTo(w)
    app.window.press_target(T2)
    assert not w.question_label.isVisibleTo(w)
    assert w.prompt.isVisibleTo(w) and w.prompt.text() == "Say this?"   # its own style
    assert w.prompt.styleSheet() == ""                 # the question never restyles the prompt
    app.add_question("Are you comfortable?")           # the AI demo's typed question
    app.window.press_cancel()
    app.ask()
    assert w.question_label.text() == "Are you comfortable?"


def test_no_question_falls_back_to_choose_a_reply(qapp):
    a = App(InputSources.KEYBOARD, view=View(), speaker=Speaker(), echo=False, question="")
    a.ask()
    assert a.window.prompt.text() == "Choose a reply" and not a.window.question_label.isVisible()
    a.close()


def test_holding_2_to_cancel_is_not_the_confirm_step(app):
    app.ask()
    app.window.press_target(T2)
    app.window.ring.start_hold("cancel", 5.0)
    assert app.steps.current == "Preview"
    app.window.ring.release()


def test_practice_clears_the_step_bar(app):
    app.ask()
    app.window.press_target(T2)
    app.window.press_target(T1)
    assert app.steps.current == "Spoken"
    app._set_reveal(False)
    app.handler.current = None
    assert app.start_practice()
    assert app.steps.current is None
    app.practice.stop()


def test_question_and_steps_follow_the_text_size(app):
    from signal2speech.ui import theme as T
    app.ask()
    before = app.window.question_label.fontInfo().pixelSize()
    try:
        T.set_scale(1.3)
        app.apply_text_scale()
        assert app.window.question_label.fontInfo().pixelSize() > before
        assert f"{T.px(T.CAPTION + 2)}px" in app.steps.separators[0].styleSheet()
    finally:
        T.set_scale(1.0)
        app.apply_text_scale()


def test_the_ai_demo_has_no_demo_question(qapp):
    from signal2speech.ai.__main__ import AnsweringDemo
    from signal2speech.ai.replies import StubProvider
    demo = AnsweringDemo(provider=StubProvider(), provider_note="test", speaker=Speaker(),
                         echo=False, view=View())
    demo.start()
    assert demo.app.window.question == "" and not demo.app.window.question_label.isVisible()
    demo.app.close()
    demo.root.close()


def test_header_and_steps_fit_1280x720_in_every_state(app):
    app.ask()
    sizes = [app.root.minimumSizeHint()]
    app.window.press_target(T2)
    sizes.append(app.root.minimumSizeHint())
    app.window.press_target(T1)
    sizes.append(app.root.minimumSizeHint())
    assert all(s.width() <= 1280 and s.height() <= 720 for s in sizes), [(s.width(), s.height()) for s in sizes]
    assert app.header_title.isVisibleTo(app.root) and app.steps.isVisibleTo(app.root)
