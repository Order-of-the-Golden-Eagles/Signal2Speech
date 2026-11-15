"""Pick the largest font size at which text fits a box (#95)."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics

MIN_PX = 32   # never smaller: still readable from the judge table


def fit_pixel_size(text: str, font: QFont, width: int, height: int, max_px: int,
                   min_px: int = MIN_PX, step: int = 2) -> int:
    """Largest pixel size in [min_px, max_px] where word-wrapped `text` fits width x height.

    Returns max_px for empty text or an unlaid-out box, and min_px if nothing fits.
    """
    if not text or width <= 0 or height <= 0:
        return max_px
    f = QFont(font)
    flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
    for px in range(max_px, min_px - 1, -step):
        f.setPixelSize(px)
        r = QFontMetrics(f).boundingRect(QRect(0, 0, width, 100_000), flags, text)
        if r.width() <= width and r.height() <= height:
            return px
    return min_px
