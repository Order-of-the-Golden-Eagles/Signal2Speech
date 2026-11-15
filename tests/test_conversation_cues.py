"""Readable conversation (#176) and sound cues (#177). Headless, with a fake cue player."""
import os
import time
import wave

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from signal2speech.app import App  # noqa: E402
from signal2speech.core import TargetIds  # noqa: E402
from signal2speech.speech import cues  # noqa: E402

T1, T2 = TargetIds.TARGET_1, TargetIds.TARGET_2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, until, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and not until():
        qapp.processEvents()
        time.sleep(0.005)


class View:
    def show_satellite(self):
        pass

    def compare_air_quality(self):
        pass


class Speaker:
    def __init__(self, log):
        self.log = log

    def say(self, text, clip=None):
        self.log.append(("speech", text))


class FakeCues:
    def __init__(self, log):
        self.log = log

    def play(self, name):
        self.log.append(("cue", name))
        return 30


def make(qapp, **kw):
    order = []
    app = App(view=View(), speaker=Speaker(order), echo=False, reopen_ms=60000, **kw)
    app.sink.cues = FakeCues(order)
    app.ask()
    return app, order


def kinds(app):
    return [(k, src) for k, _t, src in app.conversation.entries]


# ── #176: the conversation ───────────────────────────────────
def test_confirm_reads_as_options_preview_then_shown(qapp):
    app, _ = make(qapp)
    app.window.press_target(T2)
    app.window.press_target(T1)
    assert kinds(app) == [("options", None), ("preview", "Keyboard"), ("shown", "Keyboard")]
    opts, preview, shown = (t for _k, t, _s in app.conversation.entries)
    assert "Compare counties" in opts and "(from the demo script)" in opts
    assert preview == shown == "“Washtenaw's AQI rose 186 points. Wayne's rose 168 points.”"
    assert not any("round r" in t for _k, t, _s in app.conversation.entries)   # no raw log lines


def test_cancel_reads_nothing_was_said_with_its_input(qapp):
    app, _ = make(qapp)
    app.window.press_target(T2)
    app.window.press_target(T2)                                # Cancel
    k, text, src = app.conversation.last()
    assert (k, src) == ("nothing", "Keyboard") and text == "The preview was cancelled."


def test_timeout_reads_no_answer_in_time(qapp):
    app, _ = make(qapp, confirm_timeout_ms=150)
    app.window.press_target(T2)
    pump(qapp, lambda: app.conversation.last()[0] == "nothing")
    assert app.conversation.last()[1] == "No answer in time, so the preview was cancelled."


def test_disconnect_reads_headset_disconnected(qapp):
    app, _ = make(qapp)
    app.window.press_target(T2)
    app.handler.disconnect()
    assert app.conversation.last()[1] == "The headset disconnected, so nothing was said."


def test_spoken_reply_reads_said_aloud(qapp):
    from signal2speech.ai import to_choices
    app, _ = make(qapp)
    app.choices = list(to_choices(["Yes, please.", "No, thanks."]))
    app.options_origin = "Claude"
    app.ask()
    app.window.press_target(T1)
    app.window.press_target(T1)
    assert app.conversation.entries[-1][:2] == ("said", "“Yes, please.”")
    assert "(from Claude)" in app.conversation.entries[-3][1]


def test_f2_swaps_conversation_and_developer_log(qapp):
    app, _ = make(qapp)
    app.root.show()
    assert app.conversation.isVisibleTo(app.root) and not app.transcript_view.isVisibleTo(app.root)
    app.toggle_log()
    assert app.transcript_view.isVisibleTo(app.root) and not app.conversation.isVisibleTo(app.root)
    assert any("round r1 choose" in l for l in app.log.lines)  # the developer log is unchanged
    app.toggle_log()
    assert app.conversation.isVisibleTo(app.root)
    app.root.close()


def test_session_report_has_conversation_and_developer_log(qapp):
    app, _ = make(qapp)
    app.window.press_target(T2)
    app.window.press_target(T1)
    text = app.report_text()
    assert "## Conversation" in text and "**Showed the map and said** (Keyboard)" in text
    assert "## Developer log" in text and "round r1 choose" in text


# ── #177: sounds ─────────────────────────────────────────────
def test_each_event_plays_exactly_one_cue_and_confirm_precedes_speech(qapp):
    app, order = make(qapp)
    app.window.press_target(T2)
    assert order == [("cue", "preview")]
    app.window.press_target(T1)
    assert order[-1] == ("cue", "confirm")                     # speech hasn't started yet
    pump(qapp, lambda: any(o[0] == "speech" for o in order))
    assert [o for o in order if o[0] == "cue"] == [("cue", "preview"), ("cue", "confirm")]
    assert order.index(("cue", "confirm")) < next(i for i, o in enumerate(order) if o[0] == "speech")
    assert sum(1 for o in order if o[0] == "speech") == 1


def test_cancel_and_timeout_play_one_cancel_cue(qapp):
    app, order = make(qapp, confirm_timeout_ms=150)
    app.window.press_target(T2)
    app.window.press_target(T2)
    assert order == [("cue", "preview"), ("cue", "cancel")]
    app.ask()
    app.window.press_target(T1)
    pump(qapp, lambda: order[-1] == ("cue", "cancel") and len(order) == 4)
    assert order[2:] == [("cue", "preview"), ("cue", "cancel")]


def test_no_cues_by_default_or_when_muted(qapp):
    assert App(view=View(), speaker=Speaker([]), echo=False).sink.cues is None
    assert App(view=View(), mute=True, echo=False, cues=True).sink.cues is None


def test_generated_tones_are_short_quiet_and_distinct(tmp_path):
    for name in cues.TONES:
        s = cues.samples(name)
        assert abs(len(s) / cues.RATE * 1000 - cues.duration_ms(name)) < 2
        assert max(abs(v) for v in s) <= int(32767 * cues.VOLUME) + 1
        assert abs(s[0]) < 50 and abs(s[-1]) < 50              # faded: no click
        with wave.open(str(cues.write_wav(name, tmp_path / f"{name}.wav"))) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, cues.RATE)
    assert cues.TONES["confirm"][1] > cues.TONES["confirm"][0]   # rising
    assert cues.TONES["cancel"][1] < cues.TONES["cancel"][0]     # falling
    assert all(cues.duration_ms(n) <= 250 for n in cues.TONES)
