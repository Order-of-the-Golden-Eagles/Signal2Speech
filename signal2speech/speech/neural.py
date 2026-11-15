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
#: Names the voice gets wrong: give it a spelling that sounds right.
RESPELLINGS: Dict[str, str] = {
    "MODIS": "Moe-diss",
}
#: Abbreviations people say as a word, and short words written in capitals: leave them alone.
SAID_AS_WORDS = frozenset({"NASA", "FIRMS", "MODIS", "GIBS", "LED", "OK", "NO", "YES", "AM", "PM"})
_ABBREVIATION = re.compile(r"\b[A-Z]{2,5}\b")
#: A line with numbers in it is spoken this much slower, so the figures are easy to catch.
NUMBER_SLOWDOWN = 1.25


def pace(text: str) -> float:
    """Piper's length scale for a line: 1.0 is the voice's normal speed, 1.25 is 25 % slower."""
    return NUMBER_SLOWDOWN if re.search(r"\d", text) else 1.0


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_ORDINAL_ENDINGS = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                    "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
_MONTHS = {"jan": "January", "feb": "February", "mar": "March", "apr": "April", "may": "May",
           "jun": "June", "jul": "July", "aug": "August", "sep": "September", "sept": "September",
           "oct": "October", "nov": "November", "dec": "December"}
_DATE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?!\d)(?:,?\s+(\d{4})(?!\d))?")


def _two_digits(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10 - 2] + ("-" + _ONES[n % 10] if n % 10 else "")


def day_words(day: int) -> str:
    """28 -> "twenty-eighth"."""
    words = _two_digits(day)
    head, _, last = words.rpartition("-")
    if last in _ORDINAL_ENDINGS:
        last = _ORDINAL_ENDINGS[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}-{last}" if head else last


def year_words(year: int) -> str:
    """2023 -> "twenty twenty-three", 2005 -> "two thousand five", 1900 -> "nineteen hundred"."""
    high, low = divmod(year, 100)
    if year % 1000 < 10:
        return _ONES[year // 1000] + " thousand" + (" " + _ONES[year % 1000] if year % 1000 else "")
    if low == 0:
        return _two_digits(high) + " hundred"
    return _two_digits(high) + (" oh " + _ONES[low] if low < 10 else " " + _two_digits(low))


def spoken_dates(text: str) -> str:
    """"June 28, 2023" and "Jun 28" become "June twenty-eighth, twenty twenty-three" and
    "June twenty-eighth". A number after a month that can't be a day is left alone."""
    def swap(match: "re.Match[str]") -> str:
        month, day, year = match.group(1), int(match.group(2)), match.group(3)
        if not 1 <= day <= 31:
            return match.group(0)
        said = f"{_MONTHS[month[:4].lower() if month.lower().startswith('sept') else month[:3].lower()]} {day_words(day)}"
        if year and 1000 <= int(year) <= 2999:
            return f"{said}, {year_words(int(year))}"
        return said + (match.group(0)[match.end(2) - match.start():] if year else "")
    return _DATE.sub(swap, text)


def spoken_form(text: str) -> str:
    """What the voice should be given so abbreviations sound right. The screen keeps the
    original text. Dates are said as dates ("June 28, 2023" becomes "June twenty-eighth, twenty
    twenty-three"). Known abbreviations are said in full ("AQI" becomes "air quality index").
    Unknown ones are spelled out with full stops ("PDF" becomes "P.D.F."), because a neural voice
    otherwise reads them as a word."""
    def swap(match: "re.Match[str]") -> str:
        word = match.group(0)
        if word in EXPANSIONS:
            return EXPANSIONS[word]
        if word in RESPELLINGS:
            return RESPELLINGS[word]
        if word in SAID_AS_WORDS:
            return word
        dotted = ".".join(word) + "."
        return dotted[:-1] if text[match.end():match.end() + 1] == "." else dotted
    return _ABBREVIATION.sub(swap, spoken_dates(text))


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


#: How many times to retry naming a finished file before giving up on it.
RENAME_TRIES = 100
#: Lines made ahead of time are made this many at once. More than that and they slow each other
#: down enough that the line needed right now arrives late.
WARM_AT_ONCE = 2


class Clip:
    """One line being turned into a WAV file by a Piper process."""

    def __init__(self, text: str, wav: Path, process: Optional[subprocess.Popen]):
        self.text, self.wav, self.process = text, wav, process
        self._part = wav.with_suffix(".part.wav")
        self._rename_tries = 0
        self.why = ""                              # why it failed, for the log

    def state(self) -> str:
        """``ready``, ``working`` or ``failed``."""
        if self.wav.is_file():
            return "ready"
        if self.process is None:
            self.why = self.why or "Piper could not be started"
            return "failed"
        code = self.process.poll()
        if code is None:
            return "working"
        if code == 0 and self._part.is_file() and self._part.stat().st_size > 44:
            try:
                os.replace(self._part, self.wav)      # only a finished file gets the real name
            except OSError as err:
                if self.wav.is_file():
                    return "ready"
                # A virus scanner can hold a just-written file for a moment: try again shortly.
                self._rename_tries += 1
                if self._rename_tries < RENAME_TRIES:
                    return "working"
                self.why = f"could not rename the finished file ({err})"
                return "failed"
            return "ready"
        self.why = f"Piper exited with code {code}"
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
        self._queue: list = []                     # lines waiting to be made ahead of time

    def warm(self, lines) -> None:
        """Make these lines ahead of time, a couple at a time. Call ``pump`` now and then (``say``
        paths do) to start the next ones."""
        for line in lines:
            if line not in self._queue:
                self._queue.append(line)
        self.pump()

    def pump(self) -> None:
        busy = sum(1 for c in self._clips.values() if c.process is not None and c.state() == "working")
        while self._queue and busy < WARM_AT_ONCE:
            if self.request(self._queue.pop(0)).state() == "working":
                busy += 1

    @classmethod
    def find(cls) -> Optional["PiperVoice"]:
        model = find_voice()
        if model is None or not piper_installed():
            return None
        return cls(model)

    def request(self, text: str) -> Clip:
        """Start making ``text`` (or return the clip already made or under way)."""
        spoken = spoken_form(text)
        scale = pace(text)                         # dates are written out by now, but still figures
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
