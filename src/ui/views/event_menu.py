"""Event menu — schedule, track, and manage school events.

Shows all events with their status (available, scheduled, completed),
lets the player schedule events by spending points, and displays
the graduation progress.
"""

import arcade

from src.sim.engine import GameState
from src.sim.events import (
    EVENTS, EVENTS_REQUIRED_FOR_GRADUATION, SchoolEvent,
    cancel_event, get_event_by_name, schedule_event,
)
from src.sim.models import Student
from src.ui.bitmap_font import BitmapFont
from src.ui.font import COLOR_DIM, COLOR_HEADER, COLOR_LABEL
from src.ui.hud import _make_nine_slice_texture

# ── Layout ─────────────────────────────────────────────────────────

_PANEL_W = 700
_PANEL_H = 620
_BORDER = 36
_ROW_H = 56
_BTN_W = 110
_BTN_H = 28

# ── Fonts ──────────────────────────────────────────────────────────

_FONT_TITLE = BitmapFont(scale=3, color=COLOR_HEADER)
_FONT_LABEL = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_VALUE = BitmapFont(scale=2, color=(60, 50, 35, 255))
_FONT_DIM = BitmapFont(scale=2, color=COLOR_DIM)
_FONT_DONE = BitmapFont(scale=2, color=(60, 140, 80, 255))
_FONT_SCHED = BitmapFont(scale=2, color=(180, 60, 40, 255))
_FONT_BTN = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_BTN_HOVER = BitmapFont(scale=2, color=(30, 25, 15, 255))
_FONT_PROGRESS = BitmapFont(scale=2, color=(100, 85, 60, 200))
_FONT_SMALL = BitmapFont(scale=1, color=COLOR_DIM)

# Colors
_BTN_BG = (235, 225, 205, 230)
_BTN_HOVER_BG = (210, 200, 175, 245)
_BTN_BORDER = (180, 165, 140, 200)
_BTN_DIS_BG = (230, 225, 215, 120)
_DONE_BG = (180, 220, 170, 180)
_SCHED_BG = (255, 230, 200, 180)
_ROW_BG_ALT = (240, 235, 225, 100)


class EventMenuView(arcade.View):
    """Overlay panel listing all events and their status."""

    def __init__(self, state: GameState, return_view: arcade.View) -> None:
        super().__init__()
        self._state = state
        self._return_view = return_view
        self._panel_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._screen_cam = arcade.Camera2D()

        # UI state
        self._hovered_btn: str = ""  # "schedule_EventName", "cancel", "close"
        self._btn_rects: dict[str, tuple[float, float, float, float]] = {}
        self._party_host_selecting: bool = False
        self._party_student_rects: dict[int, tuple[float, float, float, float]] = {}
        self._hovered_student: int = -1

        self._panel_left = 0
        self._panel_bottom = 0

    def on_show_view(self) -> None:
        self._rebuild_layout()

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)
        self._panel_left = (w - _PANEL_W) // 2
        self._panel_bottom = (h - _PANEL_H) // 2

        pl, pb = self._panel_left, self._panel_bottom
        self._btn_rects = {}

        # Close button
        cx = pl + _PANEL_W - _BORDER - 30
        cy = pb + _PANEL_H - _BORDER - 14
        self._btn_rects["close"] = (cx - 14, cy - 14, cx + 14, cy + 14)

        # Event row buttons
        y = pb + _PANEL_H - _BORDER - 80
        for event in EVENTS:
            btn_key = f"schedule_{event.name}"
            btn_x = pl + _PANEL_W - _BORDER - _BTN_W - 10
            self._btn_rects[btn_key] = (btn_x, y - _BTN_H // 2,
                                         btn_x + _BTN_W, y + _BTN_H // 2)
            y -= _ROW_H

        # Cancel button (if event is scheduled)
        if self._state.scheduled_event:
            cancel_y = y + _ROW_H // 2  # place near the scheduled row
            # Find the scheduled event's row
            for i, event in enumerate(EVENTS):
                if event.name == self._state.scheduled_event.event_name:
                    cancel_y = pb + _PANEL_H - _BORDER - 80 - i * _ROW_H
                    break
            cancel_x = pl + _PANEL_W - _BORDER - _BTN_W - _BTN_W - 20
            self._btn_rects["cancel"] = (cancel_x, cancel_y - _BTN_H // 2,
                                          cancel_x + _BTN_W, cancel_y + _BTN_H // 2)

        # Party host selection rects (if selecting)
        if self._party_host_selecting:
            self._party_student_rects = {}
            sel_y = pb + _BORDER + 40
            for i, student in enumerate(self._state.students):
                sx = pl + _BORDER + 10 + (i % 5) * 130
                sy = sel_y + (1 - i // 5) * 30
                self._party_student_rects[student.student_id] = (sx, sy - 12, sx + 120, sy + 12)

    def on_draw(self) -> None:
        self._return_view.on_draw()
        with self._screen_cam.activate():
            # Dim overlay
            arcade.draw_lrbt_rectangle_filled(
                0, self.window.width, 0, self.window.height, (0, 0, 0, 140))

            pl, pb = self._panel_left, self._panel_bottom

            # Panel
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H // 2, _PANEL_W, _PANEL_H))

            # Title
            title_tex = _FONT_TITLE.get_texture("School Events")
            arcade.draw_texture_rect(
                title_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H - _BORDER - 20,
                            title_tex.width, title_tex.height))

            # Graduation progress
            completed = len(self._state.completed_events)
            required = EVENTS_REQUIRED_FOR_GRADUATION
            prog_text = f"Graduation: {completed}/{required} events completed"
            if completed >= required:
                prog_text += " - READY!"
            prog_tex = _FONT_PROGRESS.get_texture(prog_text)
            arcade.draw_texture_rect(
                prog_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H - _BORDER - 48,
                            prog_tex.width, prog_tex.height))

            # Points display
            pts_tex = _FONT_DIM.get_texture(f"Points: {self._state.total_points}")
            arcade.draw_texture_rect(
                pts_tex,
                arcade.XYWH(pl + _BORDER + pts_tex.width // 2, pb + _PANEL_H - _BORDER - 48,
                            pts_tex.width, pts_tex.height))

            # Close button
            cx1, cy1, cx2, cy2 = self._btn_rects["close"]
            self._draw_btn("close", "X", cx1, cy1, cx2, cy2)

            # Event rows
            y = pb + _PANEL_H - _BORDER - 80
            for i, event in enumerate(EVENTS):
                row_x = pl + _BORDER + 10
                is_completed = event.name in self._state.completed_events
                is_scheduled = (self._state.scheduled_event and
                               self._state.scheduled_event.event_name == event.name)
                has_other_scheduled = (self._state.scheduled_event is not None and not is_scheduled)
                can_afford = self._state.total_points >= event.point_cost

                # Row background
                if is_completed:
                    arcade.draw_lrbt_rectangle_filled(
                        pl + _BORDER, pl + _PANEL_W - _BORDER,
                        y - _ROW_H // 2 + 2, y + _ROW_H // 2 - 2, _DONE_BG)
                elif is_scheduled:
                    arcade.draw_lrbt_rectangle_filled(
                        pl + _BORDER, pl + _PANEL_W - _BORDER,
                        y - _ROW_H // 2 + 2, y + _ROW_H // 2 - 2, _SCHED_BG)
                elif i % 2 == 1:
                    arcade.draw_lrbt_rectangle_filled(
                        pl + _BORDER, pl + _PANEL_W - _BORDER,
                        y - _ROW_H // 2 + 2, y + _ROW_H // 2 - 2, _ROW_BG_ALT)

                # Event name
                name_font = _FONT_DONE if is_completed else _FONT_LABEL
                nt = name_font.get_texture(event.name)
                arcade.draw_texture_rect(
                    nt, arcade.XYWH(row_x + nt.width // 2, y + 8, nt.width, nt.height))

                # Description + cost
                desc = f"{event.description}  Cost: {event.point_cost}pts"
                dt = _FONT_SMALL.get_texture(desc)
                arcade.draw_texture_rect(
                    dt, arcade.XYWH(row_x + dt.width // 2, y - 10, dt.width, dt.height))

                # Status / button
                btn_key = f"schedule_{event.name}"
                bx1, by1, bx2, by2 = self._btn_rects.get(btn_key, (0, 0, 0, 0))

                if is_completed:
                    st = _FONT_DONE.get_texture("Completed")
                    arcade.draw_texture_rect(
                        st, arcade.XYWH((bx1 + bx2) / 2, y, st.width, st.height))
                elif is_scheduled:
                    days = self._state.scheduled_event.days_remaining
                    st = _FONT_SCHED.get_texture(f"In {days} days")
                    arcade.draw_texture_rect(
                        st, arcade.XYWH((bx1 + bx2) / 2, y, st.width, st.height))
                    # Cancel button
                    if "cancel" in self._btn_rects:
                        ccx1, ccy1, ccx2, ccy2 = self._btn_rects["cancel"]
                        self._draw_btn("cancel", "Cancel", ccx1, ccy1, ccx2, ccy2)
                else:
                    # Schedule button
                    disabled = has_other_scheduled or not can_afford
                    self._draw_btn(btn_key, "Schedule", bx1, by1, bx2, by2, disabled=disabled)

                y -= _ROW_H

            # Party host selection overlay
            if self._party_host_selecting:
                sel_tex = _FONT_LABEL.get_texture("Select a host student:")
                arcade.draw_texture_rect(
                    sel_tex,
                    arcade.XYWH(pl + _PANEL_W // 2, pb + _BORDER + 80,
                                sel_tex.width, sel_tex.height))
                for sid, (sx1, sy1, sx2, sy2) in self._party_student_rects.items():
                    student = next((s for s in self._state.students if s.student_id == sid), None)
                    if student:
                        hov = self._hovered_student == sid
                        bg = _BTN_HOVER_BG if hov else _BTN_BG
                        arcade.draw_lrbt_rectangle_filled(sx1, sx2, sy1, sy2, bg)
                        st = _FONT_BTN.get_texture(student.name)
                        arcade.draw_texture_rect(
                            st, arcade.XYWH((sx1+sx2)/2, (sy1+sy2)/2, st.width, st.height))

    def _draw_btn(self, key: str, label: str, x1: float, y1: float, x2: float, y2: float,
                  disabled: bool = False) -> None:
        hov = self._hovered_btn == key and not disabled
        bg = _BTN_DIS_BG if disabled else _BTN_HOVER_BG if hov else _BTN_BG
        arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, bg)
        arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2, _BTN_BORDER, border_width=1)
        font = _FONT_BTN_HOVER if hov else _FONT_BTN
        if disabled:
            font = BitmapFont(scale=2, color=(160, 150, 135, 160))
        t = font.get_texture(label)
        arcade.draw_texture_rect(t, arcade.XYWH((x1+x2)/2, (y1+y2)/2, t.width, t.height))

    # ── Input ──────────────────────────────────────────────────────

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        self._hovered_btn = ""
        self._hovered_student = -1
        for key, rect in self._btn_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._hovered_btn = key
                return
        if self._party_host_selecting:
            for sid, rect in self._party_student_rects.items():
                if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                    self._hovered_student = sid
                    return

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        # Party host selection
        if self._party_host_selecting:
            for sid, rect in self._party_student_rects.items():
                if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                    err = schedule_event(self._state, "The Big Party", host_id=sid)
                    if err:
                        pass  # TODO: show error
                    self._party_host_selecting = False
                    self._rebuild_layout()
                    return
            # Click outside = cancel selection
            self._party_host_selecting = False
            return

        for key, rect in self._btn_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                if key == "close":
                    self.window.show_view(self._return_view)
                elif key == "cancel":
                    cancel_event(self._state)
                    self._rebuild_layout()
                elif key.startswith("schedule_"):
                    event_name = key[len("schedule_"):]
                    event = get_event_by_name(event_name)
                    if not event:
                        return

                    # Check if already completed or can't afford
                    if event_name in self._state.completed_events:
                        return
                    if self._state.scheduled_event is not None:
                        return
                    if self._state.total_points < event.point_cost:
                        return

                    if event.is_party:
                        # Show host selection
                        self._party_host_selecting = True
                        self._rebuild_layout()
                    else:
                        err = schedule_event(self._state, event_name)
                        if not err:
                            self._rebuild_layout()
                return

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.ESCAPE:
            if self._party_host_selecting:
                self._party_host_selecting = False
            else:
                self.window.show_view(self._return_view)
