"""Repo-wide pytest setup, loaded before any test directory's own conftest."""
import os
import sys

# Qt's offscreen test display finds no fonts on some Windows machines (the judging laptop, #200).
# With none, text is measured with a placeholder font and every size test fails. Point it at the
# system fonts. This must happen before the first QApplication is created.
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
