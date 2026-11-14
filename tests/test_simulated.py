"""#21: simulated decisions travel g.Pype worker thread -> Qt signal -> main thread -> adapter."""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("gpype")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.core import (ActionIds, InputSources, Outcome, SelectionHandler,  # noqa: E402
                                TargetIds)
from signal2speech.eeg.simulated import SimulatedDecoder, main, parse_picks  # noqa: E402
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


def spin(app, until, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return until()


@pytest.fixture
def rig(app):
    sink = Sink()
    h = SelectionHandler(sink)
    log = []
    h.on_handled.append(lambda e, o: log.append((e, o)))
    made = []

    def make(picks=(), **kw):
        d = SimulatedDecoder(h, picks, decision_s=kw.pop("decision_s", 0.2), **kw)
        made.append(d)
        return d

    yield app, h, sink, log, make
    for d in made:
        d.close()


def test_preview_then_confirm_through_gpype(rig):
    app, h, sink, log, make = rig
    dec = make([2, 1])
    dec.start()
    h.begin_choice_round(load_demo_choices())
    assert spin(app, lambda: len(sink.actions) == 1)

    (e1, o1), (e2, o2) = log
    assert (o1, e1.source, e1.roundId, e1.targetId) == (
        Outcome.Previewed, InputSources.SIMULATED, "r1", TargetIds.TARGET_2)
    assert (o2, e2.source, e2.roundId, e2.targetId) == (
        Outcome.Confirmed, InputSources.SIMULATED, "r2", TargetIds.TARGET_1)
    assert sink.actions[0].action_id == ActionIds.COMPARE_AIR_QUALITY
    assert sink.actions[0].source == InputSources.SIMULATED
    # Decisions came off the g.Pype stream and were handled on the main thread only.
    assert dec.sink.samples_seen > 0
    assert set(dec.decision_threads) == {threading.main_thread().name}


def test_cancel_choice_round_gives_no_output(rig):
    app, h, sink, log, make = rig
    dec = make([2, 2])                      # pick tile 2, then target-2 = Cancel
    dec.start()
    h.begin_choice_round(load_demo_choices())
    assert spin(app, lambda: any(o is Outcome.Cancelled for _, o in log))
    spin(app, lambda: False, timeout=0.4)   # nothing else arrives
    assert sink.actions == []
    assert h.current is None


def test_stale_decision_is_dropped_before_the_adapter(rig):
    app, h, sink, log, make = rig
    dec = make()                            # no picks: sequences wait, no pipeline needed
    h.begin_choice_round(load_demo_choices())
    old = dec._seq
    h.cancel()                              # round closes; old sequence must not land later
    h.begin_choice_round(load_demo_choices())
    dec.decided.emit(old, 2)                # late result from the closed round
    spin(app, lambda: dec.dropped)
    assert list(dec.dropped) == [old]
    assert log == [] and sink.actions == []


def test_set_next_decides_a_waiting_sequence(rig):
    app, h, sink, log, make = rig
    dec = make()
    dec.start()
    h.begin_choice_round(load_demo_choices())
    dec.set_next(1)                         # Ctrl+1 in the window
    assert spin(app, lambda: log)
    e, o = log[0]
    assert (o, e.source, e.targetId) == (Outcome.Previewed, InputSources.SIMULATED,
                                         TargetIds.TARGET_1)
    assert sink.actions == []               # a preview never reaches output


def test_flasher_mode_decides_only_after_the_flash_sequence(rig):
    """Drop-in contract for app.py: arm on on_sequence_started, decide on on_sequence_finished."""
    from signal2speech.core import InputAdapter
    from signal2speech.ui import SelectionWindow

    app, h, sink, log, make = rig
    flashes = []
    win = SelectionWindow(h, InputAdapter(h, InputSources.KEYBOARD), flash=True,
                          on_flash=flashes.append)
    win.flasher.flash_ms, win.flasher.isi_ms, win.flasher.repetitions = 10, 5, 3
    at_preview = []
    h.on_preview.append(lambda _c: at_preview.append(len(flashes)))
    dec = make([2, 1], flasher=win.flasher, confirm_s=0.2)
    dec.start()
    h.begin_choice_round(load_demo_choices())
    assert spin(app, lambda: len(sink.actions) == 1)
    assert at_preview == [6]                # all 3 x 2 flashes ran before the decision
    assert [o for _, o in log] == [Outcome.Previewed, Outcome.Confirmed]
    assert all(e.source == InputSources.SIMULATED for e, _ in log)
    win.close()


def test_parse_picks_rejects_unknown_classes():
    assert parse_picks("2, 1") == [2, 1]
    with pytest.raises(Exception):
        parse_picks("3")


def test_headless_cli_runs_preview_and_confirm(app, capsys):
    assert main(["--picks", "2,1", "--decision-s", "0.2", "--timeout", "10"]) == 0
    out = capsys.readouterr().out
    assert '"outcome": "Previewed", "source": "simulated"' in out
    assert '"outcome": "Confirmed", "source": "simulated"' in out
    assert "compare_air_quality" in out


# ── Review fixes (PR #53) ────────────────────────────────────
def test_judge_cancel_gives_the_unused_pick_back(rig):
    app, h, sink, log, make = rig
    dec = make([2, 1], decision_s=30.0)     # decision far away: still pending at cancel
    h.begin_choice_round(load_demo_choices())
    assert dec._pick == 2
    h.cancel()                              # Esc: the same step comes again
    h.begin_choice_round(load_demo_choices())
    assert dec._pick == 2 and list(dec._picks) == [1]


def test_keyboard_using_the_round_drops_that_rounds_pick(rig):
    app, h, sink, log, make = rig
    from signal2speech.core import InputAdapter
    dec = make([2, 1], decision_s=30.0)
    h.begin_choice_round(load_demo_choices())
    InputAdapter(h, InputSources.KEYBOARD).select_now(TargetIds.TARGET_2)
    assert dec._pick == 1                   # Confirm round takes the confirm pick, not the 2


def test_set_next_waits_for_the_flash_sequence_to_end(rig):
    from signal2speech.core import InputAdapter
    from signal2speech.ui import SelectionWindow

    app, h, sink, log, make = rig
    flashes = []
    win = SelectionWindow(h, InputAdapter(h, InputSources.KEYBOARD), flash=True,
                          on_flash=flashes.append)
    win.flasher.flash_ms, win.flasher.isi_ms, win.flasher.repetitions = 10, 5, 3
    at_preview = []
    h.on_preview.append(lambda _c: at_preview.append(len(flashes)))
    dec = make(flasher=win.flasher)
    dec.start()
    h.begin_choice_round(load_demo_choices())
    dec.set_next(2)                         # Ctrl+2 during the first flash
    assert spin(app, lambda: at_preview)
    assert at_preview == [6]
    win.close()


def test_window_hooks_are_chained_and_restored_on_close(rig):
    from signal2speech.core import InputAdapter
    from signal2speech.ui import SelectionWindow

    app, h, sink, log, make = rig
    started = []
    win = SelectionWindow(h, InputAdapter(h, InputSources.KEYBOARD), flash=True,
                          on_sequence_started=lambda: started.append(1))
    original = win.flasher.on_sequence_started
    dec = make(flasher=win.flasher)
    h.begin_choice_round(load_demo_choices())
    assert started == [1] and dec._pending_seq is not None
    dec.close()
    assert win.flasher.on_sequence_started is original
    assert dec._on_round_opened not in h.on_round_opened
    seq = dec._seq
    h.begin_choice_round(load_demo_choices())
    assert dec._seq == seq                  # a closed decoder no longer arms
    win.close()


def test_headless_runs_several_rounds_then_exits(app, capsys):
    assert main(["--picks", "2,1,1,1", "--decision-s", "0.1", "--timeout", "10"]) == 0
    out = capsys.readouterr().out
    assert out.count('"outcome": "Confirmed"') == 2


def test_headless_timeout_exits_1(app, capsys):
    # One pick: the Confirm round waits for a pick that never comes.
    assert main(["--picks", "2", "--decision-s", "0.1", "--timeout", "1.5"]) == 1
    assert main(["--decision-s", "0.1"]) == 2   # headless with no picks is a usage error
