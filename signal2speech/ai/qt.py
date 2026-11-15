"""Qt glue for reply suggestions (#27, #28): a non-blocking request with a hard deadline,
and the judge-side question panel."""
from __future__ import annotations

import threading
from typing import Optional, Sequence

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .replies import CLAUDE, SAVED, STUB, TIMEOUT_S, ReplySet, ReplySuggester


class AsyncSuggester(QObject):
    """Runs ReplySuggester.suggest on a worker thread and emits `ready` on the Qt main thread.

    A hard deadline falls back to saved phrases. Only the newest request can deliver, and only
    once, so a late provider answer can never replace the choices on screen.
    """

    ready = Signal(object)          # ReplySet
    _done = Signal(int, object)     # worker -> main thread (queued)

    def __init__(self, suggester: ReplySuggester, deadline_s: float = TIMEOUT_S + 1,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.suggester = suggester
        self._gen = 0
        self._resolved = True
        self._deadline = QTimer(self, singleShot=True, interval=int(deadline_s * 1000))
        self._deadline.timeout.connect(self._on_deadline)
        self._done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)

    @property
    def pending(self) -> bool:
        return not self._resolved

    def request(self, question: str, avoid: Sequence[str] = ()) -> None:
        self._gen += 1
        gen, self._resolved = self._gen, False
        self._deadline.start()
        threading.Thread(target=lambda: self._done.emit(gen, self.suggester.suggest(question, avoid)),
                         daemon=True).start()

    def _on_done(self, gen: int, result: ReplySet) -> None:
        if gen != self._gen or self._resolved:
            return                      # stale or already timed out: ignore
        self._resolve(result)

    def _on_deadline(self) -> None:
        if not self._resolved:
            secs = self._deadline.interval() / 1000
            self._resolve(self.suggester.saved.current(f"timeout after {secs:g} s"))

    def _resolve(self, result: ReplySet) -> None:
        self._resolved = True
        self._deadline.stop()
        self.ready.emit(result)


from signal2speech.ui import theme as T  # noqa: E402  (#174: one visual design)

_ORIGIN_COLORS = {CLAUDE: T.ORIGIN_COLORS['Claude'], STUB: T.ORIGIN_COLORS['Stub'],
                  SAVED: T.ORIGIN_COLORS['Saved phrases']}


class QuestionPanel(QWidget):
    """Judge side: type a question, ask for other replies, or switch to saved phrases."""

    ask_requested = Signal(str)
    alternatives_requested = Signal()
    saved_requested = Signal()
    nasa_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("Ask a question")
        col.addWidget(self.title)
        self.title.setVisible(False)           # the box says it; the height goes to the replies
        self.restyle()
        self.question = QLineEdit(placeholderText="Ask a question: type it here, then press Enter")
        row = QHBoxLayout()                    # the question and its buttons share one row
        row.addWidget(self.question, 1)
        self.ask_btn = QPushButton("Suggest replies")
        self.alt_btn = QPushButton("Other replies")
        self.saved_btn = QPushButton("Saved phrases")
        self.nasa_btn = QPushButton("Example: NASA air quality")
        self.nasa_btn.setToolTip("Ask the built-in question about wildfire smoke, answered with "
                                 "NASA satellite images and EPA data")
        for b in (self.ask_btn, self.alt_btn, self.saved_btn, self.nasa_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(b)
        col.addLayout(row)
        notes = QHBoxLayout()                  # one line: where the replies come from, and the language
        self.origin = QLabel()
        self.origin.setWordWrap(True)
        notes.addWidget(self.origin, 3)
        self.language = QLabel("Reply language: English")   # #194
        self.language.setWordWrap(True)
        self.language.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        notes.addWidget(self.language, 2)
        col.addLayout(notes)
        self.alt_btn.setEnabled(False)

        self.question.returnPressed.connect(self._ask)
        self.ask_btn.clicked.connect(self._ask)
        self.alt_btn.clicked.connect(self.alternatives_requested)
        self.saved_btn.clicked.connect(self.saved_requested)
        self.nasa_btn.clicked.connect(self.nasa_requested)

    def restyle(self) -> None:
        """Apply the current text scale (#195)."""
        self.setStyleSheet(
            f"QLabel{{color:{T.STRIP_TEXT};font-size:{T.px(T.CAPTION + 2)}px;}}"
            f"QLineEdit{{background:{T.SURFACE};color:{T.TEXT};font-size:{T.px(T.HEADING + 2)}px;"
            f"padding:{T.S + 4}px {T.M}px;border:2px solid {T.ACCENT};border-radius:{T.RADIUS_M}px;}}"
            f"QPushButton{{background:{T.RAISED};color:{T.TEXT};font-size:{T.px(T.CAPTION)}px;"
            f"padding:{T.S}px {T.M}px;border:2px solid {T.BORDER};border-radius:{T.RADIUS_S}px;}}"
            f"QPushButton:disabled{{color:{T.QUIET};}}")
        self.title.setStyleSheet(f"color:{T.TEXT};font-size:{T.px(T.HEADING)}px;font-weight:700;")

    def _ask(self) -> None:
        text = self.question.text().strip()
        if text:
            self.question.clearFocus()   # hand keys 1/2/Esc back to the selection window
            self.ask_requested.emit(text)

    def set_busy(self, busy: bool, provider_note: str = "") -> None:
        for b in (self.ask_btn, self.alt_btn):
            b.setEnabled(not busy and (b is self.ask_btn or bool(self.question.text().strip())))
        if busy:
            self.origin.setText(f"Asking {provider_note}… current choices stay on screen")

    def show_origin(self, rs: ReplySet) -> None:
        color = _ORIGIN_COLORS.get(rs.origin, T.STRIP_TEXT)
        note = f" · {rs.note}" if rs.note else ""
        self.origin.setText(f"<span style='color:{color};font-weight:700'>Replies: {rs.origin}"
                            f"</span>{note}")

    def set_language(self, text: str) -> None:
        self.language.setText(text)
