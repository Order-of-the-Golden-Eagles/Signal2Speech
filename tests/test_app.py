"""Integration checks for #4 / #25: one confirm -> one map action + one utterance; preview,
cancel, disconnect, stale, and duplicate input -> nothing. Offscreen, no headset, no g.Pype."""
import re
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.app import App, AppSink, PendingMapView, main  # noqa: E402
from signal2speech.core import (ActionIds, ConfirmedAction, InputSources, Outcome,  # noqa: E402
                                SelectionEvent, TargetIds)

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2
COMPARE_LINE = "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeView:
    def __init__(self):
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


def make(qapp, source=InputSources.KEYBOARD, **kw):
    view, speaker = FakeView(), FakeSpeaker()
    app = App(source, view=view, speaker=speaker, echo=False, **kw)
    app.ask()
    return app, view, speaker


def pump(qapp, until, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        qapp.processEvents()
        time.sleep(0.002)


def test_keyboard_preview_is_silent_then_confirm_outputs_once(qapp):
    app, view, speaker = make(qapp)
    assert app.window.press_target(T2) is Outcome.Previewed
    assert view.calls == [] and speaker.said == []
    assert app.window.press_target(T1) is Outcome.Confirmed
    assert view.calls == [ActionIds.COMPARE_AIR_QUALITY]
    assert speaker.said == [COMPARE_LINE]
    app.window.press_target(T1)                                   # repeat key
    app.handler.handle(SelectionEvent("keyboard", "r2", "k2", T1))  # duplicate callback
    assert len(view.calls) == 1 and len(speaker.said) == 1
    assert any("OUTPUT map: compare_air_quality()  [keyboard]" in l for l in app.log.lines)


def test_show_satellite_path(qapp):
    app, view, speaker = make(qapp)
    app.window.press_target(T1)
    app.window.press_target(T1)
    assert view.calls == [ActionIds.SHOW_SATELLITE]
    assert speaker.said[0].startswith("This is the June 28, 2023 NASA MODIS view")


@pytest.mark.parametrize("stop", ["key2", "esc", "disconnect"])
def test_cancel_or_disconnect_during_preview_outputs_nothing(qapp, stop):
    app, view, speaker = make(qapp)
    app.window.press_target(T2)
    {"key2": lambda: app.window.press_target(T2), "esc": app.window.press_cancel,
     "disconnect": app.handler.disconnect}[stop]()
    app.window.press_target(T1)
    assert view.calls == [] and speaker.said == [] and app.handler.pending is None


def test_stale_choose_decision_cannot_confirm(qapp):
    app, view, speaker = make(qapp)
    app.window.press_target(T2)
    out = app.handler.handle(SelectionEvent(InputSources.LIVE_EEG, "r1", "e7", T1))
    assert out is Outcome.RejectedStaleRound
    assert view.calls == [] and speaker.said == []
    assert any("RejectedStaleRound: live-eeg e7 r1->target-1" in l for l in app.log.lines)


def test_simulated_flow_uses_capture_path_and_outputs_once(qapp):
    app, view, speaker = make(qapp, InputSources.SIMULATED, sim_script=[2, 1],
                              confirm_delay_ms=20, reopen_ms=60000)
    app.window.flasher.flash_ms = app.window.flasher.isi_ms = 2
    assert app.window.input_label.text() == "Input: Simulated"
    pump(qapp, lambda: view.calls)
    assert view.calls == [ActionIds.COMPARE_AIR_QUALITY]
    assert speaker.said == [COMPARE_LINE]
    # Event IDs come from one process-wide counter, so match the shape, not the number.
    assert any(re.search(r"Previewed: simulated s\d+ r1->target-2", l) for l in app.log.lines)
    assert any(re.search(r"Confirmed: simulated s\d+ r2->target-1", l) for l in app.log.lines)


def test_simulated_cancel_outputs_nothing(qapp):
    app, view, speaker = make(qapp, InputSources.SIMULATED, sim_script=[1, 2],
                              confirm_delay_ms=20, reopen_ms=60000)
    app.window.flasher.flash_ms = app.window.flasher.isi_ms = 2
    pump(qapp, lambda: any("Cancelled" in l for l in app.log.lines))
    assert any("Cancelled: simulated" in l for l in app.log.lines)
    assert view.calls == [] and speaker.said == []


def test_speak_reply_speaks_without_map():
    view, speaker, log = FakeView(), FakeSpeaker(), []
    AppSink(view, speaker, log.append).execute(
        ConfirmedAction(ActionIds.SPEAK_REPLY, "Yes, please.", "keyboard", "k1", "k2"))
    assert view.calls == [] and speaker.said == ["Yes, please."]


@pytest.mark.parametrize("source", [InputSources.LIVE_EEG, InputSources.RECORDED])
def test_unbuilt_inputs_are_refused(qapp, source):
    with pytest.raises(ValueError, match="blocked"):
        App(source, view=FakeView(), speaker=FakeSpeaker(), echo=False)
    assert main(["--input", "live" if source == InputSources.LIVE_EEG else "recorded"]) == 2


def test_pending_view_is_labelled(qapp):
    v = PendingMapView()
    v.compare_air_quality()
    assert "not built yet (#30)" in v.text() and "compare_air_quality" in v.text()


def test_main_keyboard_screenshot(qapp, tmp_path):
    out = tmp_path / "app.png"
    assert main(["--keys", "2,1", "--mute", "--screenshot", str(out)]) == 0
    assert out.stat().st_size > 0


class WidgetView(FakeView):
    """A QWidget map view, so App puts it in the layout like the real OpenOrbitView."""

    def __new__(cls):
        from PySide6.QtWidgets import QWidget

        class _W(QWidget):
            def __init__(self):
                super().__init__()
                self.calls = []

            def show_satellite(self):
                self.calls.append(ActionIds.SHOW_SATELLITE)

            def compare_air_quality(self):
                self.calls.append(ActionIds.COMPARE_AIR_QUALITY)
        return _W()


def test_map_confirm_enlarges_reveal_until_next_question(qapp):
    view, speaker = WidgetView(), FakeSpeaker()
    app = App(view=view, speaker=speaker, echo=False, reveal_ms=60000)
    app.ask()
    app.window.press_target(T2)
    assert not app.revealing                                   # preview: tiles stay
    app.window.press_target(T1)
    assert app.revealing and app._reopen.interval() == 60000
    assert not any(t.isVisibleTo(app.window) for t in app.window.tiles.values())
    assert app.window.input_label.isVisibleTo(app.window)      # input label always visible
    app.ask()                                                  # next question
    assert not app.revealing
    assert all(t.isVisibleTo(app.window) for t in app.window.tiles.values())


def test_cancel_and_speak_reply_do_not_reveal(qapp):
    app = App(view=WidgetView(), speaker=FakeSpeaker(), echo=False, reopen_ms=1234)
    app.ask()
    app.window.press_target(T2)
    app.window.press_target(T2)                                # cancel
    assert not app.revealing and app._reopen.interval() == 1234
    from signal2speech.ai import to_choices
    app.choices = list(to_choices(["Yes, please.", "No, thanks."]))
    app.ask()
    app.window.press_target(T1)
    app.window.press_target(T1)                                # confirm a spoken reply
    assert not app.revealing and app._reopen.interval() == 1234


# ── #94: judging laptop screen, fullscreen, key help ─────────
@pytest.mark.parametrize("source", [InputSources.KEYBOARD, InputSources.SIMULATED])
def test_window_fits_1280x720_in_every_state(qapp, source):
    app = App(source, view=WidgetView(), speaker=FakeSpeaker(), echo=False,
              reveal_ms=60000, confirm_delay_ms=600000)
    app.root.show()
    app.ask()
    sizes = [app.root.minimumSizeHint()]
    app.window.press_target(T2)
    sizes.append(app.root.minimumSizeHint())
    app.window.press_target(T1)
    sizes.append(app.root.minimumSizeHint())
    assert all(s.width() <= 1280 and s.height() <= 720 for s in sizes), [(s.width(), s.height()) for s in sizes]
    assert app.window.input_label.isVisibleTo(app.window)
    app.close()
    app.root.close()


def test_key_help_overlay_never_touches_the_round(qapp):
    app = App(view=FakeView(), speaker=FakeSpeaker(), echo=False)
    app.root.show()
    app.ask()
    app.window.press_target(T2)
    before = (app.handler.current.id, len(app.log.lines))
    app.help.toggle()
    assert app.help.isVisible() and "Pretend the headset disconnected" in app.help.text()
    app.help.toggle()
    assert not app.help.isVisible()
    assert (app.handler.current.id, len(app.log.lines)) == before
    app.root.close()


def test_simulated_help_lists_decoder_keys_only_with_a_decoder(qapp):
    app = App(view=FakeView(), speaker=FakeSpeaker(), echo=False)
    assert "Ctrl+1" not in app.help.text()
    app.root.close()


def test_fullscreen_toggle(qapp):
    app = App(view=FakeView(), speaker=FakeSpeaker(), echo=False)
    app.root.show()
    app.toggle_fullscreen()
    assert app.root.windowState() & Qt.WindowState.WindowFullScreen
    app.toggle_fullscreen()
    assert not app.root.windowState() & Qt.WindowState.WindowFullScreen
    app.root.close()


def test_connection_label_hides_for_keyboard_only(qapp):
    kb = App(view=FakeView(), speaker=FakeSpeaker(), echo=False)
    assert not kb.window.connection_label.isVisibleTo(kb.window)
    kb.window.set_connection("g.Pype Generator stream")
    assert kb.window.connection_label.isVisibleTo(kb.window)


def test_main_fullscreen_flag(qapp, tmp_path):
    out = tmp_path / "full.png"
    assert main(["--fullscreen", "--keys", "2,1", "--mute", "--screenshot", str(out)]) == 0
    assert out.stat().st_size > 0
