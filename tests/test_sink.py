"""#25 checks: offline speech choice, simulated-input selection, one confirm -> one reveal and one
utterance. Offscreen, no headset, no network."""
from pathlib import Path
import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.app import App, InjectedSimulatedInput  # noqa: E402
from signal2speech.core import ActionIds, InputSources, Outcome, TargetIds  # noqa: E402
from signal2speech.speech import OfflineSpeaker, bundled_clip  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeView:
    def __init__(self):
        self.calls = []

    def show_satellite(self):
        self.calls.append(ActionIds.SHOW_SATELLITE)

    def compare_air_quality(self):
        self.calls.append(ActionIds.COMPARE_AIR_QUALITY)


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, clip=None):
        self.said.append((text, clip))


# ── Speech ───────────────────────────────────────────────────
def test_bundled_clip_only_for_fixed_openorbit_lines(tmp_path):
    for name in ("compare_air_quality", "speak_reply"):
        (tmp_path / f"{name}.wav").write_bytes(b"RIFF")
    assert bundled_clip("compare_air_quality", tmp_path) == tmp_path / "compare_air_quality.wav"
    assert bundled_clip("speak_reply", tmp_path) is None      # generated words never use a clip
    assert bundled_clip("show_satellite", tmp_path) is None   # missing file
    assert bundled_clip(None, tmp_path) is None


def test_offline_speaker_without_any_voice_says_so(qapp, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyttsx3", None)          # import fails
    log = []
    sp = OfflineSpeaker(log.append, audio_dir=tmp_path, use_qt_tts=False)
    assert sp.backend == "none"
    sp.say("Hello.", "speak_reply")
    assert any("NO OFFLINE VOICE" in l for l in log)


def test_offline_speaker_plays_bundled_clip_instead_of_voice(qapp, tmp_path, monkeypatch):
    (tmp_path / "compare_air_quality.wav").write_bytes(b"RIFF")
    log, played = [], []

    class FakeEffect:
        def __init__(self, parent=None): pass
        def setSource(self, url): played.append(url.toLocalFile())
        def play(self): pass

    import PySide6.QtMultimedia as qm
    monkeypatch.setattr(qm, "QSoundEffect", FakeEffect)
    sp = OfflineSpeaker(log.append, audio_dir=tmp_path, use_qt_tts=False)
    sp.say("Washtenaw's AQI rose 186 points.", "compare_air_quality")
    # QUrl.toLocalFile() uses forward slashes on Windows, so compare paths, not strings.
    assert [Path(p) for p in played] == [tmp_path / "compare_air_quality.wav"]
    assert any("speech: bundled" in l for l in log)


# ── Sink: one confirm -> one reveal + one utterance ──────────
@pytest.mark.parametrize("pick,action", [(T1, ActionIds.SHOW_SATELLITE),
                                         (T2, ActionIds.COMPARE_AIR_QUALITY)])
def test_confirm_reveals_and_speaks_once_preview_does_nothing(qapp, pick, action):
    view, speaker = FakeView(), FakeSpeaker()
    app = App(view=view, speaker=speaker, echo=False)
    app.ask()
    assert app.window.press_target(pick) is Outcome.Previewed
    assert view.calls == [] and speaker.said == []
    assert app.window.press_target(T1) is Outcome.Confirmed
    app.window.press_target(T1)
    assert view.calls == [action]
    assert len(speaker.said) == 1 and speaker.said[0][1] == action   # clip key for bundled audio


# ── Simulated input selection ────────────────────────────────
def test_simulated_falls_back_with_reason_when_gpype_missing(qapp, monkeypatch):
    monkeypatch.setitem(sys.modules, "signal2speech.eeg.simulated", None)
    app = App(InputSources.SIMULATED, view=FakeView(), speaker=FakeSpeaker(), echo=False)
    assert isinstance(app.sim, InjectedSimulatedInput)
    assert "scripted, no g.Pype" in app.window.connection_label.text()
    assert any("input: Simulated (scripted, no g.Pype" in l for l in app.log.lines)


def test_simulated_uses_gpype_decoder_when_available(qapp, monkeypatch):
    made = {}

    class FakeDecoder:
        def __init__(self, handler, picks, *, flasher=None, confirm_s=None, parent=None):
            made.update(handler=handler, picks=list(picks), flasher=flasher, confirm_s=confirm_s)
            self.started = self.closed = False

        def start(self):
            self.started = True

        def close(self):
            self.closed = True

        def set_next(self, cls):
            made["next"] = cls

    mod = types.ModuleType("signal2speech.eeg.simulated")
    mod.SimulatedDecoder = FakeDecoder
    monkeypatch.setitem(sys.modules, "signal2speech.eeg.simulated", mod)
    app = App(InputSources.SIMULATED, view=FakeView(), speaker=FakeSpeaker(), echo=False,
              sim_script=[2, 1], confirm_delay_ms=1500)
    assert isinstance(app.sim, FakeDecoder) and app.sim.started
    assert made["handler"] is app.handler and made["picks"] == [2, 1]
    assert made["flasher"] is app.window.flasher and made["confirm_s"] == 1.5
    assert app.window.connection_label.text() == "Connection: g.Pype Generator stream"
    app.close()
    assert app.sim.closed
