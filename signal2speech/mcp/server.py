"""Signal2Speech MCP server (#110): an AI assistant reads and drives the g.Pype pipeline.

    python -m signal2speech.mcp                          # Generator (Simulated), stdio
    python -m signal2speech.mcp --source hybridblack     # Unicorn (Live EEG): quality and alpha

Local stdio only: no network listener. Claude Desktop or Claude Code starts it (see
``docs/ai-answering/README.md`` for the config). Tools return summaries, never raw EEG, and
every result says whether the data is Simulated, Recorded, or Live EEG.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from signal2speech.eeg import p300
from signal2speech.eeg.live import CHANNELS

from .monitor import Monitor, summarize_alpha, summarize_average, summarize_quality

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "selection-contract.md"

INSTRUCTIONS = """Signal2Speech lets someone answer without speaking: a flashing tile is chosen by
the P300 brain response, and the answer is confirmed by closing the eyes (alpha rhythm). These
tools read the live g.Pype pipeline. Always tell the user whether results are Simulated,
Recorded, or Live EEG (the "input" field). Never describe simulated data as a real person's
brain. Start with signal_quality, then p300_average for "is the P300 visible?"."""


def build_server(monitor: Monitor) -> MCPServer:
    server = MCPServer(name="signal2speech", title="Signal2Speech EEG pipeline",
                       instructions=INSTRUCTIONS)
    viewer: dict = {"proc": None}

    def labelled(body: dict) -> dict:
        return {"input": monitor.label.value, "source": monitor.kind.value,
                "pipeline_state": monitor.state, **body}

    @server.tool(description="Per-channel EEG signal quality over the last 10 s: 1-30 Hz RMS "
                             "and 50/60 Hz line noise, with ok / flat / noisy per channel.")
    def signal_quality() -> dict:
        return labelled(summarize_quality(monitor))

    @server.tool(description="The g.Pype pipeline graph: source, filters, the P300 and alpha "
                             "branches, and what each produces.")
    def pipeline_graph() -> dict:
        g = monitor.graph
        return labelled({
            "sampling_rate_hz": p300.RATE, "channels": list(CHANNELS),
            "oscar": g.oscar_note,
            "branches": [
                {"name": "source", "nodes": ["Generator + SyntheticP300" if monitor.simulated
                                             else "HybridBlack (Unicorn)"]},
                {"name": "front end", "nodes": ["Bandpass 1-30 Hz"]},
                {"name": "P300 choose", "nodes": [
                    "Marker (one code per tile flash)",
                    f"Trigger per tile ({int(p300.TIME_PRE * 1000)} ms before to "
                    f"{int(p300.TIME_POST * 1000)} ms after each flash)",
                    "Sklearn LDA scorer per tile", "per-sequence mean score -> class 1/2"]},
                {"name": "P300 evidence", "nodes": [
                    "Trigger on calibration codes 101 (target) / 100 (non-target)",
                    "EpochAverage target vs non-target"]},
                {"name": "alpha confirm", "nodes": [
                    "ChannelSelector PO7, Oz, PO8", "FFT 1 s, 90 % overlap",
                    "BandPower 8-13 Hz", "mean of the three channels"]},
                {"name": "quality", "nodes": ["last 10 s per channel (kept in this process)"]},
            ],
            "p300_calibrated": monitor.calibrated,
            "note": monitor.p300_note or ""})

    @server.tool(description="The latest P300 decisions: which tile the classifier picked each "
                             "sequence, and (Generator only) which tile was really attended.")
    def latest_decisions(n: int = 5) -> dict:
        items = list(monitor.decisions)[-max(1, min(int(n), 50)):]
        scored = [d for d in monitor.decisions if d.correct is not None]
        acc = (sum(1 for d in scored if d.correct) / len(scored)) if scored else None
        return labelled({
            "calibrated": monitor.calibrated,
            "decisions": [{"time": time.strftime("%H:%M:%S", time.localtime(d.t)),
                           "attended": d.attended, "decided": d.decided, "correct": d.correct,
                           "mean_scores": d.scores} for d in items],
            "accuracy_so_far": None if acc is None else round(acc, 2),
            "sequences_scored": len(scored),
            "note": monitor.p300_note or ("Attended tiles are the synthetic brain's choices"
                                          if monitor.simulated else "")})

    @server.tool(description="Averaged response to target vs non-target flashes for one "
                             "channel, in 20 ms bins, with the P300 peak and a visibility "
                             "verdict. Channels: Fz C3 Cz C4 Pz PO7 Oz PO8.")
    def p300_average(channel: str = "Pz") -> dict:
        if channel not in CHANNELS:
            raise ToolError(f"channel must be one of {', '.join(CHANNELS)}")
        return labelled(summarize_average(monitor, channel))

    @server.tool(description="Occipital alpha (8-13 Hz) band power, the signal behind the "
                             "eye-closure confirm: latest value and the last 30 s spread.")
    def alpha_state() -> dict:
        return labelled(summarize_alpha(monitor))

    @server.tool(description="Start or stop the g.Pype evidence window (scopes, spectrum, "
                             "averaged P300) on this computer. action: 'start' or 'stop'.")
    def evidence_view(action: str = "start") -> dict:
        proc: Optional[subprocess.Popen] = viewer["proc"]
        if action == "stop":
            if proc is None or proc.poll() is not None:
                return labelled({"evidence_view": "not running"})
            proc.terminate()
            viewer["proc"] = None
            return labelled({"evidence_view": "stopped"})
        if action != "start":
            raise ToolError("action is 'start' or 'stop'")
        if proc is not None and proc.poll() is None:
            return labelled({"evidence_view": "already running"})
        if not monitor.simulated:
            return labelled({"evidence_view": "not started",
                             "note": "The headset opens only once and this server holds it. "
                                     "Stop the server, then run: python -m "
                                     "signal2speech.evidence --source hybridblack --p300"})
        viewer["proc"] = subprocess.Popen(
            [sys.executable, "-m", "signal2speech.evidence", "--source", "generator", "--p300"],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        return labelled({"evidence_view": "started", "window": "Signal2Speech evidence",
                         "note": "A separate window with its own Generator (Simulated)."})

    @server.resource("signal2speech://selection-contract", name="selection-contract",
                     description="The selection contract: one event shape for keyboard, "
                                 "simulated, recorded, and live input, and the round rules.",
                     mime_type="text/markdown")
    def selection_contract() -> str:
        return CONTRACT.read_text(encoding="utf-8")

    server._s2s_viewer = viewer          # tests stop a viewer they started
    return server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m signal2speech.mcp")
    ap.add_argument("--source", choices=["generator", "hybridblack"], default="generator")
    ap.add_argument("--calibration", type=int, default=6, help="P300 calibration sequences")
    ap.add_argument("--period", type=float, default=6.0, help="seconds between decisions")
    args = ap.parse_args(argv)
    monitor = Monitor(args.source, calibration=args.calibration, period=args.period)
    try:
        monitor.start()
    except Exception as err:
        print(f"Couldn't start the {args.source} pipeline: {type(err).__name__}: {err}",
              file=sys.stderr)
        return 3
    try:
        build_server(monitor).run("stdio")
    finally:
        monitor.stop()
    return 0
