"""WCAG colour contrast for every text/background pair the UI draws (#135)."""
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from signal2speech.ui import theme as P  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "signal2speech" / "ui"


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def required(px: int, bold: bool) -> float:
    return 3.0 if (bold and px >= 24) else 4.5


def blend(top: str, bottom: str, alpha: float) -> str:
    t = [int(top.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(bottom.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(alpha * x + (1 - alpha) * y):02x}" for x, y in zip(t, b))


def test_contrast_formula_matches_wcag_reference_values():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("where,fg,bg,px,bold", P.TEXT_PAIRS, ids=[p[0] for p in P.TEXT_PAIRS])
def test_every_text_pair_meets_wcag_aa(where, fg, bg, px, bold):
    ratio = contrast(fg, bg)
    assert ratio >= required(px, bold), f"{where}: {fg} on {bg} is {ratio:.2f}:1"


@pytest.mark.parametrize("under", [P.BG, P.TILE_BG, P.TILE_LIT_BG], ids=["window", "tile", "flashing tile"])
def test_help_overlay_stays_readable_over_anything(under):
    shown = blend(P.HELP_BG, under, 235 / 255)            # the overlay is 92% opaque
    for fg, px in ((P.TEXT, 26), (P.ACCENT, 26), (P.QUIET, 20)):
        assert contrast(fg, shown) >= 4.5, f"{fg} over the overlay on {under}"


def test_every_input_source_has_a_checked_colour():
    from signal2speech.core import InputSources
    assert set(P.INPUT_COLORS) == set(InputSources.ALL)
    checked = {fg for _, fg, *_ in P.TEXT_PAIRS}
    assert set(P.INPUT_COLORS.values()) <= checked


def test_ui_code_takes_colours_from_the_palette():
    """A raw #rrggbb in any screen's code would bypass this check (#135, #174)."""
    pkg = UI.parent
    screens = [UI / "window.py", UI / "help_overlay.py", UI / "conversation.py", pkg / "app.py",
               pkg / "ai" / "qt.py", pkg / "__main__.py", pkg / "attract.py", pkg / "practice.py"]   # #174: every screen uses theme.py
    for path in screens:
        code = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
        assert not re.findall(r"#[0-9a-fA-F]{6}\b", "\n".join(code)), path.name
