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


def test_pyttsx3_fallback_speaks_every_line_from_its_own_process(qapp, tmp_path, monkeypatch):
    """pyttsx3 speaks the first line in a process and skips the rest, so each line gets a
    fresh helper process, and a line still being spoken is cut off before the next starts."""
    import signal2speech.speech.speaker as speaker_mod

    spawned = []

    class FakeProc:
        def __init__(self, args, **kwargs):
            self.args, self.alive, self.terminated = args, True, False
            spawned.append(self)
        def poll(self): return None if self.alive else 0
        def terminate(self): self.terminated, self.alive = True, False

    monkeypatch.setattr(speaker_mod.subprocess, "Popen", FakeProc)
    monkeypatch.setitem(sys.modules, "pyttsx3", types.ModuleType("pyttsx3"))
    log, started = [], []
    sp = OfflineSpeaker(log.append, audio_dir=tmp_path, use_qt_tts=False)
    assert sp.backend == "pyttsx3"
    sp.on_started = lambda: started.append(1)
    lines = ["Yes, please.", "I would like some water.", "Thank you very much."]
    for i, line in enumerate(lines):
        if i == 2:
            spawned[-1].alive = False                          # the second line had finished
        sp.say(line, "speak_reply")
    assert [p.args[-1] for p in spawned] == lines              # one helper per line, text as an argument
    assert all(p.args[1] == "-c" and line not in p.args[2] for p, line in zip(spawned, lines))
    assert [p.terminated for p in spawned] == [True, False, False]   # only the overlapping one was cut
    assert len(started) == 3
    assert sum("helper process" in l for l in log) == 3


# ── Natural voice (Piper) ────────────────────────────────────
def test_spoken_form_says_known_abbreviations_in_full_and_spells_unknown_ones():
    from signal2speech.speech.neural import spoken_form
    assert spoken_form("Washtenaw's AQI rose 186 points.") == "Washtenaw's air quality index rose 186 points."
    assert spoken_form("Send the PDF to me") == "Send the P.D.F. to me"
    assert spoken_form("Send me the PDF.") == "Send me the P.D.F."          # no doubled full stop
    assert spoken_form("NASA imagery. OK? Yes, I am.") == "NASA imagery. OK? Yes, I am."
    assert spoken_form("Yes, please.") == "Yes, please."


def test_find_voice_honours_off_and_an_explicit_file(tmp_path, monkeypatch):
    from signal2speech.speech import neural
    (tmp_path / "b.onnx").write_bytes(b"x")
    (tmp_path / "a.onnx").write_bytes(b"x")
    monkeypatch.delenv(neural.VOICE_ENV, raising=False)
    assert neural.find_voice(tmp_path) == tmp_path / "a.onnx"
    assert neural.find_voice(tmp_path / "missing") is None
    monkeypatch.setenv(neural.VOICE_ENV, "off")
    assert neural.find_voice(tmp_path) is None
    monkeypatch.setenv(neural.VOICE_ENV, str(tmp_path / "b.onnx"))
    assert neural.find_voice(tmp_path) == tmp_path / "b.onnx"


class _FakePiper:
    """Stands in for the Piper process: writes the WAV when told to finish."""
    made = []

    def __init__(self, args, **kwargs):
        self.args, self.code = args, None
        self.stdin = types.SimpleNamespace(write=lambda b: setattr(self, "text", b.decode()), close=lambda: None)
        _FakePiper.made.append(self)

    def poll(self):
        return self.code

    def finish(self, ok=True):
        if ok:
            from pathlib import Path
            Path(self.args[self.args.index("-f") + 1]).write_bytes(b"RIFF" + b"\0" * 100)
        self.code = 0 if ok else 1


def test_piper_voice_makes_each_line_once_and_only_names_finished_files(tmp_path, monkeypatch):
    from signal2speech.speech import neural
    _FakePiper.made = []
    monkeypatch.setattr(neural.subprocess, "Popen", _FakePiper)
    voice = neural.PiperVoice(tmp_path / "v.onnx", cache_dir=tmp_path / "cache")
    clip = voice.request("The AQI rose.")
    assert clip.state() == "working" and not clip.wav.exists()
    assert voice.request("The AQI rose.") is clip and len(_FakePiper.made) == 1   # previewed, then said
    assert _FakePiper.made[0].text == "The air quality index rose.\n"
    scale = lambda proc: proc.args[proc.args.index("--length-scale") + 1]
    assert scale(_FakePiper.made[0]) == "1.0"                                     # no numbers: normal speed
    voice.request("It rose 186 points.")
    assert scale(_FakePiper.made[-1]) == "1.25"                                   # numbers: 25 % slower
    _FakePiper.made.pop()
    _FakePiper.made[0].finish()
    assert clip.state() == "ready" and clip.wav.is_file()
    bad = voice.request("Another line.")
    _FakePiper.made[1].finish(ok=False)
    assert bad.state() == "failed"
    assert voice.request("Another line.") is not bad                              # a failure is retried


def test_speaker_falls_back_for_a_line_the_natural_voice_cannot_make(qapp, tmp_path, monkeypatch):
    from signal2speech.speech import neural
    _FakePiper.made = []
    monkeypatch.setattr(neural.subprocess, "Popen", _FakePiper)
    monkeypatch.setitem(sys.modules, "pyttsx3", None)
    log = []
    sp = OfflineSpeaker(log.append, audio_dir=tmp_path, use_qt_tts=False,
                        neural=neural.PiperVoice(tmp_path / "v.onnx", cache_dir=tmp_path / "cache"))
    assert sp.backend == "Piper (v)"
    played = []
    monkeypatch.setattr(sp, "_play_wav", played.append)
    sp.prepare("Yes, please.")                                   # previewed: starts the work, no sound
    assert len(_FakePiper.made) == 1 and not played
    _FakePiper.made[0].finish()
    sp.say("Yes, please.", "speak_reply")
    assert len(played) == 1 and len(_FakePiper.made) == 1        # ready at once, made once
    sp.say("No, thank you.", "speak_reply")
    _FakePiper.made[1].finish(ok=False)
    sp._play_neural_when_ready()
    assert len(played) == 1
    assert any("couldn't make this line" in l for l in log) and any("NO OFFLINE VOICE" in l for l in log)
