"""HUD overlay for Pixel Campus.

Draws a banner top bar (clock/points) and a 9-slice log panel (bottom-left).
Reads from GameState but never writes to it.
"""

from pathlib import Path

import arcade
from PIL import Image as _PILImage

from src.sim.engine import GameState
from src.ui.bitmap_font import BitmapFont

_PAPERNOTE = (
    Path(__file__).resolve().parent.parent.parent
    / "assets/packs/Complete_UI_Essential_Pack_v2.4/11_Papernote_Theme/Sprites"
)
_FRAME_PATH  = _PAPERNOTE / "UI_Papernote_FrameStandard03.png"
_BANNER_PATH = _PAPERNOTE / "UI_Papernote_Banner04.png"

_TILE = 32
_BITMAP_SCALE = 2  # change this to resize the log font (1 = tiny, 2 = normal, 3 = large)

# Log panel (bottom-left, flush with screen corner)
_PANEL_W = 608  # wide enough for comfortable reading
_PANEL_H = 240

# Inner padding between border tile and text
_LOG_PAD = 4

# Top bar (centered at top of screen)
_TOP_BAR_W = 560
_TOP_BAR_H = _TILE  # banner is exactly one tile tall

# Scrollbar drawn inside the right border tile (not the content area)
_SCROLL_W = 6
_SCROLL_X = _PANEL_W - _TILE + (_TILE - _SCROLL_W) // 2  # centered in right border

# Wrap width: full content area (scrollbar lives in border, so no deduction needed)
_CHAR_STEP      = (5 + 1) * _BITMAP_SCALE   # pixels per char (5px + 1px gap, scaled)
_LOG_WRAP_CHARS = (_PANEL_W - 2 * _TILE - 2 * _LOG_PAD) // _CHAR_STEP


def _make_nine_slice_texture(width: int, height: int) -> arcade.Texture:
    """Compose a panel from FrameStandard03 nine-slice tiles (PIL, runs once at startup)."""
    src = _PILImage.open(_FRAME_PATH)
    ts = _TILE

    def crop(col: int, row: int, w: int = ts, h: int = ts) -> _PILImage.Image:
        return src.crop((col * ts, row * ts, col * ts + w, row * ts + h))

    def paste(tile: _PILImage.Image, x: int, y: int) -> None:
        panel.paste(tile, (x, y), tile)

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


def _make_banner_texture(width: int) -> arcade.Texture:
    """Compose a horizontal banner from Banner04 three-piece tiles (left + tiled middle + right)."""
    src = _PILImage.open(_BANNER_PATH)
    ts = _TILE

    panel = _PILImage.new("RGBA", (width, ts), (0, 0, 0, 0))

    def paste(tile: _PILImage.Image, x: int) -> None:
        panel.paste(tile, (x, 0), tile)

    # Left cap
    paste(src.crop((0, 0, ts, ts)), 0)
    # Right cap
    paste(src.crop((2 * ts, 0, 3 * ts, ts)), width - ts)
    # Middle tiles (tiled, last tile clipped)
    for x in range(ts, width - ts, ts):
        w = min(ts, width - ts - x)
        paste(src.crop((ts, 0, ts + w, ts)), x)

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

    MAX_MESSAGES = 200

    def __init__(self, screen_width: int, screen_height: int) -> None:
        # Each entry is a list of wrapped lines for one message.
        # Storing by group lets us reverse by message while preserving
        # reading order within each message's wrapped lines.
        self._messages: list[list[str]] = []
        self._font = BitmapFont(scale=_BITMAP_SCALE, color=(30, 30, 30, 255))
        # Screen-space camera: keeps HUD sprites anchored to screen coords.
        # Camera2D.position is the world point that maps to SCREEN CENTER,
        # so (width/2, height/2) makes world coords == screen pixel coords.
        self._screen_camera = arcade.Camera2D()
        self._screen_camera.position = arcade.Vec2(screen_width / 2, screen_height / 2)

        # --- Top bar panel (clock / points) ---
        top_tex = _make_banner_texture(_TOP_BAR_W)
        top_sprite = arcade.Sprite(top_tex)
        top_sprite.center_x = screen_width // 2
        top_sprite.center_y = screen_height - _TOP_BAR_H // 2
        self._top_bar_list = arcade.SpriteList()
        self._top_bar_list.append(top_sprite)

        # Clock rendered as bitmap sprite, centered in the banner
        self._clock_cx = screen_width // 2
        self._clock_cy = screen_height - _TOP_BAR_H // 2
        _empty_clock = arcade.Texture(_PILImage.new("RGBA", (1, self._font.char_height), (0, 0, 0, 0)))
        self._clock_sprite = arcade.Sprite(_empty_clock)
        self._clock_sprite_list = arcade.SpriteList()
        self._clock_sprite_list.append(self._clock_sprite)

        # --- Log panel (bottom-left, flush with screen corner) ---
        log_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        log_sprite = arcade.Sprite(log_tex)
        log_sprite.center_x = _PANEL_W // 2
        log_sprite.center_y = _PANEL_H // 2
        self._log_panel_list = arcade.SpriteList()
        self._log_panel_list.append(log_sprite)

        # Text area: just inside the border tiles, with minimal padding
        self._inner_x   = _TILE + _LOG_PAD
        self._inner_top = _PANEL_H - _TILE - _LOG_PAD

        line_spacing = self._font.line_spacing
        content_h = _PANEL_H - 2 * _TILE - 2 * _LOG_PAD
        self._log_lines = max(1, content_h // line_spacing)

        # Scroll state: 0 = newest lines, positive = scrolled back into history
        self._scroll_offset: int = 0

        # Clickable student name regions — rebuilt each draw()
        self._student_names: set[str] = set()
        self._name_regions: list[tuple[float, float, float, float, str]] = []

        # One sprite per log line — textures swapped each draw()
        _empty = arcade.Texture(_PILImage.new("RGBA", (1, self._font.char_height), (0, 0, 0, 0)))
        self._msg_sprites: list[arcade.Sprite] = []
        self._msg_sprite_list = arcade.SpriteList()
        for _ in range(self._log_lines):
            sprite = arcade.Sprite(_empty)
            self._msg_sprites.append(sprite)
            self._msg_sprite_list.append(sprite)

    def set_student_names(self, names: set[str]) -> None:
        """Tell the HUD which names to highlight as clickable in the log."""
        self._student_names = names
        self._name_regions: list[tuple[float, float, float, float, str]] = []

    def check_name_click(self, x: int, y: int) -> str | None:
        """Return a student name if (x, y) falls within a highlighted name region."""
        for x1, x2, y1, y2, name in self._name_regions:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    def push_messages(self, messages: list[str]) -> None:
        """Add new log messages (each word-wrapped into a group), keeping MAX_MESSAGES groups."""
        for msg in messages:
            self._messages.append(_wrap(msg))
        self._messages = self._messages[-self.MAX_MESSAGES:]
        # If not scrolled back, stay pinned to newest
        if self._scroll_offset == 0:
            pass  # already pinned
        else:
            # Keep the same relative position as history grows
            self._scroll_offset = min(self._scroll_offset, self._max_scroll())

    def scroll(self, delta: int) -> None:
        """Scroll the log. Positive = back in history, negative = toward newest."""
        self._scroll_offset = max(0, min(self._scroll_offset + delta, self._max_scroll()))

    def _all_lines(self) -> list[str]:
        """All log lines flattened newest-first, reading order within each message."""
        lines: list[str] = []
        for group in reversed(self._messages):
            lines.extend(group)
        return lines

    def _max_scroll(self) -> int:
        return max(0, len(self._all_lines()) - self._log_lines)

    def draw(self, state: GameState) -> None:
        """Update and draw all HUD elements."""
        with self._screen_camera.activate():
            # Top bar + clock
            self._top_bar_list.draw()
            clock_str = (
                f"{state.clock.day_time_str}  |  "
                f"Points: {state.total_points}/{state.graduation_target}"
            )
            clock_tex = self._font.get_texture(clock_str)
            self._clock_sprite.texture = clock_tex
            self._clock_sprite.center_x = self._clock_cx
            self._clock_sprite.center_y = self._clock_cy
            self._clock_sprite_list.draw()

            # Log panel
            self._log_panel_list.draw()
            all_lines = self._all_lines()
            total = len(all_lines)
            start = self._scroll_offset
            display_lines = all_lines[start:start + self._log_lines]
            line_spacing = self._font.line_spacing
            for i, sprite in enumerate(self._msg_sprites):
                text = display_lines[i] if i < len(display_lines) else ""
                tex = self._font.get_texture(text)
                sprite.texture = tex
                sprite.center_x = self._inner_x + tex.width // 2
                sprite.center_y = self._inner_top - i * line_spacing - tex.height // 2
            self._msg_sprite_list.draw()

            # Highlight clickable student names — amber underline + click regions
            self._name_regions = []
            if self._student_names:
                line_spacing = self._font.line_spacing
                char_h = self._font.char_height
                for i, text in enumerate(display_lines):
                    line_top = self._inner_top - i * line_spacing
                    line_bot = line_top - char_h
                    for name in self._student_names:
                        idx = text.find(name)
                        while idx >= 0:
                            x1 = self._inner_x + idx * _CHAR_STEP
                            x2 = self._inner_x + (idx + len(name)) * _CHAR_STEP
                            # Underline
                            arcade.draw_line(
                                x1, line_bot - 1, x2, line_bot - 1,
                                (160, 120, 40, 220), 1,
                            )
                            self._name_regions.append((x1, x2, line_bot - 3, line_top + 2, name))
                            idx = text.find(name, idx + len(name))

            # Scrollbar (only when there's more history than fits)
            max_scroll = self._max_scroll()
            if max_scroll > 0:
                track_bottom = _TILE + _LOG_PAD
                track_top    = _PANEL_H - _TILE - _LOG_PAD
                track_h      = track_top - track_bottom
                thumb_h      = max(8, int(self._log_lines / total * track_h))
                scroll_ratio = self._scroll_offset / max_scroll
                thumb_bottom = track_top - thumb_h - int(scroll_ratio * (track_h - thumb_h))
                # Track
                arcade.draw_lrbt_rectangle_filled(
                    _SCROLL_X, _SCROLL_X + _SCROLL_W,
                    track_bottom, track_top,
                    (180, 170, 150, 120),
                )
                # Thumb
                arcade.draw_lrbt_rectangle_filled(
                    _SCROLL_X, _SCROLL_X + _SCROLL_W,
                    thumb_bottom, thumb_bottom + thumb_h,
                    (80, 60, 40, 200),
                )
