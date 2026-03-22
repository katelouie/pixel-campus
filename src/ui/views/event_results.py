"""Event results modal — shows pass/fail outcome after an event resolves.

Displays team total vs threshold for standard events, or attendance
for the party event. Press any key or click to dismiss.
"""

import arcade

from src.sim.engine import GameState
from src.ui.bitmap_font import BitmapFont
from src.ui.font import COLOR_DIM, COLOR_HEADER, COLOR_LABEL
from src.ui.hud import _make_nine_slice_texture

_PANEL_W = 600
_PANEL_H = 480
_BORDER = 36

_FONT_TITLE = BitmapFont(scale=3, color=COLOR_HEADER)
_FONT_RESULT = BitmapFont(scale=2, color=(60, 140, 80, 255))
_FONT_FAIL = BitmapFont(scale=2, color=(180, 60, 40, 255))
_FONT_LABEL = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_VALUE = BitmapFont(scale=2, color=(60, 50, 35, 255))
_FONT_DIM = BitmapFont(scale=2, color=COLOR_DIM)
_FONT_MVP = BitmapFont(scale=2, color=(200, 160, 40, 255))
_FONT_SMALL = BitmapFont(scale=1, color=COLOR_DIM)
_FONT_HINT = BitmapFont(scale=2, color=(140, 130, 110, 180))

_PASS_BG = (180, 220, 170, 180)
_FAIL_BG = (230, 190, 180, 180)


class EventResultsView(arcade.View):
    """Full-screen modal showing event results. Press any key to dismiss."""

    def __init__(self, results: dict, state: GameState, return_view: arcade.View) -> None:
        super().__init__()
        self._results = results
        self._state = state
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
            arcade.draw_lrbt_rectangle_filled(0, w, 0, h, (0, 0, 0, 160))

            pl = (w - _PANEL_W) // 2
            pb = (h - _PANEL_H) // 2

            # Panel
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H // 2, _PANEL_W, _PANEL_H))

            r = self._results
            passed = r.get("passed", False)
            is_party = "host_name" in r

            y = pb + _PANEL_H - _BORDER - 24

            # Title
            title = _FONT_TITLE.get_texture(r.get("event_name", "Event"))
            arcade.draw_texture_rect(title,
                arcade.XYWH(pl + _PANEL_W // 2, y, title.width, title.height))
            y -= 50

            # Result banner
            result_bg = _PASS_BG if passed else _FAIL_BG
            arcade.draw_lrbt_rectangle_filled(
                pl + _BORDER, pl + _PANEL_W - _BORDER, y - 18, y + 18, result_bg)

            if passed:
                rt = _FONT_RESULT.get_texture("PASSED!")
            else:
                rt = _FONT_FAIL.get_texture("Not quite...")
            arcade.draw_texture_rect(rt,
                arcade.XYWH(pl + _PANEL_W // 2, y, rt.width, rt.height))
            y -= 40

            if is_party:
                self._draw_party_results(pl, y, r)
            else:
                self._draw_standard_results(pl, y, r)

            # Dismiss hint
            ht = _FONT_HINT.get_texture("Click or press any key to continue")
            arcade.draw_texture_rect(ht,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _BORDER + 16, ht.width, ht.height))

    def _draw_standard_results(self, pl: float, y: float, r: dict) -> None:
        cx = pl + _PANEL_W // 2

        # Team total vs threshold
        total = r.get("team_total", 0)
        threshold = r.get("threshold", 0)
        skill = r.get("skill_name", "?").capitalize()

        st = _FONT_LABEL.get_texture(f"Team {skill}: {int(total)} / {threshold}")
        arcade.draw_texture_rect(st, arcade.XYWH(cx, y, st.width, st.height))
        y -= 30

        # MVP
        mvp = r.get("mvp")
        if mvp:
            name, val = mvp
            mt = _FONT_MVP.get_texture(f"MVP: {name} ({int(val)})")
            arcade.draw_texture_rect(mt, arcade.XYWH(cx, y, mt.width, mt.height))
            y -= 30

        # Per-student breakdown
        st2 = _FONT_DIM.get_texture("Student contributions:")
        arcade.draw_texture_rect(st2, arcade.XYWH(cx, y, st2.width, st2.height))
        y -= 20

        per_student = r.get("per_student", [])
        col1_x = pl + _BORDER + 20
        col2_x = pl + _PANEL_W // 2 + 20
        for i, (name, val) in enumerate(per_student):
            x = col1_x if i % 2 == 0 else col2_x
            if i % 2 == 0 and i > 0:
                y -= 16
            pt = _FONT_SMALL.get_texture(f"{name}: {int(val)}")
            arcade.draw_texture_rect(pt,
                arcade.XYWH(x + pt.width // 2, y, pt.width, pt.height))

    def _draw_party_results(self, pl: float, y: float, r: dict) -> None:
        cx = pl + _PANEL_W // 2

        # Host
        ht = _FONT_LABEL.get_texture(f"Host: {r.get('host_name', '?')}")
        arcade.draw_texture_rect(ht, arcade.XYWH(cx, y, ht.width, ht.height))
        y -= 30

        # Attendance
        att = r.get("attendance_count", 0)
        total = r.get("total_students", 0)
        at = _FONT_LABEL.get_texture(f"Attendance: {att}/{total}")
        arcade.draw_texture_rect(at, arcade.XYWH(cx, y, at.width, at.height))
        y -= 30

        # Accepted list
        attendees = r.get("attendees", [])
        if attendees:
            names = ", ".join(name for name, _ in attendees)
            at2 = _FONT_SMALL.get_texture(f"Came: {names}")
            arcade.draw_texture_rect(at2, arcade.XYWH(cx, y, at2.width, at2.height))
            y -= 18

        # Declined list
        declined = r.get("declined", [])
        if declined:
            names = ", ".join(name for name, _ in declined)
            dt = _FONT_SMALL.get_texture(f"Declined: {names}")
            arcade.draw_texture_rect(dt, arcade.XYWH(cx, y, dt.width, dt.height))

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)

    def on_key_press(self, key: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)
