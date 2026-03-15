"""HUD overlay for Pixel Campus.

Draws a 9-slice top bar (clock/points) and a 9-slice log panel (bottom-left).
Reads from GameState but never writes to it.
"""

from pathlib import Path

import arcade
from PIL import Image as _PILImage

from src.sim.engine import GameState

_UI_SHEET = (
    Path(__file__).resolve().parent.parent.parent
    / "assets/packs/modernuserinterface-win/48x48/Modern_UI_Style_1_48x48.png"
)
_TILE = 48
_FONT = "Monaco"

# Each corner tile has ~24px of transparent outer padding before the visible border.
# The bottom edge tiles have ~27px transparent at the very bottom.
# Offsetting the sprites by these amounts makes the visual border flush with the screen edge.
_EDGE_TRANS_SIDE   = 24   # left / right / top transparent padding in corner tiles
_EDGE_TRANS_BOTTOM = 27   # bottom transparent padding in bottom corner tiles

# Log panel (bottom-left, flush with corner after offset)
_PANEL_W = 480
_PANEL_H = 240

# Top bar (centered at top of screen)
_TOP_BAR_W = 560
_TOP_BAR_H = 144   # 3 tile-rows: top border + 1 center + bottom border

# Approximate visible text area inside the panel (used for word-wrap width)
_LOG_WRAP_CHARS = 52


def _make_nine_slice_texture(width: int, height: int) -> arcade.Texture:
    """Compose a panel image from Style 1 nine-slice tiles (PIL, runs once at startup)."""
    sheet = _PILImage.open(_UI_SHEET)
    ts = _TILE

    def crop(col: int, row: int, w: int = ts, h: int = ts) -> _PILImage.Image:
        return sheet.crop((col * ts, row * ts, col * ts + w, row * ts + h))

    def paste(src: _PILImage.Image, x: int, y: int) -> None:
        panel.paste(src, (x, y), src)

    panel = _PILImage.new("RGBA", (width, height), (0, 0, 0, 0))

    # Corners
    paste(crop(0, 0), 0,          0)
    paste(crop(2, 0), width - ts,  0)
    paste(crop(0, 2), 0,          height - ts)
    paste(crop(2, 2), width - ts,  height - ts)

    # Top and bottom edges (tiled, last tile clipped)
    for x in range(ts, width - ts, ts):
        w = min(ts, width - ts - x)
        paste(crop(1, 0, w, ts), x, 0)
        paste(crop(1, 2, w, ts), x, height - ts)

    # Left and right edges (tiled, last tile clipped)
    for y in range(ts, height - ts, ts):
        h = min(ts, height - ts - y)
        paste(crop(0, 1, ts, h), 0,          y)
        paste(crop(2, 1, ts, h), width - ts,  y)

    # Center fill (tiled in both axes)
    for y in range(ts, height - ts, ts):
        for x in range(ts, width - ts, ts):
            w = min(ts, width - ts - x)
            h = min(ts, height - ts - y)
            paste(crop(1, 1, w, h), x, y)

    return arcade.Texture(panel)


def _wrap(text: str, max_chars: int = _LOG_WRAP_CHARS) -> list[str]:
    """Word-wrap a message into lines of at most max_chars characters."""
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


class HUD:
    """Heads-up display drawn on top of the game view."""

    MAX_MESSAGES = 12
    _LOG_LINES = 7
    _LINE_SPACING = 16

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self._messages: list[str] = []

        # --- Top bar panel (clock / points) ---
        # Offset upward by _EDGE_TRANS_SIDE so the visible border is flush with the screen top.
        top_tex = _make_nine_slice_texture(_TOP_BAR_W, _TOP_BAR_H)
        top_sprite = arcade.Sprite(top_tex)
        top_sprite.center_x = screen_width // 2
        top_sprite.center_y = (
            screen_height + _EDGE_TRANS_SIDE - _TOP_BAR_H // 2
        )
        self._top_bar_list = arcade.SpriteList()
        self._top_bar_list.append(top_sprite)

        self._clock_text = arcade.Text(
            "",
            x=screen_width // 2,
            y=top_sprite.center_y,
            color=arcade.color.BLACK,
            font_size=16,
            font_name=_FONT,
            anchor_x="center",
            anchor_y="center",
            bold=True,
        )

        # --- Log panel (bottom-left, flush with screen corner) ---
        # Offset left by _EDGE_TRANS_SIDE and down by _EDGE_TRANS_BOTTOM so the
        # visible wooden border meets the screen edge exactly.
        log_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        log_sprite = arcade.Sprite(log_tex)
        log_sprite.center_x = _PANEL_W // 2 - _EDGE_TRANS_SIDE
        log_sprite.center_y = _PANEL_H // 2 - _EDGE_TRANS_BOTTOM
        self._log_panel_list = arcade.SpriteList()
        self._log_panel_list.append(log_sprite)

        # Text starts just inside the visible border (tile - transparent + padding)
        inner_x   = _TILE - _EDGE_TRANS_SIDE + 8           # left text margin on screen
        inner_top = _PANEL_H - _EDGE_TRANS_BOTTOM - _TILE - 8  # y of first (newest) line

        self._msg_lines: list[arcade.Text] = []
        for i in range(self._LOG_LINES):
            line = arcade.Text(
                "",
                x=inner_x,
                y=inner_top - i * self._LINE_SPACING,
                color=arcade.color.BLACK,
                font_size=11,
                font_name=_FONT,
            )
            self._msg_lines.append(line)

    def push_messages(self, messages: list[str]) -> None:
        """Add new log lines (word-wrapped), keeping only the most recent."""
        wrapped: list[str] = []
        for msg in messages:
            wrapped.extend(_wrap(msg))
        self._messages = (self._messages + wrapped)[-self.MAX_MESSAGES:]

    def draw(self, state: GameState) -> None:
        """Update and draw all HUD elements."""
        # Top bar
        self._top_bar_list.draw()
        self._clock_text.text = (
            f"Day {state.clock.day}  |  {state.clock.time_str}  |  "
            f"Points: {state.total_points}/{state.graduation_target}"
        )
        self._clock_text.draw()

        # Log panel
        self._log_panel_list.draw()
        recent = list(reversed(self._messages[-self._LOG_LINES:]))
        for i, line_text in enumerate(self._msg_lines):
            line_text.text = recent[i] if i < len(recent) else ""
            line_text.draw()
