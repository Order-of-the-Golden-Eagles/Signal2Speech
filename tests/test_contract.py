"""Runs contracts/selection-scenarios.json and the sample events against the Python core (#22)."""
import json
from pathlib import Path

import pytest

from signal2speech.core import (ActionIds, Choice, EegClassMap, InputAdapter, InputSources,
                                Outcome, SelectionEvent, SelectionHandler, TargetIds)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


class RecordingSink:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


def demo_choices():
    data = json.loads((CONTRACTS / "demo-round.json").read_text(encoding="utf-8"))
    return [Choice(c["targetId"], c["actionId"], c["label"], c.get("spokenText"))
            for c in data["choices"]]


SCENARIOS = json.loads((CONTRACTS / "selection-scenarios.json").read_text(encoding="utf-8"))["scenarios"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario(scenario):
    sink = RecordingSink()
    h = SelectionHandler(sink)
    choices = demo_choices()
    for i, step in enumerate(scenario["steps"], 1):
        where = f"step {i} ({step['do']})"
        do = step["do"]
        if do == "begin":
            h.begin_choice_round(choices)
        elif do == "cancel":
            h.cancel()
        elif do == "disconnect":
            h.disconnect()
        elif do == "armLiveConfirm":
            h.live_eeg_confirm_armed = True
        elif do == "event":
            outcome = h.handle(SelectionEvent.from_dict(step["event"]))
            assert outcome.value == step["expect"], where
        else:
            pytest.fail(f"unknown step {do}")
        if "effects" in step:
            assert len(sink.actions) == step["effects"], where + " effects"
        if "action" in step:
            assert sink.actions[-1].action_id == step["action"], where + " action"
        if "round" in step:
            assert (h.current.id if h.current else None) == step["round"], where + " round"


def test_sample_events_match_contract():
    load = lambda f: SelectionEvent.from_dict(json.loads((CONTRACTS / "events" / f).read_text()))
    sink = RecordingSink()
    h = SelectionHandler(sink)
    h.begin_choice_round(demo_choices())
    assert h.handle(load("preview.json")) is Outcome.Previewed
    assert h.handle(load("stale.json")) is Outcome.RejectedStaleRound
    assert sink.actions == []
    assert h.handle(load("confirm-fresh.json")) is Outcome.Confirmed
    assert [a.spoken_text for a in sink.actions] == [
        "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."]


def test_adapter_stamps_round_at_capture_not_arrival():
    sink = RecordingSink()
    h = SelectionHandler(sink)
    h.live_eeg_confirm_armed = True
    eeg = InputAdapter(h, InputSources.LIVE_EEG)
    cmap = EegClassMap.default()
    h.begin_choice_round(demo_choices())
    eeg.arm_capture()                                      # flashing starts in r1
    assert eeg.select_captured(cmap.target_for(2)) is Outcome.Previewed
    # A second decision from the same r1 sequence arrives after r2 opened.
    assert eeg.select_captured(cmap.target_for(1)) is Outcome.RejectedNoOpenRound
    eeg.arm_capture()                                      # flashing starts in r2
    assert eeg.select_captured(cmap.target_for(1)) is Outcome.Confirmed
    assert len(sink.actions) == 1
    assert cmap.target_for(7) is None
    assert eeg.select_captured(None) is Outcome.RejectedNoOpenRound


def test_keyboard_adapter_uses_open_round():
    sink = RecordingSink()
    h = SelectionHandler(sink)
    kb = InputAdapter(h, InputSources.KEYBOARD)
    assert kb.select_now(TargetIds.TARGET_1) is Outcome.RejectedNoOpenRound
    h.begin_choice_round(demo_choices())
    assert kb.select_now(TargetIds.TARGET_1) is Outcome.Previewed
    assert kb.select_now(TargetIds.TARGET_1) is Outcome.Confirmed
    assert sink.actions[0].action_id == ActionIds.SHOW_SATELLITE


def test_two_adapters_on_one_source_never_collide():
    """P300 previews and the alpha switch confirms, each through its own live-eeg adapter (#23)."""
    sink = RecordingSink()
    h = SelectionHandler(sink)
    h.live_eeg_confirm_armed = True
    p300 = InputAdapter(h, InputSources.LIVE_EEG)
    alpha = InputAdapter(h, InputSources.LIVE_EEG)
    h.begin_choice_round(demo_choices())
    p300.arm_capture()
    assert p300.select_captured(TargetIds.TARGET_2) is Outcome.Previewed
    alpha.arm_capture()
    assert alpha.select_captured(TargetIds.TARGET_1) is Outcome.Confirmed
    assert [a.action_id for a in sink.actions] == [ActionIds.COMPARE_AIR_QUALITY]
    assert p300.create("r9", "target-1").eventId != alpha.create("r9", "target-1").eventId
