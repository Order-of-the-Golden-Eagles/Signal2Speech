"""Preview screen and confirm ring (#175). Headless, with a fake clock where timing matters."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import ActionIds, InputSources, Outcome, TargetIds  # noqa: E402
from signal2speech.ui.confirm_ring import HOLD_S, RingModel, trailing_progress  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Clock:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


class View:
    def __init__(self):
        self.calls = []

    def show_satellite(self):
        self.calls.append("sat")

    def compare_air_quality(self):
        self.calls.append("cmp")


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text, clip=None):
        self.said.append(text)


# ── RingModel: the states ────────────────────────────────────
def test_hold_fills_and_completes_exactly_once():
    clock, done = Clock(), []
    m = RingModel(on_complete=done.append, clock=clock)
    m.start_hold("keyboard")
    clock.t += HOLD_S / 2
    m.tick()
    assert 0.49 < m.progress < 0.51 and not m.completed and done == []
    clock.t += HOLD_S
    m.tick()
    m.tick()
    assert m.completed and m.progress == 1.0 and done == ["keyboard"]
    m.start_hold("keyboard")                   # a completed ring ignores new holds
    clock.t += HOLD_S * 2
    m.tick()
    assert done == ["keyboard"]


def test_releasing_early_empties_and_confirms_nothing():
    clock, done = Clock(), []
    m = RingModel(on_complete=done.append, clock=clock)
    m.start_hold()
    clock.t += HOLD_S * 0.9
    m.tick()
    m.release()
    assert m.progress == 0.0 and not m.holding and done == []
    m.start_hold()                             # a fresh hold starts from empty
    clock.t += HOLD_S * 0.5
    m.tick()
    assert 0.49 < m.progress < 0.51


def test_eye_progress_follows_and_never_confirms_by_itself():
    done = []
    m = RingModel(on_complete=done.append)
    m.set_external(0.6)
    assert m.progress == 0.6
    m.set_external(0.0)                        # eyes opened early: the ring empties
    assert m.progress == 0.0
    m.set_external(1.0)
    assert done == [] and not m.completed      # the alpha switch confirms, not the ring
    m.mark_confirmed()
    assert m.completed and m.progress == 1.0


def test_trailing_progress_counts_the_current_closure_only():
    lvl, dwell = 10.0, 4
    assert trailing_progress([1, 2, 3], lvl, dwell) == 0.0
    assert trailing_progress([1, 11, 12], lvl, dwell) == 0.5
    assert trailing_progress([11, 11, 11, 11, 11, 11], lvl, dwell) == 1.0
    assert trailing_progress([11, 11, 11, 2], lvl, dwell) == 0.0    # eyes opened: back to empty


# ── The window: key 1, header, Spoken, eye progress ──────────
def make(qapp, source=InputSources.KEYBOARD, **kw):
    view, speaker = View(), Speaker()
    app = App(source, view=view, speaker=speaker, echo=False, reopen_ms=60000, **kw)
    app.root.show()
    app.ask()
    return app, view, speaker


def key(app, kind):
    QApplication.sendEvent(app.window, QKeyEvent(kind, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier, "1"))


def test_a_tap_of_1_picks_in_choose_but_needs_a_hold_to_confirm(qapp):
    app, view, speaker = make(qapp)
    clock = Clock()
    app.window.ring.model.clock = clock
    key(app, QEvent.Type.KeyPress)                         # Choose round: a tap picks
    key(app, QEvent.Type.KeyRelease)
    assert app.handler.current.kind.value == "confirm"
    key(app, QEvent.Type.KeyPress)                         # Confirm round: start holding
    clock.t += HOLD_S * 0.5
    app.window.ring._tick()
    key(app, QEvent.Type.KeyRelease)                       # let go early
    assert speaker.said == [] and app.window.ring.model.progress == 0.0
    key(app, QEvent.Type.KeyPress)
    clock.t += HOLD_S + 0.01
    app.window.ring._tick()
    assert len(speaker.said) == 1 and view.calls == ["sat"]
    key(app, QEvent.Type.KeyRelease)
    assert len(speaker.said) == 1                          # once, even after release
    app.close()
    app.root.close()


def test_typing_1_in_a_text_field_is_not_a_key_press(qapp):
    app, _, _ = make(qapp)
    box = QLineEdit(app.root)
    box.show()
    box.setFocus()
    qapp.processEvents()
    if QApplication.focusWidget() is not box:
        pytest.skip("offscreen platform didn't give the line edit focus")
    key(app, QEvent.Type.KeyPress)
    assert app.handler.current.kind.value == "choose"      # nothing was picked
    app.close()
    app.root.close()


def test_header_says_what_will_happen_and_spoken_state_follows(qapp):
    app, _, _ = make(qapp)
    app.window.press_target(T2)                            # compare: a map action
    assert app.window.preview_header.text() == "This will show the map and say:"
    assert app.window.preview.text().startswith("“") and "186 points" in app.window.preview.text()
    app.window.press_target(T1)
    assert app.window.preview_header.text() == "✓ Shown and spoken" and app.window.ring.model.completed
    from signal2speech.ai import to_choices
    app.choices = list(to_choices(["Yes, please.", "No, thanks."]))
    app.ask()
    assert not app.window.preview.isVisibleTo(app.window)   # the next round clears it
    app.window.press_target(T1)
    assert app.window.preview_header.text() == "This will be said aloud:"
    app.close()
    app.root.close()


def test_eye_progress_drives_the_ring_only_when_eyes_can_confirm(qapp):
    app, _, _ = make(qapp)                                  # keyboard input: eyes can't confirm
    app.window.press_target(T2)
    app.window.set_eye_progress(0.7)
    assert app.window.ring.model.progress == 0.0
    app.close()
    app.root.close()
    # Cancel picks only: no simulated eye closure holds the ring (an empty script means the
    # default [2, 1], whose confirm pick would hold it on the g.Pype path).
    app, _, _ = make(qapp, InputSources.SIMULATED, sim_script=[2, 2, 2], confirm_delay_ms=60000)
    app.window.press_target(T2)
    app.window.set_eye_progress(0.7)
    assert app.window.ring.model.progress == 0.7
    app.window.set_eye_progress(0.0)
    assert app.window.ring.model.progress == 0.0
    app.close()
    app.root.close()


def test_simulated_confirm_fills_the_ring_first(qapp):
    app, view, speaker = make(qapp, InputSources.SIMULATED, sim_script=[2, 1], confirm_delay_ms=200)
    app.window.flasher.flash_ms = app.window.flasher.isi_ms = 2
    seen_progress = []
    end = time.monotonic() + 5
    while time.monotonic() < end and not speaker.said:
        if app.window.ring.model.holding:
            seen_progress.append(app.window.ring.model.progress)
        qapp.processEvents()
        time.sleep(0.005)
    assert speaker.said and view.calls == ["cmp"]
    assert seen_progress and max(seen_progress) < 1.0       # it was filling before the confirm
    assert app.window.ring.model.completed and app.window.ring.model.source == "simulated"
    app.close()
    app.root.close()
