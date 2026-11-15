"""Dev harness for the OpenOrbit view (#30). No EEG and no selection handler: it calls the view
directly so the view can be checked offline. In the app, only #25's sink calls the view.

    python -m signal2speech.openorbit                   # S satellite, C compare, R reset, Q quit
    python -m signal2speech.openorbit --demo            # cycle reset, satellite, compare every 3 s
    python -m signal2speech.openorbit --screenshots DIR # save one PNG per mode, then exit
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .view import OpenOrbitView

BANNER = "DEV HARNESS (no EEG)  ·  S satellite  ·  C compare  ·  R reset  ·  Q quit"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m signal2speech.openorbit", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="cycle the three modes every 3 s")
    parser.add_argument("--screenshots", metavar="DIR", help="save one PNG per mode and exit")
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = QWidget()
    window.setWindowTitle("OpenOrbit view: DEV HARNESS (no EEG)")
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    banner = QLabel(BANNER)
    banner.setStyleSheet("background: #FFD400; color: #000000; padding: 6px 12px;"
                         " font-size: 18px; font-weight: bold;")
    layout.addWidget(banner)
    view = OpenOrbitView()
    layout.addWidget(view, 1)
    window.resize(1280, 800)

    actions = {"S": view.show_satellite, "C": view.compare_air_quality, "R": view.reset, "Q": app.quit}
    for key, action in actions.items():
        QShortcut(QKeySequence(key), window).activated.connect(action)

    if args.screenshots:
        window.setAttribute(Qt.WA_DontShowOnScreen, True)  # render without flashing a window
    window.show()
    if args.screenshots:
        out = Path(args.screenshots)
        out.mkdir(parents=True, exist_ok=True)
        for mode, action in (("blank", view.reset), ("satellite", view.show_satellite),
                             ("compare", view.compare_air_quality)):
            action()
            app.processEvents()
            path = out / f"openorbit_{mode}.png"
            window.grab().save(str(path))
            print(f"saved {path}")
        return 0

    if args.demo:
        cycle = itertools.cycle((view.reset, view.show_satellite, view.compare_air_quality))
        timer = QTimer(window)
        timer.timeout.connect(lambda: next(cycle)())
        timer.start(3000)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
