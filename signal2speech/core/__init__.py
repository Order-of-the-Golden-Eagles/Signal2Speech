"""Selection contract (#22). Pure Python, no g.Pype or Qt imports, so every track can test it."""
from .contract import (ActionIds, Choice, ConfirmedAction, InputSources, Outcome, Round,
                       RoundKind, SelectionEvent, TargetIds)
from .handler import ActionSink, SelectionHandler
from .adapter import EegClassMap, InputAdapter

__all__ = ["ActionIds", "ActionSink", "Choice", "ConfirmedAction", "EegClassMap", "InputAdapter",
           "InputSources", "Outcome", "Round", "RoundKind", "SelectionEvent", "SelectionHandler",
           "TargetIds"]
