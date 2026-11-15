"""The readable conversation panel (#176): what judges see instead of the raw developer log.

Each entry is one plain-language line with a label and, where it applies, the input that
caused it (Keyboard, Simulated, Recorded, Live EEG). The app builds entries from the same
handler events and sink as the developer log, so the two can't disagree.
"""
from __future__ import annotations

import html
import time
from typing import List, Optional, Tuple

from PySide6.QtWidgets import QTextBrowser

from . import theme as T

# kind -> (label, label colour)
KINDS = {
    "question": ("Question", T.MUTED),
    "options": ("Options", T.MUTED),
    "preview": ("Previewed", T.ACCENT),
    "said": ("Said aloud", T.SUCCESS),
    "shown": ("Showed the map and said", T.SUCCESS),
    "nothing": ("Nothing was said", T.QUIET),
}


class ConversationView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[Tuple[str, str, Optional[str]]] = []   # (kind, text, input label)
        self._stamps: List[str] = []
        self.setOpenLinks(False)
        self.setStyleSheet(f"QTextBrowser {{ background: {T.SURFACE}; color: {T.TEXT}; border: none;"
                           f" border-radius: {T.RADIUS_M}px; padding: {T.M}px; font-size: {T.BODY - 2}px; }}")

    def add(self, kind: str, text: str, input_label: Optional[str] = None) -> None:
        self.entries.append((kind, text, input_label))
        self._stamps.append(time.strftime("%H:%M:%S"))
        self._render()

    def label_last(self, kind: str, input_label: Optional[str]) -> None:
        """Attach the input to the latest entry of `kind` (e.g. who cancelled)."""
        for i in range(len(self.entries) - 1, -1, -1):
            if self.entries[i][0] == kind:
                k, text, _ = self.entries[i]
                self.entries[i] = (k, text, input_label)
                self._render()
                return

    def _render(self) -> None:
        parts = []
        for (kind, text, src), stamp in zip(self.entries, self._stamps):
            label, colour = KINDS[kind]
            source = f"<span style='color:{T.QUIET}'> · {html.escape(src)}</span>" if src else ""
            parts.append(
                f"<p style='margin:0 0 {T.M}px 0'>"
                f"<span style='color:{T.QUIET}; font-size:{T.CAPTION - 2}px'>{stamp}</span>"
                f"&nbsp;&nbsp;<b style='color:{colour}'>{html.escape(label)}</b>{source}<br>"
                f"<span style='color:{T.TEXT}'>{html.escape(text)}</span></p>")
        self.setHtml("".join(parts))
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def last(self) -> Optional[Tuple[str, str, Optional[str]]]:
        return self.entries[-1] if self.entries else None
