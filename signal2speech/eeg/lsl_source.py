"""EEG from a Lab Streaming Layer (LSL) stream, for a borrowed PiEEG Octopus 16 board (#150).

Our Unicorn was lost in transit. PiEEG's starter code (github.com/pieeg-club/hello_world_octopus_16)
publishes its board, or its simulator, as LSL stream ``Octopus16``: type EEG, 16 channels,
250 Hz, microvolts. This module reads that stream with g.Pype's ``LslReceiver`` and runs our
eyes-closed alpha switch (#47) on it, so a real person closing their eyes can confirm a choice.

    # 1. In PiEEG's starter folder, with the board on (or --sim for their simulator):
    python python_quickstart.py --lsl
    # 2. Here. --input says what is on the other end; LSL itself can't prove it.
    python -m signal2speech.eeg.lsl_source --input live --channels 15,16
    python -m signal2speech.eeg.lsl_source --self-test          # no board, no PiEEG code

Labels: ``--input live`` is shown as "Live EEG (PiEEG Octopus 16)"; ``--input simulated`` and
``--self-test`` are shown as Simulated. Never run a simulator with ``--input live``.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from signal2speech.core import InputSources

STREAM_NAME = "Octopus16"
STREAM_TYPE = "EEG"
CHANNELS = 16
SAMPLING_RATE = 250.0
SELF_TEST_NAME = "S2S-SelfTest"

LIVE_LABEL = "Live EEG (PiEEG Octopus 16)"
SIMULATED_LABEL = "Simulated (LSL stream)"


@dataclass(frozen=True)
class StreamInfo:
    name: str
    type: str
    channels: int
    rate: float
    source_id: str

    def line(self) -> str:
        return (f"LSL stream '{self.name}' ({self.type}), {self.channels} channels at "
                f"{self.rate:g} Hz, source id '{self.source_id}'")


def find_stream(name: str = STREAM_NAME, timeout: float = 3.0) -> Optional[StreamInfo]:
    """Look for the stream on the network. None if nothing is publishing it."""
    import pylsl

    found = pylsl.resolve_byprop("name", name, 1, timeout)
    if not found:
        return None
    s = found[0]
    return StreamInfo(s.name(), s.type(), s.channel_count(), float(s.nominal_srate()), s.source_id())


NOT_FOUND_HELP = (
    "No LSL stream named '{name}' was found.\n"
    "  1. In PiEEG's starter folder run:  python python_quickstart.py --lsl      (board on)\n"
    "     or, without a board:           python python_quickstart.py --sim --lsl\n"
    "  2. Keep that window open, then run this again.\n"
    "  3. If a firewall prompt appears, allow Python on private networks.")


def make_source(info: StreamInfo):
    """A g.Pype source reading this stream."""
    import gpype as gp

    return gp.LslReceiver(stream_name=info.name, stream_type=info.type,
                          channel_count=info.channels, sampling_rate=info.rate)


def parse_channels(text: Optional[str], count: int) -> List[int]:
    """'15,16' (1-based, as printed on the board) -> [14, 15]. Empty means every channel."""
    if not text:
        return list(range(count))
    out = []
    for part in text.split(","):
        n = int(part.strip())
        if not 1 <= n <= count:
            raise ValueError(f"channel {n} is outside 1..{count}")
        out.append(n - 1)
    if len(set(out)) != len(out):
        raise ValueError("a channel is listed twice")
    return out


class SelfTestStream:
    """A labelled-Simulated LSL publisher with the Octopus16 stream shape, for testing the path
    without a board. ``close_eyes()`` raises the 10 Hz alpha, as closing the eyes would."""

    def __init__(self, name: str = SELF_TEST_NAME, alpha_open_uv: float = 3.0,
                 alpha_closed_uv: float = 25.0, noise_uv: float = 4.0, seed: int = 0):
        import pylsl

        self.name = name
        self._open, self._closed, self._noise = alpha_open_uv, alpha_closed_uv, noise_uv
        self._amp = alpha_open_uv
        self._rng = random.Random(seed)
        info = pylsl.StreamInfo(name, STREAM_TYPE, CHANNELS, SAMPLING_RATE, "float32",
                                "signal2speech_selftest")
        self._outlet = pylsl.StreamOutlet(info)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lsl-selftest", daemon=True)

    def close_eyes(self) -> None:
        self._amp = self._closed

    def open_eyes(self) -> None:
        self._amp = self._open

    def start(self) -> "SelfTestStream":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        dt = 1.0 / SAMPLING_RATE
        n, next_t = 0, time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            while now >= next_t:
                t = n * dt
                base = self._amp * math.sin(2 * math.pi * 10.0 * t)
                self._outlet.push_sample([base + self._rng.uniform(-self._noise, self._noise)
                                          for _ in range(CHANNELS)])
                n += 1
                next_t += dt
            time.sleep(0.002)


def safe_to_arm(report: dict, closures: int) -> tuple:
    """Live confirm is switched on only after a clean check on this wearer, this session."""
    reasons = []
    if "error" in report:
        reasons.append(f"calibration failed: {report['error']}")
    if report.get("false_triggers", 1) != 0:
        reasons.append(f"{report.get('false_triggers')} false trigger(s) with eyes open")
    edges = report.get("edges_per_closure") or []
    if closures < 2 or len(edges) < closures or any(e != 1 for e in edges):
        reasons.append(f"need {max(closures, 2)} closures with exactly one confirm each, got {edges}")
    return (not reasons), reasons


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.lsl_source",
                                description="Eyes-closed confirm on an LSL EEG stream (#150)")
    p.add_argument("--stream", default=STREAM_NAME, help="LSL stream name (PiEEG: Octopus16)")
    p.add_argument("--input", choices=["live", "simulated"],
                   help="what is publishing the stream: a real board on a person, or a simulator")
    p.add_argument("--self-test", action="store_true",
                   help="publish our own simulated stream and run on it (no board needed)")
    p.add_argument("--channels", default="",
                   help="1-based channels over the back of the head, e.g. 15,16 (default: all)")
    p.add_argument("--calib-s", type=float, default=10.0)
    p.add_argument("--rest-s", type=float, default=20.0, help="eyes-open false-trigger window")
    p.add_argument("--closures", type=int, default=3)
    p.add_argument("--demo", action="store_true",
                   help="after the check: keyboard preview, then confirm by closing the eyes")
    args = p.parse_args(argv)
    if args.self_test:
        args.input, args.stream = "simulated", SELF_TEST_NAME
    if args.input is None:
        p.error("say what is publishing the stream: --input live or --input simulated")

    import gpype as gp  # noqa: F401  (fail early with a clear import error)
    from PySide6.QtCore import QCoreApplication

    from signal2speech.core import SelectionHandler
    from signal2speech.eeg import alpha_confirm as alpha
    from signal2speech.ui.__main__ import PrintSink, load_demo_choices

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    publisher = SelfTestStream().start() if args.self_test else None
    try:
        info = find_stream(args.stream, timeout=5.0)
        if info is None:
            print(NOT_FOUND_HELP.format(name=args.stream), flush=True)
            return 1
        live = args.input == "live"
        label = LIVE_LABEL if live else SIMULATED_LABEL
        source_tag = InputSources.LIVE_EEG if live else InputSources.SIMULATED
        channels = parse_channels(args.channels, info.channels)
        print(f"input: {label}\n{info.line()}\nusing channels (1-based): "
              f"{[c + 1 for c in channels]}", flush=True)

        handler = SelectionHandler(PrintSink())
        ac = alpha.AlphaConfirm(handler, input_source=source_tag, source=make_source(info),
                                channels=channels, sampling_rate=info.rate)
        if publisher is not None:
            ac.bursts = publisher          # the prompts drive our simulated eyes
        ac.start()
        try:
            report = alpha.measure(ac, args.calib_s, args.rest_s, args.closures)
            ok, reasons = safe_to_arm(report, args.closures)
            print(json.dumps({"report": report, "label": label, "safe_to_arm": ok,
                              "reasons": reasons}), flush=True)
            if args.demo and "error" not in report:
                if live and ok:
                    handler.live_eeg_confirm_armed = True
                    print("Live confirm ARMED for this session: the check above was clean.", flush=True)
                elif live:
                    print("Live confirm stays OFF: " + "; ".join(reasons), flush=True)
                for e, o in alpha.demo(ac, load_demo_choices()):
                    print(json.dumps({"outcome": o.value, "source": e.source if e else None,
                                      "roundId": e.roundId if e else None,
                                      "targetId": e.targetId if e else None}), flush=True)
            return 0 if ok else 1
        finally:
            ac.close()
            app.processEvents()
    finally:
        if publisher is not None:
            publisher.stop()


if __name__ == "__main__":
    sys.exit(main())
