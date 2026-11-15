"""AI Answering checks (#5, #27, #28). Offscreen, no network, no API key, no headset."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.ai import (CLAUDE, SAVED, STUB, ProviderError, ReplySuggester,  # noqa: E402
                              SavedPhrases, StubProvider, load_dotenv, make_provider, validate)
from signal2speech.ai.__main__ import AnsweringDemo  # noqa: E402
from signal2speech.ai.qt import AsyncSuggester  # noqa: E402
from signal2speech.core import ActionIds, Outcome, TargetIds  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, until, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        qapp.processEvents()
        time.sleep(0.002)


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text, clip=None):
        self.said.append(text)


class FixedProvider:
    name = CLAUDE

    def __init__(self, texts=("Yes, I'd love some tea.", "No thanks, I'm fine."), delay=0.0,
                 error=None):
        self.texts, self.delay, self.error, self.calls = list(texts), delay, error, []

    def replies(self, question, avoid=()):
        self.calls.append((question, tuple(avoid)))
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.texts


# ── Pure suggestion logic ────────────────────────────────────
def test_replies_become_speak_reply_choices():
    rs = ReplySuggester(FixedProvider()).suggest("Would you like tea?")
    assert rs.origin == CLAUDE
    assert [c.target_id for c in rs.choices] == [T1, T2]
    assert all(c.action_id == ActionIds.SPEAK_REPLY for c in rs.choices)
    assert all(c.label == c.spoken_text for c in rs.choices)   # tile shows the exact words
    assert rs.texts == ["Yes, I'd love some tea.", "No thanks, I'm fine."]


@pytest.mark.parametrize("error,note", [(ProviderError("provider timeout"), "provider timeout"),
                                        (ProviderError("offline: no connection to provider"), "offline"),
                                        (RuntimeError("boom"), "provider failed (RuntimeError)")])
def test_provider_failure_falls_back_to_saved(error, note):
    rs = ReplySuggester(FixedProvider(error=error)).suggest("Tea?")
    assert rs.origin == SAVED and note in rs.note and rs.texts == ["Yes.", "No."]


@pytest.mark.parametrize("texts", [["Same", "same"], ["Only one", ""], ["a", "b", "c"], ["x" * 200, "y"]])
def test_bad_provider_output_rejected(texts):
    with pytest.raises(ProviderError):
        validate(texts)
    assert ReplySuggester(FixedProvider(texts)).suggest("Q?").origin == SAVED


def test_saved_phrases_cycle():
    s = SavedPhrases([("A.", "B."), ("C.", "D.")])
    assert s.current().texts == ["A.", "B."]
    assert s.next_page().texts == ["C.", "D."]
    assert s.next_page().texts == ["A.", "B."]


def test_make_provider_without_key_is_labelled_stub(tmp_path):
    provider, note = make_provider("auto", env={})
    assert isinstance(provider, StubProvider) and "provider setup pending" in note
    with pytest.raises(ValueError):
        make_provider("claude", env={})
    assert make_provider("saved", env={})[0] is None


def test_make_provider_with_key_builds_claude_without_calling_it():
    pytest.importorskip("anthropic")
    provider, note = make_provider("auto", env={"ANTHROPIC_API_KEY": "sk-test"})
    assert provider.name == CLAUDE and "claude-sonnet-5-5" in note


def test_dotenv_loads_without_overriding(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nANTHROPIC_API_KEY='sk-file'\nexport OTHER=1\n")
    env = load_dotenv(f, {"OTHER": "keep"})
    assert env == {"ANTHROPIC_API_KEY": "sk-file", "OTHER": "keep"}


def test_claude_provider_request_shape_and_refusal():
    anthropic = pytest.importorskip("anthropic")
    from signal2speech.ai import ClaudeProvider

    class Block:
        type, text = "text", '{"reply_a": "Sure.", "reply_b": "Not today."}'

    class Resp:
        stop_reason, content = "end_turn", [Block()]

    seen = {}

    class Msgs:
        def create(self, **kw):
            seen.update(kw)
            return Resp()

    class Client:
        class beta:
            messages = Msgs()

    p = ClaudeProvider("sk-test", client=Client())
    assert p.replies("Walk later?", avoid=["Yes."]) == [("Sure.", "speak_reply"),
                                                        ("Not today.", "speak_reply")]
    assert seen["model"] == "claude-sonnet-5-5" and seen["fallbacks"] == "default"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert "Already offered" in seen["messages"][0]["content"]
    Resp.stop_reason = "refusal"
    with pytest.raises(ProviderError, match="declined"):
        p.replies("Walk later?")


# ── Grounded replies and app actions (#106) ──────────────────
def test_system_prompt_has_dataset_facts_and_is_stable():
    pytest.importorskip("anthropic")
    from signal2speech.ai import ClaudeProvider, openorbit_facts
    from signal2speech.openorbit.dataset import load_dataset

    ds = load_dataset()
    p1, p2 = ClaudeProvider("sk-test", client=object()), ClaudeProvider("sk-test", client=object())
    assert p1.system == p2.system and openorbit_facts() is not None
    for c in ds.changes:
        for value in (c.county, str(c.before), str(c.after), str(abs(c.change)),
                      c.before_category, c.after_category):
            assert value in p1.system
    for word in ("2023-06-26", "2023-06-28", "Eastern Michigan University", "Detroit",
                 "NASA GIBS", "EPA AirData", "Never invent numbers", "I don't know"):
        assert word in p1.system
    assert f"Larger increase: {ds.largest_increase().county}" in p1.system


def test_compare_action_uses_dataset_line_not_model_text():
    from signal2speech.openorbit.dataset import load_dataset

    provider = FixedProvider([("Wayne rose more.", "compare_air_quality"),
                              ("I'm not sure.", "speak_reply")])
    rs = ReplySuggester(provider).suggest("Which county's AQI rose more?")
    a, b = rs.choices
    assert rs.origin == CLAUDE
    assert (a.target_id, a.action_id) == (T1, ActionIds.COMPARE_AIR_QUALITY)
    assert a.spoken_text == load_dataset().spoken_comparison() and "Wayne rose" not in a.label
    assert "Compare counties" in a.label
    assert (b.action_id, b.spoken_text) == (ActionIds.SPEAK_REPLY, "I'm not sure.")


def test_show_satellite_action_uses_contract_line():
    import json
    from pathlib import Path
    contract = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "demo-round.json")
                          .read_text(encoding="utf-8"))
    line = next(c["spokenText"] for c in contract["choices"] if c["actionId"] == "show_satellite")
    rs = ReplySuggester(FixedProvider([("Sure.", "speak_reply"),
                                       ("Look.", "show_satellite")])).suggest("Show me?")
    assert rs.choices[1].action_id == ActionIds.SHOW_SATELLITE
    assert rs.choices[1].spoken_text == line


@pytest.mark.parametrize("items", [
    [("Yes.", "launch_rocket"), ("No.", "speak_reply")],                   # unknown action
    [("A.", "compare_air_quality"), ("B.", "compare_air_quality")],        # same action twice
    [("Same.", "speak_reply"), ("same.", "speak_reply")],                  # same words
    [("Only one", "speak_reply")],                                         # one reply
    [("x" * 200, "speak_reply"), ("No.", "speak_reply")],                  # too long
])
def test_invalid_action_output_falls_back(items):
    rs = ReplySuggester(FixedProvider(items)).suggest("Q?")
    assert rs.origin == SAVED and rs.texts == ["Yes.", "No."]


def test_claude_provider_returns_actions_from_schema():
    pytest.importorskip("anthropic")
    from signal2speech.ai import ClaudeProvider
    from signal2speech.ai.replies import REPLY_SCHEMA

    class Block:
        type = "text"
        text = ('{"reply_a": "Washtenaw.", "action_a": "compare_air_quality", '
                '"reply_b": "Let me check.", "action_b": "speak_reply"}')

    class Resp:
        stop_reason, content = "end_turn", [Block()]

    class Client:
        class beta:
            class messages:
                @staticmethod
                def create(**kw):
                    assert kw["output_config"]["format"]["schema"] is REPLY_SCHEMA
                    return Resp()

    assert set(REPLY_SCHEMA["required"]) == {"reply_a", "action_a", "reply_b", "action_b"}
    p = ClaudeProvider("sk-test", client=Client())
    assert p.replies("Which county?") == [("Washtenaw.", "compare_air_quality"),
                                          ("Let me check.", "speak_reply")]


# ── Qt: deadline and stale results ───────────────────────────
def test_deadline_falls_back_and_late_answer_is_ignored(qapp):
    got = []
    a = AsyncSuggester(ReplySuggester(FixedProvider(delay=0.3)), deadline_s=0.05)
    a.ready.connect(got.append)
    a.request("Tea?")
    pump(qapp, lambda: got)
    assert got[0].origin == SAVED and "timeout" in got[0].note
    pump(qapp, lambda: False, timeout=0.5)         # let the slow provider finish
    assert len(got) == 1                            # late answer never replaces choices


def test_newer_request_wins(qapp):
    got = []
    prov = FixedProvider(delay=0.05)
    a = AsyncSuggester(ReplySuggester(prov), deadline_s=2)
    a.ready.connect(got.append)
    a.request("first")
    a.request("second")
    pump(qapp, lambda: len(prov.calls) == 2 and got, timeout=2)
    pump(qapp, lambda: False, timeout=0.2)
    assert len(got) == 1


# ── End to end through the #4 app ────────────────────────────
class FakeView:
    def __init__(self):
        self.calls = []

    def show_satellite(self):
        self.calls.append(ActionIds.SHOW_SATELLITE)

    def compare_air_quality(self):
        self.calls.append(ActionIds.COMPARE_AIR_QUALITY)


def make_demo(qapp, provider=None, deadline_s=2, view=None):
    speaker = FakeSpeaker()
    demo = AnsweringDemo(provider=provider or FixedProvider(), provider_note="test",
                         speaker=speaker, echo=False, deadline_s=deadline_s,
                         view=view if view is not None else FakeView())
    demo.start()
    return demo, speaker


def test_question_preview_confirm_speaks_exact_reply_once(qapp):
    demo, speaker = make_demo(qapp)
    demo.ask("Would you like tea?")
    pump(qapp, lambda: demo.current and demo.current.origin == CLAUDE)
    w = demo.app.window
    assert w.tiles[T1].label == "Yes, I'd love some tea."
    assert w.press_target(T1) is Outcome.Previewed
    assert speaker.said == []                                   # preview is silent
    assert "Yes, I'd love some tea." in w.preview.text()
    assert w.press_target(T1) is Outcome.Confirmed
    assert speaker.said == ["Yes, I'd love some tea."]
    w.press_target(T1)
    assert len(speaker.said) == 1
    assert not any("BUG: map action" in l for l in demo.app.log.lines)
    assert demo.app.choices[0].spoken_text == "Yes."            # next round offers saved phrases


def test_cancel_returns_to_same_frozen_replies(qapp):
    demo, speaker = make_demo(qapp)
    demo.ask("Tea?")
    pump(qapp, lambda: demo.current and demo.current.origin == CLAUDE)
    demo.app.window.press_target(T2)
    demo.app.window.press_target(T2)                            # cancel
    assert speaker.said == []
    assert [c.spoken_text for c in demo.app.choices] == ["Yes, I'd love some tea.", "No thanks, I'm fine."]


def test_timeout_shows_saved_phrases_then_confirm_speaks_preset(qapp):
    demo, speaker = make_demo(qapp, FixedProvider(delay=0.5), deadline_s=0.05)
    demo.ask("Tea?")
    pump(qapp, lambda: demo.current and "timeout" in demo.current.note)
    assert demo.current.origin == SAVED and "Replies: Saved phrases" in demo.panel.origin.text()
    demo.app.window.press_target(T2)
    demo.app.window.press_target(T1)
    assert speaker.said == ["No."]


def test_alternatives_pass_previous_replies_and_saved_button_cycles(qapp):
    prov = FixedProvider()
    demo, _ = make_demo(qapp, prov)
    demo.ask("Tea?")
    pump(qapp, lambda: demo.current and demo.current.origin == CLAUDE)
    demo.alternatives()
    pump(qapp, lambda: len(prov.calls) == 2)
    assert prov.calls[1][1] == ("Yes, I'd love some tea.", "No thanks, I'm fine.")
    demo.saved()
    assert demo.current.origin == SAVED
    assert demo.app.window.tiles[T1].label == "Please give me a moment."


def test_stub_is_labelled_on_screen(qapp):
    demo, _ = make_demo(qapp, StubProvider())
    demo.ask("Tea?")
    pump(qapp, lambda: demo.current and demo.current.origin == STUB)
    assert "Replies: Stub" in demo.panel.origin.text()


def test_map_suggestion_reveals_the_map_once(qapp):
    """#106 lets Claude suggest a map action. The AI demo must reveal the map, not drop it."""
    from signal2speech.core import Choice
    from signal2speech.ai import ReplySet
    view = FakeView()
    demo, speaker = make_demo(qapp, view=view)
    line = "Washtenaw's AQI rose 186 points. Wayne's rose 168 points."
    demo._show(ReplySet((Choice(T1, ActionIds.COMPARE_AIR_QUALITY, "Compare counties (shows the map)", line),
                         Choice(T2, ActionIds.SPEAK_REPLY, "No, thanks.", "No, thanks.")), CLAUDE))
    demo.app.window.press_target(T1)
    assert view.calls == [] and speaker.said == []             # preview: nothing yet
    demo.app.window.press_target(T1)
    assert view.calls == [ActionIds.COMPARE_AIR_QUALITY] and speaker.said == [line]
    assert not any("BUG" in l for l in demo.app.log.lines)


def test_ai_demo_uses_the_real_map_view_by_default(qapp):
    demo = AnsweringDemo(provider=FixedProvider(), provider_note="test", speaker=FakeSpeaker(),
                         echo=False)
    assert type(demo.app.view).__name__ in ("OpenOrbitView", "PendingMapView")


# ── #134: editable saved phrases ─────────────────────────────
import json as _json  # noqa: E402

from signal2speech.ai import (PHRASES_FILE, SAVED_PHRASES, load_saved_phrases,  # noqa: E402
                              saved_phrases_from_file)


def _write(tmp_path, payload):
    f = tmp_path / "phrases.json"
    f.write_text(payload if isinstance(payload, str) else _json.dumps(payload), encoding="utf-8")
    return f


def test_repo_phrases_file_matches_the_built_in_list():
    pairs, note = load_saved_phrases(PHRASES_FILE)
    assert pairs == list(SAVED_PHRASES) and note == "phrases.json (6 pairs)"


def test_valid_file_replaces_the_phrases(tmp_path):
    f = _write(tmp_path, {"pairs": [["I'd like water.", "I'd like juice."], ["Yes, please.", "Not now."]]})
    saved = saved_phrases_from_file(f)
    assert saved.source == "phrases.json (2 pairs)"
    assert saved.current().texts == ["I'd like water.", "I'd like juice."]
    assert saved.next_page().texts == ["Yes, please.", "Not now."]


@pytest.mark.parametrize("payload,why", [
    ("{not json", "unreadable"),
    ({"pairs": []}, 'no "pairs" list'),
    ({"pairs": [["Only one"]]}, "isn't two strings"),
    ({"pairs": [["Same.", "same."]]}, "same reply twice"),
    ({"pairs": [["x" * 130, "Short."]]}, "too long"),
    ([["Yes.", 5]], "isn't two strings"),
])
def test_bad_file_falls_back_to_built_in_with_reason(tmp_path, payload, why):
    pairs, note = load_saved_phrases(_write(tmp_path, payload))
    assert pairs == list(SAVED_PHRASES) and note.startswith("built-in") and why in note


def test_missing_file_uses_built_in(tmp_path):
    pairs, note = load_saved_phrases(tmp_path / "nope.json")
    assert pairs == list(SAVED_PHRASES) and note == "built-in (no nope.json)"


def test_ai_demo_logs_where_saved_phrases_came_from(qapp):
    demo = AnsweringDemo(provider=FixedProvider(), provider_note="test", speaker=FakeSpeaker(),
                         echo=False, view=FakeView())
    assert any(l.endswith("saved phrases: phrases.json (6 pairs)") for l in demo.app.log.lines)
