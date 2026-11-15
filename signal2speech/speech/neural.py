"""A natural-sounding offline voice (#28): Piper, run as a separate program.

The operating system's built-in voices sound robotic. Piper is a neural text-to-speech engine
that runs on the laptop with no network, so the Wi-Fi-off demo keeps working.

- **Optional.** It is used only when the ``piper`` program is installed (``pip install
  piper-tts``) and a voice file is found. Otherwise the app speaks as before.
- **Voice file.** ``SIGNAL2SPEECH_VOICE`` names an ``.onnx`` file, or set it to ``off``.
  Without it, the first ``voices/*.onnx`` in the repo is used. Voice files are about 63 MB,
  carry their own licences, and are never committed.
- **Separate program.** Piper is GPL-3.0, so we run its command line and read the WAV file it
  writes. We never import it.
- **Speed.** Making a sentence takes a second or two, so the app asks for a line when it is
  previewed (``prepare``). By the time the wearer confirms, the audio is already on disk.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
VOICE_DIR = ROOT / "voices"
VOICE_ENV = "SIGNAL2SPEECH_VOICE"
PREFERRED_VOICE = "en_US-hfc_female-medium.onnx"

#: Abbreviations whose full form we know: say the full form.
EXPANSIONS: Dict[str, str] = {
    "AQI": "air quality index",
    "EMU": "Eastern Michigan University",
    "EPA": "Environmental Protection Agency",
    "EEG": "electroencephalogram",
    "BCI": "brain-computer interface",
}
#: Abbreviations people say as a word, and short words written in capitals: leave them alone.
SAID_AS_WORDS = frozenset({"NASA", "FIRMS", "MODIS", "GIBS", "LED", "OK", "NO", "YES", "AM", "PM"})
_ABBREVIATION = re.compile(r"\b[A-Z]{2,5}\b")
#: A line with numbers in it is spoken this much slower, so the figures are easy to catch.
NUMBER_SLOWDOWN = 1.25


def pace(text: str) -> float:
    """Piper's length scale for a line: 1.0 is the voice's normal speed, 1.25 is 25 % slower."""
    return NUMBER_SLOWDOWN if re.search(r"\d", text) else 1.0


def spoken_form(text: str) -> str:
    """What the voice should be given so abbreviations sound right. The screen keeps the
    original text. Known abbreviations are said in full ("AQI" becomes "air quality index").
    Unknown ones are spelled out with full stops ("PDF" becomes "P.D.F."), because a neural voice
    otherwise reads them as a word."""
    def swap(match: "re.Match[str]") -> str:
        word = match.group(0)
        if word in EXPANSIONS:
            return EXPANSIONS[word]
        if word in SAID_AS_WORDS:
            return word
        dotted = ".".join(word) + "."
        return dotted[:-1] if text[match.end():match.end() + 1] == "." else dotted
    return _ABBREVIATION.sub(swap, text)


def find_voice(voice_dir: Path = VOICE_DIR) -> Optional[Path]:
    """The voice file to use, or None when the neural voice is off or not installed."""
    choice = os.environ.get(VOICE_ENV, "").strip()
    if choice.lower() in ("off", "none", "0"):
        return None
    if choice:
        path = Path(choice)
        return path if path.is_file() else None
    preferred = voice_dir / PREFERRED_VOICE
    if preferred.is_file():
        return preferred
    found = sorted(voice_dir.glob("*.onnx")) if voice_dir.is_dir() else []
    return found[0] if found else None


def piper_installed() -> bool:
    return importlib.util.find_spec("piper") is not None


class Clip:
    """One line being turned into a WAV file by a Piper process."""

    def __init__(self, text: str, wav: Path, process: Optional[subprocess.Popen]):
        self.text, self.wav, self.process = text, wav, process
        self._part = wav.with_suffix(".part.wav")

    def state(self) -> str:
        """``ready``, ``working`` or ``failed``."""
        if self.wav.is_file():
            return "ready"
        if self.process is None:
            return "failed"
        code = self.process.poll()
        if code is None:
            return "working"
        if code == 0 and self._part.is_file() and self._part.stat().st_size > 44:
            try:
                os.replace(self._part, self.wav)      # only a finished file gets the real name
            except OSError:
                return "ready" if self.wav.is_file() else "failed"
            return "ready"
        return "failed"


class PiperVoice:
    """Turns text into WAV files with Piper. One short process per new line; a line asked for
    twice is made once."""

    def __init__(self, model: Path, cache_dir: Optional[Path] = None):
        self.model = Path(model)
        self.name = self.model.stem
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "signal2speech-voice"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._clips: Dict[str, Clip] = {}

    @classmethod
    def find(cls) -> Optional["PiperVoice"]:
        model = find_voice()
        if model is None or not piper_installed():
            return None
        return cls(model)

    def request(self, text: str) -> Clip:
        """Start making ``text`` (or return the clip already made or under way)."""
        spoken = spoken_form(text)
        scale = pace(spoken)
        key = hashlib.sha1(f"{self.name}\n{scale}\n{spoken}".encode("utf-8")).hexdigest()[:20]
        clip = self._clips.get(key)
        if clip is not None and clip.state() != "failed":
            return clip
        wav = self.cache_dir / f"{key}.wav"
        process = None
        if not wav.is_file():
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "piper", "-m", str(self.model),
                     "--length-scale", str(scale), "-f", str(wav.with_suffix(".part.wav"))],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                process.stdin.write((spoken.replace("\n", " ") + "\n").encode("utf-8"))
                process.stdin.close()
            except OSError:
                process = None
        clip = Clip(text, wav, process)
        self._clips[key] = clip
        return clip
