"""Eyes-closed confirm on a real EEG board over LSL, for the PiEEG Octopus 16 (#150).

g.tec's g.Pype stays the whole pipeline. The board is only an amplifier: PiEEG's starter
(github.com/pieeg-club/hello_world_octopus_16) publishes it as LSL stream ``Octopus16`` and
g.Pype's ``LslReceiver`` reads it. This builds on ``pieeg_lsl`` (#138), which finds the stream
on this computer and relays it under a machine-unique name so another team's stream can't be
picked up.

    # 1. In PiEEG's starter folder, board on a 5 V power bank, LED blinking slowly:
    python python_quickstart.py --lsl
    # 2. Here. --input says what is publishing; LSL can't prove it.
    python -m signal2speech.eeg.lsl_source --input live --demo
    python -m signal2speech.eeg.lsl_source --self-test --demo      # no board, no PiEEG code

What it does: detects the device (``devices.detect``), checks which pins are touching and which
respond when the wearer closes their eyes, calibrates the alpha switch (#47) on those, counts
false triggers at rest, and switches live confirm on only after a clean check.

Labels: ``--input live`` is "Live EEG (PiEEG Octopus 16)". ``--input simulated`` and
``--self-test`` are Simulated. Never run a simulator with ``--input live``.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
from typing import List, Optional, Sequence

import numpy as np

from signal2speech.core import InputSources
from signal2speech.eeg import devices

STREAM_NAME = "Octopus16"
STREAM_TYPE = "EEG"
CHANNELS = 16
SAMPLING_RATE = 250.0
SELF_TEST_NAME = "S2S-SelfTest"

SIMULATED_LABEL = "Simulated (LSL stream)"
SAFETY = ("SAFETY: while the sensor is on someone's head, power the board ONLY from a 5 V power "
          "bank. Never from this laptop's USB port or a wall charger.")


def live_label(device: devices.Device) -> str:
    return f"Live EEG ({device.name})"


def parse_channels(text: Optional[str], count: int) -> Optional[List[int]]:
    """'15,16' (1-based, as printed on the board) -> [14, 15]. Empty or 'auto' -> None."""
    if not text or text.strip().lower() == "auto":
        return None
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
    """Our own labelled-Simulated LSL publisher shaped like the Octopus 16, for testing the path
    without a board. ``close_eyes()`` raises the 10 Hz alpha on the pins with good contact.
    Pin 1 is flat (no contact) and pin 2 is railed (loose), as real dry pins can be."""

    FLAT, RAILED = 0, 1

    def __init__(self, name: str = SELF_TEST_NAME, alpha_open_uv: float = 3.0,
                 alpha_closed_uv: float = 25.0, noise_uv: float = 10.0, seed: int = 0,
                 actual_rate: float = SAMPLING_RATE):
        import pylsl

        self.name = name
        self._open, self._closed, self._noise = alpha_open_uv, alpha_closed_uv, noise_uv
        self._amp = alpha_open_uv
        self._actual_rate = actual_rate      # some boards send 244.14/s while claiming 250
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
        self._outlet = None                 # withdraw the stream now, not at garbage collection

    def _sample(self, t: float) -> List[float]:
        base = self._amp * math.sin(2 * math.pi * 10.0 * t)
        row = [base + self._rng.gauss(0, self._noise) for _ in range(CHANNELS)]
        row[self.FLAT] = 0.0
        row[self.RAILED] = self._rng.gauss(0, 400.0)
        return row

    def _run(self) -> None:
        dt = 1.0 / self._actual_rate
        n, next_t = 0, time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            while now >= next_t and self._outlet is not None:
                self._outlet.push_sample(self._sample(n * dt))
                n += 1
                next_t += dt
            time.sleep(0.002)


class RawReader:
    """Reads raw samples straight from an LSL stream, for the channel check."""

    def __init__(self, stream_name: str, timeout: float = 5.0):
        import pylsl

        found = pylsl.resolve_byprop("name", stream_name, 1, timeout)
        if not found:
            raise RuntimeError(f"LSL stream '{stream_name}' disappeared")
        newest = max(found, key=lambda s: s.created_at())    # a stale twin can linger briefly
        self._inlet = pylsl.StreamInlet(newest, max_buflen=60)
        self._inlet.open_stream(timeout=timeout)

    def read(self, seconds: float, tick=None) -> np.ndarray:
        """Samples over the next ``seconds``. ``tick()`` runs between pulls, so a window can stay
        responsive (#172); it may raise to abort."""
        while self._inlet.pull_chunk(timeout=0.0)[0]:      # drop anything buffered so far
            pass
        rows: list = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            chunk, _ = self._inlet.pull_chunk(timeout=0.05 if tick else 0.2)
            if chunk:
                rows.extend(chunk)
            if tick:
                tick()
        return np.asarray(rows, dtype=float)

    def close(self) -> None:
        self._inlet.close_stream()


def contact_report(device: devices.Device, block: np.ndarray, rate: float) -> str:
    """One line per pin: its 1-40 Hz RMS and whether it's touching."""
    rms = devices.band_rms(block, rate)
    ok = devices.contact_ok(block, rate, device.contact_rms_uv)
    lo, hi = device.contact_rms_uv or (0.0, float("inf"))
    rows = []
    for i, (r, good) in enumerate(zip(rms, ok)):
        state = "good" if good else ("flat (not touching)" if r < lo else "railed (loose or hair)")
        rows.append(f"  {device.describe_channels([i]):>6}  {r:7.1f} uV  {state}")
    return "\n".join(rows) + f"\n  {int(ok.sum())} of {len(ok)} pins have good contact"


def choose_channels(device: devices.Device, requested: Optional[List[int]], stream_name: str,
                    rate: float, probe_s: float, prompt, sim=None, say=print,
                    tick=None) -> devices.ChannelPick:
    """Use --channels or the device's montage; otherwise run the eyes open/closed channel check.
    ``tick`` keeps a window responsive while it reads (#172)."""
    if requested or device.fixed_montage:
        return devices.resolve_alpha_channels(device, requested)
    reader = RawReader(stream_name)
    try:
        prompt(f"Channel check: keep your eyes OPEN and relaxed for {probe_s:g} s")
        if sim:
            sim.open_eyes()
        open_block = reader.read(probe_s, tick)
        prompt(f"Channel check: CLOSE your eyes for {probe_s:g} s")
        if sim:
            sim.close_eyes()
        reader.read(0.5, tick)                              # let the alpha rise; not used
        closed_block = reader.read(probe_s, tick)
        prompt("Open your eyes")
        if sim:
            sim.open_eyes()
    finally:
        reader.close()
    measured = len(open_block) / probe_s if probe_s else 0.0
    say(f"measured sample rate: {measured:.1f} Hz (stream says {rate:g}). "
        "Some Octopus 16 boards run at 244.1 Hz; that's fine for this check.")
    say("pin contact (eyes open):\n" + contact_report(device, open_block, rate))
    pick = devices.resolve_alpha_channels(device, None, open_block, closed_block, rate)
    say("alpha rise with eyes closed, per pin:\n" + pick.table(device))
    return pick


def find_stream(name: str, any_host: bool = False, timeout: float = 5.0):
    """The stream on this computer. Host names are compared without case or domain, because
    Windows and LSL don't always agree on either ("Vas-Laptop" vs "VAS-LAPTOP.local")."""
    import socket

    from signal2speech.eeg import pieeg_lsl

    try:
        return pieeg_lsl.find_local_stream(timeout=timeout, any_host=any_host, name=name)
    except pieeg_lsl.PiEEGStreamNotFound:
        import pylsl

        short = lambda h: (h or "").split(".")[0].casefold()
        for s in pylsl.resolve_byprop("name", name, timeout=1.0):
            if short(s.hostname()) == short(socket.gethostname()):
                return s
        raise


def quick_check(device: devices.Device, stream_name: str, rate: float, seconds: float,
                say=print) -> bool:
    """No prompts: is data arriving, at what rate, and which pins are touching?"""
    reader = RawReader(stream_name)
    try:
        block = reader.read(seconds)
    finally:
        reader.close()
    if len(block) < rate:
        say(f"The stream is there but only {len(block)} samples arrived in {seconds:g} s. "
            "Is the board still connected (LED solid) and PiEEG's script still running?")
        return False
    measured = len(block) / seconds
    say(f"data is arriving: {measured:.1f} samples per second (stream says {rate:g})")
    say("pin contact:")
    say(contact_report(device, block, rate))
    good = int(devices.contact_ok(block, rate, device.contact_rms_uv).sum())
    if good == 0:
        say("No pin has good contact yet. Part the hair, press the sensor straight down, and "
            "hold it snug with a headband.")
    return good > 0


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
                                description="Eyes-closed confirm on an LSL EEG board (#150)")
    p.add_argument("--stream", default=STREAM_NAME, help="LSL stream name (PiEEG: Octopus16)")
    p.add_argument("--input", choices=["live", "simulated"],
                   help="what is publishing the stream: a real board on a person, or a simulator")
    p.add_argument("--self-test", action="store_true",
                   help="publish our own simulated stream and run on it (no board needed)")
    p.add_argument("--channels", default="auto",
                   help="'auto' (default): pick the pins that respond; or 1-based numbers, e.g. 3,7")
    p.add_argument("--any-host", action="store_true",
                   help="accept the stream from another computer (default: this computer only)")
    p.add_argument("--probe-s", type=float, default=8.0, help="seconds per condition in the channel check")
    p.add_argument("--calib-s", type=float, default=10.0)
    p.add_argument("--rest-s", type=float, default=20.0, help="eyes-open false-trigger window")
    p.add_argument("--closures", type=int, default=3)
    p.add_argument("--self-test-rate", type=float, default=SAMPLING_RATE,
                   help="self-test: samples per second really sent (try 244.14, as some boards do)")
    p.add_argument("--check", action="store_true",
                   help="first run: detect the device, measure the rate, report pin contact, and stop")
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
    from signal2speech.eeg import pieeg_lsl
    from signal2speech.ui.__main__ import PrintSink, load_demo_choices

    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    publisher = (SelfTestStream(actual_rate=args.self_test_rate).start()
                 if args.self_test else None)
    relay = None
    try:
        try:
            info = find_stream(args.stream, any_host=args.any_host)
        except pieeg_lsl.PiEEGSetupError as err:
            print(str(err).replace("--sim --lsl", "--lsl   (add --sim for PiEEG's simulator)"), flush=True)
            return 1
        relay = pieeg_lsl.PiEEGRelay(info).start()
        device = devices.detect(stream_name=info.name(), channel_count=info.channel_count(),
                                rate=info.nominal_srate())
        if args.self_test:
            device = devices.PIEEG_OCTOPUS16
        live = args.input == "live"
        label = live_label(device) if live else SIMULATED_LABEL
        source_tag = InputSources.LIVE_EEG if live else InputSources.SIMULATED
        print(f"input: {label}\ndevice: {device.name}, {relay.channels} channels at "
              f"{relay.rate:g} Hz (stream '{info.name()}' on {info.hostname()})", flush=True)
        if live:
            print(SAFETY, flush=True)
        if relay.channels != device.channel_count and device.channel_count:
            print(f"note: expected {device.channel_count} channels for {device.name}, the stream "
                  f"has {relay.channels}. Using the stream's count.", flush=True)
        if args.check:
            ok = quick_check(device, relay.name, relay.rate, max(args.probe_s, 3.0),
                             say=lambda t: print(t, flush=True))
            print(("READY: " if ok else "NOT READY: ") + f"{device.name} detected"
                  + ("" if ok else ", but no usable pins yet"), flush=True)
            return 0 if ok else 1

        try:
            requested = parse_channels(args.channels, relay.channels)
            pick = choose_channels(device, requested, relay.name, relay.rate, args.probe_s,
                                   alpha._prompt, sim=publisher,
                                   say=lambda t: print(t, flush=True))
        except (devices.NoAlphaResponse, ValueError) as err:
            print(f"Channel check failed: {err}", flush=True)
            return 1
        print(f"using {device.describe_channels(pick.channels)}: {pick.reason}", flush=True)

        handler = SelectionHandler(PrintSink())
        ac = alpha.AlphaConfirm(handler, input_source=source_tag,
                                source=pieeg_lsl.make_source(relay.name, relay.channels, relay.rate),
                                channels=list(pick.channels), sampling_rate=relay.rate)
        if publisher is not None:
            ac.bursts = publisher          # the prompts drive our simulated eyes
        ac.start()
        try:
            report = alpha.measure(ac, args.calib_s, args.rest_s, args.closures)
            ok, reasons = safe_to_arm(report, args.closures)
            print(json.dumps({"report": report, "label": label, "device": device.key,
                              "channels_1based": [c + 1 for c in pick.channels],
                              "safe_to_arm": ok, "reasons": reasons}), flush=True)
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
        if relay is not None:
            relay.stop()
        if publisher is not None:
            publisher.stop()
        relay = publisher = None
        import gc
        gc.collect()                        # release LSL outlets so the names are free again


if __name__ == "__main__":
    sys.exit(main())
