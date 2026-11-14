"""The single app-side state machine every input source feeds (#22).

Choose round -> preview -> fresh Confirm round -> exactly one effect.
Not thread-safe: call from the Qt main thread (marshal g.Pype outputs with a Qt signal first).
"""
from __future__ import annotations

from typing import Callable, List, Optional, Protocol, Sequence

from .contract import (ActionIds, Choice, ConfirmedAction, InputSources, Outcome, Round,
                       RoundKind, SelectionEvent, TargetIds)


class ActionSink(Protocol):
    """Implemented by the output side (#25): OpenOrbit view plus speech."""
    def execute(self, action: ConfirmedAction) -> None: ...


class SelectionHandler:
    def __init__(self, sink: ActionSink):
        self._sink = sink
        self._seen: set = set()
        self._counter = 0
        self._pending: Optional[Choice] = None
        self._pending_event_id: Optional[str] = None
        self.current: Optional[Round] = None
        # Live EEG may preview but not confirm until #23 proves rounds cannot cross.
        self.live_eeg_confirm_armed = False
        # Plain callables so core stays Qt-free; the UI wraps them in Qt signals.
        self.on_round_opened: List[Callable[[Round], None]] = []
        self.on_preview: List[Callable[[Choice], None]] = []
        self.on_cleared: List[Callable[[str], None]] = []
        self.on_handled: List[Callable[[Optional[SelectionEvent], Outcome], None]] = []

    @property
    def pending(self) -> Optional[Choice]:
        return self._pending

    def begin_choice_round(self, choices: Sequence[Choice]) -> Round:
        """Open a Choose round with frozen options. Closes any open round and clears any preview."""
        if not choices:
            raise ValueError("A round needs choices.")
        if any(c.action_id in (ActionIds.CONFIRM, ActionIds.CANCEL) for c in choices):
            raise ValueError("Confirm/Cancel belong to confirmation rounds only.")
        self._pending = None
        self._pending_event_id = None
        return self._open(RoundKind.CHOOSE, tuple(choices))

    def handle(self, e: Optional[SelectionEvent]) -> Outcome:
        """Apply one event. Side effects happen only on Confirmed."""
        outcome = self._apply(e)
        for fn in self.on_handled:
            fn(e, outcome)
        return outcome

    def cancel(self, reason: str = "cancel") -> None:
        """Judge cancel (Esc). Clears preview, no effect."""
        self._close(reason)

    def disconnect(self, reason: str = "disconnect") -> None:
        """Headset or pipeline dropped. Clears preview, no effect."""
        self._close(reason)

    def _apply(self, e: Optional[SelectionEvent]) -> Outcome:
        if e is None or not e.roundId or not e.eventId or not e.targetId:
            return Outcome.RejectedMalformed
        if e.source not in InputSources.ALL:
            return Outcome.RejectedUnknownSource
        if self.current is None:
            return Outcome.RejectedNoOpenRound
        if e.roundId != self.current.id:
            return Outcome.RejectedStaleRound
        if e.eventId in self._seen:
            return Outcome.RejectedDuplicateEvent
        if self.current.consumed:
            return Outcome.RejectedRoundConsumed
        choice = self.current.find(e.targetId)
        if choice is None:
            return Outcome.RejectedUnknownTarget
        if (self.current.kind is RoundKind.CONFIRM and choice.action_id == ActionIds.CONFIRM
                and e.source == InputSources.LIVE_EEG and not self.live_eeg_confirm_armed):
            return Outcome.RejectedLiveConfirmDisarmed  # round stays open for keyboard confirm

        # Consume before any UI update or effect so a repeated output cannot run twice.
        self._seen.add(e.eventId)
        self.current.consumed = True

        if self.current.kind is RoundKind.CHOOSE:
            self._pending, self._pending_event_id = choice, e.eventId
            for fn in self.on_preview:
                fn(choice)
            self._open(RoundKind.CONFIRM, (
                Choice(TargetIds.TARGET_1, ActionIds.CONFIRM, "Confirm"),
                Choice(TargetIds.TARGET_2, ActionIds.CANCEL, "Cancel"),
            ))
            return Outcome.Previewed

        if choice.action_id == ActionIds.CANCEL:
            self._close("cancel")
            return Outcome.Cancelled

        pending, preview_id = self._pending, self._pending_event_id
        self._pending = self._pending_event_id = None
        self.current = None
        self._sink.execute(ConfirmedAction(pending.action_id, pending.spoken_text, e.source,
                                           preview_id, e.eventId))
        return Outcome.Confirmed

    def _open(self, kind: RoundKind, choices: tuple) -> Round:
        self._counter += 1
        self.current = Round(f"r{self._counter}", kind, choices)
        for fn in self.on_round_opened:
            fn(self.current)
        return self.current

    def _close(self, reason: str) -> None:
        had = self.current is not None or self._pending is not None
        if self.current is not None:
            self.current.consumed = True
        self.current = None
        self._pending = self._pending_event_id = None
        if had:
            for fn in self.on_cleared:
                fn(reason)
