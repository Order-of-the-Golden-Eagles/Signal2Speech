"""#47: one deliberate eye closure in an armed Confirm round -> exactly one target-1."""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("gpype")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.core import (ActionIds, InputAdapter, InputSources, Outcome,  # noqa: E402
                                SelectionHandler, TargetIds)
from signal2speech.eeg.alpha_confirm import (AlphaBursts, AlphaConfirm, Calibration,  # noqa: E402
                                             CalibrationError)
from signal2speech.ui.__main__ import load_demo_choices  # noqa: E402


@pytest.fixture(scope="module")
def app():
    # QApplication, not QCoreApplication: the first app created wins, and #24 widgets need it.
    return QApplication.instance() or QApplication([])


class Sink:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


@pytest.fixture
def rig(app):
    sink = Sink()
    h = SelectionHandler(sink)
    log = []
    h.on_handled.append(lambda e, o: log.append((e, o)))
    made = []

    def make(**kw):
        ac = AlphaConfirm(h, **kw)
        made.append(ac)
        return ac

    yield app, h, sink, log, make
    for ac in made:
        ac.close()


def open_confirm_round(h):
    h.begin_choice_round(load_demo_choices())
    assert InputAdapter(h, InputSources.KEYBOARD).select_now(TargetIds.TARGET_2) is Outcome.Previewed


# ── Calibration ──────────────────────────────────────────────
def test_calibration_sits_between_open_and_closed():
    cal = Calibration.from_samples([5, 6, 7, 6, 5, 8, 6], [60, 70, 80, 75, 65, 72])
    assert cal.open_p95 < cal.release < cal.level < cal.closed_median
    assert cal.ratio > 2


def test_calibration_refuses_a_switch_that_would_false_trigger():
    with pytest.raises(CalibrationError):
        Calibration.from_samples([5, 6, 7, 6, 5, 8], [8, 9, 10, 9, 8, 9])
    with pytest.raises(CalibrationError):
        Calibration.from_samples([5, 6], [60, 70])


# ── Round gating (no stream needed) ──────────────────────────
def test_one_closure_after_settle_confirms_exactly_once(rig):
    _, h, sink, log, make = rig
    ac = make(settle_s=1.0)
    open_confirm_round(h)
    assert ac.armed
    t0 = ac._armed_at
    ac._on_rising(t0 + 0.3)                 # too soon: closure may have begun last round
    assert sink.actions == [] and h.current is not None
    ac._on_falling(t0 + 0.4)
    ac._on_rising(t0 + 1.6)                 # eyes open 1.2 s, then a deliberate closure
    assert len(sink.actions) == 1
    assert sink.actions[0].action_id == ActionIds.COMPARE_AIR_QUALITY
    e, o = log[-1]
    assert (o, e.source, e.targetId) == (Outcome.Confirmed, InputSources.SIMULATED,
                                         TargetIds.TARGET_1)
    ac._on_falling(t0 + 2.0)
    ac._on_rising(t0 + 4.0)                 # a second closure does nothing
    assert len(sink.actions) == 1 and not ac.armed


def test_closures_outside_a_confirm_round_are_ignored(rig):
    _, h, sink, log, make = rig
    ac = make()
    ac._on_rising(time.monotonic())         # no round at all
    h.begin_choice_round(load_demo_choices())
    ac._on_falling(time.monotonic())
    ac._on_rising(time.monotonic() + 5)     # Choose round: alpha never picks a tile
    assert log == [] and sink.actions == [] and not ac.armed


def test_eyes_already_closed_at_arming_must_open_first(rig):
    _, h, sink, _, make = rig
    ac = make(settle_s=1.0)
    ac.state = 1                            # closed while the preview appears
    open_confirm_round(h)
    t0 = ac._armed_at
    ac._on_rising(t0 + 3.0)                 # no falling edge yet: ignored
    assert sink.actions == []
    ac._on_falling(t0 + 3.1)
    ac._on_rising(t0 + 3.5)                 # open only 0.4 s: ignored
    assert sink.actions == []
    ac._on_falling(t0 + 3.6)
    ac._on_rising(t0 + 4.8)
    assert len(sink.actions) == 1


def test_cancel_disarms(rig):
    _, h, sink, _, make = rig
    ac = make(settle_s=0.0)
    open_confirm_round(h)
    h.cancel()
    ac._on_rising(time.monotonic() + 2)
    assert sink.actions == [] and not ac.armed


def test_live_confirm_stays_disarmed_in_the_handler_until_23(rig):
    _, h, sink, log, make = rig
    ac = make(input_source=InputSources.LIVE_EEG, settle_s=0.0)
    open_confirm_round(h)
    ac._on_rising(ac._armed_at + 0.1)
    assert log[-1][1] is Outcome.RejectedLiveConfirmDisarmed
    assert sink.actions == [] and h.current is not None   # keyboard can still confirm


# ── Through the real g.Pype pipeline ─────────────────────────
def test_generator_alpha_burst_confirms_once_through_gpype(rig):
    app, h, sink, log, make = rig
    bursts = AlphaBursts(amplitude_uv=8.0)
    ac = make(bursts=bursts, settle_s=0.5)
    ac.start()
    ac.collect(1.0)                                     # fill the 1 s FFT window
    open_vals = ac.collect(1.0)
    bursts.close_eyes()
    ac.collect(1.0)
    closed_vals = ac.collect(1.0)
    bursts.open_eyes()
    cal = ac.calibrate(open_vals, closed_vals)
    assert cal.ratio > 2
    ac.collect(1.5)                                     # alpha decays below release
    assert ac.threshold.get_control()["level"] == pytest.approx(cal.level)

    rest_edges = len(ac.edges)
    ac.collect(1.0)
    assert len(ac.edges) == rest_edges                  # no false trigger at rest

    open_confirm_round(h)
    ac.collect(0.6)                                     # past settle_s, eyes open
    bursts.close_eyes()
    ac.collect(2.0)
    bursts.open_eyes()
    ac.collect(1.0)

    assert len(sink.actions) == 1
    assert [o for _, o in log] == [Outcome.Previewed, Outcome.Confirmed]
    assert log[-1][0].source == InputSources.SIMULATED
    assert len(ac.edges) - rest_edges == 1              # one closure, one edge
    assert set(ac.decision_threads) == {threading.main_thread().name}


# ── Review fixes (PR #58) ────────────────────────────────────
def test_an_ignored_early_closure_restarts_the_settle_clock(rig):
    _, h, sink, _, make = rig
    ac = make(settle_s=1.0)
    open_confirm_round(h)
    t0 = ac._armed_at
    ac._on_rising(t0 + 0.3)                 # too soon: ignored
    ac._on_falling(t0 + 0.4)                # eyes open from here
    ac._on_rising(t0 + 1.1)                 # open only 0.7 s: must not confirm
    assert sink.actions == []
    ac._on_falling(t0 + 1.2)
    ac._on_rising(t0 + 2.3)                 # open 1.1 s
    assert len(sink.actions) == 1


def test_arming_reads_the_worker_state_not_the_lagging_copy(rig):
    _, h, sink, _, make = rig
    ac = make(settle_s=1.0)
    ac._state = 1                           # worker saw eyes close; queued edge not delivered yet
    open_confirm_round(h)
    assert ac._open_since is None
    ac._on_rising(ac._armed_at - 0.1)       # the late edge from before arming: ignored
    ac._on_rising(ac._armed_at + 5.0)       # no falling edge yet: still ignored
    assert sink.actions == []


def test_calibration_refuses_nan_band_power():
    with pytest.raises(CalibrationError):
        Calibration.from_samples([5, 6, float("nan"), 6, 5, 8], [60, 70, 80, 75, 65, 72])


def test_rejected_live_confirm_keeps_listening_in_that_round(rig):
    _, h, sink, log, make = rig
    ac = make(input_source=InputSources.LIVE_EEG, settle_s=0.0)
    open_confirm_round(h)
    t0 = ac._armed_at
    ac._on_rising(t0 + 0.1)
    assert log[-1][1] is Outcome.RejectedLiveConfirmDisarmed and ac.armed
    h.live_eeg_confirm_armed = True         # #23 arms live confirm while the round is open
    ac._on_falling(t0 + 0.5)
    ac._on_rising(t0 + 0.9)
    assert log[-1][1] is Outcome.Confirmed and len(sink.actions) == 1


def test_close_unhooks_from_the_handler(rig):
    _, h, sink, _, make = rig
    ac = make()
    ac.close()
    assert ac._on_round_opened not in h.on_round_opened and ac._on_cleared not in h.on_cleared
    open_confirm_round(h)
    assert not ac.armed


def test_buffers_are_bounded():
    import numpy as np
    h = SelectionHandler(Sink())
    ac = AlphaConfirm(h)
    try:
        ac._on_power_rows(np.ones((ac._power.maxlen + 500, 1)))
        assert len(ac._power) == ac._power.maxlen
        assert ac.power_count() == ac._power.maxlen + 500
        assert len(ac.power_since(ac.power_count() - 10)) == 10
    finally:
        ac.close()


def test_fft_and_dwell_follow_the_sampling_rate():
    h = SelectionHandler(Sink())
    ac = AlphaConfirm(h, sampling_rate=500.0, dwell_s=1.0)
    try:
        assert ac.fft_window == 500 and ac.frame_rate == pytest.approx(10.0)
        assert ac.dwell == 10                   # still 1.0 s of band-power rows
    finally:
        ac.close()
