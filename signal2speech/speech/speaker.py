"""Offline speech (#25, #28). Only AppSink calls say(), once per confirmed action.

Order, all offline:
1. Bundled clip: data/openorbit/audio/<action_id>.wav, only for the fixed OpenOrbit lines
   (show_satellite, compare_air_quality). Generated replies never use a clip, because a
   recording can't match words the wearer just approved.
2. The OS voice through Qt TextToSpeech (darwin on macOS, sapi/winrt on Windows, speechd on
   Linux). Non-blocking, so the window keeps updating while it speaks.
3. pyttsx3, if Qt has no usable engine. It blocks the UI while speaking, so it is last.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Protocol

from PySide6.QtCore import QObject, QTimer, QUrl

from signal2speech.core import ActionIds

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "data" / "openorbit" / "audio"
BUNDLED_CLIPS = frozenset({ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY})
ENGLISH_LINE = "english-line"   # clip hint: English text, use the English voice (#194)

Log = Callable[[str], None]


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

    def stop(self) -> None:
        pass

    def set_language(self, code: str) -> bool:
        return True                   # nothing is audible, so no voice can be wrong


class OfflineSpeaker(QObject):
    def __init__(self, log: Log, audio_dir: Path = AUDIO_DIR, use_qt_tts: bool = True,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.log = log
        self.audio_dir = audio_dir
        self._sound = None
        self._pyttsx3 = None
        # Called once when audio actually starts for the latest say() (#130 timing).
        self.on_started: Optional[Callable[[], None]] = None
        self._awaiting_start = False
        self.tts = self._make_qt_tts() if use_qt_tts else None
        self.language = "en"
        self._default_locale = self.tts.locale() if self.tts is not None else None
        self._reply_locale = None
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

    def voice_locales(self, code: str) -> list:
        """Installed OS-voice locales for a language code such as "es" (#194)."""
        if self.tts is None:
            return []
        from PySide6.QtCore import QLocale
        want = QLocale(code).language()
        return [loc for loc in self.tts.availableLocales() if loc.language() == want]

    def set_language(self, code: str) -> bool:
        """Speak replies in `code`. False (and English kept) if no OS voice for it is installed.
        The bundled OpenOrbit lines are English and always use the English voice."""
        if code == "en":
            self.language, self._reply_locale = "en", None
            return True
        found = self.voice_locales(code)
        if not found:
            return False
        self.language, self._reply_locale = code, found[0]
        return True

    def _use_locale(self, clip: Optional[str]) -> None:
        if self.tts is None or self._default_locale is None:
            return
        reply = self._reply_locale is not None and clip not in BUNDLED_CLIPS and clip != ENGLISH_LINE
        loc = self._reply_locale if reply else self._default_locale
        if self.tts.locale() != loc:
            self.tts.setLocale(loc)

    def stop(self) -> None:
        """Stop any audio now (attract mode ending, #193)."""
        if self._sound is not None:
            try:
                self._sound.stop()
            except RuntimeError:
                pass
        if self.tts is not None:
            self.tts.stop()

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
            self._use_locale(clip)
            self.log(f"speech: OS voice, {self.backend}" +
                     (f", {self.tts.locale().name()}" if self._reply_locale is not None else ""))
            self.tts.say(text)
            return
        if self.backend == "pyttsx3":
            self.log("speech: pyttsx3 (blocks the window while speaking)")
            QTimer.singleShot(0, lambda: self._speak_pyttsx3(text))   # let the UI paint first
            return
        self.log("speech: NO OFFLINE VOICE AVAILABLE, nothing audible")

    def _speak_pyttsx3(self, text: str) -> None:
        import pyttsx3
        if self._pyttsx3 is None:
            self._pyttsx3 = pyttsx3.init()
        self._pyttsx3.say(text)
        self._started()
        self._pyttsx3.runAndWait()
