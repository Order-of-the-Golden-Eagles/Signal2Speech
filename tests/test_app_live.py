"""#103: live EEG inside the app. P300 chooses and the alpha switch confirms, on one pipeline.

The end-to-end test runs the live code path on the Generator plus a synthetic P300, labelled
Simulated. The live wiring is checked without hardware: building the HybridBlack graph doesn't
touch the device. Opening it is a manual step at the headset slot (#23).
"""
import importlib.util
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
if importlib.util.find_spec("gpype") is None or importlib.util.find_spec("sklearn") is None:
    pytest.skip("g.Pype and scikit-learn are needed for the live path", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech import app as app_module  # noqa: E402
from signal2speech.app import App  # noqa: E402
from signal2speech.core import (ActionIds, InputSources, Outcome, RoundKind,  # noqa: E402
                                TargetIds)
from signal2speech.eeg import app_live  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    # QApplication, not QCoreApplication: the first app created wins, and #24 widgets need it.
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

    def build(source, **kw):
        kw.setdefault("reopen_ms", 60_000)
        app = App(source, view=FakeView(), speaker=FakeSpeaker(), echo=False, **kw)
        log = []
        app.handler.on_handled.append(lambda e, o: log.append((e, o)))
        made.append(app)
        return app, log

    yield build
    for app in made:
        app.close()
        app.root.close()


def test_simulated_p300_path_previews_and_alpha_confirms_once(qapp, make):
    app, log = make(InputSources.SIMULATED, p300=True, sim_script=[2, 1], confirm_timeout_ms=0,
                    live_options={"calibration_sequences": 6, "alpha_calib_s": 1.5})
    assert isinstance(app.sim, app_live.LiveEegInput)
    app.sim.start()
    assert app.sim.calibrate({c.target_id: c.label for c in app.choices})
    assert app.sim.p300_calibration["target_epochs"] > 0 and app.sim.alpha_calibration
    app.ask()
    assert app_live.pump(25, until=lambda: len(app.view.calls) == 1), [o for _, o in log]
    app_live.pump(1.0)                                  # nothing extra arrives late
    assert len(app.view.calls) == 1 and len(app.speaker.said) == 1
    outcomes = [(o, e.source) for e, o in log if e is not None and not o.rejected]
    assert outcomes == [(Outcome.Previewed, InputSources.SIMULATED),
                        (Outcome.Confirmed, InputSources.SIMULATED)]
    # The chooser's flash timing drove the app's own tiles.
    f = app.window.flasher
    assert (f.repetitions, f.flash_ms, f.isi_ms) == (5, 100, 150)


def test_live_wiring_without_hardware(qapp, make):
    app, log = make(InputSources.LIVE_EEG, confirm_timeout_ms=0)
    live = app.sim
    assert isinstance(live, app_live.LiveEegInput) and not live.simulated
    assert app.window.flash_enabled
    assert app.window.input_label.text() == "Input: Live EEG"
    assert "eye confirm off (#23)" in live.connection_label()
    assert app.handler.live_eeg_confirm_armed is False
    assert live.alpha.pipeline is live.nodes.pipeline          # one headset, one pipeline
    assert live.alpha.adapter.source == InputSources.LIVE_EEG
    assert live.adapter.source == InputSources.LIVE_EEG

    app.ask()
    app.window.flasher.stop()                                   # no device: skip the flashes
    assert app.window.press_target(T2) is Outcome.Previewed     # keys still work
    assert app.handler.current.kind is RoundKind.CONFIRM
    assert "eye-closure confirm is off until #23" in app.window.hint.text()
    assert app.window.press_target(T1) is Outcome.Confirmed     # key 1 confirms while disarmed
    assert app.view.calls == [ActionIds.COMPARE_AIR_QUALITY]


def test_arm_live_confirm_flag(qapp, make):
    app, log = make(InputSources.LIVE_EEG, arm_live_confirm=True, confirm_timeout_ms=0)
    assert app.handler.live_eeg_confirm_armed is True
    assert "eye confirm armed" in app.sim.connection_label()
    app.ask()
    app.window.flasher.stop()
    app.window.press_target(T2)
    assert "close your eyes" in app.window.hint.text()


def test_live_without_a_headset_exits_3_with_pairing_help(qapp, monkeypatch, capsys):
    monkeypatch.setattr(app_live, "find_unicorn", lambda timeout_s=15.0: [])
    t = time.monotonic()
    assert app_module.main(["--input", "live", "--mute"]) == 3
    assert time.monotonic() - t < 15
    err = capsys.readouterr().err
    assert "no Unicorn Hybrid Black found" in err and "pair it in the OS Bluetooth" in err


# ── Review fixes (PR #120) ───────────────────────────────────
def test_failed_calibration_turns_that_path_off_and_says_so(qapp, make, monkeypatch):
    app, log = make(InputSources.LIVE_EEG, confirm_timeout_ms=0)
    live = app.sim
    monkeypatch.setattr(live, "_calibrate_p300", lambda labels, wait: False)
    monkeypatch.setattr(live, "_calibrate_alpha", lambda wait: False)
    assert live.calibrate() is False
    assert app.window.flash_enabled is False                    # no brain choosing
    assert "P300 OFF" in app.window.prompt.text() and "use key 1" in app.window.prompt.text()
    label = live.connection_label()
    assert "P300 off (calibration failed)" in label and "eye confirm off (calibration failed)" in label


def test_close_restores_the_flasher(qapp, make):
    app, log = make(InputSources.LIVE_EEG, confirm_timeout_ms=0)
    f = app.window.flasher
    hooks = app.sim._saved_flasher
    app.sim.close()
    assert (f.repetitions, f.flash_ms, f.isi_ms, f.on_sequence_started, f.on_flash,
            f.on_sequence_finished) == hooks and not f.running


def test_script_values_are_checked(qapp):
    with pytest.raises(ValueError):
        App(InputSources.SIMULATED, p300=True, sim_script=[3], view=FakeView(),
            speaker=FakeSpeaker(), echo=False)
    assert app_module.main(["--input", "simulated", "--p300", "--sim", "0"]) == 2


def test_spent_script_hands_over_to_keys(qapp, make):
    app, log = make(InputSources.SIMULATED, p300=True, sim_script=[2], confirm_timeout_ms=0)
    app.sim.script.clear()
    app.ask()                                                   # flashing would start here
    assert not app.window.flasher.running
    assert "press 1 or 2" in app.window.hint.text()


def test_no_decision_reflashes_then_hands_over(qapp, make, monkeypatch):
    app, log = make(InputSources.LIVE_EEG, confirm_timeout_ms=0)
    live = app.sim
    starts = []
    monkeypatch.setattr(app.window.flasher, "start", lambda targets: starts.append(targets))
    monkeypatch.setattr(live.chooser, "end_sequence", lambda: None)
    app.ask()
    for _ in range(app_live.MAX_REFLASH + 1):
        live._got_decision = False
        live._force_decision()
    assert len(starts) == 1 + app_live.MAX_REFLASH            # ask() plus the re-flashes
    assert "No brain decision" in app.window.hint.text()


def test_closing_the_window_during_calibration_exits_cleanly(qapp, monkeypatch):
    monkeypatch.setattr(app_live.LiveEegInput, "start", lambda self, no_data_s=8.0: None)
    monkeypatch.setattr(app_live.LiveEegInput, "calibrate", lambda self, labels=None: None)
    assert app_module.main(["--input", "live", "--mute"]) == 0


# ── Review fixes (PR #124) ───────────────────────────────────
def test_reflash_keeps_the_same_attention_and_script(qapp, make):
    app, log = make(InputSources.SIMULATED, p300=True, sim_script=[2, 1], confirm_timeout_ms=0)
    live = app.sim
    app.ask()                                   # flashing starts: pops 2 (attend tile 2)
    app.window.flasher.stop()
    assert list(live.script) == [1] and live._last_attended == T2
    live._got_decision = False
    live.chooser.end_sequence = lambda: None    # no scores arrived
    live._force_decision()                      # re-flash
    app.window.flasher.stop()
    assert list(live.script) == [1] and live._last_attended == T2   # nothing consumed


def test_hints_follow_failed_calibrations(qapp, make, monkeypatch):
    app, log = make(InputSources.SIMULATED, p300=True, sim_script=[2, 1], confirm_timeout_ms=0)
    live = app.sim
    monkeypatch.setattr(live, "_calibrate_p300", lambda labels, wait: False)
    monkeypatch.setattr(live, "_calibrate_alpha", lambda wait: True)
    live.calibrate()
    app.ask()
    assert "Press 1 or 2" in app.window.hint.text() and not app.window.flasher.running
    assert list(live.script) == [1]             # the Choose value was the keyboard's
    app.window.press_target(T2)
    assert live.eyes.closing()                  # the Confirm value (1) still closes the eyes

    app2, _ = make(InputSources.LIVE_EEG, arm_live_confirm=True, confirm_timeout_ms=0)
    monkeypatch.setattr(app2.sim, "_calibrate_p300", lambda labels, wait: True)
    monkeypatch.setattr(app2.sim, "_calibrate_alpha", lambda wait: False)
    app2.sim.calibrate()
    app2.ask()
    app2.window.flasher.stop()
    app2.window.press_target(T2)
    assert "calibration failed" in app2.window.hint.text()


def test_a_hung_open_leaves_the_pipeline_alone(qapp, make, monkeypatch):
    app, log = make(InputSources.LIVE_EEG, confirm_timeout_ms=0)
    live = app.sim
    monkeypatch.setattr(app_live, "find_unicorn", lambda timeout_s=15.0: ["UN-1"])
    monkeypatch.setattr(app_live, "_bounded", lambda fn, t, name: (False, None, None))
    closed = []
    monkeypatch.setattr(live.nodes.pipeline, "close", lambda: closed.append(1))
    with pytest.raises(RuntimeError, match="couldn't open it"):
        live.start()
    live.close()
    assert closed == []                          # start() is still inside it in its thread


def test_scan_errors_are_not_reported_as_not_paired(monkeypatch):
    monkeypatch.setattr(app_live, "_bounded", lambda fn, t, name: (True, None, OSError("no lib")))
    with pytest.raises(RuntimeError, match="couldn't search for a Unicorn"):
        app_live.find_unicorn()


def test_setup_and_calibration_errors_exit_cleanly(qapp, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("driver missing")
    monkeypatch.setattr(app_live.LiveEegInput, "__init__", boom)
    assert app_module.main(["--input", "live", "--mute"]) == 3
    assert "Couldn't set up the EEG pipeline" in capsys.readouterr().err
    monkeypatch.undo()

    closed = []
    monkeypatch.setattr(app_live.LiveEegInput, "start", lambda self, no_data_s=8.0: None)
    monkeypatch.setattr(app_live.LiveEegInput, "calibrate",
                        lambda self, labels=None: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(app_live.LiveEegInput, "close", lambda self: closed.append(1))
    assert app_module.main(["--input", "live", "--mute"]) == 1
    assert closed                                # the headset is released


def test_placeholder_model_is_built_once():
    assert app_live.placeholder_model() is app_live.placeholder_model()
