"""P300 chooser (#46) on synthetic data. Headless; no headset, no window.

Trains the LDA on a synthetic calibration recording cut by g.Pype's Epochs, then checks
above-chance accuracy on a held-out synthetic recording, plus the aggregation and the
contract hand-off. Synthetic results say nothing about a real wearer.
"""
import threading

import pytest

gp = pytest.importorskip("gpype")
pytest.importorskip("sklearn")
pytest.importorskip("h5py")

from signal2speech.core import Choice, EegClassMap, InputAdapter, InputSources, Outcome, \
    SelectionHandler, TargetIds  # noqa: E402
from signal2speech.eeg import p300  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    return p300.train_on_synthetic(n_sequences=16, seed=3,
                                   workdir=str(tmp_path_factory.mktemp("cal")))


def test_offline_accuracy_above_chance(model, tmp_path):
    attended = [T1, T2, T2, T1, T1, T2, T1, T2, T2, T1, T2, T1]
    path = str(tmp_path / "test.h5")
    p300.write_synthetic_recording(path, attended, calibration=False, seed=11)
    report = p300.offline_accuracy(model, path, attended)
    print(report)
    assert report["epoch_accuracy"] > 0.65          # chance 0.5
    assert report["sequence_accuracy"] >= 0.9       # 5 flashes per tile
    reps = report["sequence_accuracy_by_reps"]
    assert reps[p300.FLASHES_PER_TILE] >= reps[1] - 0.1  # more repetitions don't hurt


def test_no_p300_means_chance(model, tmp_path):
    attended = [T1, T2] * 6
    path = str(tmp_path / "flat.h5")
    p300.write_synthetic_recording(path, attended, calibration=False, seed=5, amplitude=0.0)
    report = p300.offline_accuracy(model, path, attended)
    assert report["sequence_accuracy"] < 0.95       # nothing to find, so no free lunch


def test_aggregator_decides_once_per_sequence():
    got = []
    agg = p300.SequenceAggregator(flashes_per_tile=2, on_decision=lambda c, m: got.append(c))
    agg.add(T1, 5.0)                    # before start: ignored
    agg.start()
    for s in (1.0, -1.0):
        agg.add(T1, s)
    agg.add(T2, 2.0)
    assert got == []
    agg.add(T2, 0.5)                    # all in: tile 2 mean 1.25 > tile 1 mean 0
    agg.add(T2, 9.0)                    # after decision: ignored
    assert got == [2]
    assert agg.finish() is None


def test_aggregator_is_thread_safe():
    got = []
    agg = p300.SequenceAggregator(flashes_per_tile=200, on_decision=lambda c, m: got.append(c))
    agg.start()
    threads = [threading.Thread(target=lambda t=t: [agg.add(t, 1.0 if t == T1 else -1.0)
                                                    for _ in range(200)]) for t in (T1, T2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert got == [1]


def test_decision_reaches_contract_with_round_stamped_at_sequence_start():
    class Sink:
        def execute(self, action):
            pass

    handler = SelectionHandler(Sink())
    adapter = InputAdapter(handler, InputSources.SIMULATED)
    handler.begin_choice_round([Choice(T1, "show_satellite", "Satellite"),
                                Choice(T2, "compare_air_quality", "Compare")])
    adapter.arm_capture()                       # sequence starts in r1
    outcomes = []
    agg = p300.SequenceAggregator(flashes_per_tile=1, on_decision=lambda c, m: outcomes.append(
        adapter.select_captured(EegClassMap.default().target_for(c))))
    agg.start()
    agg.add(T1, -1.0)
    agg.add(T2, 1.0)
    assert outcomes == [Outcome.Previewed]
    assert handler.pending.target_id == T2


def test_make_sequence_balanced_no_triples():
    import random
    order = p300.make_sequence(5, random.Random(0))
    assert order.count(T1) == order.count(T2) == 5
    assert not any(order[i] == order[i + 1] == order[i + 2] for i in range(len(order) - 2))


def test_realtime_generator_pipeline_reaches_adapter_on_qt_thread(model):
    """Generator + synthetic P300 -> Trigger -> scorer -> Qt signal -> InputAdapter. ~5 s."""
    import random
    import time

    QtCore = pytest.importorskip("PySide6.QtCore")
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    class Sink:
        def execute(self, action):
            pass

    handler = SelectionHandler(Sink())
    adapter = InputAdapter(handler, InputSources.SIMULATED)
    nodes = p300.build_pipeline("generator", model=model, calibration=False)
    chooser = p300.P300Chooser(nodes, adapter, flashes_per_tile=3)
    main_thread = threading.get_ident()
    seen = []
    chooser.bridge.listeners.append(
        lambda cls, target, outcome: seen.append((target, outcome, threading.get_ident())))
    choices = [Choice(T1, "show_satellite", "Satellite"),
               Choice(T2, "compare_air_quality", "Compare")]

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.005)

    nodes.pipeline.start()
    try:
        pump(0.5)                                   # fill the Trigger buffers
        for attended in (T2, T1):
            handler.begin_choice_round(choices)
            chooser.begin_sequence(attended_for_synthetic=attended)
            for tile in p300.make_sequence(3, random.Random(attended)):
                chooser.on_flash(tile)
                pump(0.2)
            deadline = time.monotonic() + p300.TIME_POST + 1.0
            while chooser.aggregator._open and time.monotonic() < deadline:
                pump(0.05)
            pump(0.05)
            handler.cancel("next")
    finally:
        nodes.pipeline.stop()
        nodes.pipeline.close()

    assert [s[0] for s in seen] == [T2, T1]
    assert all(s[1] is Outcome.Previewed for s in seen)
    assert all(s[2] == main_thread for s in seen)   # slot ran on the Qt thread
