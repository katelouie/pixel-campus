"""Student profile view -- full detail panel for a selected student.

Shows portrait, identity, needs, skills, grades, personality preferences,
recent thoughts, and journal entries. ESC returns to campus view.

All text is built into arcade.Text objects once in on_show_view so that
on_draw never calls the slow arcade.draw_text() path.
"""

from pathlib import Path

import arcade

from src.sim.academics import Subject
from src.sim.engine import GameState
from src.sim.models import Skill, Student
from src.sim.needs import NeedType
from src.sim.personality import fmt_romance_interests
from src.ui.hud import _make_nine_slice_texture

_PAPERNOTE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "assets/packs/Complete_UI_Essential_Pack_v2.4/11_Papernote_Theme/Sprites"
)
_CLOSE_BTN_PATH = str(_PAPERNOTE / "UI_Papernote_Button01.png")
_CLOSE_BTN_SIZE = 28   # render size (Button01 is 32px, scale down slightly)

_PANEL_W = 1020
_PANEL_H = 620
_BORDER  = 36   # nine-slice border + inner padding

# Column x-offsets from inner_left
_COL1_W = 180
_COL2_X = _COL1_W + 20
_COL2_W = 280
_COL3_X = _COL2_X + _COL2_W + 20
_COL3_W = 270

_BAR_W  = 170
_BAR_H  = 11
_BAR_SPACING = 20

_LABEL_COLOR  = (40,  30,  20,  255)
_DIM_COLOR    = (80,  70,  55,  200)
_HEADER_COLOR = (30,  20,  10,  255)
_BAR_BG       = (190, 180, 165, 200)

_NEED_COLORS: dict[NeedType, tuple] = {
    NeedType.REST:       ( 70, 130, 180, 255),
    NeedType.FUN:        (218, 165,  32, 255),
    NeedType.SOCIAL:     (219, 112, 147, 255),
    NeedType.ACADEMICS:  ( 60, 179, 113, 255),
    NeedType.CREATIVITY: (147, 112, 219, 255),
    NeedType.ATHLETICS:  (255, 140,   0, 255),
}

_SKILL_COLOR = (100, 149, 237, 255)

_GRADE_COLORS: dict[str, tuple] = {
    "A": ( 60, 179, 113, 255),
    "B": (100, 200, 130, 255),
    "C": (218, 165,  32, 255),
    "D": (255, 140,   0, 255),
    "F": (210,  70,  70, 255),
}


def _fmt(value: str) -> str:
    return value.replace("_", " ").replace("r and b", "R&B").title()


class ProfileView(arcade.View):
    """Full-screen detail panel for one student. ESC returns to the previous view."""

    def __init__(
        self,
        state: GameState,
        student: Student,
        portrait_tex: arcade.Texture,
        return_view: arcade.View,
    ) -> None:
        super().__init__()
        self._state        = state
        self._student      = student
        self._portrait_tex = portrait_tex
        self._return_view  = return_view

        self._panel_tex    = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._close_btn_tex = arcade.load_texture(_CLOSE_BTN_PATH)
        self._screen_cam   = arcade.Camera2D()

        self._panel_sprite:    arcade.Sprite | None = None
        self._portrait_sprite: arcade.Sprite | None = None
        self._panel_left   = 0
        self._panel_bottom = 0

        # Pre-built render data (populated in on_show_view)
        self._texts:    list[arcade.Text]  = []
        self._bar_rects: list[tuple]       = []  # (x1, x2, y1, y2, color)
        self._lines:     list[tuple]       = []  # (x1, y, x2, y, color)

        # Close button (top-right corner of panel)
        self._close_btn:  arcade.Sprite | None = None
        self._close_label: arcade.Text  | None = None
        self._close_rect: tuple[float, float, float, float] = (0, 0, 0, 0)  # x1,y1,x2,y2

    def on_show_view(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)
        self._panel_left   = (w - _PANEL_W) // 2
        self._panel_bottom = (h - _PANEL_H) // 2

        self._panel_sprite = arcade.Sprite(self._panel_tex)
        self._panel_sprite.center_x = self._panel_left   + _PANEL_W // 2
        self._panel_sprite.center_y = self._panel_bottom + _PANEL_H // 2

        self._portrait_sprite = arcade.Sprite(self._portrait_tex, scale=1.5)
        il = self._panel_left   + _BORDER
        it = self._panel_bottom + _PANEL_H - _BORDER
        self._portrait_sprite.center_x = il + _COL1_W // 2
        self._portrait_sprite.center_y = it - 72

        # Close button — top-right corner, inset by half a tile
        btn_cx = self._panel_left + _PANEL_W - 20
        btn_cy = self._panel_bottom + _PANEL_H - 20
        self._close_btn = arcade.Sprite(
            self._close_btn_tex,
            scale=_CLOSE_BTN_SIZE / self._close_btn_tex.width,
        )
        self._close_btn.center_x = btn_cx
        self._close_btn.center_y = btn_cy
        half = _CLOSE_BTN_SIZE // 2
        self._close_rect = (btn_cx - half, btn_cy - half, btn_cx + half, btn_cy + half)
        self._close_label = arcade.Text(
            "✕", btn_cx, btn_cy,
            color=(80, 40, 20, 230), font_size=11, bold=True,
            anchor_x="center", anchor_y="center",
        )

        self._texts.clear()
        self._bar_rects.clear()
        self._lines.clear()
        self._build_all_content()

    def on_draw(self) -> None:
        self._return_view.on_draw()
        with self._screen_cam.activate():
            arcade.draw_lrbt_rectangle_filled(
                0, self.window.width, 0, self.window.height, (0, 0, 0, 140),
            )
            if self._panel_sprite:
                arcade.draw_sprite(self._panel_sprite)
            if self._portrait_sprite:
                arcade.draw_sprite(self._portrait_sprite)
            for x1, x2, y1, y2, color in self._bar_rects:
                arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
            for x1, y1, x2, y2, color in self._lines:
                arcade.draw_line(x1, y1, x2, y2, color, 1)
            for t in self._texts:
                t.draw()
            if self._close_btn:
                arcade.draw_sprite(self._close_btn)
            if self._close_label:
                self._close_label.draw()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(self._return_view)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        x1, y1, x2, y2 = self._close_rect
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.window.show_view(self._return_view)

    # ------------------------------------------------------------------
    # Build phase — called once in on_show_view
    # ------------------------------------------------------------------

    def _build_all_content(self) -> None:
        il = self._panel_left   + _BORDER
        it = self._panel_bottom + _PANEL_H - _BORDER
        ib = self._panel_bottom + _BORDER

        self._build_identity(il, it)
        self._build_traits(il, it - 144 - 14 - 5 * 16 - 20)
        self._build_needs(il + _COL2_X, it)
        self._build_skills(il + _COL2_X, it - 22 - 6 * _BAR_SPACING - 20)
        self._build_grades(il + _COL3_X, it)
        self._build_personality(il + _COL3_X, it - 22 - 6 * 18 - 16)
        self._build_journal_and_thoughts(il, ib)

    def _build_identity(self, il: float, it: float) -> None:
        s  = self._student
        cx = il + _COL1_W // 2
        y  = it - 144 - 14

        self._add_text(s.name, cx, y, _HEADER_COLOR, font_size=13, bold=True,
                       anchor_x="center", anchor_y="center")
        y -= 20

        meta = [
            f"{s.year.value.capitalize()} · Age {s.age}",
            s.personality.zodiac.value.capitalize() if s.personality else "—",
            s.gender.value.replace("_", " ").title(),
            f"{s.mood.icon} {s.mood.name.capitalize()}",
            f"State: {s.state.value.capitalize()}",
        ]
        for line in meta:
            self._add_text(line, cx, y, _LABEL_COLOR, font_size=9,
                           anchor_x="center", anchor_y="center")
            y -= 16

    def _build_traits(self, il: float, top: float) -> None:
        traits = self._student.traits
        if not traits:
            return
        self._section_header(il, top, "TRAITS")
        y = top - 22
        for trait in traits:
            self._add_text(f"• {trait.name}", il, y, _LABEL_COLOR, font_size=9, anchor_y="center")
            y -= 14
            if trait.description:
                self._add_text(trait.description, il + 10, y, _DIM_COLOR, font_size=7,
                               anchor_y="center", width=_COL1_W - 10, multiline=True)
                y -= 14

    def _build_needs(self, x: float, top: float) -> None:
        self._section_header(x, top, "NEEDS")
        y = top - 22
        for need_type, color in _NEED_COLORS.items():
            self._bar(x, y, need_type.value.capitalize(),
                      self._student.needs[need_type].value, color)
            y -= _BAR_SPACING

    def _build_skills(self, x: float, top: float) -> None:
        self._section_header(x, top, "SKILLS")
        y = top - 22
        for skill in Skill:
            self._bar(x, y, skill.value.capitalize(),
                      self._student.skills.get(skill, 0.0), _SKILL_COLOR)
            y -= _BAR_SPACING

    def _build_grades(self, x: float, top: float) -> None:
        self._section_header(x, top, "GRADES")
        y = top - 22
        for subj in Subject:
            if subj not in self._student.grades:
                continue
            grade  = self._student.grades[subj]
            letter = grade.letter_full
            color  = _GRADE_COLORS.get(letter[0], _LABEL_COLOR)
            self._add_text(f"{subj.value.capitalize():<14}", x, y, _LABEL_COLOR,
                           font_size=9, anchor_y="center")
            self._add_text(letter, x + 130, y, color,
                           font_size=10, bold=True, anchor_y="center")
            self._add_text(f"{grade.value:.0f}", x + 155, y, _DIM_COLOR,
                           font_size=8, anchor_y="center")
            y -= 18

    def _build_personality(self, x: float, top: float) -> None:
        if not self._student.personality:
            return
        p = self._student.personality
        self._section_header(x, top, "PERSONALITY")
        y = top - 22
        prefs = [
            ("Music",   _fmt(p.music_genre.value)),
            ("Movies",  _fmt(p.movie_genre.value)),
            ("Views",   _fmt(p.worldview.value)),
            ("Time",    _fmt(p.time_of_day.value)),
            ("Weather", _fmt(p.weather.value)),
            ("Romance", fmt_romance_interests(p.romance_interest)),
        ]
        for label, value in prefs:
            self._add_text(f"{label}:", x, y, _DIM_COLOR, font_size=8, anchor_y="center")
            self._add_text(value, x + 60, y, _LABEL_COLOR, font_size=9, anchor_y="center")
            y -= 17

    def _build_journal_and_thoughts(self, il: float, ib: float) -> None:
        s = self._student

        # Thoughts — bottom of col 1
        thoughts_top = ib + 110
        self._section_header(il, thoughts_top, "THOUGHTS")
        y = thoughts_top - 20
        shown = 0
        for thought in reversed(s.thoughts):
            if shown >= 4:
                break
            sign = "+" if thought.mood_effect >= 0 else ""
            self._add_text(f"{sign}{thought.mood_effect:.0f}  {thought.label}",
                           il, y, _LABEL_COLOR, font_size=8, anchor_y="center")
            y -= 14
            shown += 1
        if not s.thoughts:
            self._add_text("Nothing on their mind.", il, y, _DIM_COLOR,
                           font_size=8, anchor_y="center")

        # Journal — bottom strip, col 2+3
        jx = il + _COL2_X
        journal_top = ib + 110
        self._section_header(jx, journal_top, "JOURNAL")
        y = journal_top - 20
        entries = s.journal[-4:]
        if entries:
            for day, text in reversed(entries):
                self._add_text(f"Day {day}: {text}", jx, y, _LABEL_COLOR,
                               font_size=8, anchor_y="center",
                               width=_COL2_W + 20 + _COL3_W, multiline=True)
                y -= 22
        else:
            self._add_text("No journal entries yet.", jx, y, _DIM_COLOR,
                           font_size=8, anchor_y="center")

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _add_text(self, text: str, x: float, y: float, color: tuple,
                  font_size: int = 9, bold: bool = False,
                  anchor_x: str = "left", anchor_y: str = "baseline",
                  width: int = 0, multiline: bool = False) -> None:
        kwargs: dict = dict(
            color=color, font_size=font_size, bold=bold,
            anchor_x=anchor_x, anchor_y=anchor_y,
        )
        if multiline and width:
            kwargs["width"] = width
            kwargs["multiline"] = True
        self._texts.append(arcade.Text(text, x, y, **kwargs))

    def _section_header(self, x: float, y: float, text: str) -> None:
        self._add_text(text, x, y, _HEADER_COLOR, font_size=9, bold=True, anchor_y="top")
        self._lines.append((x, y - 13, x + _BAR_W, y - 13, (140, 120, 90, 180)))

    def _bar(self, x: float, y: float, label: str, value: float, color: tuple) -> None:
        LABEL_W = 82
        GAP     = 5
        bar_x   = x + LABEL_W + GAP

        self._add_text(label, bar_x - GAP, y, _DIM_COLOR, font_size=8,
                       anchor_x="right", anchor_y="center")
        # Background track
        self._bar_rects.append((bar_x, bar_x + _BAR_W, y - _BAR_H // 2, y + _BAR_H // 2, _BAR_BG))
        # Fill
        fill = int(_BAR_W * max(0.0, min(100.0, value)) / 100.0)
        if fill > 0:
            self._bar_rects.append((bar_x, bar_x + fill, y - _BAR_H // 2, y + _BAR_H // 2, color))
        # Value
        self._add_text(f"{int(value)}", bar_x + _BAR_W + GAP + 2, y, _DIM_COLOR,
                       font_size=8, anchor_y="center")
