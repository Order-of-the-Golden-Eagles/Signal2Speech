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
from .replies import TIMEOUT_S, ReplySet, ReplySuggester, make_provider


class AnsweringDemo:
    def __init__(self, input_source: str = InputSources.KEYBOARD, provider_kind: str = "auto", *,
                 provider=None, provider_note: Optional[str] = None, speaker=None, view=None,
                 mute: bool = False, echo: bool = True, deadline_s: float = TIMEOUT_S + 1):
        if provider is None and provider_note is None:
            provider, provider_note = make_provider(provider_kind)
        self.provider_note = provider_note or ""
        # view=None gives the real OpenOrbit view, so map suggestions (#106) reveal the map.
        self.app = App(input_source, view=view, speaker=speaker, mute=mute, echo=echo)
        self.suggester = ReplySuggester(provider)
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

    def start(self) -> None:
        self._show(self.suggester.saved.current("waiting for a question"))

    def ask(self, question: str) -> None:
        self.question = question
        self.app.log(f"question: \"{question}\"")
        self._request(())

    def alternatives(self) -> None:
        if self.question:
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
        self.app.ask()

    def _after_handled(self, _e, outcome: Outcome) -> None:
        if outcome is Outcome.Confirmed:
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
    p.add_argument("--deadline", type=float, default=TIMEOUT_S + 1,
                   help="seconds before falling back to saved phrases")
    p.add_argument("--screenshot", type=Path, help="save a PNG after --keys (or replies) and exit")
    args = p.parse_args(argv)

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        provider, note = make_provider(args.provider)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    demo = AnsweringDemo(args.input, provider=provider, provider_note=note, mute=args.mute,
                         deadline_s=args.deadline)
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
