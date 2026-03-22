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

# Time & weather icon sheet
_ICON_SHEET_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets/packs/UI assets pack 2/Time & weather.png"
)
_ICON_SIZE = 48  # each icon is 48x48 in the sheet
_ICON_DISPLAY = 28  # display size in the HUD (scaled down to fit the banner)

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


def _load_time_weather_icons() -> dict[str, arcade.Texture]:
    """Parse the Time & Weather sprite sheet into named icon textures.

    Returns a dict with keys like:
      time_dawn, time_morning, time_afternoon, time_sunset, time_evening, time_night
      weather_cloudy_morning, weather_cloudy_afternoon, weather_cloudy_night
      weather_storm_morning, weather_storm_afternoon, weather_storm_night
      weather_rain_morning, weather_rain_afternoon, weather_rain_night
    """
    sheet = _PILImage.open(_ICON_SHEET_PATH)
    # Square-frame icons start at x=176, y=16 in the sheet
    # Grid: 3 cols × 6 rows of 48×48 icons
    # Row 0: empty frame (skip)
    # Rows 1-2: time of day (6 icons wrapped)
    # Rows 3-5: weather × time variant (cloudy, storm, rain × morning/afternoon/night)
    ox, oy = 176, 16
    s = _ICON_SIZE
    icons = {}

    time_names = ["dawn", "morning", "afternoon", "sunset", "evening", "night"]
    idx = 0
    for r in range(1, 3):
        for c in range(3):
            cell = sheet.crop((ox + c*s, oy + r*s, ox + (c+1)*s, oy + (r+1)*s))
            icons[f"time_{time_names[idx]}"] = arcade.Texture(cell)
            idx += 1

    weather_types = ["cloudy", "storm", "rain"]
    time_variants = ["morning", "afternoon", "night"]
    for ri, weather in enumerate(weather_types):
        for ci, tod in enumerate(time_variants):
            cell = sheet.crop((ox + ci*s, 176 + ri*s, ox + (ci+1)*s, 176 + (ri+1)*s))
            icons[f"weather_{weather}_{tod}"] = arcade.Texture(cell)

    return icons


def _tick_to_time_phase(tick: int, season: str = "spring") -> str:
    """Map a game tick (0-84) to a time-of-day phase name, adjusted by season.

    Winter: sunset starts earlier (hour 14), evening by 16.
    Summer: sunset pushes late (hour 18), long bright afternoons.
    Spring/Fall: in between.
    """
    hour = 8 + (tick * 10 // 60)

    # Season-adjusted thresholds: (dawn_end, morning_end, afternoon_end, sunset_end, evening_end)
    _SEASON_THRESHOLDS = {
        "winter": (10, 11, 14, 16, 18),
        "fall":   (10, 12, 15, 17, 19),
        "spring": (10, 12, 15, 17, 19),
        "summer": ( 9, 12, 16, 18, 20),
    }
    dawn_end, morning_end, afternoon_end, sunset_end, evening_end = _SEASON_THRESHOLDS.get(
        season, (10, 12, 15, 17, 19)
    )

    if hour < dawn_end:
        return "dawn"
    if hour < morning_end:
        return "morning"
    if hour < afternoon_end:
        return "afternoon"
    if hour < sunset_end:
        return "sunset"
    if hour < evening_end:
        return "evening"
    return "night"


def _tick_to_weather_col(tick: int) -> str:
    """Map a game tick to a weather icon time variant (morning/afternoon/night)."""
    hour = 8 + (tick * 10 // 60)
    if hour < 13:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "night"


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

        # Time & weather icons (native 48x48, top-right, left of minimap)
        # Minimap is 160px wide with 8px margin from right edge
        self._tw_icons = _load_time_weather_icons()
        _minimap_left = screen_width - 8 - 160
        self._icon_cx = _minimap_left - _ICON_SIZE // 2 - 8
        self._icon_cy = screen_height - _ICON_SIZE // 2 - 8
        self._icon_hover = False
        self._icon_rect = (
            self._icon_cx - _ICON_SIZE // 2,
            self._icon_cy - _ICON_SIZE // 2,
            self._icon_cx + _ICON_SIZE // 2,
            self._icon_cy + _ICON_SIZE // 2,
        )
        self._weather_label = ""

        # Events button (below the top bar, left side)
        _evt_font = BitmapFont(scale=2, color=(40, 30, 20, 255))
        self._evt_btn_tex = _evt_font.get_texture("Events")
        _evt_w = 90
        _evt_h = 28
        self._evt_btn_rect = (
            screen_width // 2 - _TOP_BAR_W // 2,
            screen_height - _TOP_BAR_H - _evt_h - 4,
            screen_width // 2 - _TOP_BAR_W // 2 + _evt_w,
            screen_height - _TOP_BAR_H - 4,
        )
        self._evt_btn_hovered = False
        self._countdown_font = BitmapFont(scale=1, color=(180, 60, 40, 255))

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

    def check_icon_hover(self, x: int, y: int) -> None:
        """Update hover state for the weather icon and events button."""
        ix1, iy1, ix2, iy2 = self._icon_rect
        self._icon_hover = ix1 <= x <= ix2 and iy1 <= y <= iy2

        ex1, ey1, ex2, ey2 = self._evt_btn_rect
        self._evt_btn_hovered = ex1 <= x <= ex2 and ey1 <= y <= ey2

    def check_events_click(self, x: int, y: int) -> bool:
        """Return True if the events button was clicked."""
        ex1, ey1, ex2, ey2 = self._evt_btn_rect
        return ex1 <= x <= ex2 and ey1 <= y <= ey2

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
            # Top bar + clock + time/weather icon
            self._top_bar_list.draw()

            # Pick the right icon for current time + weather
            from src.sim.personality import Weather as _Weather
            tick = state.clock.tick
            weather = state.current_weather
            time_phase = _tick_to_time_phase(tick, state.clock.season)
            if weather in (_Weather.SUNNY, _Weather.WINDY, _Weather.SNOW):
                icon_key = f"time_{time_phase}"
            else:
                weather_name = {_Weather.CLOUDY: "cloudy", _Weather.RAIN: "rain",
                                _Weather.STORM: "storm"}.get(weather, "cloudy")
                icon_key = f"weather_{weather_name}_{_tick_to_weather_col(tick)}"

            self._weather_label = f"{weather.value.capitalize()} - {time_phase.capitalize()}"

            icon_tex = self._tw_icons.get(icon_key)
            if icon_tex:
                arcade.draw_texture_rect(
                    icon_tex,
                    arcade.XYWH(self._icon_cx, self._icon_cy, _ICON_SIZE, _ICON_SIZE),
                )

            # Hover tooltip for the weather icon
            if self._icon_hover and self._weather_label:
                _tip_font = BitmapFont(scale=1, color=(40, 30, 20, 255))
                label_tex = _tip_font.get_texture(self._weather_label)
                tip_x = self._icon_cx - label_tex.width // 2 - 4
                tip_y = self._icon_cy - _ICON_SIZE // 2 - label_tex.height // 2 - 6
                pad = 4
                arcade.draw_lrbt_rectangle_filled(
                    tip_x - pad, tip_x + label_tex.width + pad,
                    tip_y - label_tex.height // 2 - pad, tip_y + label_tex.height // 2 + pad,
                    (240, 230, 210, 230),
                )
                arcade.draw_lrbt_rectangle_outline(
                    tip_x - pad, tip_x + label_tex.width + pad,
                    tip_y - label_tex.height // 2 - pad, tip_y + label_tex.height // 2 + pad,
                    (180, 165, 140, 200), border_width=1,
                )
                arcade.draw_texture_rect(
                    label_tex,
                    arcade.XYWH(tip_x + label_tex.width // 2, tip_y,
                                label_tex.width, label_tex.height),
                )

            season_label = state.clock.season.capitalize()
            clock_str = (
                f"{state.clock.day_time_str}  |  {season_label}  |  "
                f"Points: {state.total_points}"
            )
            clock_tex = self._font.get_texture(clock_str)
            self._clock_sprite.texture = clock_tex
            self._clock_sprite.center_x = self._clock_cx
            self._clock_sprite.center_y = self._clock_cy
            self._clock_sprite_list.draw()

            # Events button
            ex1, ey1, ex2, ey2 = self._evt_btn_rect
            evt_bg = (210, 200, 175, 245) if self._evt_btn_hovered else (235, 225, 205, 220)
            arcade.draw_lrbt_rectangle_filled(ex1, ex2, ey1, ey2, evt_bg)
            arcade.draw_lrbt_rectangle_outline(ex1, ex2, ey1, ey2, (180, 165, 140, 200), border_width=1)
            arcade.draw_texture_rect(
                self._evt_btn_tex,
                arcade.XYWH((ex1 + ex2) / 2, (ey1 + ey2) / 2,
                            self._evt_btn_tex.width, self._evt_btn_tex.height))

            # Event countdown (right of the events button)
            if state.scheduled_event:
                days = state.scheduled_event.days_remaining
                cd_text = f"{state.scheduled_event.event_name} in {days}d"
                cd_tex = self._countdown_font.get_texture(cd_text)
                arcade.draw_texture_rect(
                    cd_tex,
                    arcade.XYWH(ex2 + 8 + cd_tex.width // 2, (ey1 + ey2) / 2,
                                cd_tex.width, cd_tex.height))

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
