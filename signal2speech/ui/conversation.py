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
    "note": ("Note", T.MUTED),
    "help": ("Asked for help", T.ACCENT),
}


class ConversationView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[Tuple[str, str, Optional[str]]] = []   # (kind, text, input label)
        self._stamps: List[str] = []
        #: Show only the most recent thing chosen or said. The full history stays in ``entries``
        #: (and in the developer log and the session report); this only saves screen space.
        self.latest_only = False
        self.setOpenLinks(False)
        self.restyle()

    def restyle(self) -> None:
        """Apply the current text scale (#195)."""
        self.setStyleSheet(f"QTextBrowser {{ background: {T.SURFACE}; color: {T.TEXT}; border: none;"
                           f" border-radius: {T.RADIUS_M}px; padding: {T.M}px; font-size: {T.px(T.BODY - 2)}px; }}")
        self._render()

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
        rows = list(zip(self.entries, self._stamps))
        if self.latest_only and rows:
            chosen = [r for r in rows if r[0][0] in ("preview", "said", "shown", "nothing", "help")]
            last = (chosen or rows)[-1]
            if last[0][0] == "nothing":                # dismissed: still show what was dismissed
                previews = [r for r in rows if r[0][0] == "preview"]
                if previews:
                    (kind, _text, src), stamp = last
                    last = ((kind, f"Cancelled: {previews[-1][0][1]}", src), stamp)
            rows = [last]
        for (kind, text, src), stamp in rows:
            label, colour = KINDS[kind]
            source = f"<span style='color:{T.QUIET}'> · {html.escape(src)}</span>" if src else ""
            parts.append(
                f"<p style='margin:0 0 {T.M}px 0'>"
                f"<span style='color:{T.QUIET}; font-size:{T.px(T.CAPTION - 2)}px'>{stamp}</span>"
                f"&nbsp;&nbsp;<b style='color:{colour}'>{html.escape(label)}</b>{source}<br>"
                f"<span style='color:{T.TEXT}'>{html.escape(text)}</span></p>")
        self.setHtml("".join(parts))
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def truncate(self, n: int) -> None:
        """Drop entries after the first n (attract mode's entries never stay, #193)."""
        if len(self.entries) > n:
            del self.entries[n:]
            del self._stamps[n:]
            self._render()

    def last(self) -> Optional[Tuple[str, str, Optional[str]]]:
        return self.entries[-1] if self.entries else None
