"""Flash timing tool (#46): statistics and PASS/WARN logic, plus a short offscreen run.

The offscreen run only proves the tool executes. Offscreen Qt never presents a frame, so its
numbers mean nothing and the verdict must be WARN.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from signal2speech.eeg import flash_timing as ft  # noqa: E402


def _samples(offsets_ms, step=0.175):
    out = []
    for i, off in enumerate(offsets_ms):
        t0 = 10.0 + i * step
        s = ft.FlashSample(tile="target_1" if i % 2 else "target_2", start_t=t0,
                           flushed_t=t0 + 0.001, marker_t=t0 + 0.002)
        if off is not None:
            s.present_t = s.marker_t + off / 1000.0
        out.append(s)
    return out


def test_percentile_matches_numpy_linear():
    np = pytest.importorskip("numpy")
    xs = [3.0, 1.0, 4.0, 1.5, 9.0, 2.6, 5.0]
    for q in (0, 5, 50, 95, 100):
        assert ft.percentile(xs, q) == pytest.approx(float(np.percentile(xs, q)))
    assert ft.percentile([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        ft.percentile([], 50)


def test_summarize_known_values():
    s = ft.summarize([0.0, 10.0, 20.0, 30.0, 40.0])
    assert s.n == 5
    assert s.mean_ms == pytest.approx(20.0)
    assert s.max_ms == 40.0 and s.min_ms == 0.0
    assert s.p95_ms == pytest.approx(38.0)
    assert s.std_ms == pytest.approx(14.1421, rel=1e-4)
    assert s.jitter_ms == pytest.approx(38.0 - 2.0)
    assert ft.summarize([]) is None


def test_constant_offset_has_zero_jitter_and_passes():
    r = ft.build_report(_samples([25.0] * 40), source=ft.SOURCE_DWM, tiles="widget",
                        platform="windows", refresh_hz=60.0, frames_missed=0)
    assert r.stats.mean_ms == pytest.approx(25.0)
    assert r.stats.jitter_ms == pytest.approx(0.0, abs=1e-6)
    assert r.verdict == "PASS" and r.reasons == []
    assert r.interval.mean_ms == pytest.approx(175.0)
    assert r.repaint.mean_ms == pytest.approx(1.0)
    text = ft.format_report(r)
    assert "PASS" in text and "60.00 Hz" in text and "dwm-vblank-estimate" in text


def test_frame_quantised_jitter_passes_at_60hz():
    offsets = [(i % 17) * 1.0 for i in range(60)]   # 0..16 ms, one frame of quantisation
    r = ft.build_report(_samples(offsets), source=ft.SOURCE_GL, tiles="gl",
                        platform="windows", refresh_hz=60.0)
    assert r.stats.jitter_ms < ft.JITTER_WARN_MS
    assert r.verdict == "PASS"


def test_large_jitter_warns():
    offsets = [0.0, 40.0] * 30
    r = ft.build_report(_samples(offsets), source=ft.SOURCE_GL, tiles="gl",
                        platform="windows", refresh_hz=60.0)
    assert r.verdict == "WARN"
    assert any("jitter" in x for x in r.reasons)
    assert "WARN" in ft.format_report(r)


def test_threshold_is_configurable():
    offsets = [0.0, 15.0] * 30
    ok = ft.build_report(_samples(offsets), source=ft.SOURCE_GL, tiles="gl",
                         platform="windows", refresh_hz=60.0)
    strict = ft.build_report(_samples(offsets), source=ft.SOURCE_GL, tiles="gl",
                             platform="windows", refresh_hz=60.0, threshold_ms=10.0)
    assert ok.verdict == "PASS" and strict.verdict == "WARN"


def test_offscreen_always_warns():
    r = ft.build_report(_samples([5.0] * 40), source=ft.SOURCE_DWM, tiles="widget",
                        platform="offscreen", refresh_hz=60.0)
    assert r.verdict == "WARN"
    assert any("offscreen" in x for x in r.reasons)


def test_missing_present_timestamps_warn():
    offsets = [5.0] * 30 + [None] * 10
    r = ft.build_report(_samples(offsets), source=ft.SOURCE_GL, tiles="gl",
                        platform="windows", refresh_hz=60.0)
    assert r.stats.n == 30 and r.flashes == 40
    assert r.verdict == "WARN"
    assert any("no present timestamp" in x for x in r.reasons)


def test_no_source_and_too_few_flashes_warn():
    none = ft.build_report(_samples([None] * 30), source=ft.SOURCE_NONE, tiles="widget",
                           platform="cocoa", refresh_hz=None)
    assert none.verdict == "WARN" and none.stats is None
    assert "unknown" in ft.format_report(none)
    few = ft.build_report(_samples([5.0] * 5), source=ft.SOURCE_GL, tiles="gl",
                          platform="windows", refresh_hz=60.0)
    assert few.verdict == "WARN" and any("run longer" in x for x in few.reasons)


def test_missed_frames_warn():
    r = ft.build_report(_samples([5.0] * 40), source=ft.SOURCE_DWM, tiles="widget",
                        platform="windows", refresh_hz=60.0, frames_missed=3)
    assert r.verdict == "WARN" and any("missed 3" in x for x in r.reasons)


def test_next_vblank():
    period = 1 / 60
    assert ft.next_vblank(1.0, 1.0, period) == pytest.approx(1.0)
    assert ft.next_vblank(1.001, 1.0, period) == pytest.approx(1.0 + period)
    assert ft.next_vblank(1.0 + 2.5 * period, 1.0, period) == pytest.approx(1.0 + 3 * period)
    assert ft.next_vblank(0.99, 1.0, period) == pytest.approx(1.0)   # vblank sample is later
    with pytest.raises(ValueError):
        ft.next_vblank(1.0, 1.0, 0.0)


def test_cli_rejects_bad_seconds():
    with pytest.raises(SystemExit):
        ft.main(["--seconds", "0"])


def test_offscreen_run_executes(capsys):
    pytest.importorskip("PySide6")
    rc = ft.main(["--seconds", "1"])
    out = capsys.readouterr().out
    assert rc == 1                       # offscreen is never a PASS
    assert "lit flashes:" in out and "WARN" in out and "offscreen" in out


def test_ground_truth_constant_delay_cancels():
    markers = [i * 0.175 for i in range(40)]
    onsets = [100.0 + m + 0.033 for m in markers]          # other clock, fixed 33 ms delay
    gt = ft.compare_ground_truth(markers, onsets)
    assert gt.pairs == 40 and gt.count_mismatch == 0
    assert gt.diff.max_ms == pytest.approx(0.0, abs=1e-6)
    assert gt.verdict == "PASS"


def test_ground_truth_jitter_and_count_mismatch_warn():
    markers = [i * 0.175 for i in range(40)]
    onsets = [m + (0.030 if i % 2 else 0.0) for i, m in enumerate(markers)]
    gt = ft.compare_ground_truth(markers, onsets)
    assert gt.verdict == "WARN" and any("spread" in r for r in gt.reasons)
    assert gt.jitter_std_ms == pytest.approx(30.0 / 2 ** 0.5, rel=1e-2)
    short = ft.compare_ground_truth(markers, onsets[:-1])
    assert short.count_mismatch == -1 and short.verdict == "WARN"


def test_csv_round_trip_and_compare_cli(tmp_path, capsys):
    samples = _samples([5.0] * 30 + [None])
    csv = tmp_path / "run.csv"
    ft.write_csv(str(csv), samples)
    markers = ft.read_marker_times(str(csv))
    assert markers == pytest.approx([s.marker_t for s in samples], abs=1e-6)
    onsets = tmp_path / "onsets.txt"
    onsets.write_text("# camera seconds\n" + "\n".join(f"{m + 7.0:.6f}" for m in markers) + "\n")
    assert ft.read_onsets(str(onsets)) == pytest.approx([m + 7.0 for m in markers])
    rc = ft.main(["--compare", str(csv), str(onsets)])
    assert rc == 0 and "PASS" in capsys.readouterr().out


def test_read_marker_times_filters_by_tile(tmp_path):
    samples = _samples([5.0] * 10)
    csv = tmp_path / "run.csv"
    ft.write_csv(str(csv), samples)
    t1 = ft.read_marker_times(str(csv), "target_1")
    assert t1 == pytest.approx([s.marker_t for s in samples if s.tile == "target_1"], abs=1e-6)
    assert len(t1) == 5
