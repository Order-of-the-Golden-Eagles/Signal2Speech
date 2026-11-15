"""The evidence pipeline: source → front end → scopes and averages.

Built without a window so tests can check the graph headlessly. The GUI
in ``app.py`` adds scopes to the same nodes.

Seam for #46: ``front_end`` is any callable ``(pipeline, eeg) -> node``
that connects its own filter chain after the EEG node and returns the
node whose output is "filtered EEG". It may be called twice (once for
the OSCAR branch), so it should build fresh nodes each call. The default
is a 1–30 Hz bandpass with 50 and 60 Hz notches, the chain in the
selection contract. ``signal2speech.evidence.p300_mode`` passes the P300
chooser's ``p300_front_end`` here, swaps in the chooser's synthetic P300
node and marker codes, and hangs the chooser's scorers on the same
Triggers the averages use, so the judge sees exactly what the classifier
sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

import gpype as gp

from .synthetic import NONTARGET_CODE, TARGET_CODE, SyntheticP300

#: Sampling rate of the Unicorn Hybrid Black, used for the Generator too.
SAMPLING_RATE = 250
#: EEG channels on the Unicorn Hybrid Black.
EEG_CHANNELS = 8
#: Epoch window around each flash, in seconds.
TIME_PRE = 0.2
TIME_POST = 0.8


class SourceKind(str, Enum):
    """Where the EEG comes from."""

    GENERATOR = "generator"
    HYBRIDBLACK = "hybridblack"


class InputLabel(str, Enum):
    """How the input is labelled to judges. Matches the contract's sources."""

    SIMULATED = "Simulated"
    RECORDED = "Recorded"
    LIVE = "Live EEG"


FrontEnd = Callable[[gp.Pipeline, object], object]


def default_front_end(p: gp.Pipeline, eeg) -> object:
    """Bandpass 1–30 Hz, then notch 50 and 60 Hz. Returns the last node."""
    bandpass = gp.Bandpass(f_lo=1, f_hi=30)
    notch50 = gp.Bandstop(f_lo=48, f_hi=52)
    notch60 = gp.Bandstop(f_lo=58, f_hi=62)
    p.connect(eeg, bandpass)
    p.connect(bandpass, notch50)
    p.connect(notch50, notch60)
    return notch60


@dataclass
class EvidenceGraph:
    """The nodes of one evidence pipeline, for scopes and tests to reach."""

    pipeline: gp.Pipeline
    kind: SourceKind
    label: InputLabel
    source: object
    marker: object
    raw: object
    filtered: object
    spectrum: object
    target_epochs: object
    nontarget_epochs: object
    target_average: object
    nontarget_average: object
    oscar: Optional[object] = None
    oscar_note: str = ""
    detail: str = ""
    #: The filtered stream the Triggers cut epochs from (the OSCAR branch
    #: when ``average_oscar`` asked for it and it exists).
    epoch_input: Optional[object] = None
    target_trigger: Optional[object] = None
    nontarget_trigger: Optional[object] = None
    target_code: int = TARGET_CODE
    nontarget_code: int = NONTARGET_CODE
    #: Extra ``(value, label, colour)`` markers for the time scopes.
    extra_markers: tuple = ()
    #: Title of the averaged-response scope; empty means the default.
    average_title: str = ""

    @property
    def caption(self) -> str:
        return f"Signal2Speech evidence | Input: {self.label.value}"


def oscar_node():
    """A standalone OSCAR node, or None when this g.Pype cannot build one.

    g.Pype builds OSCAR inside a source when ``enable_oscar=True``, so a
    source gives either cleaned or uncleaned EEG, never both. For a
    side-by-side comparison we build the source with OSCAR off and run
    the same ``Oscar`` node on a branch. That class lives in a private
    module (``gpype.backend.core._private.oscar``), so this falls back to
    the single-stream mode if it moves.
    """
    try:
        from gpype.backend.core._private.oscar import Oscar
    except ImportError:
        return None
    try:
        return Oscar(name="oscar")
    except Exception:  # noqa: BLE001 - e.g. the OSCAR runtime is missing
        return None


def make_source(kind: SourceKind, oscar: bool = False):
    """The EEG source. Named ``eeg`` so a recording replays into it."""
    if kind is SourceKind.GENERATOR:
        return gp.Generator(name="eeg", sampling_rate=SAMPLING_RATE,
                            channel_count=EEG_CHANNELS, signal_frequency=10,
                            signal_amplitude=5, noise_amplitude=4)
    return gp.HybridBlack(name="eeg", enable_oscar=oscar)


def build_evidence_graph(kind: SourceKind | str = SourceKind.GENERATOR, *,
                         label: InputLabel | None = None,
                         oscar: bool = True,
                         front_end: FrontEnd = default_front_end,
                         synthetic_p300: bool | None = None,
                         synthetic_node=None,
                         target_code: int = TARGET_CODE,
                         nontarget_code: int = NONTARGET_CODE,
                         time_pre: float = TIME_PRE,
                         time_post: float = TIME_POST,
                         average_oscar: bool = False,
                         dataset=None) -> EvidenceGraph:
    """Build the evidence pipeline without starting it or opening a window.

    Args:
        kind: The source to build (for a replay, the source that was recorded).
        label: How to label the input. Defaults to Simulated for the
            Generator and Live EEG for the headset; pass RECORDED for a replay.
        oscar: Show OSCAR. For the headset and for g.tec's recording
            (``dataset``), the main stream stays OSCAR off and a branch runs
            OSCAR on, so both are visible. If the standalone OSCAR node is
            unavailable, the headset is built with ``enable_oscar=True``
            instead; the recording then shows OSCAR off. Never run on the
            Generator's own simulated samples.
        front_end: Seam for #46. See the module docstring.
        synthetic_p300: Add the simulated P300 after target markers.
            Defaults to True for the Generator and False otherwise.
        synthetic_node: Use this node as the synthetic P300 instead of the
            built-in one. It gets the EEG on its ``in`` port and the
            marker on its ``trigger`` port (``eeg.p300.SyntheticP300``).
            Implies ``synthetic_p300``.
        target_code, nontarget_code: Marker codes the two averages
            trigger on.
        time_pre, time_post: Epoch window around each flash, in seconds.
        average_oscar: Cut epochs from the OSCAR branch when there is one.
        dataset: A ``dataset.Session`` (g.tec's recorded P300 data, #142). The
            Generator then only clocks the pipeline: the recorded EEG and its
            flash codes replace its samples. Labelled Recorded.

    Returns:
        The graph. Call ``graph.pipeline.start()`` to run it.
    """
    kind = SourceKind(kind)
    if label is None:
        label = InputLabel.SIMULATED if kind is SourceKind.GENERATOR \
            else InputLabel.LIVE
    if dataset is not None:
        kind = SourceKind.GENERATOR          # the clock; its samples are replaced
        label = InputLabel.RECORDED
        synthetic_p300, synthetic_node = False, None
    if synthetic_p300 is None:
        synthetic_p300 = kind is SourceKind.GENERATOR

    oscar_branch = None
    in_source_oscar = False
    if dataset is not None:
        # #164: the same OSCAR branch as the headset, on g.tec's recording (8 channels, uV).
        from .dataset import LABEL_DETAIL
        oscar_branch = oscar_node() if oscar else None
        who = f"{LABEL_DETAIL}, subject {dataset.name}: recorded by g.tec, not our headset or wearer"
        if not oscar:
            oscar_note = f"{who}. OSCAR off"
        elif oscar_branch is not None:
            oscar_note = f"{who}. OSCAR off (top right) vs OSCAR on (middle left)"
        else:
            oscar_note = f"{who}. OSCAR unavailable in this g.Pype, so not applied"
    elif kind is SourceKind.GENERATOR:
        oscar_note = "OSCAR unavailable: Generator input, no headset"
    elif not oscar:
        oscar_note = "OSCAR off"
    else:
        oscar_branch = oscar_node()
        if oscar_branch is not None:
            oscar_note = "OSCAR off (top right) vs OSCAR on (middle left)"
        else:
            in_source_oscar = True
            oscar_note = ("OSCAR on inside the source; run again with "
                          "--oscar off to compare")

    p = gp.Pipeline()
    source = make_source(kind, in_source_oscar)
    marker = gp.Marker(name="flashes")

    if synthetic_node is not None:
        p.connect(source, synthetic_node)
        p.connect(marker, synthetic_node["trigger"])
        raw = synthetic_node
    elif synthetic_p300:
        mixed = gp.Router(input_channels=[gp.Router.ALL, gp.Router.ALL],
                          name="eeg_with_markers")
        p.connect(source, mixed["in1"])
        p.connect(marker, mixed["in2"])
        raw = SyntheticP300(name="synthetic_p300")
        p.connect(mixed, raw)
    elif dataset is not None:
        from .dataset import make_player_nodes
        raw, recorded_flashes = make_player_nodes(dataset)
        p.connect(source, raw)
        p.connect(source, recorded_flashes)
        marker = recorded_flashes            # scopes and epochs use the recorded flashes
    else:
        raw = source

    filtered = front_end(p, raw)

    oscar_filtered = None
    if oscar_branch is not None:
        p.connect(raw, oscar_branch)
        oscar_filtered = front_end(p, oscar_branch)

    fft = gp.FFT(window_size=SAMPLING_RATE, overlap=0.5,
                 window_function="hamming", name="fft")
    p.connect(raw, fft)

    epoch_input = oscar_filtered if (average_oscar and oscar_filtered
                                     is not None) else filtered
    epochs, averages, triggers = {}, {}, {}
    for name, code in (("target", target_code),
                       ("nontarget", nontarget_code)):
        trigger = gp.Trigger(time_pre=time_pre, time_post=time_post,
                             target=code, name=f"{name}_trigger")
        baseline = gp.Baseline(name=f"{name}_epochs")
        average = gp.EpochAverage(name=f"{name}_average")
        p.connect(epoch_input, trigger)
        p.connect(marker, trigger[gp.Trigger.PORT_TRIGGER])
        p.connect(trigger, baseline)
        p.connect(baseline, average)
        epochs[name], averages[name] = baseline, average
        triggers[name] = trigger

    return EvidenceGraph(
        pipeline=p, kind=kind, label=label, source=source, marker=marker,
        raw=raw, filtered=filtered, spectrum=fft,
        target_epochs=epochs["target"],
        nontarget_epochs=epochs["nontarget"],
        target_average=averages["target"],
        nontarget_average=averages["nontarget"],
        oscar=oscar_filtered, oscar_note=oscar_note,
        epoch_input=epoch_input, target_trigger=triggers["target"],
        nontarget_trigger=triggers["nontarget"], target_code=target_code,
        nontarget_code=nontarget_code)
