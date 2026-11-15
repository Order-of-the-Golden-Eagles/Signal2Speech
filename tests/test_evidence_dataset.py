"""g.tec P300 Speller dataset in the evidence view (#142). Uses a tiny synthetic file in the
same format, built in tmp_path. The real dataset is never committed."""
import time

import numpy as np
import pytest

gp = pytest.importorskip("gpype")
pytest.importorskip("sklearn")
scipy_io = pytest.importorskip("scipy.io")

from signal2speech.evidence import dataset as gtec                      # noqa: E402
from signal2speech.evidence.__main__ import parse_args                  # noqa: E402
from signal2speech.evidence.pipeline import InputLabel, build_evidence_graph  # noqa: E402
from signal2speech.evidence.synthetic import NONTARGET_CODE, TARGET_CODE      # noqa: E402

FS = 250


def make_file(path, seconds=40, bump_uv=8.0, seed=0, hold=1):
    """Noise plus a bump 300 ms after each target flash, in g.tec's .mat layout."""
    rng = np.random.default_rng(seed)
    n = seconds * FS
    y = rng.normal(0, 4, size=(n, 8))
    trig = np.zeros(n)
    t = np.arange(int(0.8 * FS)) / FS
    wave = bump_uv * np.exp(-0.5 * ((t - 0.3) / 0.08) ** 2)
    for k, start in enumerate(range(FS, n - FS, int(0.2 * FS))):
        target = k % 4 == 0
        trig[start:start + hold] = 1 if target else -1
        if target:
            y[start:start + len(wave)] += wave[:, None]
    scipy_io.savemat(path, {"fs": float(FS), "y": y, "trig": trig})
    return path


def test_load_maps_triggers_to_codes(tmp_path):
    s = gtec.load(make_file(tmp_path / "S9.mat"))
    assert s.name == "S9" and s.fs == FS and s.eeg.shape[1] == 8
    assert s.targets > 0 and abs(s.nontargets - 3 * s.targets) <= 3      # every 4th flash is a target
    assert set(np.unique(s.codes)) == {0.0, float(TARGET_CODE), float(NONTARGET_CODE)}


def test_held_trigger_counts_once(tmp_path):
    one = gtec.load(make_file(tmp_path / "S1.mat", hold=1))
    held = gtec.load(make_file(tmp_path / "S2.mat", hold=5))
    assert (held.targets, held.nontargets) == (one.targets, one.nontargets)


def test_folder_resolves_to_first_subject_and_bad_files_are_refused(tmp_path):
    make_file(tmp_path / "S2.mat"); make_file(tmp_path / "S1.mat")
    assert gtec.resolve(tmp_path).name == "S1.mat"
    scipy_io.savemat(tmp_path / "other.mat", {"x": np.zeros(3)})
    with pytest.raises(ValueError):
        gtec.load(tmp_path / "other.mat")
    with pytest.raises(FileNotFoundError):
        gtec.load(tmp_path / "missing.mat")


def test_offline_report_finds_the_bump(tmp_path):
    r = gtec.analyse(gtec.load(make_file(tmp_path / "S1.mat", seconds=60)))
    assert 250 <= r.peak_ms <= 350 and r.peak_uv > 4
    assert r.lda_balanced_accuracy > 0.75
    assert "chance 0.50" in r.line()


def test_graph_is_labelled_recorded_and_names_gtec(tmp_path):
    graph = build_evidence_graph("generator", dataset=gtec.load(make_file(tmp_path / "S1.mat")))
    assert graph.label is InputLabel.RECORDED
    assert "g.tec" in graph.oscar_note and "not our headset" in graph.oscar_note
    assert graph.marker.name == "recorded_flashes" and graph.raw.name == "recorded_eeg"


def test_cli_accepts_dataset_and_refuses_bad_combinations(tmp_path):
    assert parse_args(["--source", "dataset", str(tmp_path)]).source[0] == "dataset"
    for bad in (["--source", "dataset"], ["--source", "dataset", "x", "--p300"],
                ["--source", "dataset", "x", "--record"]):
        with pytest.raises(SystemExit):
            parse_args(bad)


def test_realtime_recording_average_separates(tmp_path):
    """Play the file through the real pipeline: epochs must line up with the recorded flashes."""
    graph = build_evidence_graph("generator", dataset=gtec.load(make_file(tmp_path / "S1.mat")))
    p = graph.pipeline
    target, nontarget = gp.Collector(name="t_avg"), gp.Collector(name="n_avg")
    p.connect(graph.target_average, target)
    p.connect(graph.nontarget_average, nontarget)
    p.start()
    try:
        time.sleep(9)
    finally:
        p.stop()
        p.close()
    t = np.asarray(target.result.data)[..., -1]
    n = np.asarray(nontarget.result.data)[..., -1]
    window = slice(int((0.2 + 0.25) * FS), int((0.2 + 0.35) * FS))    # 250-350 ms after the flash
    assert t[window].mean() - n[window].mean() > 3.0, (t[window].mean(), n[window].mean())
