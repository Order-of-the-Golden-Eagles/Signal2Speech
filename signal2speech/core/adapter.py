"""Turns source-specific input into SelectionEvents.

The round ID is stamped when input is captured (the flash sequence starts), never when the
classifier output arrives.
"""
from __future__ import annotations

import itertools
from typing import Dict, Optional

from .contract import InputSources, Outcome, SelectionEvent, TargetIds
from .handler import SelectionHandler

_PREFIX = {InputSources.KEYBOARD: "k", InputSources.SIMULATED: "s",
           InputSources.RECORDED: "rec", InputSources.LIVE_EEG: "e"}

# One counter for the whole process, shared by every adapter. Event IDs must be unique per run,
# not per adapter: the P300 chooser and the alpha switch each own a live-eeg adapter, and
# per-instance counters made both emit "e1", so the handler rejected the confirm as a duplicate.
_EVENT_NUMBERS = itertools.count(1)


class InputAdapter:
    def __init__(self, handler: SelectionHandler, source: str):
        if source not in InputSources.ALL:
            raise ValueError(f"Unknown source: {source}")
        self._handler = handler
        self.source = source
        self._armed_round_id: Optional[str] = None

    def select_now(self, target_id: str) -> Outcome:
        """Keyboard: capture and arrival are the same instant, so use the open round."""
        r = self._handler.current
        if r is None:
            return Outcome.RejectedNoOpenRound
        return self._handler.handle(self.create(r.id, target_id))

    def arm_capture(self) -> None:
        """EEG: call when the flash/stimulus sequence for the open round starts."""
        r = self._handler.current
        self._armed_round_id = r.id if r else None

    def select_captured(self, target_id: Optional[str]) -> Outcome:
        """EEG: call with the decoded target from the g.Pype pipeline, on the Qt main thread."""
        round_id, self._armed_round_id = self._armed_round_id, None  # one decision per sequence
        if round_id is None:
            return Outcome.RejectedNoOpenRound
        if target_id is None:
            return Outcome.RejectedUnknownTarget
        return self._handler.handle(self.create(round_id, target_id))

    def create(self, round_id: str, target_id: str) -> SelectionEvent:
        return SelectionEvent(self.source, round_id, f"{_PREFIX[self.source]}{next(_EVENT_NUMBERS)}",
                              target_id)


class EegClassMap:
    """Classifier output index -> app target. Our own training labels define the indices."""

    def __init__(self, mapping: Dict[int, str]):
        self._map = dict(mapping)

    @classmethod
    def default(cls) -> "EegClassMap":
        """Class 1 -> target-1, class 2 -> target-2 (label training epochs this way)."""
        return cls({1: TargetIds.TARGET_1, 2: TargetIds.TARGET_2})

    def target_for(self, class_index) -> Optional[str]:
        try:
            return self._map.get(int(class_index))
        except (TypeError, ValueError):
            return None
