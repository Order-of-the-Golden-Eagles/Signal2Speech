"""One visual design for the whole app (#174): colours, type scale, spacing, corner radius.

Every screen built here (selection window and tiles, judge strip, help overlay, app shell and
transcript, AI question panel, launcher) takes its look from this module. tests/test_contrast.py
checks every text/background pair in TEXT_PAIRS against WCAG AA, and fails if a raw #rrggbb
appears in those screens' code. Add a pair here when you add a new text colour.
"""
from signal2speech.core import ActionIds, InputSources

# ── Colour roles ─────────────────────────────────────────────
BG = "#0b0d10"            # window background
SURFACE = "#151a21"       # panels: judge strip, transcript, question box
RAISED = "#1e2630"        # tiles and buttons
BORDER = "#475569"        # outlines on raised surfaces
DIVIDER = "#2a3340"       # hairlines between regions
TEXT = "#f5f7fa"          # primary text
MUTED = "#cbd5e1"         # secondary text: prompt, hint, descriptions
QUIET = "#94a3b8"         # tertiary text: countdown, footers, "waiting"
ACCENT = "#ffe066"        # the exact words to be spoken; key badges
ON_ACCENT = "#0b0d10"     # text on ACCENT
SUCCESS = "#22c55e"       # selected outline
SUCCESS_BG = "#14532d"    # selected fill

# Judge strip
STRIP_BG, STRIP_TEXT, STRIP_BORDER = SURFACE, "#e2e8f0", DIVIDER

# Tiles. Flashing must look exactly as before (#46 timing): plain white with black content.
TILE_BG, TILE_TEXT, TILE_BORDER = RAISED, "#ffffff", BORDER
TILE_LIT_BG, TILE_LIT_TEXT = "#ffffff", "#000000"
TILE_SELECTED_BG, TILE_SELECTED_TEXT, TILE_SELECTED_BORDER = SUCCESS_BG, "#ffffff", SUCCESS
TILE_DISABLED_BG, TILE_DISABLED_TEXT, TILE_DISABLED_BORDER = "#11151a", QUIET, "#1f2630"
# Back-compat names from palette.py (#135)
TILE_EMPTY_BG, TILE_EMPTY_BORDER = TILE_DISABLED_BG, TILE_DISABLED_BORDER

INPUT_COLORS = {
    InputSources.KEYBOARD: "#3b82f6",
    InputSources.SIMULATED: "#f59e0b",
    InputSources.RECORDED: "#c084fc",
    InputSources.LIVE_EEG: "#22c55e",
}

# AI reply origin labels in the question panel
ORIGIN_COLORS = {"Claude": "#22c55e", "Stub": "#f59e0b", "Saved phrases": "#60a5fa"}

HELP_BG = BG              # the overlay is BG at 92% opacity over the window

# ── Type scale (px) ──────────────────────────────────────────
DISPLAY = 56              # the largest text on screen
TILE_TITLE = 40           # tile titles at full size: readable, without filling the screen
TITLE = 36                # screen titles
PREVIEW = 24              # the words to be spoken: small enough for five words a line
PREVIEW_MIN = 20          # long replies shrink no further
HEADING = 24              # prompts, panel titles
BODY = 22                 # hints, buttons, descriptions
CAPTION = 18              # strip, footers, small print
TILE_TITLE_MIN = 32       # long tile and preview text shrinks no further (#95)
MONO = "Menlo, Consolas, monospace"
#: The interface font, first one installed wins. Segoe UI Variable is Windows 11's own.
FONT_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Inter", "SF Pro Display",
                 "Helvetica Neue", "Noto Sans", "sans-serif"]
FONT = ", ".join(f'"{f}"' if " " in f else f for f in FONT_FAMILIES)

# ── Text size (#195) ─────────────────────────────────────────
# Ctrl+= / Ctrl+- step SCALE through these; Ctrl+0 resets. Every text size on screen goes
# through px(), so one factor scales the whole app. Fitted text still shrinks to its floor.
SCALE_STEPS = (0.8, 0.9, 1.0, 1.15, 1.3, 1.45, 1.6)
SCALE = 1.0


def px(size: float) -> int:
    """A type-scale size at the current text scale."""
    return max(1, round(size * SCALE))


def set_scale(factor: float) -> float:
    global SCALE
    SCALE = min(max(float(factor), SCALE_STEPS[0]), SCALE_STEPS[-1])
    return SCALE


def step_scale(direction: int) -> float:
    """Move one step up (+1) or down (-1) from the current scale; 0 resets to 100%."""
    if direction == 0:
        return set_scale(1.0)
    if direction > 0:
        bigger = [s for s in SCALE_STEPS if s > SCALE + 1e-9]
        return set_scale(bigger[0] if bigger else SCALE_STEPS[-1])
    smaller = [s for s in SCALE_STEPS if s < SCALE - 1e-9]
    return set_scale(smaller[-1] if smaller else SCALE_STEPS[0])

# ── Spacing (px) and corner radius ───────────────────────────
XS, S, M, L, XL = 4, 8, 16, 24, 32
RADIUS_S, RADIUS_M, RADIUS_L = 8, 14, 20
BORDER_W = 4

# ── What each tile does: (icon, one-line description) ────────
ACTION_INFO = {
    ActionIds.SHOW_SATELLITE: ("satellite", "June 24 to 28, day by day"),
    ActionIds.COMPARE_AIR_QUALITY: ("chart", "County air quality"),
    ActionIds.SPEAK_REPLY: ("speech", "Says these exact words"),
    ActionIds.CONFIRM: ("check", "Hold 1, or close your eyes"),
    ActionIds.CANCEL: ("cross", "Nothing is said"),
}


#: A colour for each kind of tile, so the screen isn't all one grey-blue. It tints the border,
#: the key badge and (faintly) the background. A flashing tile ignores it: the flash stays plain
#: white, because the brain response is timed against that exact stimulus.
ACTION_TINT = {
    ActionIds.SHOW_SATELLITE: "#38bdf8",        # sky blue
    ActionIds.COMPARE_AIR_QUALITY: "#c084fc",   # violet
    ActionIds.SPEAK_REPLY: "#fbbf24",           # amber
    ActionIds.CONFIRM: "#4ade80",               # green
    ActionIds.CANCEL: "#fb7185",                # rose
}
TINT_BG_ALPHA = 0.10
#: Corner radius of the status pills: half their height, so the ends are round.
PILL_RADIUS = 15


def window_qss() -> str:
    """Style sheet for the selection window."""
    return f"""
QMainWindow, QWidget#root {{ background: {BG}; }}
QLabel {{ color: {TEXT}; }}
QLabel#prompt {{ font-size: {px(HEADING)}px; font-weight: 600; color: {TEXT}; }}
QLabel#preview {{ font-size: {px(PREVIEW)}px; font-weight: 700; color: {ACCENT}; padding: {M}px;
                  background: {SURFACE}; border-left: 6px solid {ACCENT}; border-radius: {RADIUS_M}px; }}
QLabel#hint {{ font-size: {px(BODY)}px; color: {MUTED}; }}
QLabel#previewHeader {{ font-size: {px(BODY)}px; font-weight: 600; color: {MUTED}; }}
QLabel#countdown {{ font-size: {px(BODY)}px; color: {QUIET}; }}
QFrame#strip {{ background: transparent; border: none; }}
QLabel.strip {{ font-size: {px(CAPTION - 2)}px; font-family: {FONT}; color: {STRIP_TEXT};
                background: {STRIP_BG}; border: 1px solid {STRIP_BORDER};
                border-radius: {PILL_RADIUS}px; padding: 5px 14px; }}
"""


# (where, text colour, background, font px, bold)
TEXT_PAIRS = [
    ("label text", TEXT, BG, BODY, False),
    ("prompt", MUTED, BG, HEADING, False),
    ("hint", MUTED, BG, BODY, False),
    ("preview header", MUTED, BG, BODY, True),
    ("ring label", MUTED, BG, CAPTION, False),
    ("ring done", SUCCESS, BG, TITLE, True),
    ("ring seconds", TEXT, BG, BODY, True),
    ("preview", ACCENT, SURFACE, TILE_TITLE_MIN, True),
    ("countdown", QUIET, BG, BODY, False),
    ("tile title", TILE_TEXT, TILE_BG, TILE_TITLE_MIN, True),
    ("tile description", MUTED, TILE_BG, CAPTION + 2, False),
    ("tile while flashing", TILE_LIT_TEXT, TILE_LIT_BG, TILE_TITLE_MIN, True),
    ("tile selected", TILE_SELECTED_TEXT, TILE_SELECTED_BG, TILE_TITLE_MIN, True),
    ("tile selected description", TILE_SELECTED_TEXT, TILE_SELECTED_BG, CAPTION + 2, False),
    ("tile waiting", TILE_DISABLED_TEXT, TILE_DISABLED_BG, BODY, False),
    ("key badge", ON_ACCENT, ACCENT, CAPTION + 2, True),
    ("strip text", STRIP_TEXT, STRIP_BG, CAPTION + 2, False),
    *[(f"input label {name}", colour, STRIP_BG, CAPTION + 2, True)
      for name, colour in INPUT_COLORS.items()],
    *[(f"reply origin {name}", colour, BG, CAPTION + 2, True) for name, colour in ORIGIN_COLORS.items()],
    ("transcript", STRIP_TEXT, SURFACE, 15, False),
    ("conversation text", TEXT, SURFACE, BODY - 2, False),
    ("conversation label", MUTED, SURFACE, BODY - 2, True),
    ("conversation previewed", ACCENT, SURFACE, BODY - 2, True),
    ("conversation said", SUCCESS, SURFACE, BODY - 2, True),
    ("conversation nothing / time / input", QUIET, SURFACE, CAPTION - 2, False),
    ("panel title", MUTED, BG, BODY, True),
    ("text size toast", TEXT, RAISED, HEADING, True),
    ("help phrase banner", ON_ACCENT, ACCENT, TITLE, True),
    ("attract banner", ON_ACCENT, INPUT_COLORS[InputSources.SIMULATED], HEADING, True),
    ("attract caption", TEXT, BG, BODY, False),
    ("button", TILE_TEXT, RAISED, BODY, True),
    ("help text", TEXT, HELP_BG, 26, False),
    ("help keys", ACCENT, HELP_BG, 26, True),
    ("help footer", QUIET, HELP_BG, CAPTION + 2, False),
]
