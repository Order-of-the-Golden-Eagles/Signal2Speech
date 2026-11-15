"""Offline speech (#25, #28). Only AppSink calls say(), once per confirmed action.

Order, all offline:
0. A natural neural voice (Piper, see neural.py), when it is installed and a voice file is
   present. It speaks every line, so the wearer has one voice. If a line can't be made, the
   steps below take over for that line.
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

from PySide6.QtCore import QObject, QTimer, QUrl

from signal2speech.core import ActionIds
from signal2speech.speech.neural import PiperVoice

#: How often to look whether a line being made is ready, and how long to wait before giving up.
NEURAL_POLL_MS = 25
NEURAL_WAIT_MS = 6000

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "data" / "openorbit" / "audio"
BUNDLED_CLIPS = frozenset({ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY})
ENGLISH_LINE = "english-line"   # clip hint: English text, use the English voice (#194)

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

    def stop(self) -> None:
        pass

    def set_language(self, code: str) -> bool:
        return True                   # nothing is audible, so no voice can be wrong


class OfflineSpeaker(QObject):
    def __init__(self, log: Log, audio_dir: Path = AUDIO_DIR, use_qt_tts: bool = True,
                 parent: Optional[QObject] = None, neural: Optional[PiperVoice] = None):
        super().__init__(parent)
        self.neural = neural                                 # the natural voice, when available
        self._waiting = None                                 # the neural clip say() is waiting for
        self._waited_ms = 0
        self.log = log
        self.audio_dir = audio_dir
        self._sound = None
        self._helper: Optional[subprocess.Popen] = None     # the pyttsx3 helper still speaking
        # Called once when audio actually starts for the latest say() (#130 timing).
        self.on_started: Optional[Callable[[], None]] = None
        self._awaiting_start = False
        self.tts = self._make_qt_tts() if use_qt_tts else None
        self.language = "en"
        self._default_locale = self.tts.locale() if self.tts is not None else None
        self._reply_locale = None
        self.fallback_backend = ("Qt TextToSpeech (" + self.tts.engine() + ")") if self.tts else self._pyttsx3_name()
        self.backend = f"Piper ({self.neural.name})" if self.neural else self.fallback_backend

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
        self._waiting = None                       # a natural-voice line still being made
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

    def prepare(self, text: str) -> None:
        """Start making a line that may be spoken soon (it is on screen as a preview), so it is
        ready the moment the wearer confirms. Makes no sound."""
        if self.neural is not None and text and self._reply_locale is None:
            self.neural.request(text)

    def _in_another_language(self, clip: Optional[str]) -> bool:
        """True for a reply that will be spoken in the wearer's chosen non-English language."""
        return (self._reply_locale is not None and clip not in BUNDLED_CLIPS
                and clip != ENGLISH_LINE)

    def say(self, text: str, clip: Optional[str] = None) -> None:
        self._awaiting_start = True
        self._waiting = None
        if self.neural is not None and not self._in_another_language(clip):   # an English voice
            self._waiting, self._waited_ms = (self.neural.request(text), clip), 0
            self._play_neural_when_ready()
            return
        self._say_without_neural(text, clip)

    def _play_neural_when_ready(self) -> None:
        if self._waiting is None:
            return
        made, clip = self._waiting
        state = made.state()
        if state == "working" and self._waited_ms < NEURAL_WAIT_MS:
            self._waited_ms += NEURAL_POLL_MS
            QTimer.singleShot(NEURAL_POLL_MS, self._play_neural_when_ready)
            return
        self._waiting = None
        if state == "ready":
            self._play_wav(made.wav)
            self.log(f"speech: natural voice, {self.backend}"
                     + (f" (waited {self._waited_ms} ms)" if self._waited_ms else ""))
            return
        self.log("speech: the natural voice couldn't make this line "
                 f"({made.why or 'not ready in time'}), using the standard voice")
        self._say_without_neural(made.text, clip)

    def _play_wav(self, wav: Path) -> None:
        """Play a WAV on the speaker's one sound player. One player for the whole session: a new
        QSoundEffect per line each held an audio channel that was never released, and after
        about 35 lines Windows gave out no more. The app then went silent while still reporting
        that it was playing."""
        from PySide6.QtMultimedia import QSoundEffect
        if self._sound is None:
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
        else:
            self._sound.stop()                    # a line still playing is cut off, never overlapped
        self._sound.setSource(QUrl.fromLocalFile(str(wav)))
        self._sound.play()

    def _say_without_neural(self, text: str, clip: Optional[str] = None) -> None:
        wav = bundled_clip(clip, self.audio_dir)
        if wav is not None:
            self._play_wav(wav)
            self.log(f"speech: bundled {wav.relative_to(ROOT) if wav.is_relative_to(ROOT) else wav}")
            return
        if self.tts is not None:
            self._use_locale(clip)
            self.log(f"speech: OS voice, {self.fallback_backend}" +
                     (f", {self.tts.locale().name()}" if self._reply_locale is not None else ""))
            self.tts.say(text)
            return
        if self.fallback_backend == "pyttsx3":
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
