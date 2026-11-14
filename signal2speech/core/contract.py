"""Shared types. See docs/architecture/selection-contract.md."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class InputSources:
    """Wire values for SelectionEvent.source. Label input honestly."""
    KEYBOARD = "keyboard"
    SIMULATED = "simulated"   # g.Pype Generator or injected events
    RECORDED = "recorded"     # g.Pype replay of a recording
    LIVE_EEG = "live-eeg"     # HybridBlack, live
    ALL = frozenset({KEYBOARD, SIMULATED, RECORDED, LIVE_EEG})


class TargetIds:
    TARGET_1 = "target-1"
    TARGET_2 = "target-2"


class ActionIds:
    # Effects that run only after an explicit confirmation.
    SHOW_SATELLITE = "show_satellite"
    COMPARE_AIR_QUALITY = "compare_air_quality"
    SPEAK_REPLY = "speak_reply"
    # Confirmation-round controls. They never reach an effect sink.
    CONFIRM = "confirm"
    CANCEL = "cancel"


@dataclass(frozen=True)
class SelectionEvent:
    """The one input shape for keyboard, simulator, recorded, and live EEG."""
    source: str
    roundId: str
    eventId: str
    targetId: str

    @classmethod
    def from_dict(cls, d: dict) -> "SelectionEvent":
        return cls(d.get("source"), d.get("roundId"), d.get("eventId"), d.get("targetId"))


@dataclass(frozen=True)
class Choice:
    """One visible option. spoken_text is the exact text previewed and later spoken."""
    target_id: str
    action_id: str
    label: str
    spoken_text: Optional[str] = None


class RoundKind(Enum):
    CHOOSE = "choose"    # a valid pick only previews
    CONFIRM = "confirm"  # confirm or cancel the pending preview


@dataclass
class Round:
    """Frozen options issued by the app. One valid event consumes it."""
    id: str
    kind: RoundKind
    choices: tuple
    consumed: bool = False

    def find(self, target_id: str) -> Optional[Choice]:
        return next((c for c in self.choices if c.target_id == target_id), None)


@dataclass(frozen=True)
class ConfirmedAction:
    """What a confirmed choice asks speech and OpenOrbit to do. Sent exactly once."""
    action_id: str
    spoken_text: Optional[str]
    source: str
    preview_event_id: str
    confirm_event_id: str


class Outcome(Enum):
    Previewed = "Previewed"
    Confirmed = "Confirmed"
    Cancelled = "Cancelled"
    RejectedNoOpenRound = "RejectedNoOpenRound"
    RejectedStaleRound = "RejectedStaleRound"
    RejectedDuplicateEvent = "RejectedDuplicateEvent"
    RejectedRoundConsumed = "RejectedRoundConsumed"
    RejectedUnknownTarget = "RejectedUnknownTarget"
    RejectedUnknownSource = "RejectedUnknownSource"
    RejectedMalformed = "RejectedMalformed"
    RejectedLiveConfirmDisarmed = "RejectedLiveConfirmDisarmed"

    @property
    def rejected(self) -> bool:
        return self.name.startswith("Rejected")
