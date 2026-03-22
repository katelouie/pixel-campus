"""Day summary screen — shown at end of each day.

Displays points earned, skill gains, relationship changes, conversations,
event countdown, weather, and student moods. Click or press any key to
continue to the next day.
"""

import arcade

from src.ui.bitmap_font import BitmapFont
from src.ui.font import COLOR_DIM, COLOR_HEADER, COLOR_LABEL
from src.ui.hud import _make_nine_slice_texture

_PANEL_W = 700
_PANEL_H = 560
_BORDER = 36

_FONT_TITLE = BitmapFont(scale=3, color=COLOR_HEADER)
_FONT_HEADER = BitmapFont(scale=2, color=COLOR_HEADER)
_FONT_LABEL = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_VALUE = BitmapFont(scale=2, color=(60, 50, 35, 255))
_FONT_DIM = BitmapFont(scale=2, color=COLOR_DIM)
_FONT_GOOD = BitmapFont(scale=2, color=(60, 140, 80, 255))
_FONT_SMALL = BitmapFont(scale=1, color=COLOR_DIM)
_FONT_HINT = BitmapFont(scale=2, color=(140, 130, 110, 180))
_FONT_POINTS = BitmapFont(scale=2, color=(200, 160, 40, 255))

_LINE_COLOR = (140, 120, 90, 180)


class DaySummaryView(arcade.View):
    """End-of-day summary modal. Click or press any key to continue."""

    def __init__(self, summary: dict, return_view: arcade.View) -> None:
        super().__init__()
        self._summary = summary
        self._return_view = return_view
        self._panel_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._screen_cam = arcade.Camera2D()

    def on_show_view(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)

    def on_draw(self) -> None:
        self._return_view.on_draw()
        with self._screen_cam.activate():
            w, h = self.window.width, self.window.height

            # Dim overlay
            arcade.draw_lrbt_rectangle_filled(0, w, 0, h, (0, 0, 0, 140))

            pl = (w - _PANEL_W) // 2
            pb = (h - _PANEL_H) // 2
            s = self._summary

            # Panel
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H // 2, _PANEL_W, _PANEL_H))

            y = pb + _PANEL_H - _BORDER - 24
            il = pl + _BORDER + 10  # inner left
            ir = pl + _PANEL_W - _BORDER - 10  # inner right
            cx = pl + _PANEL_W // 2

            # Title: "Day N — Season"
            season = s.get("season", "?").capitalize()
            title = _FONT_TITLE.get_texture(f"Day {s.get('day', '?')} - {season}")
            arcade.draw_texture_rect(title, arcade.XYWH(cx, y, title.width, title.height))
            y -= 36

            # Weather + Points row
            weather = s.get("weather", "?").capitalize()
            wt = _FONT_LABEL.get_texture(f"Weather: {weather}")
            arcade.draw_texture_rect(wt, arcade.XYWH(il + wt.width // 2, y, wt.width, wt.height))

            pts = s.get("points_today", 0)
            total = s.get("points_total", 0)
            pt = _FONT_POINTS.get_texture(f"+{pts} points (Total: {total})")
            arcade.draw_texture_rect(pt, arcade.XYWH(ir - pt.width // 2, y, pt.width, pt.height))
            y -= 24

            # Divider
            arcade.draw_line(il, y, ir, y, _LINE_COLOR, 1)
            y -= 16

            # ── School Skills ───────────────────────────────────────
            stats = s.get("school_stats", {})
            skill_avgs = stats.get("skills", {})
            skill_deltas = s.get("skill_deltas", {})
            mood_avg = stats.get("mood", 0)

            ht = _FONT_HEADER.get_texture("SCHOOL STATS")
            arcade.draw_texture_rect(ht, arcade.XYWH(il + ht.width // 2, y, ht.width, ht.height))
            y -= 18

            # Mood
            mood_text = f"Avg Mood: {mood_avg}"
            mt = _FONT_LABEL.get_texture(mood_text)
            arcade.draw_texture_rect(mt, arcade.XYWH(il + mt.width // 2, y, mt.width, mt.height))
            y -= 18

            # Skills with deltas
            for skill_name in ["academics", "athletics", "creativity", "social", "music"]:
                avg = skill_avgs.get(skill_name, 0)
                delta = skill_deltas.get(skill_name, 0)
                label = skill_name.capitalize()

                if delta > 0:
                    line = f"{label}: {avg}  (+{delta})"
                    font = _FONT_GOOD
                elif delta < 0:
                    line = f"{label}: {avg}  ({delta})"
                    font = _FONT_LABEL
                else:
                    line = f"{label}: {avg}"
                    font = _FONT_DIM

                lt = font.get_texture(line)
                arcade.draw_texture_rect(lt, arcade.XYWH(il + lt.width // 2, y, lt.width, lt.height))
                y -= 16
            y -= 8

            # ── Relationship Changes ───────────────────────────────
            rels = s.get("rel_changes", [])
            if rels:
                ht = _FONT_HEADER.get_texture("RELATIONSHIPS")
                arcade.draw_texture_rect(ht, arcade.XYWH(il + ht.width // 2, y, ht.width, ht.height))
                y -= 18
                for msg in rels[:4]:
                    # Truncate long messages
                    display = msg[:60] + "..." if len(msg) > 60 else msg
                    mt = _FONT_SMALL.get_texture(display)
                    arcade.draw_texture_rect(mt, arcade.XYWH(il + mt.width // 2, y, mt.width, mt.height))
                    y -= 14
                y -= 8

            # ── Conversations ──────────────────────────────────────
            convos = s.get("conversations", [])
            if convos:
                ht = _FONT_HEADER.get_texture("CONVERSATIONS")
                arcade.draw_texture_rect(ht, arcade.XYWH(il + ht.width // 2, y, ht.width, ht.height))
                y -= 18
                for msg in convos[:4]:
                    display = msg[:60] + "..." if len(msg) > 60 else msg
                    mt = _FONT_SMALL.get_texture(display)
                    arcade.draw_texture_rect(mt, arcade.XYWH(il + mt.width // 2, y, mt.width, mt.height))
                    y -= 14
                y -= 8

            # ── Event Countdown ────────────────────────────────────
            event_info = s.get("event_info")
            if event_info:
                days = event_info["days_remaining"]
                et = _FONT_LABEL.get_texture(f"Event: {event_info['name']} in {days} days")
                arcade.draw_texture_rect(et, arcade.XYWH(il + et.width // 2, y, et.width, et.height))
                y -= 22

            # ── Tomorrow's Weather ─────────────────────────────────
            tmrw = s.get("tomorrow_weather", "?").capitalize()
            tt = _FONT_DIM.get_texture(f"Tomorrow's forecast: {tmrw}")
            arcade.draw_texture_rect(tt, arcade.XYWH(il + tt.width // 2, y, tt.width, tt.height))

            # Dismiss hint
            ht = _FONT_HINT.get_texture("Click or press any key to continue")
            arcade.draw_texture_rect(ht,
                arcade.XYWH(cx, pb + _BORDER + 16, ht.width, ht.height))

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)

    def on_key_press(self, key: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)
