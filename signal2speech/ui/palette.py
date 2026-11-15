"""Every colour the selection window and help overlay draw text with (#135).

The window, tiles, judge strip, and help overlay import these, and tests/test_contrast.py
checks each text/background pair below against WCAG contrast: at least 4.5:1, or 3:1 for bold
text of 24 px or more. Add a pair here when you add a new text colour.
"""
from signal2speech.core import InputSources

BG = "#0b0d10"            # window background
TEXT = "#f5f7fa"          # default label text
MUTED = "#cbd5e1"         # prompt and hint
QUIET = "#94a3b8"         # countdown, help footer
ACCENT = "#ffe066"        # preview text, help keys
STRIP_BG = "#151a21"      # judge strip
STRIP_TEXT = "#e2e8f0"    # round, connection, last outcome
STRIP_BORDER = "#2a3340"

TILE_BG, TILE_TEXT, TILE_BORDER = "#1e2630", "#ffffff", "#475569"
TILE_LIT_BG, TILE_LIT_TEXT = "#ffffff", "#000000"
TILE_EMPTY_BG, TILE_EMPTY_BORDER = "#11151a", "#1f2630"     # no text on an empty tile

INPUT_COLORS = {
    InputSources.KEYBOARD: "#3b82f6",
    InputSources.SIMULATED: "#f59e0b",
    InputSources.RECORDED: "#c084fc",   # was #a855f7 (4.42:1 on the strip, below 4.5)
    InputSources.LIVE_EEG: "#22c55e",
}

HELP_BG = BG              # the overlay is BG at 92% opacity over the window, so contrast ~ BG

# (where, text colour, background, font px, bold)
TEXT_PAIRS = [
    ("label text", TEXT, BG, 20, False),
    ("prompt", MUTED, BG, 32, False),
    ("hint", MUTED, BG, 24, False),
    ("preview", ACCENT, BG, 32, True),          # shrinks to 32 px at the smallest (#95)
    ("countdown", QUIET, BG, 22, False),
    ("tile", TILE_TEXT, TILE_BG, 32, True),
    ("tile while flashing", TILE_LIT_TEXT, TILE_LIT_BG, 32, True),
    ("strip text", STRIP_TEXT, STRIP_BG, 20, False),
    *[(f"input label {name}", colour, STRIP_BG, 20, True)
      for name, colour in INPUT_COLORS.items()],
    ("help text", TEXT, HELP_BG, 26, False),
    ("help keys", ACCENT, HELP_BG, 26, True),
    ("help footer", QUIET, HELP_BG, 20, False),
]
