"""Title screen — the first thing the player sees.

Displays the game title and menu buttons (New Game, Load Game, Settings).
Uses the same papernote aesthetic as the rest of the UI.
"""

from pathlib import Path

import arcade

from src.ui.bitmap_font import BitmapFont
from src.ui.font import COLOR_HEADER, COLOR_LABEL, COLOR_DIM, FONT_NAME
from src.ui.hud import _make_nine_slice_texture

# ── Layout constants ───────────────────────────────────────────────

_PANEL_W = 420
_PANEL_H = 340
_BUTTON_W = 260
_BUTTON_H = 44
_BUTTON_GAP = 16

# Larger font for the title
_TITLE_FONT = BitmapFont(scale=4, color=(230, 220, 200, 255))
_SUBTITLE_FONT = BitmapFont(scale=2, color=(170, 160, 140, 220))
_BUTTON_FONT = BitmapFont(scale=2, color=COLOR_LABEL)
_BUTTON_HOVER_FONT = BitmapFont(scale=2, color=(30, 25, 15, 255))

# Button background colors
_BTN_BG = (235, 225, 205, 230)
_BTN_HOVER_BG = (210, 200, 175, 245)
_BTN_BORDER = (180, 165, 140, 200)
_BTN_HOVER_BORDER = (140, 120, 90, 255)

# Saves directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SAVES_DIR = _PROJECT_ROOT / "saves"


class TitleView(arcade.View):
    """Title screen with New Game / Load Game / Settings buttons."""

    def __init__(self) -> None:
        super().__init__()
        self._panel_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._screen_cam = arcade.Camera2D()

        # Button definitions: (label, action_name)
        self._buttons: list[tuple[str, str]] = [
            ("New Game", "new_game"),
            ("Load Game", "load_game"),
            ("Settings", "settings"),
        ]
        # Computed button rects: (x1, y1, x2, y2) — set in on_show_view
        self._button_rects: list[tuple[float, float, float, float]] = []
        self._hovered_button: int = -1  # index of hovered button, -1 = none

        # Check if saves exist (to gray out Load Game if none)
        self._has_saves = _SAVES_DIR.exists() and any(_SAVES_DIR.glob("*.json"))

    def on_show_view(self) -> None:
        self.window.background_color = (58, 55, 62)
        self._rebuild_layout()

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self._screen_cam.position = arcade.Vec2(width / 2, height / 2)
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)

        # Panel centered on screen
        self._panel_cx = w // 2
        self._panel_cy = h // 2 - 20  # slightly below center to leave room for title
        self._panel_left = self._panel_cx - _PANEL_W // 2
        self._panel_bottom = self._panel_cy - _PANEL_H // 2

        # Title position (above panel)
        self._title_y = self._panel_cy + _PANEL_H // 2 + 60

        # Buttons stacked inside panel
        total_buttons_h = len(self._buttons) * _BUTTON_H + (len(self._buttons) - 1) * _BUTTON_GAP
        btn_top = self._panel_cy + total_buttons_h // 2

        self._button_rects = []
        for i in range(len(self._buttons)):
            bx1 = self._panel_cx - _BUTTON_W // 2
            by2 = btn_top - i * (_BUTTON_H + _BUTTON_GAP)
            by1 = by2 - _BUTTON_H
            bx2 = bx1 + _BUTTON_W
            self._button_rects.append((bx1, by1, bx2, by2))

    def on_draw(self) -> None:
        self.clear()
        with self._screen_cam.activate():
            w = self.window.width

            # Draw title text
            title_tex = _TITLE_FONT.get_texture("Pixel Campus")
            arcade.draw_texture_rect(
                title_tex,
                arcade.XYWH(w // 2, self._title_y, title_tex.width, title_tex.height),
            )

            # Subtitle
            sub_tex = _SUBTITLE_FONT.get_texture("A campus life simulator")
            arcade.draw_texture_rect(
                sub_tex,
                arcade.XYWH(w // 2, self._title_y - 36, sub_tex.width, sub_tex.height),
            )

            # Draw panel background
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(self._panel_cx, self._panel_cy, _PANEL_W, _PANEL_H),
            )

            # Draw buttons
            for i, (label, action) in enumerate(self._buttons):
                x1, y1, x2, y2 = self._button_rects[i]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                is_hovered = i == self._hovered_button
                is_disabled = action == "load_game" and not self._has_saves
                is_disabled = is_disabled or action == "settings"  # settings not implemented yet

                # Button background
                if is_disabled:
                    bg = (210, 200, 185, 140)
                    border = (180, 170, 155, 120)
                elif is_hovered:
                    bg = _BTN_HOVER_BG
                    border = _BTN_HOVER_BORDER
                else:
                    bg = _BTN_BG
                    border = _BTN_BORDER

                arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, bg)
                arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2, border, border_width=2)

                # Button label
                if is_disabled:
                    font = BitmapFont(scale=2, color=(160, 150, 135, 160))
                elif is_hovered:
                    font = _BUTTON_HOVER_FONT
                else:
                    font = _BUTTON_FONT

                label_tex = font.get_texture(label)
                arcade.draw_texture_rect(
                    label_tex,
                    arcade.XYWH(cx, cy, label_tex.width, label_tex.height),
                )

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        self._hovered_button = -1
        for i, (x1, y1, x2, y2) in enumerate(self._button_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._hovered_button = i
                break

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        for i, (x1, y1, x2, y2) in enumerate(self._button_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                action = self._buttons[i][1]
                if action == "new_game":
                    self._start_new_game()
                elif action == "load_game" and self._has_saves:
                    self._load_game()
                # settings: future
                break

    def _start_new_game(self) -> None:
        """Create a new game and transition to the landing/roster view."""
        from src.sim.engine import GameState
        from src.ui.views.landing import LandingView

        state = GameState.new_game()

        # Assign appearances to all students
        from src.ui.character_composer import random_appearance
        for student in state.students:
            if student.appearance is None:
                student.appearance = random_appearance(student.student_id)

        self.window.show_view(LandingView(state))

    def _load_game(self) -> None:
        """Load the most recent save and go to campus."""
        from src.sim.serialization import load_game
        from src.ui.views.campus import CampusView

        # Find the most recent save file
        saves = sorted(_SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not saves:
            return

        state = load_game(saves[0])

        # Ensure all students have appearances (for old saves)
        from src.ui.character_composer import random_appearance
        for student in state.students:
            if student.appearance is None:
                student.appearance = random_appearance(student.student_id)

        campus = CampusView(state=state)
        self.window.show_view(campus)
