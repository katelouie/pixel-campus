"""Pre-game landing view — shows all students in a grid for customization.

Displays all students as idle sprites with names underneath. Click a student
to open the character creator. "Start Game" begins the simulation.

Inspired by the Avatar High pre-game customize screen.
"""

import arcade
from PIL import Image as _PILImage

from src.sim.engine import GameState
from src.sim.models import Student
from src.ui.bitmap_font import BitmapFont
from src.ui.character_composer import composite_sprite_sheet
from src.ui.font import COLOR_DIM, COLOR_HEADER, COLOR_LABEL
from src.ui.hud import _make_nine_slice_texture
from src.ui.sprites import CHAR_H, CHAR_W

# ── Layout ─────────────────────────────────────────────────────────

_PANEL_W = 920
_PANEL_H = 620
_BORDER = 36

# Student grid
_COLS = 5
_CELL_W = 150
_CELL_H = 200
_SPRITE_SCALE = 2  # 48x96 → 96x192

# Fonts
_FONT_TITLE = BitmapFont(scale=3, color=COLOR_HEADER)
_FONT_SUBTITLE = BitmapFont(scale=2, color=COLOR_DIM)
_FONT_NAME = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_NAME_HOVER = BitmapFont(scale=2, color=(255, 255, 255, 255))

# Button
_BTN_W = 200
_BTN_H = 44
_BTN_BG = (235, 225, 205, 230)
_BTN_HOVER_BG = (120, 100, 70, 240)
_BTN_BORDER = (180, 165, 140, 200)
_BTN_HOVER_BORDER = (80, 65, 45, 255)
_FONT_BTN = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_BTN_HOVER = BitmapFont(scale=2, color=(255, 255, 255, 255))

# Cell hover
_CELL_HOVER_BG = (200, 190, 170, 100)
_CELL_HOVER_BORDER = (160, 145, 120, 180)


class LandingView(arcade.View):
    """Pre-game roster — shows all students, click to customize."""

    def __init__(self, state: GameState) -> None:
        super().__init__()
        self._state = state
        self._panel_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._screen_cam = arcade.Camera2D()

        # Build idle-down textures for each student (static preview)
        self._student_textures: dict[int, arcade.Texture] = {}
        self._rebuild_all_previews()

        # UI state
        self._hovered_cell: int = -1  # student index
        self._hovered_button: bool = False
        self._cell_rects: list[tuple[float, float, float, float]] = []
        self._btn_rect: tuple[float, float, float, float] = (0, 0, 0, 0)

    def _rebuild_all_previews(self) -> None:
        """Rebuild idle-down textures for all students."""
        for student in self._state.students:
            self._rebuild_preview(student)

    def _rebuild_preview(self, student: Student) -> None:
        """Rebuild idle-down texture for one student."""
        if student.appearance is None:
            return
        sheet = composite_sprite_sheet(student.appearance)
        # Idle-down static frame: row 0, col 3 (down direction) in _SHEET_DIR_COL
        # down = col index 3, each direction is 1 column wide for static idle (row 0)
        # Actually row 0 has one frame per direction at specific columns
        # From sprites.py: _SHEET_DIR_COL = {"right": 0, "up": 1, "left": 2, "down": 3}
        # Row 0 = idle static, one frame per direction
        # But the columns in row 0 are packed differently — let me just grab col 3
        # Wait — looking at sprites.py more carefully:
        # idle_static: sheet.get_texture(LBWH(col * CHAR_W, 0, CHAR_W, CHAR_H))
        # where col = _SHEET_DIR_COL[direction]. For "down", col = 3
        x = 3 * CHAR_W  # down direction
        y = 0  # row 0 = idle static
        frame_img = sheet.crop((x, y, x + CHAR_W, y + CHAR_H))
        self._student_textures[student.student_id] = arcade.Texture(frame_img)

    def on_show_view(self) -> None:
        self.window.background_color = (58, 55, 62)
        # Rebuild all previews (in case a student was customized)
        self._rebuild_all_previews()
        self._rebuild_layout()

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)

        pl = (w - _PANEL_W) // 2
        pb = (h - _PANEL_H) // 2
        self._panel_left = pl
        self._panel_bottom = pb

        # Grid of students
        n = len(self._state.students)
        rows = (n + _COLS - 1) // _COLS
        grid_w = _COLS * _CELL_W
        grid_h = rows * _CELL_H
        grid_left = pl + (_PANEL_W - grid_w) // 2
        grid_top = pb + _PANEL_H - _BORDER - 70  # below title

        self._cell_rects = []
        for i in range(n):
            col = i % _COLS
            row = i // _COLS
            cx = grid_left + col * _CELL_W
            cy = grid_top - row * _CELL_H
            self._cell_rects.append((cx, cy - _CELL_H, cx + _CELL_W, cy))

        # Start Game button
        btn_cx = pl + _PANEL_W // 2
        btn_y1 = pb + _BORDER + 10
        self._btn_rect = (btn_cx - _BTN_W // 2, btn_y1,
                          btn_cx + _BTN_W // 2, btn_y1 + _BTN_H)

    def on_draw(self) -> None:
        self.clear()
        with self._screen_cam.activate():
            pl, pb = self._panel_left, self._panel_bottom

            # Panel
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H // 2, _PANEL_W, _PANEL_H),
            )

            # Title
            title_tex = _FONT_TITLE.get_texture("Customize Your Students")
            title_y = pb + _PANEL_H - _BORDER - 18
            arcade.draw_texture_rect(
                title_tex,
                arcade.XYWH(pl + _PANEL_W // 2, title_y, title_tex.width, title_tex.height),
            )

            # Subtitle
            sub_tex = _FONT_SUBTITLE.get_texture("Click a student to customize")
            arcade.draw_texture_rect(
                sub_tex,
                arcade.XYWH(pl + _PANEL_W // 2, title_y - 24, sub_tex.width, sub_tex.height),
            )

            # Student grid
            for i, student in enumerate(self._state.students):
                if i >= len(self._cell_rects):
                    break
                x1, y1, x2, y2 = self._cell_rects[i]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                is_hovered = i == self._hovered_cell

                # Cell hover background
                if is_hovered:
                    arcade.draw_lrbt_rectangle_filled(x1 + 4, x2 - 4, y1 + 4, y2 - 4,
                                                      _CELL_HOVER_BG)
                    arcade.draw_lrbt_rectangle_outline(x1 + 4, x2 - 4, y1 + 4, y2 - 4,
                                                       _CELL_HOVER_BORDER, border_width=2)

                # Sprite preview (centered in upper portion of cell)
                tex = self._student_textures.get(student.student_id)
                if tex:
                    sprite_cy = cy + 20
                    arcade.draw_texture_rect(
                        tex,
                        arcade.XYWH(cx, sprite_cy,
                                    CHAR_W * _SPRITE_SCALE, CHAR_H * _SPRITE_SCALE),
                    )

                # Name (below sprite, near bottom of cell)
                font = _FONT_NAME_HOVER if is_hovered else _FONT_NAME
                name_tex = font.get_texture(student.name)
                arcade.draw_texture_rect(
                    name_tex,
                    arcade.XYWH(cx, y1 + 14, name_tex.width, name_tex.height),
                )

            # Start Game button
            bx1, by1, bx2, by2 = self._btn_rect
            is_hovered = self._hovered_button
            bg = _BTN_HOVER_BG if is_hovered else _BTN_BG
            border = _BTN_HOVER_BORDER if is_hovered else _BTN_BORDER
            arcade.draw_lrbt_rectangle_filled(bx1, bx2, by1, by2, bg)
            arcade.draw_lrbt_rectangle_outline(bx1, bx2, by1, by2, border, border_width=2)

            font = _FONT_BTN_HOVER if is_hovered else _FONT_BTN
            btn_tex = font.get_texture("Start Game")
            arcade.draw_texture_rect(
                btn_tex,
                arcade.XYWH((bx1 + bx2) / 2, (by1 + by2) / 2,
                            btn_tex.width, btn_tex.height),
            )

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        self._hovered_cell = -1
        self._hovered_button = False

        for i, (x1, y1, x2, y2) in enumerate(self._cell_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._hovered_cell = i
                return

        bx1, by1, bx2, by2 = self._btn_rect
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            self._hovered_button = True

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        # Check student cells
        for i, (x1, y1, x2, y2) in enumerate(self._cell_rects):
            if x1 <= x <= x2 and y1 <= y <= y2:
                if i < len(self._state.students):
                    self._open_creator(self._state.students[i])
                return

        # Check start button
        bx1, by1, bx2, by2 = self._btn_rect
        if bx1 <= x <= bx2 and by1 <= y <= by2:
            self._start_game()

    def _open_creator(self, student: Student) -> None:
        """Open the character creator for a student."""
        from src.ui.views.character_creator import CharacterCreatorView
        creator = CharacterCreatorView(
            student=student,
            return_view=self,
        )
        self.window.show_view(creator)

    def _start_game(self) -> None:
        """Transition to the campus view."""
        from src.ui.views.campus import CampusView
        campus = CampusView(state=self._state)
        self.window.show_view(campus)
