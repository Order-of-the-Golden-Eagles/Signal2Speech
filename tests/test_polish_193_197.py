"""Attract mode (#193), reply language (#194), text size (#195), practice round (#196), and the
help phrase (#197). Headless, with fake speakers: CI never plays sound or calls an API."""
import os
import random
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QLocale, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import InputSources, Outcome, RoundKind, TargetIds  # noqa: E402
from signal2speech.ui import theme as T  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def reset_scale():
    T.set_scale(1.0)
    yield
    T.set_scale(1.0)


def pump(qapp, until=lambda: False, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        qapp.processEvents()
        time.sleep(0.005)


class Speaker:
    def __init__(self, voices=("en", "es")):
        self.said = []
        self.voices = set(voices)
        self.language = "en"

    def say(self, text, clip=None):
        self.said.append((text, clip))

    def stop(self):
        self.said.append(("<stop>", None))

    def set_language(self, code):
        if code not in self.voices:
            return False
        self.language = code
        return True


class View(QLabel):
    def __init__(self):
        super().__init__("map")
        self.calls = []

    def show_satellite(self):
        self.calls.append("show_satellite")

    def compare_air_quality(self):
        self.calls.append("compare_air_quality")


class PlainView:
    def show_satellite(self):
        pass

    def compare_air_quality(self):
        pass


def make(source=InputSources.KEYBOARD, **kw):
    kw.setdefault("view", PlainView())
    spk = kw.pop("speaker", None) or Speaker()
    app = App(source, speaker=spk, echo=False, reopen_ms=60000, **kw)
    return app, spk


def key(obj, k, press=True, repeat=False, text=""):
    ev = QKeyEvent(QEvent.Type.KeyPress if press else QEvent.Type.KeyRelease, k,
                   Qt.KeyboardModifier.NoModifier, text, repeat)
    QApplication.sendEvent(obj, ev)


# ── #195 text size ───────────────────────────────────────────
def test_text_size_steps_between_80_and_160_percent_and_resets(qapp):
    app, _ = make()
    app.ask()
    rid = app.handler.current.id
    seen = [app.step_text(1) for _ in range(10)]
    assert seen[-1] == 1.6 and sorted(set(seen)) == [s for s in T.SCALE_STEPS if s > 1.0]
    assert app.toast.text() == "Text size 160%" and app.toast.isVisibleTo(app.root)
    assert f"font-size: {T.px(T.HEADING)}px" in app.window.styleSheet() and T.px(T.HEADING) == round(T.HEADING * 1.6)
    assert f"font-size: {T.px(T.BODY - 2)}px" in app.conversation.styleSheet()
    assert f"font-size:{T.px(T.TITLE - 2)}px" in app.help.text()
    assert [app.step_text(-1) for _ in range(10)][-1] == 0.8
    assert app.step_text(0) == 1.0
    assert app.handler.current.id == rid and app.handler.pending is None   # never touches the handler
    app.close()


@pytest.mark.parametrize("scale", [0.8, 1.6])
def test_every_text_size_fits_1280x720_in_choose_preview_and_reveal(qapp, scale):
    T.set_scale(scale)
    app, _ = make(view=View(), reveal_ms=60000)
    app.apply_text_scale()
    app.root.show()
    # Measure at the size being claimed. The window opens no larger than the screen it is on
    # (#204), and CI's test screen is 800 x 800: a narrower window wraps the preview onto more
    # lines, which is taller than it would be on a real 1280 x 720 screen.
    app.root.resize(1280, 720)
    app.ask()
    sizes = [app.root.minimumSizeHint()]
    app.window.press_target(T2)
    sizes.append(app.root.minimumSizeHint())
    app.window.press_target(T1)
    assert app.revealing
    sizes.append(app.root.minimumSizeHint())
    assert all(s.width() <= 1280 and s.height() <= 720 for s in sizes), [(s.width(), s.height()) for s in sizes]
    app.close()
    app.root.close()


def test_contrast_still_passes_at_the_smallest_text_size():
    from tests.test_contrast import contrast, required
    for name, fg, bg, size, bold in T.TEXT_PAIRS:
        small = max(1, round(size * T.SCALE_STEPS[0]))
        assert contrast(fg, bg) >= required(small, bold), name


def test_resizing_text_during_a_flash_sequence_keeps_flash_timing(qapp):
    app, _ = make()
    app.ask()
    f = app.window.flasher
    flashes, done = [], []
    f.on_flash = lambda t: flashes.append(time.monotonic())
    f.on_sequence_finished = lambda: done.append(True)
    before = (f.flash_ms, f.isi_ms, f.repetitions)
    f.start([T1, T2])
    pump(qapp, lambda: len(flashes) >= 4)
    app.step_text(1)
    app.step_text(1)
    pump(qapp, lambda: bool(done), timeout=10)
    assert done and len(flashes) == 2 * f.repetitions
    assert (f.flash_ms, f.isi_ms, f.repetitions) == before
    app.close()


# ── #197 help phrase ─────────────────────────────────────────
def test_holding_h_for_2_s_says_the_phrase_once_and_a_tap_does_nothing(qapp):
    app, spk = make()
    app.ask()
    app.helpcall._hold.setInterval(150)
    key(app.root, Qt.Key.Key_H, press=True)
    key(app.root, Qt.Key.Key_H, press=False)                    # a tap
    pump(qapp, timeout=0.3)
    assert app.sink.help_calls == []
    key(app.root, Qt.Key.Key_H, press=True)
    key(app.root, Qt.Key.Key_H, press=True, repeat=True)        # auto-repeat is ignored
    pump(qapp, lambda: bool(app.sink.help_calls), timeout=1)
    key(app.root, Qt.Key.Key_H, press=False)
    assert len(app.sink.help_calls) == 1
    assert spk.said == [("I need help, please.", "english-line")]
    assert app.conversation.last()[:2] == ("help", "“I need help, please.”")
    assert app.help_banner.isVisibleTo(app.root)
    text = app.report_text()
    assert "## Help phrase" in text and "Keyboard (held H)" in text
    assert "| 0 | 0 | 0 |" in text                             # not counted as a choice
    app.close()


def test_help_phrase_repeats_at_most_once_every_10_s(qapp):
    now = [100.0]
    app, spk = make()
    app.helpcall.clock = lambda: now[0]
    assert app.helpcall.trigger("keyboard")
    now[0] += 9.9
    assert not app.helpcall.trigger("keyboard")
    now[0] += 0.2
    assert app.helpcall.trigger("keyboard")
    assert len(app.sink.help_calls) == 2 and app.helpcall.blocked == 1
    app.close()


@pytest.mark.parametrize("state", ["waiting", "choose", "preview", "reveal", "help overlay", "practice"])
def test_help_phrase_works_from_every_state_and_leaves_the_round_alone(qapp, state):
    app, spk = make(view=View(), reveal_ms=60000, practice_s=30)
    app.root.show()
    if state != "waiting":
        app.ask()
    if state == "preview":
        app.window.press_target(T2)
    if state == "reveal":
        app.window.press_target(T2)
        app.window.press_target(T1)
    if state == "help overlay":
        app.help.toggle()
    if state == "practice":
        assert app.start_practice()
    rnd, pending = app.handler.current, app.handler.pending
    said_before = len(spk.said)
    assert app.helpcall.trigger("keyboard")
    assert app.handler.current is rnd and app.handler.pending is pending
    assert spk.said[said_before:] == [("I need help, please.", "english-line")]
    if state == "preview":                                     # the open preview still confirms
        app.window.press_target(T1)
        assert app.sink.timings and app.sink.timings[-1]["action"] == "compare_air_quality"
    app.close()
    app.root.close()


def test_long_eye_closure_calls_for_help_only_outside_confirm_and_only_when_enabled(qapp):
    now = [0.0]
    app, spk = make()
    hc = app.helpcall
    hc.clock = lambda: now[0]
    app.ask()

    def hold(seconds):
        for _ in range(int(seconds * 10) + 1):
            hc.feed_eyes(1.0)
            now[0] += 0.1

    hold(5)
    assert app.sink.help_calls == []                           # off unless --help-by-eyes
    hc.eyes_enabled = True
    hold(2.5)
    assert app.sink.help_calls == []                           # needs 3 s past a full ring
    hc.feed_eyes(0.4)
    hold(3.2)
    assert len(app.sink.help_calls) == 1
    assert app.sink.help_calls[0]["source"] == "Keyboard (long eye closure)"
    now[0] += 20
    app.window.press_target(T2)                                # Confirm round: a confirm, never help
    hold(10)
    assert len(app.sink.help_calls) == 1
    app.close()


def test_no_false_help_triggers_in_key_fuzz_and_a_simulated_run(qapp):
    rng = random.Random(197)
    app, spk = make()
    app.ask()
    keys = [Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_Escape, Qt.Key.Key_H, Qt.Key.Key_D]
    for _ in range(400):
        k = rng.choice(keys)
        key(app.root, k, press=True)
        if rng.random() < 0.3:
            pump(qapp, timeout=0.01)
        key(app.root, k, press=False)                          # every press is a short tap
        if app.handler.current is None:
            app.ask()
    pump(qapp, timeout=0.2)
    assert app.sink.help_calls == []
    app.close()
    sim, sspk = make(InputSources.SIMULATED, sim_script=[2, 1], confirm_delay_ms=200)
    sim.window.flasher.repetitions = 2
    sim.ask()
    pump(qapp, lambda: bool(sim.sink.timings), timeout=8)
    assert sim.sink.timings and sim.sink.help_calls == []
    sim.close()


# ── #196 practice round ──────────────────────────────────────
def test_practice_round_flashes_says_practice_throughout_and_sends_nothing(qapp):
    app, spk = make(practice_s=0.4)
    app.practice.ready_ms = 100
    app.practice.flasher.repetitions = 2
    app.ask()
    prompts = []
    orig = app.practice._flashed

    def on_flash(t):
        orig(t)
        prompts.append((app.window.prompt.text(), app.window.round_label.text(), app.handler.current))
    app.practice.flasher.on_flash = on_flash
    assert app.start_practice()
    assert app.conversation.entries[-1][0] == "options"       # no "cleared" line for practice
    for k in (T1, T2, T1):                                     # keys can't pick anything
        app.window.press_target(k)
    pump(qapp, lambda: app.practice.ready, timeout=8)
    assert prompts and all(p.startswith("Practice") and r == "Round: practice" and c is None
                           for p, r, c in prompts)
    assert app.practice.target_flashes == sum(1 for _ in prompts) // 2 > 0
    assert "Ready" in app.window.prompt.text()
    pump(qapp, lambda: app.handler.current is not None, timeout=3)
    assert app.handler.current.kind is RoundKind.CHOOSE        # then the first real question
    assert spk.said == [] and app.sink.timings == []
    assert "| 0 | 0 | 0 | 0 | 0 |" in app.report_text() and "**Practice rounds:** 1" in app.report_text()
    app.close()


def test_esc_ends_practice_early_and_practice_waits_for_an_open_preview(qapp):
    app, spk = make(practice_s=30)
    app.ask()
    app.window.press_target(T2)
    assert not app.start_practice()                            # finish or cancel the preview first
    app.window.press_cancel()
    assert app.start_practice() and app.practicing
    app.window.press_cancel()                                  # Esc
    assert not app.practicing and app.handler.current.kind is RoundKind.CHOOSE
    app.close()


def test_practice_does_not_use_up_the_simulated_script(qapp):
    app, spk = make(InputSources.SIMULATED, sim_script=[2, 1], practice_s=0.2)
    app.practice.flasher.repetitions = 1
    app.practice.ready_ms = 50
    script = list(getattr(app.sim, "script", []))
    assert app.start_practice()
    pump(qapp, lambda: not app.practicing, timeout=5)
    if hasattr(app.sim, "script"):
        assert app.sim.script == script
    assert app.sink.timings == []
    app.close()


# ── #193 attract mode ────────────────────────────────────────
def demo_factory(speakers):
    def make_demo():
        spk = Speaker()
        speakers.append(spk)
        demo = App(InputSources.SIMULATED, speaker=spk, view=PlainView(), echo=False,
                   sim_script=[2, 1], reopen_ms=200, reveal_ms=200, confirm_delay_ms=200)
        demo.window.flasher.repetitions = 2
        return demo
    return make_demo


def test_attract_loops_a_labelled_simulated_demo_and_stays_out_of_the_report(qapp):
    from signal2speech.attract import AttractMode
    app, spk = make()
    app.root.show()
    app.ask()
    speakers = []
    mode = app.attract = AttractMode(app, make_demo=demo_factory(speakers))
    mode.start()
    frames = []
    rounds = []
    mode.demo.handler.on_round_opened.append(lambda r: rounds.append(r.kind))

    def sample():
        frames.append((mode.banner.isVisibleTo(app.root), mode.banner.text(),
                       mode.demo.window.input_label.text()))
        return rounds.count(RoundKind.CHOOSE) >= 1 and speakers[0].said
    pump(qapp, sample, timeout=10)
    pump(qapp, lambda: sample() and False, timeout=0.6)         # into the next loop
    assert speakers[0].said, "the loop's confirm should speak"
    assert all(v and "SIMULATED" in b and t == "Input: Simulated" for v, b, t in frames)
    assert app.sink.timings == [] and spk.said == []          # main session untouched
    assert "| 0 | 0 | 0 | 0 | 0 |" in app.report_text()
    assert "**Attract-mode loops:** 1" in app.report_text()
    mode.stop("test")
    app.close()
    app.root.close()


def test_a_key_mid_loop_stops_attract_with_no_output(qapp):
    from signal2speech.attract import AttractMode
    app, spk = make()
    app.root.show()
    app.ask()
    entries = len(app.conversation.entries)
    speakers = []
    mode = app.attract = AttractMode(app, make_demo=demo_factory(speakers))
    mode.start()
    demo = mode.demo
    pump(qapp, lambda: demo.handler.current is not None
         and demo.handler.current.kind is RoundKind.CONFIRM, timeout=10)
    assert demo.handler.current.kind is RoundKind.CONFIRM       # the ring is filling
    key(app.root, Qt.Key.Key_1, press=True)                    # any key
    assert not mode.active and mode.stops == ["key"] and mode.overlay is None
    key(app.root, Qt.Key.Key_1, press=False)
    pump(qapp, timeout=1.0)                                    # past the ring and cue delays
    assert [s for s, _ in speakers[0].said if s != "<stop>"] == []   # nothing from the loop
    assert app.handler.current.kind is RoundKind.CHOOSE and app.handler.pending is None
    assert app.sink.timings == [] and len(app.conversation.entries) == entries
    app.close()
    app.root.close()


def test_attract_starts_after_idle_but_not_over_an_open_preview(qapp):
    from signal2speech.attract import AttractMode
    app, spk = make()
    app.root.show()
    app.ask()
    app.window.press_target(T2)                                # preview open
    speakers = []
    mode = app.attract = AttractMode(app, idle_ms=100, make_demo=demo_factory(speakers))
    mode.poke()
    pump(qapp, timeout=0.4)
    assert not mode.active
    app.window.press_cancel()
    app.ask()
    pump(qapp, lambda: mode.active, timeout=2)
    assert mode.active
    app.handler.on_handled[-1](None, Outcome.Previewed)       # main input wakes it
    assert not mode.active and mode.stops == ["input"]
    mode.enabled = False
    app.close()
    app.root.close()


# ── #194 reply language ──────────────────────────────────────
def test_system_prompt_asks_for_the_reply_language():
    from signal2speech.ai.replies import system_prompt, language_code
    en, es = system_prompt(None), system_prompt(None, "es")
    assert "plain spoken English" in en and "Spanish" not in en
    assert "Write both replies in plain spoken Spanish" in es and es == system_prompt(None, "es")
    assert language_code("Spanish") == language_code("ES") == "es"
    with pytest.raises(ValueError):
        language_code("Klingon")


def test_claude_gets_the_language_in_its_system_prompt():
    pytest.importorskip("anthropic")
    from signal2speech.ai import ClaudeProvider

    class Block:
        type, text = "text", '{"reply_a": "Sí.", "action_a": "speak_reply", "reply_b": "No.", "action_b": "speak_reply"}'

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

    p = ClaudeProvider("sk-test", client=Client(), language="es")
    p.replies("¿Quieres caminar?")
    assert "plain spoken Spanish" in seen["system"]


def test_offline_replies_switch_language_or_say_they_are_english_only():
    from signal2speech.ai.replies import ReplySuggester, StubProvider
    s = ReplySuggester(StubProvider())
    assert s.set_language("es") == ""
    assert s.suggest("¿Vamos?").texts == ["Sí, me parece bien.", "No, prefiero que no."]
    assert s.saved.current().texts == ["Sí.", "No."]
    note = s.set_language("fr")
    assert "Stub replies are English only" in note and "saved phrases are English only" in note
    assert "English only" in s.saved.current().note
    s.set_language("en")
    assert s.saved.current().texts == ["Yes.", "No."] and s.saved.current().note == ""


def test_ai_demo_speaks_replies_in_the_chosen_language(qapp):
    from signal2speech.ai.__main__ import AnsweringDemo
    from signal2speech.ai.replies import StubProvider
    spk = Speaker(voices=("en", "es"))
    demo = AnsweringDemo(provider=StubProvider(), provider_note="Stub", speaker=spk,
                         view=PlainView(), echo=False, reply_language="es")
    demo.start()
    assert spk.language == "es" and demo.suggester.language == "es"
    assert [c.label for c in demo.app.choices] == ["Sí.", "No."]
    assert "Reply language: Spanish" in demo.panel.language.text()
    assert demo.app.help_text == "Necesito ayuda, por favor." and not demo.app.help_english
    demo.app.window.press_target(T1)
    demo.app.window.press_target(T1)
    assert spk.said[-1] == ("Sí.", "speak_reply")
    demo.toggle_language()
    assert spk.language == "en" and [c.label for c in demo.app.choices] == ["Yes.", "No."]
    demo.app.close()


def test_ai_demo_without_the_voice_says_so_and_stays_english(qapp):
    from signal2speech.ai.__main__ import AnsweringDemo
    from signal2speech.ai.replies import StubProvider
    spk = Speaker(voices=("en",))
    demo = AnsweringDemo(provider=StubProvider(), provider_note="Stub", speaker=spk,
                         view=PlainView(), echo=False, reply_language="es")
    demo.start()
    assert demo.language == "en" and spk.language == "en"
    notes = [t for k, t, _ in demo.app.conversation.entries if k == "note"]
    assert notes == ["No Spanish voice is installed, so replies stay in English."]
    assert [c.label for c in demo.app.choices] == ["Yes.", "No."]
    demo.app.close()


def test_os_voice_reads_replies_in_the_language_and_english_lines_in_english(qapp):
    from signal2speech.speech import OfflineSpeaker
    from signal2speech.speech.speaker import ENGLISH_LINE

    class TTS:
        def __init__(self):
            self.loc = QLocale("en_US")
            self.spoken = []

        def availableLocales(self):
            return [QLocale("en_US"), QLocale("es_MX")]

        def locale(self):
            return self.loc

        def setLocale(self, loc):
            self.loc = loc

        def say(self, text):
            self.spoken.append((text, self.loc.name()))

        def stop(self):
            pass

    s = OfflineSpeaker(lambda _m: None, use_qt_tts=False)
    s.tts, s._default_locale, s.backend = TTS(), QLocale("en_US"), "fake"
    assert not s.set_language("de")
    assert s.set_language("es")
    s.say("Sí, gracias.")
    s.say("I need help, please.", ENGLISH_LINE)
    assert s.tts.spoken == [("Sí, gracias.", "es_MX"), ("I need help, please.", "en_US")]
