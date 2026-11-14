"""OpenOrbit dataset and view (#29, #30). The data tests need no Qt; the view tests run offscreen."""
import json
import os
import sys
from pathlib import Path

import pytest

from signal2speech.core import ActionIds
from signal2speech.openorbit import load_dataset
from signal2speech.openorbit.dataset import AFTER, BEFORE

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


def test_changes_are_computed_from_the_epa_rows():
    ds = load_dataset()
    washtenaw, wayne = ds.change_for("Washtenaw"), ds.change_for("Wayne")
    assert (washtenaw.before, washtenaw.after, washtenaw.change) == (32, 218, 186)
    assert (wayne.before, wayne.after, wayne.change) == (58, 226, 168)
    assert ds.largest_increase().county == "Washtenaw"
    assert ds.highest_after().county == "Wayne"


def test_spoken_line_matches_the_contract():
    data = json.loads((CONTRACTS / "demo-round.json").read_text(encoding="utf-8"))
    spoken = next(c["spokenText"] for c in data["choices"] if c["actionId"] == "compare_air_quality")
    assert load_dataset().spoken_comparison() == spoken


def test_pixel_mapping_and_markers():
    ds = load_dataset()
    b = ds.bbox
    assert ds.to_pixel(b["north"], b["west"]) == (0, 0)
    assert ds.to_pixel(b["south"], b["east"]) == pytest.approx((ds.width, ds.height))
    for place in ds.places:
        x, y = ds.to_pixel(place.lat, place.lon)
        assert 0 < x < ds.width and 0 < y < ds.height, place.id
    detroit = next(p for p in ds.places if p.id == "detroit")
    assert tuple(round(v) for v in ds.to_pixel(detroit.lat, detroit.lon)) == (1083, 375)
    assert {p.short for p in ds.places} == {"EMU", "Detroit"}


def test_missing_data_names_the_rebuild_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_dataset.py"):
        load_dataset(tmp_path)


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform == "win32":  # the offscreen platform finds no fonts on Windows otherwise
        os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def visible_texts(view):
    from PySide6.QtWidgets import QLabel
    return [label.text() for label in view.findChildren(QLabel) if label.isVisibleTo(view)]


def test_view_starts_blank_and_switches_modes(qapp):
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView()
    assert view.mode == "blank" and visible_texts(view) == []
    view.show_satellite()
    assert view.mode == "satellite"
    view.compare_air_quality()
    assert view.mode == "compare"
    view.reset()
    assert view.mode == "blank" and visible_texts(view) == []


def test_perform_exposes_both_action_ids_only(qapp):
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView()
    assert view.perform(ActionIds.SHOW_SATELLITE) and view.mode == "satellite"
    assert view.perform(ActionIds.COMPARE_AIR_QUALITY) and view.mode == "compare"
    assert not view.perform(ActionIds.SPEAK_REPLY)
    assert view.mode == "compare"  # unchanged by an action OpenOrbit doesn't own
    assert set(view.ACTION_IDS) == {ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY}


def test_compare_shows_computed_values_and_separate_credits(qapp):
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView()
    view.compare_air_quality()
    texts = visible_texts(view)
    assert "+186" in texts and "+168" in texts
    assert "32  Good" in texts and "226  Very Unhealthy" in texts
    nasa = [t for t in texts if "NASA" in t]
    epa = [t for t in texts if "EPA" in t]
    assert nasa and epa and not any("NASA" in t and "EPA" in t for t in texts)


def test_satellite_shows_only_the_nasa_credit(qapp):
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView()
    view.show_satellite()
    texts = visible_texts(view)
    assert any("NASA" in t for t in texts) and not any("EPA" in t for t in texts)


def assert_labels_belong_to_their_markers(map_image, context):
    """Each label stays on the image, covers no other label, marker, or the caption, and is
    nearer its own marker than any other (a reader links a label to the nearest marker)."""
    from PySide6.QtCore import QRectF
    _, radius, labels = map_image.label_layout()
    image = map_image.image_rect()
    caption = map_image.caption_layout()
    for i, (place, point, box, _) in enumerate(labels):
        where = (place.id, context)
        assert image.contains(box), where
        assert caption is None or not box.intersects(caption[1]), where
        for j, (_, other_point, other_box, _) in enumerate(labels):
            if i == j:
                continue
            assert not box.intersects(other_box), where
            ring = QRectF(other_point.x() - radius, other_point.y() - radius, 2 * radius, 2 * radius)
            assert not box.intersects(ring), where
            own = (box.center() - point).manhattanLength()
            assert own < (box.center() - other_point).manhattanLength(), where


@pytest.mark.parametrize("width", [240, 300, 360, 420, 520, 640, 800, 1000])
@pytest.mark.parametrize("date", [BEFORE, AFTER])
def test_marker_labels_at_any_image_size(qapp, date, width):
    """Font-independent: small images make labels wide relative to the map, forcing edge cases."""
    from signal2speech.openorbit.view import MapImage
    m = MapImage(load_dataset(), date, caption="June 28, 2023")
    m.resize(width, round(width * 800 / 1440))
    assert_labels_belong_to_their_markers(m, width)


@pytest.mark.parametrize("size", [(1280, 720), (1024, 600), (800, 480)])
@pytest.mark.parametrize("mode", ["show_satellite", "compare_air_quality"])
def test_marker_labels_in_the_view(qapp, mode, size):
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import MapImage
    view = OpenOrbitView()
    view.resize(*size)
    getattr(view, mode)()
    view.grab()  # lays out at this size
    for m in [m for m in view.findChildren(MapImage) if m.isVisibleTo(view)]:
        assert_labels_belong_to_their_markers(m, size)


def test_images_load_with_matching_sizes_and_render(qapp):
    from PySide6.QtGui import QImageReader
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import MapImage
    ds = load_dataset()
    sizes = {QImageReader(str(ds.images[d])).size().toTuple() for d in (BEFORE, AFTER)}
    assert sizes == {(ds.width, ds.height)}
    view = OpenOrbitView()
    view.resize(1280, 760)
    view.compare_air_quality()
    assert not view.grab().isNull()
    maps = [m for m in view.findChildren(MapImage) if m.isVisibleTo(view)]
    assert sorted(m.date for m in maps) == [BEFORE, AFTER]
    for m in maps:
        rect = m.image_rect()
        assert all(rect.contains(point) for _, point in m.marker_points())
