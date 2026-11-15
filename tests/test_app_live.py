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
    assert app.window.hint.text() == app_live.DISARMED_HINT
    assert app.window.press_target(T1) is Outcome.Confirmed     # key 1 confirms while disarmed
    assert app.view.calls == [ActionIds.COMPARE_AIR_QUALITY]


def test_arm_live_confirm_flag(qapp, make):
    app, log = make(InputSources.LIVE_EEG, arm_live_confirm=True, confirm_timeout_ms=0)
    assert app.handler.live_eeg_confirm_armed is True
    assert "eye confirm armed" in app.sim.connection_label()
    app.ask()
    app.window.flasher.stop()
    app.window.press_target(T2)
    assert app.window.hint.text() != app_live.DISARMED_HINT


def test_live_without_a_headset_exits_3_with_pairing_help(qapp, monkeypatch, capsys):
    monkeypatch.setattr(app_live, "find_unicorn", lambda timeout_s=15.0: [])
    t = time.monotonic()
    assert app_module.main(["--input", "live", "--mute"]) == 3
    assert time.monotonic() - t < 15
    err = capsys.readouterr().err
    assert "no Unicorn Hybrid Black found" in err and "pair it in the OS Bluetooth" in err
