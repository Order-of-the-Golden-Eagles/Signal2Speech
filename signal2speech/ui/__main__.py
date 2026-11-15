"""Standalone keyboard run of the selection UI (#24).

    python -m signal2speech.ui [--flash] [--keys 2] [--screenshot out.png]

The sink here only prints the ConfirmedAction. No audio, no map: output belongs to #25.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from signal2speech.core import (Choice, ConfirmedAction, InputAdapter, InputSources, Outcome,
                                SelectionHandler, TargetIds)

from .window import SelectionWindow

DEMO_ROUND = Path(__file__).resolve().parents[2] / "contracts" / "demo-round.json"


class PrintSink:
    """Stand-in for #25. Logs the confirmed action; never speaks or changes the map."""

    def execute(self, action: ConfirmedAction) -> None:
        print(f"[sink stub] {action}", flush=True)


#: The conversation partner's question for the OpenOrbit demo (#178). Shown above the tiles.
DEMO_QUESTION = "Which county's AQI rose more when wildfire smoke reached southeast Michigan?"


def load_demo_choices(path: Path = DEMO_ROUND):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Choice(c["targetId"], c["actionId"], c["label"], c.get("spokenText"))
            for c in data["choices"]]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m signal2speech.ui")
    p.add_argument("--flash", action="store_true", help="flash tiles in Choose rounds (P300)")
    p.add_argument("--keys", default="", help="keys to press after start, e.g. '2' or '2,1'")
    p.add_argument("--screenshot", type=Path, help="save a PNG after --keys and exit")
    args = p.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    handler = SelectionHandler(PrintSink())
    keyboard = InputAdapter(handler, InputSources.KEYBOARD)
    win = SelectionWindow(handler, keyboard, flash=args.flash,
                          on_flash=lambda t: print(f"[flash] {t}", flush=True) if args.flash else None)
    choices = load_demo_choices()

    # Demo driver (stands in for app.py, #25): reopen the question after confirm or cancel.
    reopen = QTimer(win, singleShot=True, interval=1500)
    reopen.timeout.connect(lambda: handler.begin_choice_round(choices))
    handler.on_cleared.append(lambda _reason: reopen.start())
    handler.on_handled.append(lambda _e, o: reopen.start() if o is Outcome.Confirmed else None)

    win.show()
    handler.begin_choice_round(choices)
    keymap = {"1": TargetIds.TARGET_1, "2": TargetIds.TARGET_2}
    for k in filter(None, (s.strip() for s in args.keys.split(","))):
        win.press_cancel() if k.lower() == "esc" else win.press_target(keymap[k])

    if args.screenshot:
        app.processEvents()
        win.grab().save(str(args.screenshot))
        print(f"saved {args.screenshot}")
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
