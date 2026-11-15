"""Evidence view driven by the P300 chooser (#48 + #46). Headless; no window.

Synthetic data only: these tests show the wiring, not how well a real wearer is decoded.
"""
import random
import time

import pytest

gp = pytest.importorskip("gpype")
pytest.importorskip("sklearn")
pytest.importorskip("h5py")

from signal2speech.core import Outcome, SelectionHandler, TargetIds  # noqa: E402
from signal2speech.eeg import p300  # noqa: E402
from signal2speech.evidence import InputLabel, SourceKind  # noqa: E402
from signal2speech.evidence.__main__ import parse_args  # noqa: E402
from signal2speech.evidence.p300_mode import CHOICES, build_p300_evidence  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    return p300.train_on_synthetic(n_sequences=16, seed=3,
                                   workdir=str(tmp_path_factory.mktemp("cal")))


class Sink:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


def test_generator_graph_uses_p300_front_end_and_chooser_markers(model):
    ev = build_p300_evidence("generator", model=model)
    g, n = ev.graph, ev.nodes
    try:
        assert g.label is InputLabel.SIMULATED and g.kind is SourceKind.GENERATOR
        # The chooser's synthetic P300 sits between the source and the filter.
        assert isinstance(g.raw, p300.SyntheticP300) and n.synth is g.raw
        # p300_front_end returns a single 1-30 Hz Bandpass.
        assert isinstance(g.filtered, gp.Bandpass) and g.epoch_input is g.filtered
        # Averages trigger on the calibration codes the LDA trains on, and the
        # chooser's calibration epochs come off those very Trigger nodes.
        assert (g.target_code, g.nontarget_code) == (p300.CAL_TARGET, p300.CAL_NONTARGET)
        assert n.cal_triggers[p300.TARGET_LABEL] is g.target_trigger
        assert n.cal_triggers[p300.NONTARGET_LABEL] is g.nontarget_trigger
        # One marker for everything: the chooser emits on the evidence graph's marker.
        assert n.marker is g.marker and n.eeg is g.epoch_input
        assert set(n.scorers) == {T1, T2}
        assert {code for code, _, _ in g.extra_markers} == set(p300.FLASH_CODES.values())
        assert ev.adapter.source == "simulated"
    finally:
        g.pipeline.close()


def test_headset_graph_builds_without_hardware(model):
    ev = build_p300_evidence("hybridblack", model=model)
    try:
        assert ev.graph.label is InputLabel.LIVE
        assert ev.nodes.synth is None and ev.graph.raw is ev.graph.source
        assert ev.adapter.source == "live-eeg"
        if ev.graph.oscar is not None:   # classifier and averages use the OSCAR branch
            assert ev.graph.epoch_input is ev.graph.oscar
    finally:
        ev.graph.pipeline.close()


def test_decision_path_reaches_selection_handler(model):
    """Scores -> aggregator -> chooser -> InputAdapter -> SelectionHandler preview."""
    handler = SelectionHandler(Sink())
    ev = build_p300_evidence("generator", model=model, handler=handler, flashes_per_tile=2)
    try:
        chooser = ev.attach_chooser(use_qt=False)
        handler.begin_choice_round(CHOICES)
        round_id = handler.current.id
        handled = []
        handler.on_handled.append(lambda e, o: handled.append((e, o)))
        chooser.begin_sequence()
        for tile, score in ((T1, -1.0), (T2, 2.0), (T1, -0.5), (T2, 1.0)):
            ev.nodes.scorers[tile].on_score(tile, score)
        assert len(handled) == 1
        event, outcome = handled[0]
        assert outcome is Outcome.Previewed
        assert event.targetId == T2 and event.roundId == round_id
        assert handler.pending.target_id == T2
    finally:
        ev.graph.pipeline.close()


def test_realtime_flashes_reach_handler_through_evidence_graph(model):
    """Generator run: chooser markers on graph.marker -> Triggers -> LDA -> handler. ~5 s."""
    handler = SelectionHandler(Sink())
    ev = build_p300_evidence("generator", model=model, handler=handler, flashes_per_tile=3)
    chooser = ev.attach_chooser(use_qt=False)
    outcomes = []
    handler.on_handled.append(lambda e, o: outcomes.append((e.targetId, o)))
    ev.graph.pipeline.start()
    try:
        time.sleep(0.5)                                # fill the Trigger buffers
        for attended in (T2, T1):
            handler.begin_choice_round(CHOICES)
            chooser.begin_sequence(attended_for_synthetic=attended)
            for tile in p300.make_sequence(3, random.Random(attended)):
                chooser.on_flash(tile)
                time.sleep(0.2)
            deadline = time.monotonic() + p300.TIME_POST + 1.0
            while chooser.aggregator.is_open and time.monotonic() < deadline:
                time.sleep(0.05)
            if chooser.aggregator.is_open:
                chooser.end_sequence()
            handler.cancel("next")
    finally:
        ev.graph.pipeline.stop()
        ev.graph.pipeline.close()
    assert [o for _, o in outcomes] == [Outcome.Previewed, Outcome.Previewed]
    assert [t for t, _ in outcomes] == [T2, T1]


def test_cli_p300_flags():
    args = parse_args(["--source", "generator", "--p300", "--calibration", "2"])
    assert args.p300 and args.calibration == 2 and args.flashes == 5
    assert not parse_args(["--source", "hybridblack"]).p300
    with pytest.raises(SystemExit):
        parse_args(["--source", "replay", "somewhere", "--p300"])
