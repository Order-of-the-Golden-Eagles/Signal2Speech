"""F1 key-help overlay for the people running the demo (#94).

It only shows text over its parent. It never touches the selection handler, so opening it
can't pick, confirm, or cancel anything.
"""
from __future__ import annotations

import html
from typing import Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QLabel, QWidget

from . import palette as P

Row = Tuple[str, str]


class KeyHelpOverlay(QLabel):
    def __init__(self, parent: QWidget, rows: Sequence[Row], title: str = "Keys"):
        super().__init__(parent)
        self.rows = list(rows)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(11, 13, 16, 235); "      # P.HELP_BG at 92%
                           f"color: {P.TEXT}; font-size: 26px;")
        body = "".join(
            f"<tr><td style='padding:8px 28px 8px 0; color:{P.ACCENT}; font-weight:700'>"
            f"{html.escape(k)}</td><td style='padding:8px 0'>{html.escape(v)}</td></tr>"
            for k, v in self.rows)
        self.setText(f"<div style='font-size:34px; font-weight:700'>{html.escape(title)}</div>"
                     f"<table align='center' style='margin-top:18px'>{body}</table>"
                     f"<div style='margin-top:22px; color:{P.QUIET}; font-size:20px'>"
                     "F1 or click to close</div>")
        self.hide()
        parent.installEventFilter(self)
        self._fit()

    def toggle(self) -> None:
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self._fit()
            self.raise_()

    def mousePressEvent(self, event) -> None:
        self.hide()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._fit()
        return False

    def _fit(self) -> None:
        parent: Optional[QWidget] = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
