"""PiEEG's simulated EEG through our g.Pype pipeline, over LSL (#138).

PiEEG Cloud has no stream out, but PiEEG's own simulator publishes Lab Streaming Layer (LSL):

    python python_quickstart.py --sim --lsl       # PiEEG's starter, github.com/pieeg-club/hello_world_octopus_16
    python -m signal2speech.eeg.pieeg_lsl --check # is the stream on this computer, at what rate?
    python -m signal2speech.eeg.pieeg_lsl --demo  # keyboard previews, PiEEG's alpha confirms

The simulator's 10.2 Hz alpha switches between weak and strong every 6 s, like eyes opening and
closing, so it can drive the #47 alpha switch. It has no P300 and takes no markers, so it can't
drive the P300 chooser: the demo previews by keyboard and labels each event honestly. Everything
from this source is Simulated.

A venue can have several PiEEG simulators on one network, all publishing "Octopus16".
``PiEEGRelay`` takes the one running on this computer and republishes it under a name unique to
this machine, so g.Pype's ``LslReceiver`` can't pick up another team's stream.

Needs ``pylsl`` (``pip install pylsl``). It isn't in ``pyproject.toml`` yet (#138, #19).
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from typing import Callable, List, Optional

import numpy as np

STREAM_NAME = "Octopus16"           # what PiEEG's starter publishes with --lsl
STREAM_TYPE = "EEG"
CHANNELS = 16
RATE = 250.0
LABEL = "Simulated (PiEEG Octopus 16 simulator)"

SETUP_HELP = f"""No PiEEG simulator stream ("{STREAM_NAME}") is running on this computer.
  1. pip install pylsl numpy
  2. Get PiEEG's starter: https://github.com/pieeg-club/hello_world_octopus_16
  3. Run it and leave it running: python python_quickstart.py --sim --lsl
Then run this again."""


class PiEEGSetupError(RuntimeError):
    """Something on this computer isn't set up yet. The message says what to do."""


class PiEEGStreamNotFound(PiEEGSetupError):
    """No PiEEG simulator stream on this computer. The message says how to start one."""


def _pylsl():
    try:
        import pylsl
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise PiEEGSetupError("PiEEG over LSL needs pylsl: pip install pylsl") from exc
    return pylsl


def find_local_stream(timeout: float = 5.0, any_host: bool = False, name: Optional[str] = None):
    """The PiEEG stream running on this computer, as a pylsl ``StreamInfo``.

    Streams with the same name on other computers are ignored unless ``any_host`` is set."""
    pylsl = _pylsl()
    name = name or STREAM_NAME
    found = pylsl.resolve_byprop("name", name, timeout=timeout)
    host = socket.gethostname()
    local = [s for s in found if s.hostname() == host]
    if local:
        return local[0]
    if any_host and found:
        return found[0]
    others = f"\n({len(found)} '{name}' stream(s) on other computers were ignored.)" if found else ""
    raise PiEEGStreamNotFound(SETUP_HELP + others)


class PiEEGRelay:
    """Republishes one PiEEG stream under a name unique to this machine."""

    def __init__(self, info, name: Optional[str] = None):
        pylsl = _pylsl()
        self.name = name or f"S2S-PiEEG-{socket.gethostname()}"
        self.channels = info.channel_count()
        self.rate = info.nominal_srate()
        self._inlet = pylsl.StreamInlet(info, max_buflen=2)
        out = pylsl.StreamInfo(self.name, STREAM_TYPE, self.channels, self.rate, "float32", self.name)
        self._outlet = pylsl.StreamOutlet(out)
        self.rows = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pieeg-relay", daemon=True)

    def start(self) -> "PiEEGRelay":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            chunk, _ = self._inlet.pull_chunk(timeout=0.2)
            if chunk:
                self._outlet.push_chunk(chunk)
                self.rows += len(chunk)

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


def make_source(stream_name: str, channels: int = CHANNELS, rate: float = RATE):
    """A g.Pype source node that reads the (relayed) PiEEG stream."""
    import gpype as gp
    return gp.LslReceiver(stream_name=stream_name, stream_type=STREAM_TYPE,
                          channel_count=channels, sampling_rate=rate)


def alpha_ratio_per_second(samples: np.ndarray, rate: float = RATE) -> List[float]:
    """8–13 Hz over 13–30 Hz power for each whole second of channel 1."""
    n = int(rate)
    out = []
    for i in range(0, len(samples) - n + 1, n):
        seg = samples[i:i + n, 0] - samples[i:i + n, 0].mean()
        f = np.fft.rfftfreq(n, 1 / rate)
        p = np.abs(np.fft.rfft(seg)) ** 2
        beta = p[(f >= 13) & (f < 30)].sum()
        out.append(float(p[(f >= 8) & (f < 13)].sum() / beta) if beta > 0 else float("inf"))
    return out


def check(seconds: float = 12.0, any_host: bool = False, echo: Callable[[str], None] = print) -> int:
    """Read the PiEEG stream for ``seconds`` and report its rate and alpha switching."""
    pylsl = _pylsl()
    info = find_local_stream(any_host=any_host)
    echo(f"[{LABEL}] found '{info.name()}' on {info.hostname()}: "
         f"{info.channel_count()} ch at {info.nominal_srate():g} Hz")
    inlet = pylsl.StreamInlet(info)
    rows, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        chunk, _ = inlet.pull_chunk(timeout=1.0)
        rows.extend(chunk)
    x = np.asarray(rows, dtype=float)
    if len(x) == 0:
        echo("no samples arrived")
        return 1
    echo(f"{len(x)} samples in {seconds:g} s = {len(x) / seconds:.1f} Hz")
    ratios = alpha_ratio_per_second(x, info.nominal_srate() or RATE)
    echo("alpha/beta per second: " + " ".join(f"{r:.1f}" for r in ratios))
    return 0


class _RecordingSink:
    def __init__(self, echo: Callable[[str], None]):
        self.actions = []
        self.echo = echo

    def execute(self, action) -> None:
        self.actions.append(action)
        self.echo(f"OUTPUT map: {action.action_id}()  [{action.source}]")
        if action.spoken_text:
            self.echo(f'OUTPUT speak: "{action.spoken_text}"')


def run_demo(any_host: bool = False, calib_s: float = 13.0, timeout_s: float = 30.0,
             stream_name: Optional[str] = None, echo: Callable[[str], None] = print) -> list:
    """Keyboard previews "Compare counties", then PiEEG's next alpha burst confirms it.

    Returns the confirmed actions (one on success). Needs a Qt application instance."""
    from PySide6.QtCore import QCoreApplication

    from signal2speech.core import InputAdapter, InputSources, SelectionHandler, TargetIds
    from signal2speech.eeg.alpha_confirm import AlphaConfirm
    from signal2speech.ui.__main__ import load_demo_choices

    app = QCoreApplication.instance() or QCoreApplication([])
    info = find_local_stream(any_host=any_host, name=stream_name)
    relay = PiEEGRelay(info).start()
    sink = _RecordingSink(echo)
    handler = SelectionHandler(sink)
    handler.on_handled.append(lambda e, o: echo(
        f"{o.value}: {e.source} {e.eventId} {e.roundId}->{e.targetId}" if e else o.value))
    ac = AlphaConfirm(handler, input_source=InputSources.SIMULATED,
                      source=make_source(relay.name, relay.channels, relay.rate),
                      sampling_rate=relay.rate)
    try:
        ac.start()
        echo(f"[{LABEL}] calibrating the alpha switch from the stream for {calib_s:g} s")
        ac.collect(1.0)                                  # let the 1 s FFT window fill
        values = np.sort(ac.collect(calib_s))
        k = max(5, int(len(values) * 0.4))               # lowest 40% = open, highest 40% = closed
        cal = ac.calibrate(values[:k], values[-k:])
        echo(f"alpha switch calibrated: ratio {cal.ratio:.1f}")

        handler.begin_choice_round(load_demo_choices())
        InputAdapter(handler, InputSources.KEYBOARD).select_now(TargetIds.TARGET_2)
        echo("waiting for PiEEG's next 'eyes closed' alpha burst to confirm")
        end = time.monotonic() + timeout_s
        while time.monotonic() < end and not sink.actions:
            app.processEvents()
            time.sleep(0.01)
        if not sink.actions:
            echo(f"no confirm within {timeout_s:g} s")
        return sink.actions
    finally:
        ac.close()
        relay.stop()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.eeg.pieeg_lsl", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="report the stream's rate and alpha switching")
    p.add_argument("--demo", action="store_true", help="keyboard preview, PiEEG alpha confirm")
    p.add_argument("--seconds", type=float, default=12.0, help="--check: seconds to read")
    p.add_argument("--any-host", action="store_true",
                   help="accept a PiEEG stream on another computer (not recommended at a venue)")
    args = p.parse_args(argv)
    try:
        if not args.demo:
            return check(args.seconds, args.any_host)
        from signal2speech.eeg.alpha_confirm import CalibrationError
        try:
            return 0 if run_demo(any_host=args.any_host) else 1
        except CalibrationError as exc:
            print(f"The alpha switch couldn't calibrate from this stream: {exc}", file=sys.stderr)
            return 4
    except PiEEGSetupError as exc:
        print(exc, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
