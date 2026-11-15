"""PiEEG simulated EEG over LSL (#138). A fake Octopus stream stands in for PiEEG's simulator,
so no third-party code runs. Skips where pylsl or g.Pype isn't installed (CI, for now)."""
import os
import socket
import threading
import time
import uuid

import numpy as np
import pytest

pylsl = pytest.importorskip("pylsl")
pytest.importorskip("gpype")

from signal2speech.core import ActionIds, InputSources  # noqa: E402
from signal2speech.eeg import pieeg_lsl as pl  # noqa: E402


class FakeOctopus:
    """16 ch at 250 Hz like PiEEG's simulator; 10.2 Hz alpha weak, then strong, every `period` s."""

    def __init__(self, period: float = 3.0):
        self.name = f"S2S-test-Octopus-{uuid.uuid4().hex[:8]}"
        info = pylsl.StreamInfo(self.name, "EEG", 16, 250, "float32", self.name)
        self.outlet = pylsl.StreamOutlet(info)
        self.period = period
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        i, rng, next_t = 0, np.random.default_rng(0), time.monotonic()
        while not self._stop.is_set():
            t = (i + np.arange(25)) / 250.0
            amp = np.where((t // self.period) % 2 == 1, 32.0, 6.0)
            base = (6 * np.sin(2 * np.pi * 2.5 * t) + 5 * np.sin(2 * np.pi * 6 * t)
                    + amp * np.sin(2 * np.pi * 10.2 * t) + 6 * np.sin(2 * np.pi * 20 * t))
            chunk = base[:, None] * np.ones(16) + rng.uniform(-4, 4, (25, 16))
            self.outlet.push_chunk(chunk.astype(np.float32).tolist())
            i += 25
            next_t += 0.1
            time.sleep(max(0.0, next_t - time.monotonic()))

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)


@pytest.fixture
def fake():
    f = FakeOctopus()
    yield f
    f.close()


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_alpha_ratio_separates_open_and_closed():
    t = np.arange(500) / 250.0
    weak = (6 * np.sin(2 * np.pi * 10.2 * t) + 6 * np.sin(2 * np.pi * 20 * t))[:, None]
    strong = (32 * np.sin(2 * np.pi * 10.2 * t) + 6 * np.sin(2 * np.pi * 20 * t))[:, None]
    assert max(pl.alpha_ratio_per_second(weak)) < 2 < 10 < min(pl.alpha_ratio_per_second(strong))


def test_missing_stream_explains_how_to_start_pieeg():
    with pytest.raises(pl.PiEEGStreamNotFound, match="python_quickstart.py --sim --lsl"):
        pl.find_local_stream(timeout=0.5, name=f"S2S-absent-{uuid.uuid4().hex[:8]}")


def test_cli_without_a_stream_prints_setup_help(monkeypatch, capsys):
    def no_stream(*args, **kwargs):
        raise pl.PiEEGStreamNotFound(pl.SETUP_HELP)

    monkeypatch.setattr(pl, "find_local_stream", no_stream)
    assert pl.main(["--check"]) == 3
    assert "python_quickstart.py --sim --lsl" in capsys.readouterr().err


def test_finds_the_local_stream_and_relays_it(fake):
    info = pl.find_local_stream(timeout=5, name=fake.name)
    assert info.hostname() == socket.gethostname()
    relay = pl.PiEEGRelay(info, name=f"{fake.name}-relay").start()
    try:
        out = pylsl.resolve_byprop("name", relay.name, timeout=5)
        assert out, "relay stream not found"
        inlet = pylsl.StreamInlet(out[0])
        rows, end = [], time.monotonic() + 2.0
        while time.monotonic() < end:
            chunk, _ = inlet.pull_chunk(timeout=0.5)
            rows.extend(chunk)
        assert len(rows) > 200 and len(rows[0]) == 16
    finally:
        relay.stop()


@pytest.mark.slow
def test_pieeg_alpha_burst_confirms_a_keyboard_preview(qapp, fake):
    lines = []
    actions = pl.run_demo(stream_name=fake.name, calib_s=7.0, timeout_s=20.0, echo=lines.append)
    assert len(actions) == 1, "\n".join(lines)
    action = actions[0]
    assert action.action_id == ActionIds.COMPARE_AIR_QUALITY
    assert action.source == InputSources.SIMULATED      # the confirm came from the EEG path
    assert any(l.startswith("Previewed: keyboard") for l in lines)
    assert any(l.startswith("Confirmed: simulated") for l in lines)
