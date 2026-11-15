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
    # #174: the confirmed tile stays in its selected state; the other one waits.
    assert (w.tiles[T1].label, w.tiles[T1].state) == ("Confirm", "selected")
    assert w.tiles[T2].state == "waiting"
    # #175: a brief "Spoken" state keeps the confirmed words on screen until the next round.
    assert w.preview.isVisibleTo(w) and w.preview_header.text() == "✓ Shown and spoken"
    assert w.ring.model.completed
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
    end = time.monotonic() + 3.0          # wait for the sequence to finish, not a fixed time
    while time.monotonic() < end and done != ["start", "end"]:
        app.processEvents()
        time.sleep(0.002)
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


# ── #95: long text shrinks to fit ────────────────────────────
from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402

from signal2speech.ui.fit import MIN_PX, fit_pixel_size  # noqa: E402
from signal2speech.ui.window import Tile  # noqa: E402

LONG_REPLY = "I think so, but can we talk about it after lunch today?"


def _fits(text, px, w, h):
    f = QFont()
    f.setBold(True)
    f.setPixelSize(px)
    r = QFontMetrics(f).boundingRect(QRect(0, 0, w, 100000),
                                     int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), text)
    return r.width() <= w and r.height() <= h


def test_fit_pixel_size_bounds(app):
    f = QFont()
    f.setBold(True)
    assert fit_pixel_size("Yes.", f, 400, 300, 56) == 56
    assert fit_pixel_size("", f, 400, 300, 56) == 56
    assert fit_pixel_size("word " * 200, f, 200, 100, 56) == MIN_PX


def test_tile_shrinks_long_label_and_fits(app):
    t = Tile("target-1", "1")
    t.resize(300, 300)
    t.set_label(LONG_REPLY + " " + LONG_REPLY)
    assert MIN_PX <= t.font_px < Tile.MAX_PX
    w, h = 300 - 2 * Tile.INSET, 300 - 2 * Tile.INSET
    assert _fits(t.text(), t.font_px, w, h) or t.font_px == MIN_PX


def test_tile_short_label_stays_full_size_and_flash_keeps_size(app):
    t = Tile("target-2", "2")
    t.resize(420, 400)
    t.set_label("Compare counties")
    assert t.font_px == Tile.MAX_PX
    t.set_label(LONG_REPLY * 3)
    px = t.font_px
    t.set_lit(True)
    t.set_lit(False)
    assert t.font_px == px                     # flashing never changes the size


def test_window_fits_twelve_word_reply_at_1280x720(ui):
    from signal2speech.ai import to_choices
    h, w, _, _ = ui
    w.resize(760, 720)                          # the left column at 1280x720
    w.show()
    h.begin_choice_round(list(to_choices([LONG_REPLY, "No thanks, I would rather stay here and rest for now."])))
    app = QApplication.instance()
    app.processEvents()
    for tile in w.tiles.values():
        assert tile.font_px >= MIN_PX
        assert _fits(tile.text(), tile.font_px, tile.width() - 2 * Tile.INSET,
                     tile.height() - 2 * Tile.INSET) or tile.font_px == MIN_PX
    w.press_target(T1)
    app.processEvents()
    assert w.PREVIEW_MIN_PX <= w.preview_px <= w.PREVIEW_MAX_PX


# ── #174: redesigned tiles ───────────────────────────────────
def test_tile_states_and_descriptions(app):
    from signal2speech.core import ActionIds
    from signal2speech.ui import theme
    t = Tile("target-1", "1")
    t.resize(400, 360)
    assert t.state == "waiting"
    t.set_label("Compare counties", ActionIds.COMPARE_AIR_QUALITY)
    assert t.state == "idle" and t.icon == "chart"
    assert t.description == theme.ACTION_INFO[ActionIds.COMPARE_AIR_QUALITY][1]
    assert "[1]" not in t.text()                       # the key is a badge now, not in the title
    t.set_lit(True)
    assert t.state == "lit"
    t.set_lit(False)
    t.set_selected(True)
    assert t.state == "selected"
    t.set_label("Show the satellite view", ActionIds.SHOW_SATELLITE)
    assert t.state == "idle" and t.icon == "satellite"   # a new label clears "selected"


def test_flash_still_looks_the_same(app):
    """The classifier's stimulus must not change: a lit tile is plain white with black content."""
    from PySide6.QtGui import QColor
    from signal2speech.core import ActionIds
    from signal2speech.ui import theme
    t = Tile("target-1", "1")
    t.resize(400, 360)
    t.set_label("Compare counties", ActionIds.COMPARE_AIR_QUALITY)
    t.set_lit(True)
    img = t.grab().toImage()
    # In the padding between the border and the content, where nothing is ever drawn. (A point
    # further in can land on the title's edge now that tiles are smaller.)
    corner = img.pixelColor(int(Tile.INSET) - 6, img.height() // 2)
    assert corner == QColor(theme.TILE_LIT_BG)
    assert (theme.TILE_LIT_BG, theme.TILE_LIT_TEXT) == ("#ffffff", "#000000")


def test_every_tile_kind_draws_an_icon(app):
    from PySide6.QtGui import QImage, QPainter, QColor
    from PySide6.QtCore import QRectF
    from signal2speech.ui.icons import draw_icon
    for kind in ("satellite", "chart", "speech", "check", "cross"):
        img = QImage(64, 64, QImage.Format.Format_ARGB32)
        img.fill(QColor("#000000"))
        p = QPainter(img)
        draw_icon(p, kind, QRectF(8, 8, 48, 48), "#ffffff")
        p.end()
        lit = sum(1 for x in range(64) for y in range(64) if img.pixelColor(x, y).red() > 128)
        assert lit > 30, kind


def test_tile_repaint_stays_well_under_a_frame(app):
    """#174 draws tiles by hand; a flash must still repaint in far less than one 60 Hz frame."""
    import time
    from signal2speech.core import ActionIds
    t = Tile("target-1", "1")
    t.resize(420, 560)
    t.set_label("Compare counties", ActionIds.COMPARE_AIR_QUALITY)
    t.show()
    app.processEvents()
    ms = []
    for i in range(60):
        start = time.perf_counter()
        t.set_lit(i % 2 == 0)
        t.repaint()
        ms.append((time.perf_counter() - start) * 1000)
    ms.sort()
    assert ms[int(0.95 * len(ms))] < 16.0, ms[-5:]
    t.close()
