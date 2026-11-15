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
                 mute: bool = False, echo: bool = True, deadline_s: float = TIMEOUT_S + 1):
        if provider is None and provider_note is None:
            provider, provider_note = make_provider(provider_kind)
        self.provider_note = provider_note or ""
        # view=None gives the real OpenOrbit view, so map suggestions (#106) reveal the map.
        # No demo question here: the partner types theirs (#178).
        self.app = App(input_source, view=view, speaker=speaker, mute=mute, echo=echo, cues=cues,
                       question="")
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
        self.root.resize(1700, 1000)

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

    def start(self) -> None:
        self._show(self.suggester.saved.current("waiting for a question"))

    def ask(self, question: str) -> None:
        self.question = question
        self.app.add_question(question)
        self.app.log(f"question: \"{question}\"")
        self._request(())

    def alternatives(self) -> None:
        if self.question:
            avoid = self.current.texts if self.current and self.current.origin != "Saved phrases" else ()
            self.app.log("judge: other replies")
            self._request(avoid)

    def saved(self) -> None:
        self.app.log("judge: saved phrases")
        self.app.window.question = ""                 # saved phrases answer no particular question
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
        self.app.ask()

    def _after_handled(self, _e, outcome: Outcome) -> None:
        if outcome is Outcome.Confirmed:
            self.app.window.question = ""             # answered: the next round is saved phrases
            rs = self.suggester.saved.current("after confirm")
            self.current = rs
            self.panel.show_origin(rs)
            self.app.choices = list(rs.choices)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.ai")
    p.add_argument("--input", default="keyboard", choices=["keyboard", "simulated"])
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
    demo = AnsweringDemo(args.input, provider=provider, provider_note=note, mute=args.mute, cues=not args.no_cues,
                         reply_language=reply_language, deadline_s=args.deadline)
    demo.root.show()
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
