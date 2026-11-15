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

# Offscreen Qt on Windows finds no fonts unless pointed at the system font folder. Set it at
# import (collection) time, before any test module creates the QApplication, so text widths are
# real in every test session. Only the offscreen platform reads this variable.
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))


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
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def visible_texts(view):
    from PySide6.QtWidgets import QLabel
    return [label.text() for label in view.findChildren(QLabel) if label.isVisibleTo(view)]


def test_view_starts_blank_and_switches_modes(qapp):
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import BLANK_HINT
    view = OpenOrbitView()
    assert view.data_error is None
    assert view.mode == "blank" and BLANK_HINT in visible_texts(view)
    view.show_satellite()
    assert view.mode == "satellite"
    view.compare_air_quality()
    assert view.mode == "compare"
    view.reset()
    assert view.mode == "blank" and BLANK_HINT in visible_texts(view)


def test_idle_panel_shows_a_dimmed_region_and_no_results(qapp):
    """#182: before any confirm the panel isn't an empty box, but it must not look like a reveal."""
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import BLANK_HINT, IDLE_OPACITY
    view = OpenOrbitView()
    texts = visible_texts(view)
    assert BLANK_HINT in texts and any("southeast Michigan" in t for t in texts)
    assert any("NASA" in t for t in texts)                                # attribution stays visible
    ds = view.dataset
    numbers = {str(v) for c in ds.changes for v in (c.before, c.after)}
    assert not any(n in t for t in texts for n in numbers)                # no AQI values before a confirm
    assert not any("Biggest jump" in t or "Highest" in t for t in texts)
    assert view.idle_image.opacity == IDLE_OPACITY and IDLE_OPACITY <= 0.4
    assert view.idle_image.graphicsEffect() is None                       # an effect here crashed macOS
    missing = OpenOrbitView(data_root=Path("no-such-folder"))             # no data: the plain hint only
    assert visible_texts(missing) == [BLANK_HINT]


def test_missing_data_shows_a_labelled_panel_instead_of_crashing(qapp, tmp_path):
    """The app's load_view() only catches ImportError, so the view itself must not raise."""
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView(data_root=tmp_path)
    assert view.data_error and "build_dataset.py" in view.data_error
    for action in (ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY):
        assert view.perform(action)
        texts = visible_texts(view)
        assert any("OpenOrbit data missing (#29)" in t for t in texts)
        assert not any("NASA" in t or "EPA" in t for t in texts)
    view.reset()
    assert view.mode == "blank"


def test_view_fits_the_app_output_panel(qapp):
    """The app (#4) puts the view next to the selection tiles (about 936 px wide). To fit a
    1536x864 screen (1920x1080 at 125%), the view must stay narrow and short enough."""
    from PySide6.QtGui import QFont, QFontMetricsF
    from signal2speech.openorbit import OpenOrbitView
    metrics = QFontMetricsF(QFont())
    if metrics.horizontalAdvance("iiii") == metrics.horizontalAdvance("WWWW"):
        pytest.skip("Qt started without real fonts in this session, so text widths are placeholders")
    hint = OpenOrbitView().minimumSizeHint()
    assert hint.width() <= 560 and hint.height() <= 520, hint.toTuple()


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
    from PySide6.QtWidgets import QLabel
    view = OpenOrbitView()
    view.compare_air_quality()
    texts = visible_texts(view)
    assert "+186" in texts and "+168" in texts
    cells = {l.accessibleName() for l in view.findChildren(QLabel) if l.isVisibleTo(view)}
    assert {"32 Good", "218 Very Unhealthy", "58 Moderate", "226 Very Unhealthy"} <= cells
    nasa = [t for t in texts if "NASA" in t]
    epa = [t for t in texts if "EPA" in t]
    assert nasa and epa and not any("NASA" in t and "EPA" in t for t in texts)


def test_satellite_shows_only_the_nasa_credit(qapp):
    from signal2speech.openorbit import OpenOrbitView
    view = OpenOrbitView()
    view.show_satellite()
    texts = visible_texts(view)
    assert any("NASA" in t for t in texts) and not any("EPA" in t for t in texts)


def assert_labels_belong_to_their_markers(map_image, context, require_all=False):
    """Each drawn label stays on the image, covers no other label, marker, or the caption, and
    is nearer its own marker than any other (a reader links a label to the nearest marker).
    Holds for any font, because labels that can't be placed cleanly are left out."""
    from PySide6.QtCore import QRectF
    _, radius, labels = map_image.label_layout()
    image = map_image.image_rect()
    caption = map_image.caption_layout()
    markers = map_image.marker_points()
    if require_all:
        assert len(labels) == len(markers), context
    for i, (place, point, box, _) in enumerate(labels):
        where = (place.id, context)
        assert image.contains(box), where
        assert caption is None or not box.intersects(caption[1]), where
        for j, (_, _, other_box, _) in enumerate(labels):
            assert i == j or not box.intersects(other_box), where
        for other_place, other_point in markers:
            if other_place.id == place.id:
                continue
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
    assert_labels_belong_to_their_markers(m, width, require_all=width >= 640)


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
    assert [m.date for m in maps] == [AFTER]              # one flowing image, resting on the smoke
    for m in maps:
        rect = m.image_rect()
        assert all(rect.contains(point) for _, point in m.marker_points())


# ── Optional FIRMS layer (#31, #32) ─────────────────────────────────────────
DATA = Path(__file__).resolve().parents[1] / "data" / "openorbit"


def core_only_copy(tmp_path):
    """data/openorbit without the optional firms/ folder."""
    import shutil
    dst = tmp_path / "openorbit"
    shutil.copytree(DATA, dst, ignore=shutil.ignore_patterns("firms", "raw"))
    return dst


def test_fires_sample_has_vegetation_fires_only_and_none_in_the_demo_area():
    from signal2speech.openorbit.dataset import load_fires
    fires = load_fires()
    assert fires is not None and fires.dates == (BEFORE, AFTER)
    summary = json.loads((DATA / "firms" / "summary.json").read_text(encoding="utf-8"))
    for date in fires.dates:
        assert sum(p.date == date for p in fires.points) == summary["counts"][date]["vegetation_fires"] > 0
    b = fires.bbox
    assert all(b["south"] <= p.lat <= b["north"] and b["west"] <= p.lon <= b["east"] for p in fires.points)
    demo = load_dataset().bbox  # southeast Michigan: smoke there, but no wildfire detections
    assert not any(demo["south"] <= p.lat <= demo["north"] and demo["west"] <= p.lon <= demo["east"]
                   for p in fires.points)


def test_satellite_shows_fires_beside_the_smoke_with_their_own_credit(qapp):
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import FiresMap
    view = OpenOrbitView()
    view.show_satellite()
    texts = visible_texts(view)
    assert any("Where the smoke came from" in t for t in texts)
    assert any("NASA FIRMS" in t for t in texts)
    assert not any("FIRMS" in t and "MODIS" in t for t in texts)   # separate from the smoke image credit
    assert not any("EPA" in t or "AQI" in t for t in texts)        # separate from air quality
    assert len([m for m in view.findChildren(FiresMap) if m.isVisibleTo(view)]) == 1
    view.compare_air_quality()
    assert not any("FIRMS" in t for t in visible_texts(view))


def test_core_view_works_without_the_fires_asset(qapp, tmp_path):
    """#31 Done when: the core comparison still runs without the optional asset."""
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import FiresMap
    view = OpenOrbitView(data_root=core_only_copy(tmp_path))
    assert view.data_error is None and view.fires is None
    view.show_satellite()
    assert view.findChildren(FiresMap) == [] and not any("FIRMS" in t for t in visible_texts(view))
    view.compare_air_quality()
    assert "+186" in visible_texts(view) and "+168" in visible_texts(view)


def test_broken_fires_asset_is_ignored(qapp, tmp_path):
    from signal2speech.openorbit import OpenOrbitView
    root = core_only_copy(tmp_path)
    (root / "firms").mkdir()
    (root / "firms" / "summary.json").write_text("{not json", encoding="utf-8")
    view = OpenOrbitView(data_root=root)
    assert view.fires is None and view.data_error is None
    assert view.perform(ActionIds.SHOW_SATELLITE) and view.mode == "satellite"


def test_fire_dots_and_home_marker_land_on_the_image(qapp):
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.openorbit.view import FiresMap
    view = OpenOrbitView()
    view.resize(1150, 500)
    view.show_satellite()
    view.grab()
    fires_map = [m for m in view.findChildren(FiresMap) if m.isVisibleTo(view)][0]
    rect = fires_map.image_rect()
    dots = fires_map.dot_points()
    assert len(dots) == len(view.fires.points)
    assert all(rect.contains(p) for _, p in dots)
    assert rect.contains(fires_map.home_point())


def test_defining_pollutants_are_loaded_and_shown(qapp):
    """#153: the view says which pollutant set each AQI when they differ, from the data."""
    from signal2speech.openorbit.view import OpenOrbitView
    ds = load_dataset()
    w = ds.change_for("Washtenaw")
    assert (w.before_pollutant, w.after_pollutant) == ("Ozone", "PM2.5")
    wayne = ds.change_for("Wayne")
    assert (wayne.before_pollutant, wayne.after_pollutant) == ("PM2.5", "PM2.5")
    line = OpenOrbitView(ds)._pollutant_line()
    assert line.endswith("PM2.5 for all values except Washtenaw Jun 26 (Ozone).")


def test_cloudy_before_image_is_captioned(qapp):
    """#153: June 26 was overcast; the caption says so, so white isn't read as clean air."""
    from signal2speech.openorbit.view import MapImage, OpenOrbitView
    view = OpenOrbitView(load_dataset())
    view.compare_air_quality()
    # The comparison now flows through the days; each overcast day's caption says cloud.
    captions = {d: view._lapse_caption(d, note) for d, note in view.dataset.timelapse}
    assert captions[BEFORE].endswith("mostly cloud") and "June 26" in captions[BEFORE]
    assert "cloud" not in captions[AFTER] and "June 28" in captions[AFTER]
    assert "cloud" not in view.cmp_image.caption          # at rest it shows June 28


def test_pollutant_line_is_stable_and_never_overclaims(qapp):
    """#153 review: ties pick the same pollutant every run; an unknown pollutant means no line."""
    from dataclasses import replace

    from signal2speech.openorbit.view import OpenOrbitView
    ds = load_dataset()
    w, wayne = ds.change_for("Washtenaw"), ds.change_for("Wayne")
    tie = replace(ds, changes=(replace(w, before_pollutant="PM2.5", after_pollutant="PM2.5"),
                               replace(wayne, before_pollutant="Ozone", after_pollutant="Ozone")))
    assert "Ozone for all values except Washtenaw Jun 26 (PM2.5), Washtenaw Jun 28 (PM2.5)" in \
        OpenOrbitView(tie)._pollutant_line()              # 2-2 tie: alphabetical first wins
    unknown = replace(ds, changes=(w, replace(wayne, after_pollutant="")))
    assert OpenOrbitView(unknown)._pollutant_line() == ""
    same = replace(ds, changes=(replace(w, before_pollutant="PM2.5"), wayne))
    assert OpenOrbitView(same)._pollutant_line() == ""


def test_long_caption_falls_back_to_the_date_on_a_small_image(qapp):
    """#153 review: at the smallest image size the caption box stays inside the image."""
    from signal2speech.openorbit.view import MapImage
    m = MapImage(load_dataset(), BEFORE, caption="June 26, 2023 · mostly cloud",
                 caption_short="June 26, 2023")
    for width in (200, 240, 1440):
        m.resize(width, round(width * 800 / 1440))
        _, box = m.caption_layout()
        assert m.image_rect().contains(box), width
    m.resize(1440, 800)
    assert m.caption_text() == "June 26, 2023 · mostly cloud"


def test_satellite_view_plays_the_days_in_order_and_ends_on_the_smoke(qapp, monkeypatch):
    """The satellite view steps through June 24 to 28 and stops on June 28. The fire map beside
    it shows only what had been detected by each day."""
    from signal2speech.openorbit import OpenOrbitView
    from signal2speech.ui import fade
    ds = load_dataset()
    dates = [d for d, _ in ds.timelapse]
    assert dates == sorted(dates) and dates[-1] == AFTER and len(dates) >= 3
    assert all(ds.images[d].exists() for d in dates)

    view = OpenOrbitView()
    view.show_satellite()                                   # fades off (tests): straight to the last day
    assert view.sat_image.date == AFTER and "wildfire smoke" in view.sat_image.caption
    view.compare_air_quality()                              # the comparison flows the same way
    from signal2speech.openorbit.view import COMPARE_SCOPE_NOTE
    assert COMPARE_SCOPE_NOTE in visible_texts(view)        # images cover five days, numbers two
    assert "June 26" in COMPARE_SCOPE_NOTE and "June 28" in COMPARE_SCOPE_NOTE and "June 24" in COMPARE_SCOPE_NOTE
    assert view.cmp_image.date == AFTER and view._lapse_image is view.cmp_image
    view.show_satellite()
    assert view.fires_map.until is None                     # every detection shown at the end

    monkeypatch.setattr(fade, "ENABLED", True)              # as on screen: start on the first day
    view.reset()
    view.show_satellite()
    assert view.sat_image.date == dates[0] and view.fires_map.until == dates[0]
    seen = [view.sat_image.date]
    while view.lapse_index < len(dates) - 1:
        view._lapse_next()
        seen.append(view.sat_image.date)
    assert seen == dates and view.fires_map.until is None and not view._lapse_timer.isActive()
    hidden_early = [d for d, _ in view.fires_map.dot_points() if d > dates[0]]
    assert hidden_early                                     # there were detections to hold back
