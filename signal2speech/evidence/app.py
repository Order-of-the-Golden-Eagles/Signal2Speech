"""The judge-facing evidence window: g.Pype MainApp plus scopes.

Layout with the headset (3 rows x 2 columns)::

    raw EEG + flash markers          | filtered EEG, OSCAR off
    filtered EEG, OSCAR on           | spectrum (FFT of raw EEG)
    averaged target vs non-target response (TriggerScope)

With the Generator there is no OSCAR panel, so the grid is 2 x 2. The
input label (Simulated / Recorded / Live EEG) is in the window title and
in a coloured banner above the scopes, with the OSCAR state.
"""

from __future__ import annotations

import gpype as gp

from .pipeline import EEG_CHANNELS, EvidenceGraph
from .synthetic import NONTARGET_CODE, TARGET_CODE



def _with_markers(graph: EvidenceGraph, node, name: str):
    """Route ``node`` and the flash markers into one stream for a scope."""
    p = graph.pipeline
    both = gp.Router(input_channels=[gp.Router.ALL, gp.Router.ALL],
                     name=f"{name}_with_markers")
    p.connect(node, both["in1"])
    p.connect(graph.marker, both["in2"])
    return both


def _time_scope(name: str, amplitude: float):
    mk = gp.TimeSeriesScope.Markers
    markers = [mk(color="r", label="T", channel=EEG_CHANNELS,
                  value=TARGET_CODE),
               mk(color="c", label="NT", channel=EEG_CHANNELS,
                  value=NONTARGET_CODE)]
    return gp.TimeSeriesScope(name=name, amplitude_limit=amplitude,
                              time_window=10, markers=markers,
                              hidden_channels=[EEG_CHANNELS])


def add_scopes(graph: EvidenceGraph) -> list:
    """Create the scopes and connect them. Returns ``[(widget, cells)]``."""
    p = graph.pipeline
    label = graph.label.value
    placed = []

    raw_scope = _time_scope(f"Raw EEG ({label})", 50)
    p.connect(_with_markers(graph, graph.raw, "raw"), raw_scope)
    placed.append((raw_scope, [1]))

    oscar_off = ", OSCAR off" if graph.oscar is not None else ""
    filtered_scope = _time_scope(f"Filtered EEG 1-30 Hz{oscar_off} ({label})",
                                 30)
    p.connect(_with_markers(graph, graph.filtered, "filtered"),
              filtered_scope)
    placed.append((filtered_scope, [2]))

    if graph.oscar is not None:
        oscar_scope = _time_scope(f"Filtered EEG, OSCAR on ({label})", 30)
        p.connect(_with_markers(graph, graph.oscar, "oscar"), oscar_scope)
        placed.append((oscar_scope, [3]))

    spectrum = gp.SpectrumScope(name=f"Spectrum ({label})",
                                amplitude_limit=5)
    p.connect(graph.spectrum, spectrum)
    placed.append((spectrum, [4]))

    average = gp.TriggerScope(
        name=f"Averaged response, target vs non-target ({label})",
        amplitude_limit=8, plots=["T", "NT"],
        labels=["Target flashes", "Non-target flashes"], colors=["r", "c"])
    p.connect(graph.target_epochs, average["T"])
    p.connect(graph.nontarget_epochs, average["NT"])
    placed.append((average, [5, 6] if graph.oscar is not None else [3]))

    return placed


BANNER_COLORS = {"Simulated": "#c98a00", "Recorded": "#2f6fb0",
                 "Live EEG": "#2e8b57"}


def banner_text(graph: EvidenceGraph) -> str:
    """The one-line label shown above the scopes."""
    parts = [f"INPUT: {graph.label.value.upper()}", graph.oscar_note]
    if graph.detail:
        parts.append(graph.detail)
    return "   |   ".join(parts)


def _banner(graph: EvidenceGraph):
    from PySide6.QtWidgets import QLabel

    label = QLabel(banner_text(graph))
    label.setWordWrap(True)
    color = BANNER_COLORS.get(graph.label.value, "#555555")
    label.setStyleSheet(f"background:{color}; color:white; font-size:16px;"
                        " font-weight:bold; padding:6px 12px;")
    return label


def run_window(graph: EvidenceGraph, on_started=None) -> int:
    """Open the window, run the pipeline, and block until it closes."""
    grid = [3, 2] if graph.oscar is not None else [2, 2]
    app = gp.MainApp(caption=graph.caption, grid_size=grid,
                     position=[60, 60, 1400, 900])
    for widget, cells in add_scopes(graph):
        app.add_widget(widget, grid_positions=cells)
    window = app.window
    if window is not None:
        window.setMenuWidget(_banner(graph))
    try:
        graph.pipeline.start()
    except Exception as error:  # noqa: BLE001 - shown to the operator
        graph.pipeline.close()
        cause = error
        while cause.__cause__ is not None:
            cause = cause.__cause__
        raise SystemExit(f"Could not start the {graph.label.value} "
                         f"pipeline: {cause}") from error
    if on_started is not None:
        on_started(app)
    try:
        return app.run()
    finally:
        graph.pipeline.stop()
        graph.pipeline.close()
