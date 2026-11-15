"""One entry point for judges and teammates (#136).

    python -m signal2speech                 # a small window with a button per tool
    python -m signal2speech --help          # the same list, in the terminal
    python -m signal2speech demo-keyboard   # run one tool directly, no window

Each tool runs as its own process with this same Python, so a crash in one can't take down the
launcher. Buttons say which input they use, and a tool whose dependency is missing is grayed out
with the reason.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Tool:
    key: str
    title: str
    what: str
    args: List[str]
    needs: Optional[str] = None          # module that must be importable
    fullscreen_ok: bool = False
    inline: bool = False                 # run inside the launcher and show the output

    def command(self, fullscreen: bool = False, python: str = sys.executable) -> List[str]:
        extra = ["--fullscreen"] if fullscreen and self.fullscreen_ok else []
        return [python, *self.args, *extra]


TOOLS: List[Tool] = [
    Tool("ai", "Signal2Speech · Keyboard", "The main app. Ask any question, pick a suggested reply, preview it, "
         "confirm it, and it is spoken. The NASA example is one click inside.",
         ["-m", "signal2speech.ai"]),
    Tool("demo-keyboard", "NASA example · Keyboard", "Choose, preview, and confirm with keys 1 and 2. The map and voice answer.",
         ["-m", "signal2speech.app", "--input", "keyboard"], fullscreen_ok=True),
    Tool("demo-simulated", "NASA example · Simulated", "The same flow driven by simulated brain signals (g.Pype if installed, otherwise scripted).",
         ["-m", "signal2speech.app", "--input", "simulated", "--sim", "2,1"], fullscreen_ok=True),
    Tool("evidence", "Evidence view · Simulated", "g.Pype scopes: raw and filtered EEG, OSCAR, and the averaged P300.",
         ["-m", "signal2speech.evidence", "--source", "generator"], needs="gpype"),
    Tool("smoke", "Smoke check", "A hardware-free check of the whole demo. Shows PASS or FAIL here.",
         ["-m", "signal2speech.app", "--smoke"], inline=True),
]
BY_KEY = {t.key: t for t in TOOLS}


def missing(tool: Tool, find_spec: Callable = importlib.util.find_spec) -> Optional[str]:
    """Why this tool can't run here, or None."""
    if tool.needs and find_spec(tool.needs) is None:
        return f"needs {tool.needs}: pip install -r requirements-lock.txt"
    return None


def tool_list() -> str:
    width = max(len(t.key) for t in TOOLS)
    return "\n".join(f"  {t.key:<{width}}  {t.title}: {t.what}" for t in TOOLS)


def run_window(spawn: Optional[Callable[[List[str]], object]] = None,
               find_spec: Callable = importlib.util.find_spec):
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtWidgets import (QApplication, QCheckBox, QLabel, QPlainTextEdit, QPushButton,
                                   QVBoxLayout, QWidget)
    from signal2speech.ui import theme as P

    QApplication.instance() or QApplication(sys.argv[:1])

    def detached(cmd: List[str]) -> object:
        return QProcess.startDetached(cmd[0], cmd[1:], str(ROOT))

    spawn = spawn or detached
    win = QWidget()
    win.setWindowTitle("Signal2Speech")
    win.setStyleSheet(f"QWidget {{ background: {P.BG}; color: {P.TEXT}; font-size: {P.CAPTION}px; }}"
                      f"QPushButton {{ background: {P.RAISED}; color: {P.TILE_TEXT}; font-size: {P.BODY + 2}px;"
                      f" font-weight: 700; padding: 14px; border: 2px solid {P.TILE_BORDER}; border-radius: 12px; text-align: left; }}"
                      f"QPushButton:disabled {{ color: {P.QUIET}; }}"
                      f"QLabel#what {{ color: {P.MUTED}; padding: 0 0 10px 6px; }}"
                      f"QPlainTextEdit {{ background: {P.STRIP_BG}; color: {P.STRIP_TEXT};"
                      f" font-family: {P.MONO}; font-size: 14px; }}")
    col = QVBoxLayout(win)
    head = QLabel("Signal2Speech")
    head.setStyleSheet(f"font-size: {P.TITLE}px; font-weight: 700;")
    col.addWidget(head)
    sub = QLabel("Answer without speaking or typing. Pick a tool:")
    sub.setStyleSheet(f"color: {P.MUTED}; padding-bottom: 8px;")
    col.addWidget(sub)
    full = QCheckBox("Start demos fullscreen (F11 to leave)")
    col.addWidget(full)
    status = QLabel("")
    output = QPlainTextEdit(readOnly=True)
    output.setVisible(False)
    win.buttons = {}
    win.status, win.output, win.fullscreen_box = status, output, full
    win.smoke = None

    def launch(tool: Tool) -> None:
        cmd = tool.command(fullscreen=full.isChecked())
        if tool.inline:
            output.setVisible(True)
            output.setPlainText(f"$ {' '.join(cmd[1:])}\n")
            status.setText(f"{tool.title}: running…")
            proc = QProcess(win)
            proc.setWorkingDirectory(str(ROOT))
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.readyReadStandardOutput.connect(
                lambda: output.appendPlainText(bytes(proc.readAllStandardOutput()).decode(errors="replace").rstrip()))
            proc.finished.connect(lambda code, _s: status.setText(
                f"{tool.title}: {'PASS' if code == 0 else f'FAIL (exit {code})'}"))
            win.smoke = proc
            proc.start(cmd[0], cmd[1:])
            return
        ok = spawn(cmd)
        status.setText(f"Started: {tool.title}" if ok is not False else f"Couldn't start {tool.title}")

    for tool in TOOLS:
        btn = QPushButton(tool.title)
        why = missing(tool, find_spec)
        what = QLabel(tool.what if not why else f"{tool.what}  Unavailable here: {why}.", objectName="what")
        what.setWordWrap(True)
        btn.setEnabled(why is None)
        btn.setToolTip(" ".join(tool.command()[1:]))
        btn.clicked.connect(lambda _=False, t=tool: launch(t))
        col.addWidget(btn)
        col.addWidget(what)
        win.buttons[tool.key] = btn
    col.addWidget(status)
    col.addWidget(output, 1)
    win.resize(760, 720)
    return win


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m signal2speech", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Open the Signal2Speech launcher, or run one tool directly.",
        epilog="tools:\n" + tool_list())
    p.add_argument("tool", nargs="?", choices=list(BY_KEY), help="run this tool directly, no window")
    p.add_argument("--fullscreen", action="store_true", help="start demos fullscreen")
    args = p.parse_args(argv)
    if args.tool:
        tool = BY_KEY[args.tool]
        why = missing(tool)
        if why:
            print(f"{tool.title} is unavailable: {why}", file=sys.stderr)
            return 2
        return subprocess.call(tool.command(fullscreen=args.fullscreen), cwd=str(ROOT))
    from PySide6.QtWidgets import QApplication
    win = run_window()
    win.fullscreen_box.setChecked(args.fullscreen)
    win.show()
    return QApplication.instance().exec()


if __name__ == "__main__":
    sys.exit(main())
