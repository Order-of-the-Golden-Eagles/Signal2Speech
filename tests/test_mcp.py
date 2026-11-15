"""#110: the MCP server answers from the real g.Pype pipeline, labels its input, never ships raw EEG."""
import asyncio
import json
import subprocess
import sys

import pytest

pytest.importorskip("mcp")
pytest.importorskip("gpype")
pytest.importorskip("sklearn")

from signal2speech.mcp.monitor import Monitor  # noqa: E402
from signal2speech.mcp.server import build_server  # noqa: E402

pytestmark = pytest.mark.slow       # real-time pipeline, about 15-25 s


def call(server, name, args=None):
    result = asyncio.run(server.call_tool(name, args or {}))
    return json.loads(result.content[0].text)


def longest_list(obj) -> int:
    if isinstance(obj, dict):
        return max([longest_list(v) for v in obj.values()] + [0])
    if isinstance(obj, list):
        return max([len(obj)] + [longest_list(v) for v in obj])
    return 0


@pytest.fixture(scope="module")
def running():
    m = Monitor("generator", calibration=6, period=0.3, seed=2)
    m.start()
    try:
        assert m.wait(lambda: len(m.decisions) >= 2, 60), "no P300 decisions within 60 s"
        yield m, build_server(m)
    finally:
        m.stop()


def test_every_tool_answers_from_the_pipeline_and_labels_simulated(running):
    m, s = running
    q = call(s, "signal_quality")
    assert q["input"] == "Simulated" and q["ready"] and len(q["channels"]) == 8
    assert {c["name"] for c in q["channels"]} >= {"Pz", "Oz", "PO7", "PO8"}

    a = call(s, "p300_average", {"channel": "Pz"})
    assert a["input"] == "Simulated" and a["ready"]
    assert a["epochs"]["target"] > 0 and a["epochs"]["nontarget"] > 0
    assert 250 <= a["peak_latency_ms"] <= 500 and a["peak_difference_uv"] > 0
    assert isinstance(a["p300_visible"], bool)      # the verdict itself is pinned below

    d = call(s, "latest_decisions", {"n": 5})
    assert d["calibrated"] and d["decisions"] and d["accuracy_so_far"] is not None
    assert d["sequences"] >= len(d["decisions"]) and "sequences_without_decision" in d
    assert all(x["attended"] in ("target-1", "target-2") for x in d["decisions"])

    al = call(s, "alpha_state")
    assert al["input"] == "Simulated" and al["ready"] and al["channels"] == ["PO7", "Oz", "PO8"]

    g = call(s, "pipeline_graph")
    assert g["p300_calibrated"] and {b["name"] for b in g["branches"]} >= {
        "P300 choose", "P300 evidence", "alpha confirm", "quality"}
    assert g["mermaid"].startswith("flowchart LR") and "SyntheticP300" in g["mermaid"]   # #166


def test_results_are_summaries_not_raw_eeg(running):
    m, s = running
    for name, args in (("signal_quality", {}), ("p300_average", {"channel": "Oz"}),
                       ("alpha_state", {}), ("latest_decisions", {"n": 50}),
                       ("pipeline_graph", {})):
        # 10 s of 8-channel EEG would be 20,000 numbers; summaries stay tiny.
        assert longest_list(call(s, name, args)) <= 64, name


def test_unknown_channel_is_refused(running):
    from mcp.server.mcpserver.exceptions import ToolError
    m, s = running
    with pytest.raises(ToolError, match="channel must be one of"):
        asyncio.run(s.call_tool("p300_average", {"channel": "T7"}))


def test_evidence_view_start_and_stop(running, monkeypatch):
    m, s = running
    launched = []

    class FakeProc:
        def poll(self):
            return None

        def terminate(self):
            launched.append("terminated")

        def wait(self, timeout=None):
            return 0
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: launched.append(args) or FakeProc())
    assert call(s, "evidence_view", {"action": "start"})["evidence_view"] == "started"
    assert launched[0][1:] == ["-m", "signal2speech.evidence", "--source", "generator", "--p300"]
    assert call(s, "evidence_view", {"action": "start"})["evidence_view"] == "already running"
    assert call(s, "evidence_view", {"action": "stop"})["evidence_view"] == "stopped"
    assert launched[-1] == "terminated"


def test_selection_contract_resource(running):
    m, s = running
    contents = asyncio.run(s.read_resource("signal2speech://selection-contract"))
    text = list(contents)[0].content
    assert "Selection contract" in text


def test_live_monitor_is_honest_without_flashes():
    m = Monitor("hybridblack")                       # built, never started: no device needed
    s = build_server(m)
    try:
        a = call(s, "p300_average", {"channel": "Pz"})
        assert a["input"] == "Live EEG" and a["ready"] is False and "no tiles" in a["note"]
        ev = call(s, "evidence_view", {"action": "start"})
        assert ev["evidence_view"] == "not started" and "opens only once" in ev["note"]
    finally:
        m.graph.pipeline.close()


def test_stdio_transport_with_the_official_client():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "signal2speech.mcp", "--calibration", "2"])

    async def go():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                out = await session.call_tool("signal_quality", {})
                bad = await session.call_tool("p300_average", {"channel": "T7"})
                return names, json.loads(out.content[0].text), bad
    names, quality, bad = asyncio.run(go())
    assert bad.is_error                             # a bad argument is a tool error, not a crash
    assert names == {"signal_quality", "pipeline_graph", "latest_decisions", "p300_average",
                     "alpha_state", "evidence_view"}
    assert quality["input"] == "Simulated"


def test_visibility_verdict_is_deterministic():
    """The verdict rule on constructed averages: a clear 300 ms peak is visible, noise isn't."""
    import numpy as np

    from signal2speech.eeg import p300
    from signal2speech.mcp.monitor import summarize_average

    n = int(round((p300.TIME_PRE + p300.TIME_POST) * p300.RATE))
    t_ms = (np.arange(n) - int(round(p300.TIME_PRE * p300.RATE))) / p300.RATE * 1000

    class Fake:
        p300_note = ""

        def __init__(self, bump_uv):
            rng = np.random.default_rng(0)
            self.non = rng.normal(0, 0.3, (n, 8))
            self.tgt = self.non + bump_uv * np.exp(-((t_ms - 300) / 60) ** 2)[:, None]

        def averages(self):
            return {"target": self.tgt, "nontarget": self.non}, {"target": 30, "nontarget": 30}

    clear = summarize_average(Fake(5.0), "Pz")
    assert clear["p300_visible"] is True and 280 <= clear["peak_latency_ms"] <= 320
    flat = summarize_average(Fake(0.0), "Pz")
    assert flat["p300_visible"] is False


def test_stop_viewer_kills_and_reaps_a_stubborn_window():
    from signal2speech.mcp.server import stop_viewer
    calls = []

    class Stubborn:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def kill(self):
            calls.append("kill")

        def wait(self, timeout=None):
            calls.append("wait")
            if "kill" not in calls:
                raise subprocess.TimeoutExpired("evidence", timeout)
            return -9
    viewer = {"proc": Stubborn()}
    assert stop_viewer(viewer) is True and viewer["proc"] is None
    assert calls == ["terminate", "wait", "kill", "wait"]


def test_live_start_without_a_headset_exits_3_and_releases(monkeypatch, capsys):
    from signal2speech.eeg import app_live
    from signal2speech.mcp import server
    monkeypatch.setattr(app_live, "find_unicorn", lambda timeout_s=15.0: [])
    assert server.main(["--source", "hybridblack"]) == 3
    assert "no Unicorn Hybrid Black found" in capsys.readouterr().err
