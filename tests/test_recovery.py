"""#26: cancel, disconnect, duplicate, and stale input never fire an extra effect.

Everything runs through the real App (handler, window, adapters, AppSink) with a fake map and
speaker. Sources are labelled as they are: keyboard, simulated (a real g.Pype Generator stream
through #21's SimulatedDecoder), and recorded (contract events replayed as `recorded`).
Live EEG is out of scope until #23.
"""
import json
import os
import time
from pathlib import Path

import importlib.util

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

# g.Pype can't be installed everywhere (e.g. macOS 12, Intel Macs). These tests need it; the
# rest of the file is pure Python. CI installs g.Pype, so they still run there (#98).
needs_gpype = pytest.mark.skipif(importlib.util.find_spec("gpype") is None,
                                 reason="needs g.Pype: pip install -r requirements-lock.txt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import (ActionIds, InputSources, Outcome, SelectionEvent,  # noqa: E402
                                TargetIds)

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2
EVENTS = Path(__file__).resolve().parents[1] / "contracts" / "events"
KB, SIM, REC = InputSources.KEYBOARD, InputSources.SIMULATED, InputSources.RECORDED


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
def rig(qapp):
    made = []

    def make(source=KB, **kw):
        kw.setdefault("reopen_ms", 60_000)       # no automatic next question during a test
        app = App(source, view=FakeView(), speaker=FakeSpeaker(), echo=False, **kw)
        log = []
        app.handler.on_handled.append(lambda e, o: log.append((e, o)))
        cleared = []
        app.handler.on_cleared.append(cleared.append)
        if source == SIM:
            app.window.flasher.flash_ms = app.window.flasher.isi_ms = 5
            app.window.flasher.repetitions = 1
        made.append(app)
        app.ask()
        return app, log, cleared

    yield make
    for app in made:
        app.close()
        app.root.close()


def pump(qapp, until=lambda: False, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()
    return until()


def outputs(app):
    return len(app.view.calls), len(app.speaker.said)


def preview(qapp, app, source):
    """Open a preview of 'Compare counties' from the given source; return the Confirm round."""
    if source == KB:
        assert app.window.press_target(T2) is Outcome.Previewed
    else:                                         # SIM: script [2] picks target-2 after flashing
        assert pump(qapp, lambda: app.handler.pending is not None), "simulated preview"
    rnd = app.handler.current
    assert rnd is not None and rnd.kind.value == "confirm"
    assert outputs(app) == (0, 0)                 # a preview never outputs
    return rnd


def recorded(name, **override):
    d = json.loads((EVENTS / name).read_text(encoding="utf-8"))
    d.update(source=REC, **override)
    return SelectionEvent.from_dict(d)


# ── Cancel during preview ────────────────────────────────────
@pytest.mark.parametrize("source", [KB, SIM])
@pytest.mark.parametrize("how", ["esc", "key2", "timeout"])
def test_cancel_during_preview_outputs_nothing(qapp, rig, source, how):
    kw = {"sim_script": [2]} if source == SIM else {}   # SIM: choose only, never confirms
    app, log, cleared = rig(source, confirm_timeout_ms=300 if how == "timeout" else 0, **kw)
    preview(qapp, app, source)
    if how == "esc":
        app.window.press_cancel()
    elif how == "key2":
        assert app.window.press_target(T2) is Outcome.Cancelled
    else:
        assert pump(qapp, lambda: cleared, timeout=3.0), "confirm timeout never fired"
    assert app.handler.current is None and app.handler.pending is None
    expected = {"esc": "cancel", "key2": "cancel", "timeout": "timeout"}[how]
    assert cleared == [expected]
    pump(qapp, timeout=0.4)                       # anything late (sim decisions) lands here
    assert outputs(app) == (0, 0)


def test_timeout_off_keeps_the_preview(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    preview(qapp, app, KB)
    pump(qapp, timeout=0.5)
    assert cleared == [] and app.handler.current is not None


def test_confirm_inside_the_timeout_outputs_once_and_stops_the_timer(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=300)
    preview(qapp, app, KB)
    assert app.window.press_target(T1) is Outcome.Confirmed
    pump(qapp, timeout=0.6)                       # past the timeout: no late cancel
    assert outputs(app) == (1, 1) and cleared == []


# ── Disconnect during preview ────────────────────────────────
def test_keyboard_disconnect_key_during_preview(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    preview(qapp, app, KB)
    app.handler.disconnect()                      # what key D does
    assert app.window.press_target(T1) is Outcome.RejectedNoOpenRound
    assert cleared == ["disconnect"] and outputs(app) == (0, 0)


@needs_gpype
def test_gpype_stream_stop_during_preview(qapp, rig):
    app, log, cleared = rig(SIM, sim_script=[2, 1], confirm_delay_ms=1500, confirm_timeout_ms=0)
    preview(qapp, app, SIM)
    seq = app.sim._pending_seq                    # the Confirm decision is now in flight
    app.sim.disconnect_stream()                   # g.Pype source stops, round clears
    assert cleared == ["disconnect"] and not app.sim.running
    app.sim.decided.emit(seq, 1)                  # a late confirm from the stopped stream
    pump(qapp, timeout=0.5)
    assert seq in app.sim.dropped
    assert outputs(app) == (0, 0)


# ── Duplicate events ─────────────────────────────────────────
def test_duplicate_keyboard_event_is_rejected(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    e = SelectionEvent(KB, "r1", "k99", T2)
    assert app.handler.handle(e) is Outcome.Previewed
    assert app.handler.handle(e) is Outcome.RejectedStaleRound     # round moved on to r2
    # The same event id again, now stamped with the open round: a true duplicate.
    assert app.handler.handle(SelectionEvent(KB, "r2", "k99", T1)) is Outcome.RejectedDuplicateEvent
    assert app.handler.current is not None and outputs(app) == (0, 0)
    confirm = SelectionEvent(KB, "r2", "k100", T1)
    assert app.handler.handle(confirm) is Outcome.Confirmed
    assert app.handler.handle(confirm) is Outcome.RejectedNoOpenRound
    assert outputs(app) == (1, 1)


def test_held_or_repeated_confirm_key_outputs_once(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    preview(qapp, app, KB)
    results = [app.window.press_target(T1) for _ in range(3)]
    assert results[0] is Outcome.Confirmed and all(r.rejected for r in results[1:])
    assert outputs(app) == (1, 1)


@needs_gpype
def test_duplicate_simulated_decision_outputs_once(qapp, rig):
    app, log, cleared = rig(SIM, sim_script=[2, 1], confirm_delay_ms=200, confirm_timeout_ms=0)
    preview(qapp, app, SIM)
    seq = app.sim._pending_seq
    assert pump(qapp, lambda: outputs(app) == (1, 1)), "simulated confirm"
    app.sim.decided.emit(seq, 1)                  # the same decision delivered again
    pump(qapp, timeout=0.4)
    assert seq in app.sim.dropped and outputs(app) == (1, 1)


def test_replayed_recording_twice_outputs_once(qapp, rig):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    session = [recorded("preview.json"), recorded("confirm-fresh.json")]
    first = [app.handler.handle(e) for e in session]
    second = [app.handler.handle(e) for e in session]         # the same replay again
    assert first == [Outcome.Previewed, Outcome.Confirmed]
    assert all(o.rejected for o in second)
    assert outputs(app) == (1, 1)
    assert all(e.source == REC for e, _ in log)


# ── Stale events ─────────────────────────────────────────────
@pytest.mark.parametrize("source", [KB, REC])
def test_stale_choose_decision_cannot_confirm(qapp, rig, source):
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    preview(qapp, app, KB)                        # now in Confirm round r2
    late = (recorded("stale.json") if source == REC
            else SelectionEvent(KB, "r1", "k50", T1))   # a target-1 stamped with old round r1
    assert app.handler.handle(late) is Outcome.RejectedStaleRound
    assert app.handler.current is not None and outputs(app) == (0, 0)


@needs_gpype
def test_late_simulated_decision_from_a_closed_round_is_dropped(qapp, rig):
    app, log, cleared = rig(SIM, sim_script=[2], confirm_timeout_ms=0)
    preview(qapp, app, SIM)
    old = app.sim._pending_seq                    # Confirm round's sequence (no pick queued)
    app.window.press_cancel()
    app.ask()                                     # next question opens and starts flashing
    app.sim.decided.emit(old, 1)                  # the old round's "confirm" arrives late
    pump(qapp, timeout=0.4)
    assert old in app.sim.dropped and outputs(app) == (0, 0)


# ── Everything at once ───────────────────────────────────────
def test_gauntlet_then_one_good_confirm(qapp, rig):
    """Every bad input in one session, then one deliberate confirm: exactly one output."""
    app, log, cleared = rig(KB, confirm_timeout_ms=0)
    accepted = []                                                 # ids the handler accepted
    app.handler.on_handled.append(lambda e, o: accepted.append(e.eventId) if e and not o.rejected else None)
    preview(qapp, app, KB)
    app.window.press_cancel()                                     # cancel
    app.ask()
    preview(qapp, app, KB)
    app.handler.disconnect()                                      # disconnect
    app.ask()
    preview(qapp, app, KB)
    assert app.handler.handle(recorded("stale.json", roundId="r1")) is Outcome.RejectedStaleRound
    # Replay the first preview's real id (ids come from one process-wide counter, not "k1").
    dup = SelectionEvent(KB, app.handler.current.id, accepted[0], T1)
    assert app.handler.handle(dup) is Outcome.RejectedDuplicateEvent
    assert outputs(app) == (0, 0)
    assert app.window.press_target(T1) is Outcome.Confirmed       # the one real confirm
    app.window.press_target(T1)                                   # repeat
    assert outputs(app) == (1, 1)
    assert app.view.calls == [ActionIds.COMPARE_AIR_QUALITY]
