"""AI Answering demo (#5): typed question -> two reply tiles -> preview -> confirm -> spoken once.

    python -m signal2speech.ai [--provider auto|claude|stub|slow-stub|saved] [--question "..."]

Reuses the #4 App (same handler, adapters, sink, transcript, and the real OpenOrbit view).
A confirmed speak_reply is spoken once with no map change. A confirmed map suggestion
(show_satellite or compare_air_quality, #106) reveals the map and speaks its line once, the
same as in `python -m signal2speech.app`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from signal2speech.app import App
from signal2speech.core import InputSources, Outcome, TargetIds

from .qt import AsyncSuggester, QuestionPanel
from .replies import (HELP_PHRASES, TIMEOUT_S, ReplySet, ReplySuggester, language_code,
                      language_name, make_provider, saved_phrases_from_file)


class AnsweringDemo:
    def __init__(self, input_source: str = InputSources.KEYBOARD, provider_kind: str = "auto", *,
                 provider=None, provider_note: Optional[str] = None, speaker=None, view=None,
                 cues: bool = False, reply_language: str = "en",
                 mute: bool = False, echo: bool = True, deadline_s: float = TIMEOUT_S + 1,
                 recording=None):
        if provider is None and provider_note is None:
            provider, provider_note = make_provider(provider_kind)
        self.provider_note = provider_note or ""
        # view=None gives the real OpenOrbit view, so map suggestions (#106) reveal the map.
        self.app = App(input_source, view=view, speaker=speaker, mute=mute, echo=echo, cues=cues,
                       recording=recording)
        # Recorded brain data (#104): it answers only a question that was asked. Which reply the
        # scripted wearer attends alternates, or the operator sets it with Ctrl+1 / Ctrl+2.
        self.recorded = input_source == InputSources.RECORDED
        self.next_pick = 1
        self._asked = False
        if self.recorded:
            self.app.sim.script.clear()
            self.app.sim.idle_hint = "Type a question above. The recorded brain data will answer it."
        self.suggester = ReplySuggester(provider, saved_phrases_from_file())   # #134
        self.async_ = AsyncSuggester(self.suggester, deadline_s, parent=self.app.window)
        self.panel = QuestionPanel()
        self.question = ""
        self.current: Optional[ReplySet] = None

        self.root = QWidget()
        self.root.setWindowTitle("Signal2Speech · AI Answering")
        self.root.setStyleSheet("background:#0b0d10;")
        col = QVBoxLayout(self.root)
        col.setContentsMargins(16, 12, 0, 0)
        col.addWidget(self.panel)
        col.addWidget(self.app.root, 1)
        from signal2speech.app import fit_to_screen
        fit_to_screen(self.root, (1700, 1000))            # never larger than the screen it is on

        self.panel.ask_requested.connect(self.ask)
        self.panel.alternatives_requested.connect(self.alternatives)
        self.panel.saved_requested.connect(self.saved)
        self.async_.ready.connect(self._show)
        # After a confirm the app reopens a round: offer saved phrases, not the spoken pair.
        self.app.handler.on_handled.append(self._after_handled)
        self.app.log(f"replies provider: {self.provider_note}")
        self.app.log(f"saved phrases: {self.suggester.saved.source}")
        # #194: F3 switches between English and the chosen reply language.
        self.language = "en"
        self.other_language = reply_language if reply_language != "en" else "es"
        if reply_language != "en":
            self.set_language(reply_language)
        else:
            self._label_language()
        from PySide6.QtGui import QKeySequence, QShortcut
        sc = QShortcut(QKeySequence("F3"), self.root)
        sc.setAutoRepeat(False)
        sc.activated.connect(self.toggle_language)
        if self.recorded:
            for n in (1, 2):
                pick = QShortcut(QKeySequence(f"Ctrl+{n}"), self.root)
                pick.setAutoRepeat(False)
                pick.activated.connect(lambda n=n: self.attend(n))
            self.app.help.rows.insert(-1, ("Ctrl+1 / Ctrl+2", "Which reply the scripted wearer looks at next"))
        self.app.help.rows.insert(-1, ("F3", f"Replies in English or {language_name(self.other_language)}"))
        self.app.help.restyle()
        self.app.on_text_scale.append(self.panel.restyle)

    def set_language(self, code: str) -> bool:
        """Switch the reply language (#194). Checks the OS voice first: with no voice for the
        language it says so and stays in English, so a reply is never read in the wrong accent."""
        speaker = self.app.speaker
        has_voice = speaker.set_language(code) if hasattr(speaker, "set_language") else code == "en"
        if not has_voice:
            msg = f"No {language_name(code)} voice is installed, so replies stay in English."
            self.app.log(f"reply language: {msg}")
            self.app.conversation.add("note", msg)
            if hasattr(speaker, "set_language"):
                speaker.set_language("en")
            code = "en"
        note = self.suggester.set_language(code)
        self.language = code
        self.app.help_text = HELP_PHRASES.get(code, HELP_PHRASES["en"])
        self.app.help_english = code not in HELP_PHRASES or code == "en"
        self.app.log(f"reply language: {language_name(code)}" + (f" ({note})" if note else ""))
        self._label_language(note if has_voice else f"no {language_name(self.other_language)} voice installed")
        return has_voice

    def toggle_language(self) -> None:
        self.set_language(self.other_language if self.language == "en" else "en")
        if not self.async_.pending:            # show the offline replies in the new language now
            if self.question:
                self._request(())
            else:
                self._show(self.suggester.saved.current("language changed"))

    def _label_language(self, note: str = "") -> None:
        other = language_name("en" if self.language != "en" else self.other_language)
        self.panel.set_language(f"Reply language: {language_name(self.language)}"
                                + (f" ({note})" if note else "") + f"   ·   F3: {other}")

    def attend(self, n: int) -> None:
        """Recorded input: the reply (1 or 2) the scripted wearer will look at for the next question."""
        self.next_pick = n
        self.app.log(f"walkthrough: for the next question the wearer looks at reply {n}")

    def start(self) -> None:
        self._show(self.suggester.saved.current("waiting for a question"))

    def ask(self, question: str) -> None:
        self._asked = True
        self.question = question
        self.app.add_question(question)
        self.app.log(f"question: \"{question}\"")
        self._request(())

    def alternatives(self) -> None:
        if self.question:
            self._asked = True
            avoid = self.current.texts if self.current and self.current.origin != "Saved phrases" else ()
            self.app.log("judge: other replies")
            self._request(avoid)

    def saved(self) -> None:
        self.app.log("judge: saved phrases")
        self._show(self.suggester.saved.next_page("chosen by judge"))

    def _request(self, avoid) -> None:
        self.panel.set_busy(True, self.provider_note)
        self.async_.request(self.question, avoid)

    def _show(self, rs: ReplySet) -> None:
        self.panel.set_busy(False)
        self.current = rs
        self.panel.show_origin(rs)
        note = f" ({rs.note})" if rs.note else ""
        self.app.log(f"replies from {rs.origin}{note}: " + " | ".join(rs.texts))
        self.app.choices = list(rs.choices)
        self.app.options_origin = rs.origin.lower() if rs.origin != "Claude" else "Claude"
        if self.recorded and self._asked:
            # One scripted look and one confirm for this question, then the script is empty again.
            self._asked = False
            self.app.sim.script.clear()
            self.app.sim.script.extend([self.next_pick, 1])
            self.next_pick = 2 if self.next_pick == 1 else 1
        self.app.ask()

    def _after_handled(self, _e, outcome: Outcome) -> None:
        if outcome is Outcome.Confirmed:
            rs = self.suggester.saved.current("after confirm")
            self.current = rs
            self.panel.show_origin(rs)
            self.app.choices = list(rs.choices)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.ai")
    p.add_argument("--input", default="keyboard", choices=["keyboard", "simulated", "recorded"])
    p.add_argument("--recording", type=Path, default=None,
                   help="--input recorded: a subject file of g.tec's P300 Speller dataset, e.g. S4.mat "
                        "(or set SIGNAL2SPEECH_GTEC). Real recorded responses answer the flashes")
    p.add_argument("--calibration", type=int, default=10,
                   help="--input recorded: calibration sequences before the first question")
    p.add_argument("--provider", default="auto",
                   choices=["auto", "claude", "stub", "slow-stub", "saved"])
    p.add_argument("--question", default="", help="ask this question at start")
    p.add_argument("--keys", default="", help="keys after the replies arrive, e.g. '1,1'")
    p.add_argument("--mute", action="store_true")
    p.add_argument("--no-cues", action="store_true", help="no preview/confirm/cancel sounds")
    p.add_argument("--reply-language", default="en",
                   help="suggest and speak replies in this language, e.g. es or Spanish (#194); F3 switches")
    p.add_argument("--deadline", type=float, default=TIMEOUT_S + 1,
                   help="seconds before falling back to saved phrases")
    p.add_argument("--screenshot", type=Path, help="save a PNG after --keys (or replies) and exit")
    args = p.parse_args(argv)

    try:
        reply_language = language_code(args.reply_language)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        provider, note = make_provider(args.provider)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    recording = None
    if args.input == InputSources.RECORDED:
        import os
        from signal2speech.app import DEFAULT_RECORDING, RECORDING_ENV, RECORDING_HELP
        recording = args.recording or os.environ.get(RECORDING_ENV) or DEFAULT_RECORDING
        if not Path(recording).is_file():
            print(f"No recording at {recording}\n{RECORDING_HELP}", file=sys.stderr)
            return 2
    try:
        demo = AnsweringDemo(args.input, provider=provider, provider_note=note, mute=args.mute,
                             cues=not args.no_cues, reply_language=reply_language,
                             deadline_s=args.deadline, recording=recording)
    except Exception as err:
        if recording is None:
            raise
        print(f"Couldn't set up the recorded pipeline: {type(err).__name__}: {err}", file=sys.stderr)
        return 3
    demo.root.show()
    if hasattr(demo.app.sim, "calibrate"):         # recorded: open the stream and calibrate first
        qapp.aboutToQuit.connect(demo.app.close)
        demo.app.sim.calibration_sequences = args.calibration
        try:
            demo.app.sim.start()
            ok = demo.app.sim.calibrate({TargetIds.TARGET_1: "Reply 1", TargetIds.TARGET_2: "Reply 2"})
        except Exception as err:
            demo.app.close()
            print(f"Calibration failed: {type(err).__name__}: {err}", file=sys.stderr)
            return 1
        if ok is None:                             # the window was closed during calibration
            demo.app.close()
            return 0
    demo.start()

    keymap = {"1": TargetIds.TARGET_1, "2": TargetIds.TARGET_2}
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    def after_replies(_rs=None) -> None:
        for k in keys:
            demo.app.window.press_target(keymap[k])
        if args.screenshot:
            QTimer.singleShot(400, shoot)

    def shoot() -> None:
        demo.root.grab().save(str(args.screenshot))
        print(f"saved {args.screenshot}", flush=True)
        qapp.exit(0)

    if args.screenshot:
        QTimer.singleShot(int((args.deadline + 10) * 1000), shoot)   # never hang
    if args.question:
        once = {"done": False}

        def first(rs) -> None:
            if not once["done"]:
                once["done"] = True
                QTimer.singleShot(0, after_replies)
        demo.async_.ready.connect(first)
        demo.panel.question.setText(args.question)
        demo.ask(args.question)
    elif args.screenshot or keys:
        QTimer.singleShot(0, after_replies)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
