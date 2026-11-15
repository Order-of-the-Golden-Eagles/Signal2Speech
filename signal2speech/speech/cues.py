"""Short, quiet sound cues for preview, confirm, and cancel (#177).

A wearer with their eyes closed can't see that a confirm registered, so each event gets a
distinct cue:
    preview  one soft note
    confirm  two rising notes (played BEFORE the spoken reply, never over it)
    cancel   two falling notes (cancel, timeout, or disconnect)

The tones are generated here with the standard library (sine waves with a short fade so they
don't click), written once to a temporary folder, and played with QSoundEffect. Nothing is
downloaded and there is no third-party audio, so there is nothing to license.
"""
from __future__ import annotations

import math
import struct
import tempfile
import wave
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

RATE = 22050
VOLUME = 0.22             # quiet: under the spoken reply's level
NOTE_MS = 90
GAP_MS = 25
TONES: Dict[str, Sequence[float]] = {
    "preview": (660.0,),
    "confirm": (523.25, 783.99),     # C5 -> G5, rising
    "cancel": (440.0, 329.63),       # A4 -> E4, falling
}


def duration_ms(name: str) -> int:
    notes = len(TONES[name])
    return notes * NOTE_MS + (notes - 1) * GAP_MS


def samples(name: str) -> List[int]:
    """16-bit mono samples for a cue: each note is a sine with a 10 ms fade in and out."""
    out: List[int] = []
    fade = int(RATE * 0.010)
    note_n, gap_n = int(RATE * NOTE_MS / 1000), int(RATE * GAP_MS / 1000)
    for i, freq in enumerate(TONES[name]):
        if i:
            out.extend([0] * gap_n)
        for n in range(note_n):
            env = min(1.0, n / fade, (note_n - 1 - n) / fade)
            out.append(int(32767 * VOLUME * env * math.sin(2 * math.pi * freq * n / RATE)))
    return out


def write_wav(name: str, path: Path) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{len(s := samples(name))}h", *s))
    return path


class CuePlayer:
    """Plays the three cues with QSoundEffect. Create it on the Qt main thread."""

    def __init__(self, folder: Optional[Path] = None, parent=None):
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect
        self.folder = Path(folder or tempfile.mkdtemp(prefix="s2s-cues-"))
        self.effects: Dict[str, object] = {}
        for name in TONES:
            path = write_wav(name, self.folder / f"{name}.wav")
            fx = QSoundEffect(parent)
            fx.setSource(QUrl.fromLocalFile(str(path)))
            fx.setVolume(1.0)            # the loudness is already in the samples
            self.effects[name] = fx
        self.played: List[Tuple[str, float]] = []

    def play(self, name: str) -> int:
        """Play a cue and return its length in ms, so speech can start after it."""
        import time
        self.played.append((name, time.monotonic()))
        fx = self.effects.get(name)
        if fx is not None:
            fx.play()
        return duration_ms(name)
