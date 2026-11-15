"""Our g.Pype pipelines as Mermaid diagrams, drawn from the real pipeline objects (#166).

    python -m signal2speech.evidence.diagram                 # every mode, printed
    python -m signal2speech.evidence.diagram app             # one mode
    python -m signal2speech.evidence.diagram --source generator evidence
    python -m signal2speech.evidence.diagram --write         # regenerate the docs

Nothing here is drawn by hand. Each mode calls the same builder the app or tool uses, builds the
pipeline without starting it (no headset needed), and walks ``Pipeline.serialize()``: g.Pype's
own record of every node, its parameters, and every connection. ``--write`` puts the diagrams in
``docs/architecture/pipelines.md`` and the README. ``tests/test_diagram.py`` fails when the
pipelines change and the docs weren't regenerated.

Modes: ``evidence`` (the evidence view), ``p300`` (the P300 chooser), ``alpha`` (the standalone
eye-closure switch), and ``app`` (what ``--input live`` runs: the chooser and the switch on one
headset). ``--source hybridblack`` (the default) draws the Unicorn; ``generator`` draws the
simulated input.
"""
from __future__ import annotations

import argparse
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture" / "pipelines.md"
README = ROOT / "README.md"
MODES = ("app", "evidence", "p300", "alpha")
SOURCES = ("hybridblack", "generator")
README_MODE = "app"
BEGIN = "<!-- BEGIN generated pipeline diagram: {mode} ({source}). python -m signal2speech.evidence.diagram --write -->"
END = "<!-- END generated pipeline diagram -->"

TITLES = {
    "app": "The app with live EEG (`python -m signal2speech.app --input live`)",
    "evidence": "The evidence view (`python -m signal2speech.evidence --p300`)",
    "p300": "The P300 chooser (`python -m signal2speech.eeg.p300`)",
    "alpha": "The eye-closure switch on its own (`python -m signal2speech.eeg.alpha_confirm`)",
}
SOURCE_LABELS = {"hybridblack": "Live EEG: g.tec Unicorn Hybrid Black",
                 "generator": "Simulated: g.Pype Generator"}


# ── Graph from a pipeline ────────────────────────────────────
@dataclass
class Node:
    key: str            # n1, n2, ... in g.Pype's own order, so the text is stable
    name: str
    cls: str
    detail: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)


@dataclass
class Graph:
    nodes: List[Node]
    edges: List[Tuple[str, str, str, str]]     # (from key, from port, to key, to port)

    def as_dict(self) -> dict:
        """A small summary for the MCP pipeline_graph tool (#110)."""
        return {"nodes": [{"id": n.key, "name": n.name, "type": n.cls, "detail": n.detail}
                          for n in self.nodes],
                "edges": [f"{a}.{ap} -> {b}.{bp}" for a, ap, b, bp in self.edges]}


def _hz(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def describe(cls: str, cfg: dict) -> str:
    """The parameters a reader needs, per node type. Unknown types show only their type."""
    g = cfg.get
    if cls in ("Bandpass", "Bandstop") and g("f_lo") is not None:
        return f"{_hz(g('f_lo'))}–{_hz(g('f_hi'))} Hz"
    if cls == "Trigger":
        return (f"{round(g('time_pre', 0) * 1000)} ms before to {round(g('time_post', 0) * 1000)} "
                f"ms after code {', '.join(str(c) for c in g('target') or [])}")
    if cls == "FFT":
        return f"{g('window_size')} samples, {round(g('overlap', 0) * 100)}% overlap"
    if cls == "BandPower":
        bands = []
        for band in g("bands") or []:
            if isinstance(band, (list, tuple)) and len(band) == 3:
                bands.append(f"{band[0]} {_hz(band[1])}–{_hz(band[2])} Hz")
            else:
                bands.append(str(band))
        return ", ".join(bands)
    if g("estimator"):                                  # gp.Sklearn and our P300Scorer
        shrink = (g("params") or {}).get("shrinkage")
        return f"{g('estimator')}" + (f", shrinkage {shrink}" if shrink else "")
    if cls == "Collector":
        return "hands its data to our Python code"
    if cls == "ChannelSelector":
        if g("indices") is not None:
            return "channels " + ", ".join(str(i + 1) for i in g("indices"))
        return str(g("roles") or "")
    if cls == "HybridBlack":
        return (f"{_hz(g('sampling_rate'))} Hz, {g('eeg_channel_count') or (g('channel_count') or ['?'])[0]} "
                f"EEG channels, OSCAR {'on' if g('enable_oscar') else 'off'}")
    if cls == "Generator":
        return f"{_hz(g('sampling_rate'))} Hz, {(g('channel_count') or ['?'])[0]} channels, simulated"
    if cls == "LslReceiver":
        return f"LSL stream {g('stream_name')}"
    if cls in ("Baseline", "EpochAverage") and g("mode"):
        return str(g("mode"))
    if cls == "SyntheticP300":
        return "simulated P300 on the attended tile"
    if cls == "AlphaBursts":
        return "simulated eyes-closed alpha"
    if cls == "Oscar":
        return "artifact removal"
    if cls == "Threshold":
        return f"{g('direction', 'above')} the calibrated level for {g('dwell')} frames"
    return ""


def graph_of(pipeline) -> Graph:
    """Walk g.Pype's serialized record of ``pipeline``: nodes, parameters, connections."""
    data = pipeline.serialize()
    nodes: List[Node] = []
    by_id: Dict[str, Node] = {}
    by_port: Dict[str, Tuple[Node, str]] = {}
    names: Dict[str, List[Node]] = {}
    for i, raw in enumerate(data["nodes"], 1):
        cfg = raw.get("config", {})
        node = Node(f"n{i}", str(cfg.get("name") or raw["class"]), raw["class"],
                    describe(raw["class"], cfg),
                    [p["name"] for p in cfg.get("input_ports", [])],
                    [p["name"] for p in cfg.get("output_ports", [])])
        nodes.append(node)
        by_id[cfg.get("id", node.key)] = node
        names.setdefault(node.name, []).append(node)
        for p in cfg.get("input_ports", []) + cfg.get("output_ports", []):
            by_port[p["id"]] = (node, p["name"])

    def resolve(ref: str) -> Tuple[Node, str]:
        if ref in by_port:                              # a port id
            return by_port[ref]
        name, _, port = ref.rpartition(".")             # "name.port" when the name is unique
        if len(names.get(name, [])) == 1:
            return names[name][0], port
        raise ValueError(f"can't resolve connection end {ref!r}")

    edges = []
    for src, dst in data["connections"]:
        (a, ap), (b, bp) = resolve(src), resolve(dst)
        edges.append((a.key, ap, b.key, bp))
    return Graph(nodes, edges)


def _esc(text: str) -> str:
    return text.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")


def mermaid(graph: Graph) -> str:
    """A left-to-right Mermaid flowchart. Sources are rounded, sinks are boxed twice."""
    has_in = {b for _, _, b, _ in graph.edges}
    has_out = {a for a, _, _, _ in graph.edges}
    lines = ["flowchart LR"]
    for n in graph.nodes:
        label = _esc(n.name if n.name == n.cls else f"{n.name}: {n.cls}")
        if n.detail:
            label += "<br/><small>" + _esc(n.detail) + "</small>"
        if n.key not in has_in:
            lines.append(f'    {n.key}(["{label}"])')
        elif n.key not in has_out:
            lines.append(f'    {n.key}[["{label}"]]')
        else:
            lines.append(f'    {n.key}["{label}"]')
    for a, ap, b, bp in graph.edges:
        tag = " → ".join(p for p in (ap if ap != "out" else "", bp if bp != "in" else "") if p)
        lines.append(f"    {a} -->|{tag}| {b}" if tag else f"    {a} --> {b}")
    return "\n".join(lines)


# ── The real builders, built but never started ───────────────
@contextmanager
def built(mode: str, source: str = "hybridblack") -> Iterator[object]:
    """Yield the pipeline ``mode`` runs, built by the same code the app or tool uses."""
    if mode not in MODES:
        raise ValueError(f"mode is one of {', '.join(MODES)}")
    if source not in SOURCES:
        raise ValueError(f"source is one of {', '.join(SOURCES)}")
    # No Qt application is created here: AlphaConfirm is a plain QObject, and creating a
    # QCoreApplication would stop any later QApplication (the app's windows) in this process.
    from signal2speech.core import InputSources, SelectionHandler

    class _NoSink:
        def execute(self, _action) -> None:
            raise AssertionError("a diagram build never confirms anything")

    handler = SelectionHandler(_NoSink())
    live = source == "hybridblack"
    closers: List[object] = []
    pipeline = None
    try:
        if mode == "evidence":
            from signal2speech.evidence.p300_mode import build_p300_evidence
            from signal2speech.eeg.app_live import placeholder_model
            ev = build_p300_evidence(source, model=placeholder_model())
            pipeline = ev.graph.pipeline
        elif mode == "p300":
            from signal2speech.eeg import p300
            from signal2speech.eeg.app_live import placeholder_model
            pipeline = p300.build_pipeline(source, model=placeholder_model()).pipeline
        elif mode == "alpha":
            from signal2speech.eeg import alpha_confirm as am
            src, bursts, label = am.standalone_source("hybrid-black" if live else "generator")
            ac = am.AlphaConfirm(handler, input_source=label, source=src, bursts=bursts)
            closers.append(ac)
            pipeline = ac.pipeline
        else:
            from signal2speech.eeg import p300
            from signal2speech.eeg.app_live import build_live_alpha, placeholder_model
            nodes = p300.build_pipeline(source, model=placeholder_model())
            if not live:
                # Simulated, the alpha switch runs on a second pipeline; draw the chooser's.
                closers.append(build_live_alpha(handler, nodes, InputSources.SIMULATED,
                                                simulated=True)[0])
            else:
                closers.append(build_live_alpha(handler, nodes, InputSources.LIVE_EEG,
                                                simulated=False)[0])
            pipeline = nodes.pipeline
        yield pipeline
    finally:
        for c in closers:
            c.close()
        if pipeline is not None:
            pipeline.close()


def diagram(mode: str, source: str = "hybridblack") -> str:
    with built(mode, source) as pipeline:
        return mermaid(graph_of(pipeline))


# ── Docs ─────────────────────────────────────────────────────
def block(mode: str, source: str, text: Optional[str] = None) -> str:
    text = diagram(mode, source) if text is None else text
    return f"{BEGIN.format(mode=mode, source=source)}\n```mermaid\n{text}\n```\n{END}"


def render_doc() -> str:
    parts = ["# Our g.Pype pipelines (generated)", "",
             "Generated by `python -m signal2speech.evidence.diagram --write` from the real "
             "pipeline objects (#166): each mode calls the same builder the app or tool uses and "
             "walks g.Pype's `Pipeline.serialize()`. Don't edit the diagrams by hand. "
             "`tests/test_diagram.py` fails when they're out of date.", "",
             "Rounded boxes are sources, double boxes are ends of the graph. Edge labels name the "
             "ports that aren't the default `out` → `in` (for example a Trigger's `trigger` input, "
             "which takes the flash markers). `Collector` and `_Tap` nodes hand data to our Python "
             "code: the classifier's scores, the alpha switch's power and state. The evidence "
             "view's scopes and spectrum attach to its nodes when its window opens, so the nodes "
             "they read (the raw filter and the FFT) show here as ends.", ""]
    for mode in MODES:
        for source in SOURCES:
            if mode == "app" and source == "generator":
                continue                                # same chooser as p300 (generator)
            parts += [f"## {TITLES[mode]}: {SOURCE_LABELS[source]}", "", block(mode, source), ""]
    parts += ["Simulated `--input simulated --p300` runs the chooser drawn under the P300 chooser "
              "(Simulated), and its alpha switch on a second Generator with simulated alpha "
              "bursts, drawn under the eye-closure switch (Simulated).", ""]
    return "\n".join(parts)


def replace_block(text: str, mode: str, source: str, new_block: str) -> str:
    pat = re.compile(re.escape(BEGIN.format(mode=mode, source=source)) + r".*?" + re.escape(END),
                     re.S)
    if not pat.search(text):
        raise ValueError(f"no generated block for {mode} ({source}) found")
    return pat.sub(lambda _m: new_block, text, count=1)


def write_docs() -> List[Path]:
    DOC.write_text(render_doc(), encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    README.write_text(replace_block(readme, README_MODE, "hybridblack",
                                    block(README_MODE, "hybridblack")), encoding="utf-8")
    return [DOC, README]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.evidence.diagram",
                                 description="Mermaid diagrams of our g.Pype pipelines (#166)")
    ap.add_argument("modes", nargs="*", choices=[[], *MODES], default=[],
                    help=f"which pipelines (default: all): {', '.join(MODES)}")
    ap.add_argument("--source", choices=SOURCES, default="hybridblack",
                    help="hybridblack (Live EEG, the default) or generator (Simulated)")
    ap.add_argument("--write", action="store_true",
                    help="regenerate docs/architecture/pipelines.md and the README diagram")
    args = ap.parse_args(argv)
    if args.write:
        for path in write_docs():
            print(f"wrote {path.relative_to(ROOT)}")
        return 0
    for mode in args.modes or MODES:
        print(f"%% {TITLES[mode]}: {SOURCE_LABELS[args.source]}")
        print(diagram(mode, args.source))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
