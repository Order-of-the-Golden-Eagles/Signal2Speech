"""UI checks for #24. Run: pytest signal2speech/ui (offscreen, no headset, no g.Pype)."""
import os
import random
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.core import (InputAdapter, InputSources, Outcome, SelectionEvent,  # noqa: E402
                                SelectionHandler, TargetIds)
from signal2speech.ui import FlashScheduler, SelectionWindow  # noqa: E402
from signal2speech.ui.__main__ import load_demo_choices, main  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Sink:
    def __init__(self):
        self.actions = []

    def execute(self, a):
        self.actions.append(a)


@pytest.fixture
def ui(app):
    sink = Sink()
    h = SelectionHandler(sink)
    kb = InputAdapter(h, InputSources.KEYBOARD)
    flashes = []
    w = SelectionWindow(h, kb, on_flash=flashes.append)
    yield h, w, sink, flashes
    w.close()


def pump(app, ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.002)


def test_round_renders_frozen_labels(ui):
    h, w, _, _ = ui
    h.begin_choice_round(load_demo_choices())
    assert w.tiles[T1].label == "Show the satellite view"
    assert w.tiles[T2].label == "Compare counties"
    assert "r1 (choose)" in w.round_label.text()
    assert not w.preview.isVisibleTo(w)
    assert w.input_label.text() == "Input: Keyboard"


def test_key_preview_then_confirm_sends_one_effect(ui):
    h, w, sink, _ = ui
    h.begin_choice_round(load_demo_choices())
    assert w.press_target(T2) is Outcome.Previewed
    assert sink.actions == []                               # preview: no output
    assert w.preview.isVisibleTo(w)
    assert "Washtenaw's AQI rose 186 points" in w.preview.text()
    assert (w.tiles[T1].label, w.tiles[T2].label) == ("Confirm", "Cancel")
    assert "r2 (confirm)" in w.round_label.text()
    assert w.outcome_label.text().startswith("Last: Previewed")

    assert w.press_target(T1) is Outcome.Confirmed
    assert [a.action_id for a in sink.actions] == ["compare_air_quality"]
    assert w.press_target(T1) is Outcome.RejectedNoOpenRound   # repeat: no second effect
    assert len(sink.actions) == 1
    assert w.tiles[T1].label == "" and not w.preview.isVisibleTo(w)
    assert "RejectedNoOpenRound" in w.outcome_label.text()


def test_key2_in_confirm_cancels_and_clears(ui):
    h, w, sink, _ = ui
    h.begin_choice_round(load_demo_choices())
    w.press_target(T2)
    assert w.press_target(T2) is Outcome.Cancelled
    assert sink.actions == [] and h.current is None
    assert not w.preview.isVisibleTo(w) and w.round_label.text() == "Round: —"
    assert "Cancelled" in w.outcome_label.text()


def test_esc_calls_handler_cancel(ui):
    h, w, sink, _ = ui
    h.begin_choice_round(load_demo_choices())
    w.press_target(T1)
    w.press_cancel()
    assert h.current is None and h.pending is None and sink.actions == []
    assert w.tiles[T1].label == "" and "Cleared (cancel)" in w.outcome_label.text()


def test_stale_event_only_updates_strip(ui):
    h, w, _, _ = ui
    h.begin_choice_round(load_demo_choices())
    w.press_target(T2)
    h.handle(SelectionEvent(InputSources.LIVE_EEG, "r1", "e7", T1))
    assert "RejectedStaleRound" in w.outcome_label.text()
    assert w.preview.isVisibleTo(w) and h.current.id == "r2"


def test_input_label_is_honest(ui):
    _, w, _, _ = ui
    w.set_input_source(InputSources.SIMULATED)
    assert w.input_label.text() == "Input: Simulated"
    w.set_input_source(InputSources.LIVE_EEG)
    assert w.input_label.text() == "Input: Live EEG"


def test_keyboard_adapter_required(app):
    h = SelectionHandler(Sink())
    with pytest.raises(ValueError):
        SelectionWindow(h, InputAdapter(h, InputSources.LIVE_EEG))


def test_flash_calls_on_flash_after_tile_lights(app):
    events = []
    lit = {}

    def set_lit(t, on):
        lit[t] = on
        events.append(("lit" if on else "dark", t))

    def on_flash(t):
        assert lit[t] is True                     # tile already lit when the marker fires
        events.append(("flash", t))

    done = []
    s = FlashScheduler(set_lit, on_flash, flash_ms=5, isi_ms=5, repetitions=3,
                       rng=random.Random(1), on_sequence_started=lambda: done.append("start"),
                       on_sequence_finished=lambda: done.append("end"))
    s.start([T1, T2])
    pump(app, 400)
    flashes = [t for kind, t in events if kind == "flash"]
    assert sorted(flashes) == [T1, T1, T1, T2, T2, T2]
    assert all(a != b for a, b in zip(flashes, flashes[1:]))   # no target twice in a row
    for i, (kind, t) in enumerate(events):
        if kind == "flash":
            assert events[i - 1] == ("lit", t)
    assert done == ["start", "end"] and not any(lit.values()) and not s.running


def test_window_flashes_choose_rounds_and_stops_on_preview(app):
    h = SelectionHandler(Sink())
    flashes = []
    w = SelectionWindow(h, InputAdapter(h, InputSources.KEYBOARD), flash=True,
                        on_flash=flashes.append)
    w.flasher.flash_ms = w.flasher.isi_ms = 5
    h.begin_choice_round(load_demo_choices())
    assert w.flasher.running and flashes            # first flash is synchronous
    w.press_target(T2)
    assert not w.flasher.running                   # Confirm round never flashes
    assert not any(t.lit for t in w.tiles.values())
    n = len(flashes)
    pump(app, 50)
    assert len(flashes) == n
    w.close()


def test_main_screenshot(app, tmp_path):
    out = tmp_path / "ui.png"
    assert main(["--keys", "2", "--screenshot", str(out)]) == 0
    assert out.stat().st_size > 0
