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


_ORIGIN_COLORS = {CLAUDE: "#22c55e", STUB: "#f59e0b", SAVED: "#60a5fa"}


class QuestionPanel(QWidget):
    """Judge side: type a question, ask for other replies, or switch to saved phrases."""

    ask_requested = Signal(str)
    alternatives_requested = Signal()
    saved_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(
            "QLabel{color:#e2e8f0;font-size:20px;}"
            "QLineEdit{background:#151a21;color:#f5f7fa;font-size:22px;padding:8px;"
            "border:2px solid #475569;border-radius:8px;}"
            "QPushButton{background:#1e2630;color:#f5f7fa;font-size:18px;padding:8px 14px;"
            "border:2px solid #475569;border-radius:8px;}"
            "QPushButton:disabled{color:#64748b;}")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Question from the conversation partner")
        title.setStyleSheet("color:#cbd5e1;font-size:22px;font-weight:600;")
        col.addWidget(title)
        self.question = QLineEdit(placeholderText="Type a question, then press Enter")
        col.addWidget(self.question)
        row = QHBoxLayout()
        self.ask_btn = QPushButton("Suggest replies")
        self.alt_btn = QPushButton("Other replies")
        self.saved_btn = QPushButton("Saved phrases")
        for b in (self.ask_btn, self.alt_btn, self.saved_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(b)
        col.addLayout(row)
        self.origin = QLabel()
        self.origin.setWordWrap(True)
        col.addWidget(self.origin)
        self.alt_btn.setEnabled(False)

        self.question.returnPressed.connect(self._ask)
        self.ask_btn.clicked.connect(self._ask)
        self.alt_btn.clicked.connect(self.alternatives_requested)
        self.saved_btn.clicked.connect(self.saved_requested)

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
        color = _ORIGIN_COLORS.get(rs.origin, "#e2e8f0")
        note = f" · {rs.note}" if rs.note else ""
        self.origin.setText(f"<span style='color:{color};font-weight:700'>Replies: {rs.origin}"
                            f"</span>{note}")
