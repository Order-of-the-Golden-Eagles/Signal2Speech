"""Offline speech (#25, #28). Only AppSink calls say(), once per confirmed action.

Order, all offline:
1. Bundled clip: data/openorbit/audio/<action_id>.wav, only for the fixed OpenOrbit lines
   (show_satellite, compare_air_quality). Generated replies never use a clip, because a
   recording can't match words the wearer just approved.
2. The OS voice through Qt TextToSpeech (darwin on macOS, sapi/winrt on Windows, speechd on
   Linux). Non-blocking, so the window keeps updating while it speaks.
3. pyttsx3, if Qt has no usable engine. Each line is spoken from its own short-lived helper
   process: inside one process, pyttsx3 speaks the first line and silently skips the rest
   (measured on Windows, 2026-11-15), and a helper also keeps the window from freezing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from PySide6.QtCore import QObject, QUrl

from signal2speech.core import ActionIds

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "data" / "openorbit" / "audio"
BUNDLED_CLIPS = frozenset({ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY})

Log = Callable[[str], None]

#: Run by the helper process. The text arrives as an argument, never inside the code string.
PYTTSX3_HELPER = "import sys, pyttsx3; e = pyttsx3.init(); e.say(sys.argv[1]); e.runAndWait()"


class Speaker(Protocol):
    def say(self, text: str, clip: Optional[str] = None) -> None: ...


def bundled_clip(clip: Optional[str], audio_dir: Path = AUDIO_DIR) -> Optional[Path]:
    if clip not in BUNDLED_CLIPS:
        return None
    wav = audio_dir / f"{clip}.wav"
    return wav if wav.is_file() else None


class MutedSpeaker:
    def __init__(self, log: Log):
        self.log = log
        self.said: List[str] = []
        self.on_started: Optional[Callable[[], None]] = None   # never fires: nothing is audible

    def say(self, text: str, clip: Optional[str] = None) -> None:
        self.said.append(text)
        self.log("speech: muted (--mute), nothing audible")


class OfflineSpeaker(QObject):
    def __init__(self, log: Log, audio_dir: Path = AUDIO_DIR, use_qt_tts: bool = True,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.log = log
        self.audio_dir = audio_dir
        self._sound = None
        self._helper: Optional[subprocess.Popen] = None     # the pyttsx3 helper still speaking
        # Called once when audio actually starts for the latest say() (#130 timing).
        self.on_started: Optional[Callable[[], None]] = None
        self._awaiting_start = False
        self.tts = self._make_qt_tts() if use_qt_tts else None
        self.backend = ("Qt TextToSpeech (" + self.tts.engine() + ")") if self.tts else self._pyttsx3_name()

    def _make_qt_tts(self):
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
        except ImportError:
            return None
        engines = [e for e in QTextToSpeech.availableEngines() if e != "mock"]
        if not engines:
            return None
        tts = QTextToSpeech(engines[0], self)
        if tts.state() == QTextToSpeech.State.Error:
            return None
        tts.stateChanged.connect(lambda s: self.log(f"speech engine: {s.name}"))
        tts.stateChanged.connect(lambda s: self._started() if s.name == "Speaking" else None)
        return tts

    def _started(self) -> None:
        if self._awaiting_start:
            self._awaiting_start = False
            if self.on_started is not None:
                self.on_started()

    def _pyttsx3_name(self) -> str:
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            return "none"
        return "pyttsx3"

    def say(self, text: str, clip: Optional[str] = None) -> None:
        self._awaiting_start = True
        wav = bundled_clip(clip, self.audio_dir)
        if wav is not None:
            from PySide6.QtMultimedia import QSoundEffect
            self._sound = QSoundEffect(self)
            sound = self._sound
            if hasattr(sound, "playingChanged"):
                def on_playing(sound=sound) -> None:
                    try:
                        playing = sound.isPlaying()
                    except RuntimeError:          # Qt already deleted it (app quitting)
                        return
                    if playing:
                        self._started()
                sound.playingChanged.connect(on_playing)
            self._sound.setSource(QUrl.fromLocalFile(str(wav)))
            self._sound.play()
            self.log(f"speech: bundled {wav.relative_to(ROOT) if wav.is_relative_to(ROOT) else wav}")
            return
        if self.tts is not None:
            self.log(f"speech: OS voice, {self.backend}")
            self.tts.say(text)
            return
        if self.backend == "pyttsx3":
            self.log("speech: pyttsx3, in a helper process")
            self._speak_pyttsx3(text)
            return
        self.log("speech: NO OFFLINE VOICE AVAILABLE, nothing audible")

    def _speak_pyttsx3(self, text: str) -> None:
        """Speak ``text`` from a fresh process. Returns at once; a line still being spoken is cut
        off first, as Qt's voice does, so two lines never overlap."""
        if self._helper is not None and self._helper.poll() is None:
            self._helper.terminate()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)      # no console flash on Windows
        try:
            self._helper = subprocess.Popen([sys.executable, "-c", PYTTSX3_HELPER, text],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=flags)
        except OSError as err:
            self.log(f"speech: could not start the voice helper ({err}), nothing audible")
            return
        self._started()
