"""Headless tests for the evidence view (#48). No window is opened."""

import json
import time

import numpy as np
import pytest

gp = pytest.importorskip("gpype")

from signal2speech.evidence import (  # noqa: E402
    InputLabel,
    SourceKind,
    build_evidence_graph,
)
from signal2speech.evidence import recording  # noqa: E402
from signal2speech.evidence.__main__ import parse_args  # noqa: E402
from signal2speech.evidence.synthetic import (  # noqa: E402
    NONTARGET_CODE,
    TARGET_CODE,
    Flasher,
    inject,
    p300_waveform,
)


def test_waveform_peaks_near_300_ms():
    wave = p300_waveform(250, amplitude=8.0)
    assert np.argmax(wave) / 250 == pytest.approx(0.3, abs=0.005)
    assert wave.max() == pytest.approx(8.0)


def test_inject_only_after_target_and_spills_over_frames():
    wave = p300_waveform(250)
    markers = np.zeros(10)
    markers[3] = TARGET_CODE
    markers[6] = NONTARGET_CODE
    out = inject(markers, wave, np.zeros(0), TARGET_CODE)
    assert len(out) == 3 + len(wave)
    np.testing.assert_allclose(out[3:3 + len(wave)], wave)
    # The spill-over continues into the next frame and is added there.
    nxt = inject(np.zeros(10), wave, out[10:], TARGET_CODE)
    np.testing.assert_allclose(nxt[:10], wave[7:17])


def test_flasher_mixes_targets_and_nontargets():
    flasher = Flasher(marker=None, seed=1)
    codes = [flasher.next_code() for _ in range(400)]
    share = codes.count(TARGET_CODE) / len(codes)
    assert 0.2 < share < 0.45
    assert set(codes) == {TARGET_CODE, NONTARGET_CODE}


def test_generator_graph_labels_simulated_and_has_no_oscar():
    graph = build_evidence_graph("generator")
    try:
        assert graph.kind is SourceKind.GENERATOR
        assert graph.label is InputLabel.SIMULATED
        assert "Simulated" in graph.caption
        assert graph.oscar is None
        assert "unavailable" in graph.oscar_note
    finally:
        graph.pipeline.close()


def test_headset_graph_builds_without_hardware():
    """Building (not starting) the HybridBlack graph needs no headset."""
    graph = build_evidence_graph("hybridblack")
    try:
        assert graph.label is InputLabel.LIVE
        assert graph.raw is graph.source  # no synthetic P300 on real EEG
        if graph.oscar is not None:
            assert "OSCAR on" in graph.oscar_note
    finally:
        graph.pipeline.close()


def test_replay_label_is_recorded():
    graph = build_evidence_graph("generator", label=InputLabel.RECORDED)
    try:
        assert "Recorded" in graph.caption
    finally:
        graph.pipeline.close()


def test_front_end_seam_is_used():
    seen = {}

    def front_end(p, eeg):
        node = gp.Lowpass(f_c=20, name="custom_front_end")
        p.connect(eeg, node)
        seen["node"] = node
        return node

    graph = build_evidence_graph("generator", front_end=front_end)
    try:
        assert graph.filtered is seen["node"]
    finally:
        graph.pipeline.close()


def test_generator_average_separates_target_from_nontarget():
    """Run the real pipeline headless and compare the two averages."""
    graph = build_evidence_graph("generator")
    p = graph.pipeline
    target = gp.Collector(name="target_avg")
    nontarget = gp.Collector(name="nontarget_avg")
    p.connect(graph.target_average, target)
    p.connect(graph.nontarget_average, nontarget)
    flasher = Flasher(graph.marker, interval=0.25, target_ratio=0.5, seed=3)
    p.start()
    try:
        flasher.start()
        time.sleep(9)
    finally:
        flasher.stop()
        time.sleep(1.2)
        p.stop()
        p.close()
    assert target.result is not None and nontarget.result is not None
    # EpochAverage emits (samples, channels, n): the running average after
    # each epoch. The last one is the average of all of them.
    t = np.asarray(target.result.data)[..., -1]
    n = np.asarray(nontarget.result.data)[..., -1]
    rate = 250
    window = slice(int((0.2 + 0.25) * rate), int((0.2 + 0.35) * rate))
    signal = slice(0, 8)
    t_peak = t[window, signal].mean()
    n_peak = n[window, signal].mean()
    # The synthetic bump is 10 uV, but a slow CI runner fits fewer flashes into 9 s, and the
    # gap has measured as low as 2.45 uV (macOS). Non-target sits near 0, so 1.5 uV still
    # proves the averages separate without flaking.
    assert t_peak - n_peak > 1.5, (t_peak, n_peak)


def test_cli_parses_sources(tmp_path):
    assert parse_args([]).source == ["generator"]
    args = parse_args(["--source", "replay", str(tmp_path)])
    assert args.source == ["replay", str(tmp_path)]
    with pytest.raises(SystemExit):
        parse_args(["--source", "replay"])
    with pytest.raises(SystemExit):
        parse_args(["--source", "replay", str(tmp_path), "--record"])


def test_recording_meta_round_trip(tmp_path):
    assert recording.read_kind(tmp_path) is SourceKind.GENERATOR
    recording.write_meta(tmp_path, SourceKind.HYBRIDBLACK, oscar=True)
    assert recording.read_kind(tmp_path) is SourceKind.HYBRIDBLACK
    meta = json.loads((tmp_path / recording.META_FILE).read_text())
    assert meta["oscar_requested"] is True
