"""Draw the video's title card, closing card, and architecture diagram (#132).

    python docs/demo-submission/make_graphics.py      # writes media/title-card.png, closing-card.png, architecture.png

1920x1080 PNGs, drawn with Qt's QPainter (no new dependency) in the app's high-contrast colours.
Edit the text below and run it again; the wording matches the README and submission checklist.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath,  # noqa: E402
                           QPen, QPolygonF)

OUT = Path(__file__).resolve().parent / "media"
W, H = 1920, 1080
BG, FG, MUTED, ACCENT, PANEL, LINE = "#0b0d10", "#f5f7fa", "#cbd5e1", "#ffe066", "#1e2630", "#475569"
BLUE, GREEN, AMBER = "#60a5fa", "#22c55e", "#f59e0b"

TEAM = "Vasanth Anbukumar · Long Le · Nate · In Young Song"
PITCH = "Answer without speaking or typing.\nPick, preview, and confirm the exact words with a brain-computer interface."
REPO = "github.com/Order-of-the-Golden-Eagles/Signal2Speech"
AI_NOTE = ("AI use: Claude helped write the code and can suggest replies. "
           "The wearer always previews and confirms the exact words.")


def font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def canvas():
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return img, p


def text(p, rect, s, px, color=FG, bold=False, align=Qt.AlignmentFlag.AlignCenter):
    p.setFont(font(px, bold))
    p.setPen(QColor(color))
    p.drawText(QRectF(*rect), int(align | Qt.TextFlag.TextWordWrap), s)


def box(p, x, y, w, h, title, sub="", border=LINE, title_color=FG, title_px=40):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), 22, 22)
    p.fillPath(path, QColor(PANEL))
    p.setPen(QPen(QColor(border), 4))
    p.drawPath(path)
    if sub:
        text(p, (x + 16, y + 18, w - 32, h * 0.45), title, title_px, title_color, True)
        text(p, (x + 16, y + h * 0.48, w - 32, h * 0.48), sub, 28, MUTED)
    else:
        text(p, (x + 16, y, w - 32, h), title, title_px, title_color, True)


def arrow(p, x1, y1, x2, y2, color=MUTED, label=""):
    p.setPen(QPen(QColor(color), 5))
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    dx, dy = x2 - x1, y2 - y1
    n = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / n, dy / n
    tip = QPointF(x2, y2)
    left = QPointF(x2 - 22 * ux + 12 * uy, y2 - 22 * uy - 12 * ux)
    right = QPointF(x2 - 22 * ux - 12 * uy, y2 - 22 * uy + 12 * ux)
    p.setBrush(QColor(color))
    p.drawPolygon(QPolygonF([tip, left, right]))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if label:
        text(p, ((x1 + x2) / 2 - 160, (y1 + y2) / 2 - 52, 320, 40), label, 26, color)


def title_card(path: Path) -> None:
    img, p = canvas()
    text(p, (0, 250, W, 170), "Signal2Speech", 150, FG, True)
    text(p, (160, 450, W - 320, 200), PITCH, 46, ACCENT, True)
    text(p, (0, 760, W, 60), TEAM, 38, MUTED)
    text(p, (0, 830, W, 60), "Hack the Nest 2026 · Order of the Golden Eagles · built on g.tec g.Pype", 32, MUTED)
    p.end()
    img.save(str(path), "PNG")


def closing_card(path: Path) -> None:
    img, p = canvas()
    text(p, (0, 200, W, 120), "Signal2Speech", 110, FG, True)
    text(p, (0, 360, W, 70), REPO, 50, BLUE, True)
    text(p, (0, 470, W, 60), TEAM, 38, FG)
    text(p, (0, 560, W, 60), "Built with g.Pype and the g.tec Unicorn Hybrid Black · NASA MODIS imagery · EPA AirData", 32, MUTED)
    text(p, (220, 680, W - 440, 130), AI_NOTE, 32, MUTED)
    text(p, (0, 880, W, 60), "Code, docs, and the full AI-use disclosure are in the repo.", 30, MUTED)
    p.end()
    img.save(str(path), "PNG")


def elbow(p, points, color=MUTED):
    """A multi-segment arrow; the head points along the last segment."""
    p.setPen(QPen(QColor(color), 5))
    for (x1, y1), (x2, y2) in zip(points, points[1:-1]):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    arrow(p, *points[-2], *points[-1], color)


def architecture(path: Path) -> None:
    img, p = canvas()
    text(p, (0, 40, W, 80), "How a brain signal becomes one spoken answer", 56, FG, True)
    # Column 1: inputs
    box(p, 40, 200, 440, 160, "Unicorn Hybrid Black", "8-channel EEG headset", BLUE, title_px=34)
    box(p, 40, 790, 440, 130, "Keyboard or simulator", "same events, labelled honestly", LINE, MUTED, title_px=34)
    # Column 2: g.Pype
    box(p, 580, 170, 500, 220, "g.Pype", "OSCAR artifact removal\nand filters", GREEN)
    box(p, 580, 450, 500, 130, "P300 → LDA", "choose a tile", GREEN)
    box(p, 580, 610, 500, 130, "Alpha switch", "eyes closed ≈ 2 s to confirm", GREEN)
    box(p, 580, 790, 500, 130, "Evidence scopes", "raw · OSCAR · averaged P300", LINE, MUTED, title_px=34)
    # Column 3: contract
    box(p, 1200, 400, 340, 360, "Selection contract",
        "preview first\nconfirm in a new round\nexactly one output\nlate or repeated input ignored", ACCENT, ACCENT)
    # Column 4: outputs
    box(p, 1640, 400, 240, 160, "Speech", "says the exact words", LINE)
    box(p, 1640, 600, 240, 160, "Map", "NASA + EPA reveal", LINE)
    arrow(p, 480, 280, 576, 280)
    arrow(p, 830, 390, 830, 446)
    arrow(p, 1080, 515, 1196, 520, GREEN)
    arrow(p, 1080, 675, 1196, 650, GREEN)
    elbow(p, [(260, 920), (260, 960), (1370, 960), (1370, 764)], MUTED)
    arrow(p, 1540, 480, 1636, 480, ACCENT)
    arrow(p, 1540, 680, 1636, 680, ACCENT)
    text(p, (0, 990, W, 60), "One Python process · fully offline · CI on Windows, macOS, and Linux", 34, MUTED)
    p.end()
    img.save(str(path), "PNG")


def main() -> int:
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in (("title-card.png", title_card), ("closing-card.png", closing_card),
                       ("architecture.png", architecture)):
        draw(OUT / name)
        print(f"wrote {OUT / name} ({(OUT / name).stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
