"""#166: the pipeline diagrams come from the real g.Pype pipelines, and the docs stay in sync."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("gpype")
pytest.importorskip("sklearn")

import gpype as gp  # noqa: E402

from signal2speech.evidence import diagram  # noqa: E402

FIX = "Run `python -m signal2speech.evidence.diagram --write` and commit the result."


def test_docs_match_the_pipelines_the_code_builds():
    """Fails when a pipeline changes and the diagrams weren't regenerated."""
    assert diagram.DOC.read_text(encoding="utf-8") == diagram.render_doc(), FIX
    readme = diagram.README.read_text(encoding="utf-8")
    want = diagram.block(diagram.README_MODE, "hybridblack")
    assert want in readme, FIX


def test_connections_resolve_even_when_node_names_repeat():
    """g.Pype names a connection end by "name.port" when the name is unique, else by port id."""
    p = gp.Pipeline()
    src = gp.Generator(sampling_rate=250, channel_count=2)
    a, b = gp.Bandpass(f_lo=1, f_hi=30), gp.Bandpass(f_lo=8, f_hi=13)      # both "Bandpass"
    sel = gp.ChannelSelector(indices=[1])
    p.connect(src, a)
    p.connect(a, b)
    p.connect(b, sel)
    try:
        g = diagram.graph_of(p)
    finally:
        p.close()
    kinds = {n.key: (n.cls, n.detail) for n in g.nodes}
    assert [(kinds[x], kinds[y]) for x, _, y, _ in g.edges] == [
        (("Generator", "250 Hz, 2 channels, simulated"), ("Bandpass", "1–30 Hz")),
        (("Bandpass", "1–30 Hz"), ("Bandpass", "8–13 Hz")),
        (("Bandpass", "8–13 Hz"), ("ChannelSelector", "channels 2"))]
    text = diagram.mermaid(g)
    assert text.startswith("flowchart LR") and '(["Generator' in text and '[["ChannelSelector' in text


def test_the_live_app_diagram_shows_one_headset_feeding_both_signals():
    with diagram.built("app", "hybridblack") as p:
        g = diagram.graph_of(p)
    by = {n.key: n for n in g.nodes}
    sources = [n for n in g.nodes if n.key not in {b for _, _, b, _ in g.edges}]
    assert [(n.cls, n.detail) for n in sources if n.cls == "HybridBlack"] == [
        ("HybridBlack", "250 Hz, 8 EEG channels, OSCAR on")]
    assert sum(1 for a, _, _, bp in g.edges if by[a].cls == "Marker" and bp == "trigger") == 4
    assert any(n.cls == "BandPower" and n.detail == "alpha 8–13 Hz" for n in g.nodes)
    assert any(n.cls == "ChannelSelector" and n.detail == "channels 6, 7, 8" for n in g.nodes)


def test_cli_prints_one_mode(capsys):
    assert diagram.main(["alpha", "--source", "generator"]) == 0
    out = capsys.readouterr().out
    assert "Simulated: g.Pype Generator" in out and "AlphaBursts" in out and "flowchart LR" in out
