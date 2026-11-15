"""Evidence view driven by the P300 chooser (#46 + #48).

``python -m signal2speech.evidence --source generator --p300`` builds the
evidence graph with the chooser's front end (``p300_front_end``), puts the
chooser's scorers and calibration collectors in the same g.Pype pipeline,
and lets a ``P300Chooser`` emit the flash markers on ``graph.marker``.

What the judge sees is what the classifier sees:

- The averages trigger on the calibration codes (``CAL_TARGET`` /
  ``CAL_NONTARGET``) from the same Trigger nodes whose epochs are collected
  to train the LDA, on the same filtered stream.
- Online flashes use the tile codes (``FLASH_CODES``), scored by the LDA;
  each sequence's decision goes through ``InputAdapter.select_captured`` to
  the ``SelectionHandler`` and is shown in the header.

The flash schedule comes from ``eeg.p300.make_sequence`` and the tiles are
drawn in the window header, so a wearer has something to attend. On the
Generator the attended tile is chosen at random and a synthetic P300 is
added after its flashes (labelled Simulated). Online averages are not split
into target / non-target because, on live EEG, which tile was attended is
only what the cue asked for.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional

import gpype as gp

from signal2speech.core import (
    Choice,
    InputAdapter,
    InputSources,
    SelectionHandler,
    TargetIds,
)
from signal2speech.eeg import p300

from .pipeline import EvidenceGraph, InputLabel, SourceKind, \
    build_evidence_graph

#: The two options offered each selection round (same as the chooser CLI).
CHOICES = (Choice(TargetIds.TARGET_1, "show_satellite", "Satellite"),
           Choice(TargetIds.TARGET_2, "compare_air_quality", "Compare counties"))
DEFAULT_CALIBRATION = 6


@dataclass
class P300Evidence:
    """One evidence graph with the P300 chooser wired into it."""

    graph: EvidenceGraph
    nodes: p300.P300Nodes
    handler: SelectionHandler
    adapter: InputAdapter
    flashes_per_tile: int = p300.FLASHES_PER_TILE
    chooser: Optional[p300.P300Chooser] = None

    def attach_chooser(self, use_qt: bool = True) -> p300.P300Chooser:
        """Create the chooser. With ``use_qt``, call after the QApplication exists."""
        self.chooser = p300.P300Chooser(self.nodes, self.adapter,
                                        flashes_per_tile=self.flashes_per_tile,
                                        use_qt=use_qt)
        return self.chooser


def input_source(label: InputLabel) -> str:
    """Contract source for an evidence input label."""
    return {InputLabel.SIMULATED: InputSources.SIMULATED,
            InputLabel.RECORDED: InputSources.RECORDED,
            InputLabel.LIVE: InputSources.LIVE_EEG}[label]


def build_p300_evidence(kind: SourceKind | str = SourceKind.GENERATOR, *,
                        label: InputLabel | None = None, oscar: bool = True,
                        model: Optional[p300.P300Model] = None,
                        flashes_per_tile: int = p300.FLASHES_PER_TILE,
                        handler: Optional[SelectionHandler] = None
                        ) -> P300Evidence:
    """Build (don't start) the evidence graph with the chooser's nodes in it.

    Args:
        kind: Generator (simulated, with the chooser's synthetic P300) or
            HybridBlack (live).
        label: Input label; defaults as in ``build_evidence_graph``.
        oscar: Headset only. OSCAR is shown on its own branch; the classifier and the
            averages use the OSCAR-off stream, because the branch's ~324 ms delay
            misaligns epochs with the flash markers (#164).
        model: Fitted model for the online scorers. g.Pype refuses to start
            unfitted scorers, so by default a small synthetic placeholder is
            fitted; calibration in the run replaces it.
        flashes_per_tile: Flashes per tile in a sequence.
        handler: SelectionHandler the decisions go to. The default one is
            preview-only: the evidence view cancels each round after its
            preview, so its sink is never asked to confirm anything.
    """
    kind = SourceKind(kind)
    synth = p300.SyntheticP300(name="p300_synth") \
        if kind is SourceKind.GENERATOR else None
    graph = build_evidence_graph(
        kind, label=label, oscar=oscar, front_end=p300.p300_front_end,
        synthetic_node=synth, synthetic_p300=synth is not None,
        target_code=p300.CAL_TARGET, nontarget_code=p300.CAL_NONTARGET,
        time_pre=p300.TIME_PRE, time_post=p300.TIME_POST, average_oscar=True)
    graph.extra_markers = tuple(
        (code, str(code), "y") for code in p300.FLASH_CODES.values())
    stream = "OSCAR on" if graph.epoch_input is graph.oscar \
        and graph.oscar is not None else "filtered"
    graph.average_title = (
        f"Averaged response, target vs non-target calibration flashes "
        f"({stream}; the epochs the LDA trains on) ({graph.label.value})")

    if model is None:
        model = p300.train_on_synthetic(n_sequences=4, seed=99)
    p = graph.pipeline
    triggers, scorers, sinks = {}, {}, []
    for tile, code in p300.FLASH_CODES.items():
        trig = gp.Trigger(time_pre=p300.TIME_PRE, time_post=p300.TIME_POST,
                          target=code, name=f"p300_trigger_{code}")
        scorer = model.scorer(tile_id=tile, name=f"p300_scorer_{code}")
        sink = gp.Collector(name=f"p300_scores_{code}")
        p.connect(graph.epoch_input, trig)
        p.connect(graph.marker, trig[gp.Trigger.PORT_TRIGGER])
        p.connect(trig, scorer)
        p.connect(scorer, sink)
        triggers[tile], scorers[tile] = trig, scorer
        sinks.append(sink)

    # Calibration epochs come straight off the averages' Triggers.
    cal_triggers = {p300.TARGET_LABEL: graph.target_trigger,
                    p300.NONTARGET_LABEL: graph.nontarget_trigger}
    cal_collectors = {}
    for lab, trig in cal_triggers.items():
        coll = gp.Collector(name=f"p300_cal_epochs_{lab}")
        p.connect(trig, coll)
        cal_collectors[lab] = coll

    nodes = p300.P300Nodes(p, graph.source, graph.epoch_input, graph.marker,
                           synth, triggers, scorers, cal_triggers,
                           cal_collectors, sinks)
    handler = handler or SelectionHandler(_PreviewOnlySink())
    adapter = InputAdapter(handler, input_source(graph.label))
    return P300Evidence(graph, nodes, handler, adapter, flashes_per_tile)


class _PreviewOnlySink:
    """Default action sink for the evidence view.

    The evidence view stops at the preview: ``P300Session`` cancels every
    round right after the chooser's decision is previewed, so nothing is ever
    confirmed and this sink is never called. Confirmation belongs to the app.
    """

    def execute(self, action) -> None:
        print(f"[evidence p300] unexpected confirm: {action}")


class P300Session:
    """Runs calibration, then selection rounds forever, on QTimers.

    Callbacks (all on the Qt main thread): ``on_light(tile, lit)``,
    ``on_cue(tile or None)``, ``on_status(text)``.
    """

    def __init__(self, ev: P300Evidence, calibration: int = DEFAULT_CALIBRATION,
                 soa: float = p300.SOA_S, seed: int = 0,
                 on_light: Callable[[str, bool], None] = lambda t, lit: None,
                 on_cue: Callable[[Optional[str]], None] = lambda t: None,
                 on_status: Callable[[str], None] = lambda s: None):
        self.ev = ev
        self.calibration = max(1, calibration)
        self.soa = soa
        self.rng = random.Random(seed)
        self.on_light, self.on_cue, self.on_status = on_light, on_cue, on_status
        self.tiles = list(p300.FLASH_CODES)
        self.attended: List[str] = []
        self.hits = self.decided = 0
        self.simulated = ev.nodes.synth is not None

    def start(self) -> None:
        from PySide6.QtCore import QTimer

        chooser = self.ev.chooser or self.ev.attach_chooser(use_qt=True)
        chooser.bridge.listeners.append(self._on_decision)
        self.on_status(f"Calibrating: {self.calibration} sequences, attend "
                       "the cued tile")
        QTimer.singleShot(1000, lambda: self._sequence(0))  # fill Triggers

    def _sequence(self, i: int) -> None:
        from PySide6.QtCore import QTimer

        chooser = self.ev.chooser
        calibrating = i < self.calibration
        attended = self.tiles[i % 2] if calibrating else \
            self.rng.choice(self.tiles)
        if calibrating:
            chooser.begin_calibration(attended)
            self.on_status(f"Calibration {i + 1}/{self.calibration}: "
                           f"attend {attended}")
        else:
            if i == self.calibration:
                try:
                    model = chooser.finish_calibration()
                    self.on_status(
                        f"LDA trained on {model.n_target} target and "
                        f"{len(model.trials) - model.n_target} non-target "
                        "calibration epochs. Selecting...")
                except Exception as error:  # noqa: BLE001 - shown on screen
                    self.on_status(f"Calibration failed: {error}")
            self.ev.handler.begin_choice_round(CHOICES)
            self.attended.append(attended)
            chooser.begin_sequence(attended_for_synthetic=attended)
        # Simulated selection rounds: no cue, the synthetic P300 picks the tile.
        self.on_cue(attended if calibrating or not self.simulated else None)

        order = p300.make_sequence(self.ev.flashes_per_tile, self.rng)
        lead = 1.0  # time to look at the cued tile
        for k, tile in enumerate(order):
            QTimer.singleShot(int((lead + k * self.soa) * 1000),
                              lambda t=tile: self._flash(t))
        tail = lead + len(order) * self.soa + p300.TIME_POST + 0.4
        QTimer.singleShot(int(tail * 1000), lambda: self._after(i, calibrating))

    def _flash(self, tile: str) -> None:
        from PySide6.QtCore import QTimer

        self.on_light(tile, True)
        QTimer.singleShot(int(p300.FLASH_ON_S * 1000),
                          lambda: self.on_light(tile, False))
        self.ev.chooser.on_flash(tile)

    def _after(self, i: int, calibrating: bool) -> None:
        if not calibrating and self.ev.chooser.aggregator.is_open:
            self.ev.chooser.end_sequence()  # dropped epochs: decide anyway
        self._sequence(i + 1)

    def _on_decision(self, cls: int, target: Optional[str], outcome) -> None:
        truth = self.attended.pop(0) if self.attended else None
        self.decided += 1
        self.hits += target == truth
        name = next((c.label for c in CHOICES if c.target_id == target),
                    target)
        who = "simulated attended" if self.simulated else "cued"
        text = (f"Decision {self.decided}: class {cls} -> {target} ({name}) "
                f"-> {getattr(outcome, 'name', outcome)}; {who} {truth}; "
                f"{self.hits}/{self.decided} correct")
        print(f"[evidence p300] {text}")
        self.on_status(text)
        self.ev.handler.cancel("next sequence")


def make_header(banner, session_box: dict):
    """Banner, two tiles and a decision label. Fills ``session_box``."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

    header = QWidget()
    column = QVBoxLayout(header)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    column.addWidget(banner)
    row = QHBoxLayout()
    row.setContentsMargins(8, 6, 8, 6)
    tiles = {}
    for tile in p300.FLASH_CODES:
        lab = QLabel(tile)
        lab.setFixedSize(180, 70)
        lab.setStyleSheet(tile_style(False))
        row.addWidget(lab)
        tiles[tile] = lab
    status = QLabel("P300 chooser starting...")
    status.setWordWrap(True)
    status.setStyleSheet("font-size:15px; font-weight:bold; padding-left:12px;")
    row.addWidget(status, 1)
    column.addLayout(row)
    session_box.update(tiles=tiles, status=status, cue=None)
    return header


def tile_style(lit: bool, cued: bool = False) -> str:
    border = "5px solid #e0a000" if cued else "5px solid #333"
    bg, fg = ("#ffffff", "#000000") if lit else ("#202020", "#cccccc")
    return (f"background:{bg}; color:{fg}; border:{border}; font-size:20px;"
            " qproperty-alignment:AlignCenter;")


def wire_session(session: P300Session, box: dict) -> None:
    """Point the session's callbacks at the header widgets in ``box``."""
    def light(tile, lit):
        lab = box["tiles"][tile]
        lab.setStyleSheet(tile_style(lit, tile == box["cue"]))
        lab.repaint()  # paint before the marker, as close as Qt allows

    def cue(tile):
        box["cue"] = tile
        for t, lab in box["tiles"].items():
            lab.setStyleSheet(tile_style(False, t == tile))

    session.on_light, session.on_cue = light, cue
    session.on_status = box["status"].setText
