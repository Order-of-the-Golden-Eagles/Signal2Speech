"""#104: recorded human EEG chooses the tile in the app.

CI has no g.tec dataset (it is for Hack the Nest projects only and is never committed), so the
end-to-end test builds its own small "recording" from the synthetic P300 shape plus noise. One
extra test runs on the real dataset when it is present on the machine.
"""
import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
if importlib.util.find_spec("gpype") is None or importlib.util.find_spec("sklearn") is None:
    pytest.skip("g.Pype and scikit-learn are needed for the recorded path", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech import app as app_module  # noqa: E402
from signal2speech.app import App  # noqa: E402
from signal2speech.core import ActionIds, InputSources, Outcome, TargetIds  # noqa: E402
from signal2speech.eeg import app_live, p300  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2
SAMPLES = int(p300.TIME_POST * p300.RATE)


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


def made_up_recording(n=120, seed=3) -> p300.RecordedResponses:
    """Stands in for a real recording: noisy single-flash responses, attended ones with a P300."""
    rng = np.random.default_rng(seed)
    shape = p300.p300_template(p300.RATE, amplitude=6.0, duration=p300.TIME_POST)[:SAMPLES]
    noise = lambda: rng.normal(0, 4.0, (n, SAMPLES, p300.EEG_CHANNELS))
    return p300.RecordedResponses(noise() + shape[None], noise(), name="made-up test recording", seed=seed)


def test_each_recorded_response_is_used_once_before_any_is_repeated():
    target = np.arange(3)[:, None, None] * np.ones((3, SAMPLES, p300.EEG_CHANNELS))
    r = p300.RecordedResponses(target, target + 10, name="t")
    first = sorted(int(r.next(True)[0, 0]) for _ in range(3))
    assert first == [0, 1, 2] and r.reused == 0                    # all three, each once
    assert int(r.next(False)[0, 0]) >= 10                          # unattended come from their own pool
    r.next(True)
    assert r.reused == 3 and r.served == {True: 4, False: 1}       # a second pass is counted, not hidden
    with pytest.raises(ValueError, match="channels"):
        p300.RecordedResponses(np.zeros((2, SAMPLES, 3)), np.zeros((2, SAMPLES, 3)))
    with pytest.raises(ValueError, match="needs RecordedResponses"):
        p300.build_pipeline("recorded")


def test_recorded_responses_choose_the_tile_and_the_app_labels_it(qapp):
    """The whole path: recorded responses -> g.Pype pipeline -> calibration -> a pick -> preview
    -> simulated eye closure -> one map action and one spoken line. Labels say what did what."""
    app = App(InputSources.RECORDED, view=FakeView(), speaker=FakeSpeaker(), echo=False,
              recording=made_up_recording(), sim_script=[2, 1], confirm_timeout_ms=0, reopen_ms=60_000,
              live_options={"calibration_sequences": 6, "alpha_calib_s": 1.5})
    log = []
    app.handler.on_handled.append(lambda e, o: log.append((e, o)))
    try:
        assert isinstance(app.sim, app_live.RecordedEegInput)
        assert app.window.flash_enabled                                # the tiles must flash
        assert "Recorded (g.tec dataset, re-mapped to our tiles)" in app.input_summary()
        assert "Confirm: Simulated" in app.input_summary()
        app.sim.start()
        assert app.sim.calibrate({c.target_id: c.label for c in app.choices})
        assert app.sim.p300_calibration["target_epochs"] > 0
        app.ask()
        assert app_live.pump(40, until=lambda: len(app.view.calls) == 1), [o for _, o in log]
        app_live.pump(1.0)
        assert len(app.view.calls) == 1 and len(app.speaker.said) == 1
        outcomes = [(o, e.source, e.targetId) for e, o in log if e is not None and not o.rejected]
        assert outcomes == [(Outcome.Previewed, InputSources.RECORDED, T2),      # recorded EEG chose
                            (Outcome.Confirmed, InputSources.SIMULATED, T1)]     # simulated eyes confirmed
        f = app.window.flasher
        assert f.flash_ms + f.isi_ms == int(p300.RECORDED_SOA_S * 1000)            # slower flashes
        used = app.sim.usage()
        assert used["target_responses"] > 0 and used["nontarget_responses"] > 0 and used["played_twice"] == 0
    finally:
        app.close()
        app.root.close()


GTEC = Path(os.environ.get(app_module.RECORDING_ENV) or app_module.DEFAULT_RECORDING)


@pytest.mark.skipif(not GTEC.is_file(), reason="g.tec's P300 Speller dataset isn't on this machine")
def test_real_gtec_recording_loads_as_responses():
    r = p300.RecordedResponses.from_gtec(GTEC)
    assert "g.tec P300 Speller dataset" in r.name
    for attended in (True, False):
        assert r.pools[attended].shape[1:] == (SAMPLES, p300.EEG_CHANNELS)
    assert len(r.pools[True]) >= 100 and len(r.pools[False]) > len(r.pools[True])
    # Attended and unattended responses really differ, at some channel and time after the flash:
    # that difference is the human P300 the classifier works from.
    diff = r.pools[True].mean(axis=0) - r.pools[False].mean(axis=0)
    assert np.abs(diff[int(0.2 * p300.RATE):int(0.6 * p300.RATE)]).max() > 3.0
