"""#172: keys choose, a PiEEG board's eye closure confirms, inside the real app.

No board needed. The end-to-end tests use ``lsl_source.SelfTestStream``, our own 16-pin LSL
publisher (labelled Simulated), and close its eyes from the test. The label and arming rules are
checked without any stream: building the app doesn't touch LSL.
"""
import importlib.util
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
if importlib.util.find_spec("gpype") is None or importlib.util.find_spec("pylsl") is None:
    pytest.skip("g.Pype and pylsl are needed for the PiEEG path", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech import app as app_module  # noqa: E402
from signal2speech.app import App  # noqa: E402
from signal2speech.core import ActionIds, InputSources, Outcome, TargetIds  # noqa: E402
from signal2speech.eeg import app_live  # noqa: E402
from signal2speech.eeg import devices  # noqa: E402
from signal2speech.eeg import lsl_source as lsl  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2
CLEAN = {"false_triggers": 0, "edges_per_closure": [1, 1, 1]}
QUICK = {"probe_s": 3.0, "alpha_calib_s": 4.0, "rest_s": 5.0, "closures": 2}


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


@pytest.fixture
def make(qapp):
    made = []

    def build(**pieeg):
        app = App(InputSources.KEYBOARD, view=FakeView(), speaker=FakeSpeaker(), echo=False,
                  reopen_ms=60_000, confirm_timeout_ms=0, pieeg=pieeg)
        log = []
        app.handler.on_handled.append(lambda e, o: log.append((e, o)))
        made.append(app)
        return app, log

    yield build
    for app in made:
        app.close()
        app.root.close()


def start_or_skip(app):
    try:
        app.sim.start()
    except RuntimeError as err:
        if "no LSL stream" in str(err):
            pytest.skip("LSL streams can't be discovered on this machine (multicast blocked)")
        raise


def accepted(log):
    return [(o, e.source) for e, o in log if e is not None and not o.rejected]


# ── End to end, on the self-test board ───────────────────────
def test_self_test_board_confirms_in_the_app_exactly_once(make):
    app, log = make(stream_is="simulated", self_test=True, stream="S2S-AppPiEEG1",
                    auto_eyes=False, **QUICK)
    start_or_skip(app)
    assert app.sim.calibrate() is True, app.sim.reasons
    assert app.sim.armed and app.sim.report["false_triggers"] == 0
    assert app.window.input_label.text() == \
        "Choose: Keyboard · Confirm: Simulated (self-test LSL stream)"
    assert app.handler.live_eeg_confirm_armed is False      # Simulated never arms the Live gate

    app.ask()
    assert app.window.press_target(T2) is Outcome.Previewed
    app_live.pump(app.sim.alpha.settle_s + 0.3)             # eyes open since the preview
    app.sim.publisher.close_eyes()
    assert app_live.pump(10, until=lambda: app.view.calls), accepted(log)
    app.sim.publisher.open_eyes()
    app_live.pump(2.0)                                      # nothing extra arrives late
    assert app.view.calls == [ActionIds.COMPARE_AIR_QUALITY]
    assert len(app.speaker.said) == 1
    assert accepted(log) == [(Outcome.Previewed, InputSources.KEYBOARD),
                             (Outcome.Confirmed, InputSources.SIMULATED)]


def test_a_failed_check_leaves_key_1_as_the_only_confirm(make, monkeypatch):
    class EyesNeverClose(lsl.SelfTestStream):
        def close_eyes(self):
            pass                                            # no alpha rise on any pin

    monkeypatch.setattr(lsl, "SelfTestStream", EyesNeverClose)
    app, log = make(stream_is="simulated", self_test=True, stream="S2S-AppPiEEG2",
                    auto_eyes=False, **QUICK)
    start_or_skip(app)
    assert app.sim.calibrate() is False
    assert not app.sim.armed and app.sim.alpha is None      # nothing from the board can confirm
    assert app.sim.reasons and ("channel check" in app.sim.reasons[0]
                                or "calibration failed" in app.sim.reasons[0])
    assert app.window.input_label.text().startswith("Choose: Keyboard · Confirm: key 1 · ")
    assert app.window.input_label.text().endswith("eye check failed")
    assert "the eye check failed" in app.window.confirm_hint()

    app.ask()
    app.window.press_target(T2)
    app.window.press_target(T1)
    assert accepted(log) == [(Outcome.Previewed, InputSources.KEYBOARD),
                             (Outcome.Confirmed, InputSources.KEYBOARD)]


# ── Labels and arming, no stream ─────────────────────────────
def test_live_label_and_arming_follow_the_check(make):
    app, _ = make(stream_is="live")
    sim = app.sim
    assert app.handler.live_eeg_confirm_armed is False and app.window.eye_confirm is False
    assert "the eye check hasn't run yet" in app.window.confirm_hint()
    assert app.window.input_label.text() == \
        "Choose: Keyboard · Confirm: key 1 · Live EEG (PiEEG Octopus 16): eye check not run yet"
    assert sim._finish({**CLEAN, "false_triggers": 1}) is False
    assert app.handler.live_eeg_confirm_armed is False
    assert sim._finish(CLEAN) is True
    assert app.handler.live_eeg_confirm_armed is True and app.window.eye_confirm is True
    assert app.window.input_label.text() == "Choose: Keyboard · Confirm: Live EEG (PiEEG Octopus 16)"
    assert app.root.windowTitle() == "Signal2Speech · " + app.window.input_label.text()
    sim.close()
    assert app.handler.live_eeg_confirm_armed is False      # closing disarms
    # The report is written on quit, after close: it still names what really confirmed.
    assert "- **Input:** Choose: Keyboard · Confirm: Live EEG (PiEEG Octopus 16)" in app.report_text()


def test_recorded_and_simulated_streams_are_never_labelled_live(make):
    rec, _ = make(stream_is="recorded")
    assert rec.sim.input_source == InputSources.RECORDED
    rec.sim._finish(CLEAN)
    assert rec.window.input_label.text() == "Choose: Keyboard · Confirm: Recorded (PiEEG Octopus 16)"
    assert rec.handler.live_eeg_confirm_armed is False
    st, _ = make(stream_is="live", self_test=True)          # our simulator can't be called live
    assert st.sim.input_source == InputSources.SIMULATED
    assert "Live" not in st.window.input_label.text()


def test_the_board_never_chooses(qapp):
    with pytest.raises(ValueError, match="chooses by keyboard"):
        App(InputSources.SIMULATED, view=FakeView(), speaker=FakeSpeaker(), echo=False,
            pieeg={"stream_is": "simulated"})
    with pytest.raises(ValueError, match="2 closures"):
        app_live.PiEEGConfirm(None, None, print, stream_is="live", closures=1)


@pytest.mark.parametrize("args, message", [
    (["--input", "pieeg"], "say what is publishing"),
    (["--input", "pieeg", "--pieeg-self-test", "--pieeg", "live"], "can't be labelled live"),
    (["--input", "pieeg", "--pieeg", "live", "--arm-live-confirm"], "check in this session decides"),
    (["--input", "pieeg", "--pieeg", "live", "--p300"], "the board only confirms"),
    (["--input", "pieeg", "--pieeg", "live", "--closures", "1"], "at least 2"),
    (["--input", "live", "--pieeg", "live"], "only for --input pieeg"),
    (["--input", "keyboard", "--channels", "3,7"], "only for --input pieeg"),
])
def test_cli_refuses_unlabelled_or_unsafe_runs(qapp, capsys, args, message):
    assert app_module.main(args) == 2
    assert message in capsys.readouterr().err


def test_a_stream_error_during_the_check_fails_safe(make, monkeypatch):
    """Any failure mid-check leaves key 1 confirming instead of ending the demo."""
    app, _ = make(stream_is="live")
    sim = app.sim

    class Relay:
        name, channels, rate, rows = "S2S-Gone", 16, 250.0, 1

        def stop(self):
            pass
    sim.relay, sim.device = Relay(), devices.PIEEG_OCTOPUS16

    def gone(*a, **k):
        raise RuntimeError("LSL stream 'S2S-Gone' disappeared")
    monkeypatch.setattr(lsl, "choose_channels", gone)
    assert sim.calibrate() is False
    assert "disappeared" in sim.reasons[0] and not app.handler.live_eeg_confirm_armed


def test_cli_without_a_stream_exits_3_with_board_help(qapp, monkeypatch, capsys):
    from signal2speech.eeg import pieeg_lsl

    def missing(*a, **k):
        raise pieeg_lsl.PiEEGStreamNotFound("none")
    monkeypatch.setattr(lsl, "find_stream", missing)
    assert app_module.main(["--input", "pieeg", "--pieeg", "live", "--mute", "--no-report"]) == 3
    err = capsys.readouterr().err
    assert "no LSL stream 'Octopus16'" in err and "power bank" in err
