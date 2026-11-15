"""Fuzz the selection contract's exactly-once guarantee (#129).

Thousands of seeded random sequences of picks, confirms, cancels, disconnects, late and stale
decisions, duplicates, malformed events, and every input source go through SelectionHandler.
An independent checker in this file (not a copy of the handler's logic) watches only public
outcomes and listeners, and asserts after every step:

1. Outputs equal Confirmed outcomes: one output per confirm, never more, never otherwise.
2. A Confirmed needs a fresh Previewed (no cancel, disconnect, new question, or other outcome
   since), lands in the confirm round that preview opened, and outputs exactly the previewed
   action and words.
3. An accepted event ID is never accepted again. Rejections change nothing.
4. Live EEG never confirms while live confirm is disarmed.
5. A decision captured in an older round (arm_capture, then select_captured later) never acts
   in a newer round.

Default: 3,000 sequences x 60 steps, a few seconds. More: FUZZ_SEQUENCES=50000 pytest tests/test_contract_fuzz.py
Reproduce a failure: FUZZ_SEED=<seed printed in the failure> pytest tests/test_contract_fuzz.py
"""
import json
import os
import random
from pathlib import Path

import pytest

from signal2speech.core import (Choice, InputAdapter, InputSources, Outcome,
                                RoundKind, SelectionEvent, SelectionHandler, TargetIds)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
SEQUENCES = int(os.environ.get("FUZZ_SEQUENCES", "3000"))
STEPS = int(os.environ.get("FUZZ_STEPS", "60"))
ACCEPTED = {Outcome.Previewed, Outcome.Confirmed, Outcome.Cancelled}
SOURCES = sorted(InputSources.ALL) + ["bogus-source"]
TARGETS = [TargetIds.TARGET_1, TargetIds.TARGET_2]


def demo_choices():
    data = json.loads((CONTRACTS / "demo-round.json").read_text(encoding="utf-8"))
    return [Choice(c["targetId"], c["actionId"], c["label"], c.get("spokenText"))
            for c in data["choices"]]


class Sink:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


class Checker:
    """Expectations built only from public outcomes and listeners."""

    def __init__(self, handler: SelectionHandler):
        self.h = handler
        self.preview = None          # (choice, confirm_round_id) while a preview is fresh
        self.confirmed = 0
        self.accepted_ids = set()
        self.round_ids = []          # every round the app opened, in order
        self._just_previewed = None
        handler.on_round_opened.append(self._opened)
        handler.on_preview.append(self._previewed)
        handler.on_cleared.append(lambda _r: self._clear())

    def _opened(self, rnd):
        self.round_ids.append(rnd.id)
        if rnd.kind is RoundKind.CONFIRM and self._just_previewed is not None:
            self.preview = (self._just_previewed, rnd.id)
        else:
            self.preview = None      # a new question replaces any preview
        self._just_previewed = None

    def _previewed(self, choice):
        self._just_previewed = choice

    def _clear(self):
        self.preview = None

    def check(self, e, outcome, sink, armed, before_outputs, preview_before, trace):
        def fail(msg):
            raise AssertionError(f"{msg}\n  event={e}\n  outcome={outcome}\n  last steps:\n    "
                                 + "\n    ".join(trace[-12:]))
        if outcome in ACCEPTED:
            if e.eventId in self.accepted_ids:
                fail("an event ID was accepted twice")
            self.accepted_ids.add(e.eventId)
        if outcome is Outcome.Confirmed:
            if preview_before is None:
                fail("confirmed without a fresh preview")
            choice, confirm_round = preview_before
            if e.roundId != confirm_round:
                fail(f"confirmed in round {e.roundId}, not the preview's confirm round {confirm_round}")
            if e.source == InputSources.LIVE_EEG and not armed:
                fail("live EEG confirmed while live confirm was disarmed")
            out = sink.actions[-1] if sink.actions else None
            if out is None or (out.action_id, out.spoken_text) != (choice.action_id, choice.spoken_text):
                fail(f"output {out} doesn't match the previewed choice {choice}")
            self.confirmed += 1
            self.preview = None
        elif outcome is Outcome.Cancelled:
            self.preview = None
        if len(sink.actions) != self.confirmed:
            fail(f"{len(sink.actions)} outputs for {self.confirmed} confirms")
        if outcome is not Outcome.Confirmed and len(sink.actions) != before_outputs:
            fail("an output happened without a Confirmed outcome")


def run_sequence(seed: int):
    rng = random.Random(seed)
    sink = Sink()
    h = SelectionHandler(sink)
    chk = Checker(h)
    keyboard = InputAdapter(h, InputSources.KEYBOARD)
    eeg = InputAdapter(h, InputSources.LIVE_EEG)
    sim = InputAdapter(h, InputSources.SIMULATED)
    choices = demo_choices()
    trace, used_ids, n = [], [], 0
    armed_round = {}             # adapter -> round id it was armed in

    def fresh_id():
        nonlocal n
        n += 1
        return f"x{seed}-{n}"

    def random_event():
        r = rng.random()
        if r < 0.03:
            return None
        cur = h.current.id if h.current else None
        rid = rng.choices([cur, rng.choice(chk.round_ids) if chk.round_ids else None, "r999", ""],
                          weights=[60, 28, 8, 4])[0] or ""
        eid = rng.choices([fresh_id(), rng.choice(used_ids) if used_ids else fresh_id(), ""],
                          weights=[78, 18, 4])[0]
        tid = rng.choices(TARGETS + ["target-9", ""], weights=[45, 45, 7, 3])[0]
        src = rng.choices(SOURCES, weights=[1] * (len(SOURCES) - 1) + [0.2])[0]
        return SelectionEvent(src, rid, eid, tid)

    for step in range(STEPS):
        op = rng.choices(["begin", "event", "keyboard", "arm", "captured", "cancel",
                          "disconnect", "toggle_live"],
                         weights=[10, 40, 18, 8, 10, 5, 4, 2])[0]
        before, preview_before, armed = len(sink.actions), chk.preview, h.live_eeg_confirm_armed
        e, outcome = None, None
        if op == "begin":
            h.begin_choice_round(choices)
        elif op == "event":
            e = random_event()
            outcome = h.handle(e)
        elif op == "keyboard":
            tid = rng.choice(TARGETS)
            outcome = keyboard.select_now(tid)
            e = SelectionEvent(InputSources.KEYBOARD, "?", "?", tid)   # placeholder for messages
        elif op == "arm":
            ad = rng.choice([eeg, sim])
            ad.arm_capture()
            armed_round[ad] = h.current.id if h.current else None
        elif op == "captured":
            ad = rng.choice([eeg, sim])
            captured_in = armed_round.pop(ad, None)
            tid = rng.choice(TARGETS + [None])
            # Catch the event the adapter builds, so the checker sees its real IDs.
            built = []
            orig_handle = h.handle
            h.handle = lambda ev: (built.append(ev), orig_handle(ev))[1]
            try:
                outcome = ad.select_captured(tid)
            finally:
                h.handle = orig_handle
            e = built[0] if built else SelectionEvent(ad.source, "?", "?", str(tid))
            if outcome in ACCEPTED and e.roundId != captured_in:
                raise AssertionError(f"seed {seed}: a decision captured in {captured_in} acted in {e.roundId}")
        elif op == "cancel":
            h.cancel()
        elif op == "disconnect":
            h.disconnect()
        elif op == "toggle_live":
            h.live_eeg_confirm_armed = not h.live_eeg_confirm_armed
        if op == "keyboard" and outcome in ACCEPTED:
            e = SelectionEvent(InputSources.KEYBOARD, h_last_round(chk, outcome), f"k-accepted-{step}", e.targetId)
        trace.append(f"{step:02d} {op:<11} {e!s:<90} -> {outcome}")
        if e is not None and getattr(e, "eventId", "?") not in ("?", ""):
            used_ids.append(e.eventId)
        if outcome is not None and op in ("event", "captured"):
            try:
                chk.check(e, outcome, sink, armed, before, preview_before, trace)
            except AssertionError as err:
                raise AssertionError(f"seed {seed}: {err}") from None
        elif outcome is not None:
            # keyboard path: IDs are internal to the adapter; check counts and freshness only
            if outcome is Outcome.Confirmed:
                if preview_before is None:
                    raise AssertionError(f"seed {seed}: keyboard confirmed without a fresh preview\n" + "\n".join(trace[-12:]))
                chk.confirmed += 1
                chk.preview = None
            elif outcome is Outcome.Cancelled:
                chk.preview = None
            if len(sink.actions) != chk.confirmed:
                raise AssertionError(f"seed {seed}: {len(sink.actions)} outputs for {chk.confirmed} confirms\n" + "\n".join(trace[-12:]))
        elif len(sink.actions) != before:
            raise AssertionError(f"seed {seed}: output during '{op}'\n" + "\n".join(trace[-12:]))
        if op in ("cancel", "disconnect") and (h.current is not None or h.pending is not None):
            raise AssertionError(f"seed {seed}: {op} left a round or a preview open")
    return chk.confirmed, len(chk.accepted_ids)


def h_last_round(chk, outcome):
    return chk.round_ids[-1] if chk.round_ids else ""


def test_exactly_once_under_random_sequences():
    seeds = [int(os.environ["FUZZ_SEED"])] if "FUZZ_SEED" in os.environ else range(SEQUENCES)
    confirms = accepted = 0
    for seed in seeds:
        c, a = run_sequence(seed)
        confirms, accepted = confirms + c, accepted + a
    # The fuzzer must actually reach the interesting paths, not only rejections.
    if "FUZZ_SEED" not in os.environ:
        assert confirms > SEQUENCES // 4, f"only {confirms} confirms reached; the generator is too weak"
        assert accepted > SEQUENCES, f"only {accepted} accepted events"


def test_fuzzer_catches_a_double_output():
    """Mutation check: a sink that runs twice must be caught, or the fuzzer proves nothing."""
    orig = Sink.execute

    def twice(self, action):
        orig(self, action)
        orig(self, action)
    Sink.execute = twice
    try:
        with pytest.raises(AssertionError, match="outputs for"):
            for seed in range(200):
                run_sequence(seed)
    finally:
        Sink.execute = orig


def test_fuzzer_catches_a_cancel_that_keeps_the_preview(monkeypatch):
    """Mutation check: if Cancel or disconnect left the preview pending, the fuzzer must say so."""
    from signal2speech.core import handler as hmod
    real_close = hmod.SelectionHandler._close

    def leaky_close(self, reason):
        pending, pid = self._pending, self._pending_event_id
        real_close(self, reason)
        self._pending, self._pending_event_id = pending, pid
    monkeypatch.setattr(hmod.SelectionHandler, "_close", leaky_close)
    with pytest.raises(AssertionError, match="left a round or a preview open"):
        for seed in range(300):
            run_sequence(seed)


def test_fuzzer_catches_stale_decisions_being_accepted(monkeypatch):
    """Mutation check: a handler that ignored round IDs would let late decisions confirm."""
    real_handle = SelectionHandler.handle

    def stamp_current(self, e):
        if e is not None and self.current is not None and e.roundId:
            e = SelectionEvent(e.source, self.current.id, e.eventId, e.targetId)
        return real_handle(self, e)
    monkeypatch.setattr(SelectionHandler, "handle", stamp_current)
    with pytest.raises(AssertionError, match="not the preview's confirm round|acted in"):
        for seed in range(500):
            run_sequence(seed)
