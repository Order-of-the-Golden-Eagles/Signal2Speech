"""Offline speech for confirmed actions (#25, #28). See speaker.py."""
from .speaker import (AUDIO_DIR, BUNDLED_CLIPS, MutedSpeaker, OfflineSpeaker, Speaker,
                      bundled_clip)

__all__ = ["AUDIO_DIR", "BUNDLED_CLIPS", "MutedSpeaker", "OfflineSpeaker", "Speaker",
           "bundled_clip"]
