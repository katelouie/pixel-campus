"""Global font configuration for Pixel Campus.

Provides shared BitmapFont instances for pixel-perfect text rendering.
All UI text should use the fonts from this module for consistency.

To restyle the game (e.g., different scale or color), change the values here.
"""

from src.ui.bitmap_font import BitmapFont

# ── Color presets ───────────────────────────────────────────────────

COLOR_HEADER    = (30,  20,  10,  255)
COLOR_LABEL     = (40,  30,  20,  255)
COLOR_DIM       = (80,  70,  55,  200)
COLOR_TIMESTAMP = (110,  90,  65, 200)
COLOR_JOURNAL   = (45,  35,  25,  255)
COLOR_WHITE     = (255, 255, 255, 255)
COLOR_SCROLL    = (140, 120,  90, 160)

# ── Shared font instances ───────────────────────────────────────────
# Scale 2 = each pixel of the 5x12 glyph becomes 2x2 on screen (10x24 per char).

FONT: BitmapFont = BitmapFont(scale=2, color=COLOR_LABEL)
FONT_HEADER: BitmapFont = BitmapFont(scale=2, color=COLOR_HEADER)
FONT_DIM: BitmapFont = BitmapFont(scale=2, color=COLOR_DIM)
FONT_TIMESTAMP: BitmapFont = BitmapFont(scale=2, color=COLOR_TIMESTAMP)
FONT_JOURNAL: BitmapFont = BitmapFont(scale=2, color=COLOR_JOURNAL)
FONT_WHITE: BitmapFont = BitmapFont(scale=2, color=COLOR_WHITE)
FONT_SCROLL: BitmapFont = BitmapFont(scale=2, color=COLOR_SCROLL)

# TTF fallback name (for arcade.Text objects that can't use bitmap, e.g., emoji)
FONT_NAME: str = "monogram"


def load_game_font() -> None:
    """Load the TTF font into arcade's font system (for fallback use). Safe to call multiple times."""
    import arcade
    from pathlib import Path
    _path = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "monogram-extended.ttf"
    try:
        arcade.load_font(str(_path))
    except Exception:
        pass  # non-fatal — bitmap font is primary
