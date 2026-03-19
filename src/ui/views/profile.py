"""Student profile view -- full detail panel for a selected student.

Shows portrait, identity, needs, skills, grades, personality preferences,
recent thoughts, and journal entries. A second tab shows all relationships.
ESC returns to campus view.

All text is built into arcade.Text objects once in on_show_view so that
on_draw never calls the slow arcade.draw_text() path.
"""

from pathlib import Path

import arcade

from src.sim.academics import Subject
from src.sim.engine import GameState
from src.sim.models import FriendshipLevel, RomanceLevel, Skill, Student
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
_TAB_H   = 26   # tab strip height at top of inner area

# Column x-offsets from inner_left (profile tab)
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
_TAB_ACTIVE_BG = (220, 210, 190, 220)
_TAB_INACTIVE  = (120, 110,  90, 160)

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

_FRIENDSHIP_COLORS: dict[FriendshipLevel, tuple] = {
    FriendshipLevel.STRANGER:      (130, 120, 100, 180),
    FriendshipLevel.ACQUAINTANCE:  (160, 140,  90, 220),
    FriendshipLevel.FRIEND:        ( 80, 160,  90, 255),
    FriendshipLevel.CLOSE_FRIEND:  ( 80, 130, 200, 255),
    FriendshipLevel.BEST_FRIEND:   (200, 160,  40, 255),
}

_ROMANCE_COLORS: dict[RomanceLevel, tuple] = {
    RomanceLevel.PLATONIC: (130, 120, 100, 160),
    RomanceLevel.CRUSH:    (220, 100, 140, 255),
    RomanceLevel.DATING:   (210,  50,  90, 255),
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

        # Tab state
        self._active_tab: str = "profile"  # "profile" | "relationships"
        self._tab_rects: dict[str, tuple] = {}  # name → (x1, y1, x2, y2)
        self._tab_labels: dict[str, list[arcade.Text]] = {}  # name → [active_text, inactive_text]

        # Profile tab render data
        self._texts:     list[arcade.Text] = []
        self._bar_rects: list[tuple]       = []  # (x1, x2, y1, y2, color)
        self._lines:     list[tuple]       = []  # (x1, y1, x2, y2, color)

        # Relationships tab render data
        self._rel_texts:     list[arcade.Text] = []
        self._rel_bar_rects: list[tuple]       = []
        self._rel_lines:     list[tuple]       = []

        # Close button
        self._close_btn:   arcade.Sprite | None = None
        self._close_label: arcade.Text   | None = None
        self._close_rect: tuple[float, float, float, float] = (0, 0, 0, 0)

    def on_show_view(self) -> None:
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)
        self._panel_left   = (w - _PANEL_W) // 2
        self._panel_bottom = (h - _PANEL_H) // 2

        il = self._panel_left   + _BORDER
        it = self._panel_bottom + _PANEL_H - _BORDER

        self._panel_sprite = arcade.Sprite(self._panel_tex)
        self._panel_sprite.center_x = self._panel_left   + _PANEL_W // 2
        self._panel_sprite.center_y = self._panel_bottom + _PANEL_H // 2

        # Portrait — shifted down by tab strip height
        self._portrait_sprite = arcade.Sprite(self._portrait_tex, scale=1.5)
        self._portrait_sprite.center_x = il + _COL1_W // 2
        self._portrait_sprite.center_y = it - _TAB_H - 72

        # Close button — top-right corner
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

        # Build tab click regions and pre-built label Text objects
        tab_y_center = it - _TAB_H // 2
        tab_w = 110
        tab_x = il
        display = {"profile": "Profile", "relationships": "Relationships"}
        for name in ("profile", "relationships"):
            self._tab_rects[name] = (tab_x, tab_y_center - 10, tab_x + tab_w, tab_y_center + 10)
            cx = tab_x + tab_w // 2
            self._tab_labels[name] = [
                arcade.Text(display[name], cx, tab_y_center,  # active: dark + bold
                            color=_HEADER_COLOR, font_size=8, bold=True,
                            anchor_x="center", anchor_y="center"),
                arcade.Text(display[name], cx, tab_y_center,  # inactive: dim
                            color=_TAB_INACTIVE, font_size=8, bold=False,
                            anchor_x="center", anchor_y="center"),
            ]
            tab_x += tab_w + 8

        # Build content
        self._texts.clear();     self._bar_rects.clear();     self._lines.clear()
        self._rel_texts.clear(); self._rel_bar_rects.clear(); self._rel_lines.clear()
        self._build_profile_tab(il, it)
        self._build_relationships_tab(il, it)

    def on_draw(self) -> None:
        self._return_view.on_draw()
        with self._screen_cam.activate():
            arcade.draw_lrbt_rectangle_filled(
                0, self.window.width, 0, self.window.height, (0, 0, 0, 140),
            )
            if self._panel_sprite:
                arcade.draw_sprite(self._panel_sprite)

            # Tab strip
            self._draw_tabs()

            if self._active_tab == "profile":
                if self._portrait_sprite:
                    arcade.draw_sprite(self._portrait_sprite)
                for x1, x2, y1, y2, color in self._bar_rects:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
                for x1, y1, x2, y2, color in self._lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for t in self._texts:
                    t.draw()
            else:
                for x1, x2, y1, y2, color in self._rel_bar_rects:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
                for x1, y1, x2, y2, color in self._rel_lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for t in self._rel_texts:
                    t.draw()

            if self._close_btn:
                arcade.draw_sprite(self._close_btn)
            if self._close_label:
                self._close_label.draw()

    def _draw_tabs(self) -> None:
        for name, (x1, y1, x2, y2) in self._tab_rects.items():
            if name == self._active_tab:
                arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, _TAB_ACTIVE_BG)
            idx = 0 if name == self._active_tab else 1
            self._tab_labels[name][idx].draw()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(self._return_view)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        # Close button
        x1, y1, x2, y2 = self._close_rect
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.window.show_view(self._return_view)
            return
        # Tab clicks
        for name, (tx1, ty1, tx2, ty2) in self._tab_rects.items():
            if tx1 <= x <= tx2 and ty1 <= y <= ty2:
                self._active_tab = name
                return

    # ------------------------------------------------------------------
    # Profile tab build
    # ------------------------------------------------------------------

    def _build_profile_tab(self, il: float, it: float) -> None:
        ib = self._panel_bottom + _BORDER
        ct = it - _TAB_H  # content top, below tab strip

        self._build_identity(il, ct)
        self._build_traits(il, ct - 144 - 14 - 5 * 16 - 20)
        self._build_needs(il + _COL2_X, ct)
        self._build_skills(il + _COL2_X, ct - 22 - 6 * _BAR_SPACING - 20)
        self._build_grades(il + _COL3_X, ct)
        self._build_personality(il + _COL3_X, ct - 22 - 6 * 18 - 16)
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

        thoughts_top = ib + 110
        self._section_header(il, thoughts_top, "THOUGHTS")
        y = thoughts_top - 20
        shown = 0
        for thought in reversed(s.thoughts):
            if shown >= 6:
                break
            sign = "+" if thought.mood_effect >= 0 else ""
            self._add_text(f"{sign}{thought.mood_effect:.0f}  {thought.label}",
                           il, y, _LABEL_COLOR, font_size=8, anchor_y="center")
            y -= 14
            shown += 1
        if not s.thoughts:
            self._add_text("Nothing on their mind.", il, y, _DIM_COLOR,
                           font_size=8, anchor_y="center")

        jx = il + _COL2_X
        journal_top = ib + 110
        self._section_header(jx, journal_top, "JOURNAL")
        y = journal_top - 20
        entries = s.journal[-6:]
        if entries:
            for entry in reversed(entries):
                header = f"Day {entry.day} — {entry.period_label}"
                self._add_text(header, jx, y, _DIM_COLOR,
                               font_size=7, anchor_y="center")
                y -= 13
                self._add_text(entry.text, jx, y, _LABEL_COLOR,
                               font_size=8, anchor_y="center",
                               width=_COL2_W + 20 + _COL3_W, multiline=True)
                y -= 22
        else:
            self._add_text("No journal entries yet.", jx, y, _DIM_COLOR,
                           font_size=8, anchor_y="center")

    # ------------------------------------------------------------------
    # Relationships tab build
    # ------------------------------------------------------------------

    def _build_relationships_tab(self, il: float, it: float) -> None:
        s   = self._student
        ct  = it - _TAB_H - 8  # content top, a little padding below tab strip
        ib  = self._panel_bottom + _BORDER
        sid = s.student_id

        # Column layout (full inner width)
        inner_w = _COL1_W + 20 + _COL2_W + 20 + _COL3_W  # ~590
        col_name   = il
        col_friend = il + 145
        col_rom_me = il + 330   # my feelings → them
        col_rom_them = il + 460 # their feelings → me
        col_status = il + 590   # mutual status label

        # Section header
        self._rel_section_header(il, ct, "RELATIONSHIPS")
        y = ct - 22

        # Column headers
        for text, x in (
            ("NAME",        col_name),
            ("FRIENDSHIP",  col_friend),
            ("MY FEELINGS", col_rom_me),
            ("THEIR FEELINGS", col_rom_them),
            ("STATUS",      col_status),
        ):
            self._add_rel_text(text, x, y, _DIM_COLOR, font_size=7, bold=True)
        y -= 4
        # Header underline
        self._rel_lines.append((il, y, il + inner_w, y, (140, 120, 90, 140)))
        y -= 12

        # Build sorted student list: dating first, then crush, then by friendship level desc
        others = [st for st in self._state.students if st.student_id != sid]

        def _sort_key(other: Student) -> tuple:
            key = (min(sid, other.student_id), max(sid, other.student_id))
            rom = self._state.romances.get(key)
            fri = self._state.friendships.get(key)
            rom_score = 0
            if rom:
                if rom.is_dating:
                    rom_score = 3
                elif rom.is_mutual_crush:
                    rom_score = 2
                elif rom.is_unrequited:
                    rom_score = 1
            fri_level = fri.level if fri else FriendshipLevel.STRANGER
            return (-rom_score, -int(fri_level), other.name)

        others.sort(key=_sort_key)

        row_h = 18
        for other in others:
            if y < ib + 8:
                break
            key = (min(sid, other.student_id), max(sid, other.student_id))
            fri = self._state.friendships.get(key)
            rom = self._state.romances.get(key)

            fri_level   = fri.level   if fri else FriendshipLevel.STRANGER
            fri_affinity = fri.affinity if fri else 0
            fri_color   = _FRIENDSHIP_COLORS.get(fri_level, _DIM_COLOR)

            # Name
            self._add_rel_text(other.name, col_name, y, _LABEL_COLOR, font_size=9)

            # Friendship level + mini affinity bar
            fri_label = fri_level.name.replace("_", " ").title()
            self._add_rel_text(fri_label, col_friend, y, fri_color, font_size=8)
            bar_x = col_friend + 90
            bar_w = 50
            self._rel_bar_rects.append((bar_x, bar_x + bar_w, y - 4, y + 4, _BAR_BG))
            fill = int(bar_w * min(100, fri_affinity) / 100)
            if fill > 0:
                self._rel_bar_rects.append((bar_x, bar_x + fill, y - 4, y + 4, fri_color))

            # Romance columns
            if rom:
                my_feelings   = rom.feelings_of(sid)
                their_feelings = rom.feelings_of(other.student_id)

                my_color   = _ROMANCE_COLORS.get(my_feelings, _DIM_COLOR)
                their_color = _ROMANCE_COLORS.get(their_feelings, _DIM_COLOR)

                if my_feelings != RomanceLevel.PLATONIC:
                    self._add_rel_text(
                        my_feelings.name.title(), col_rom_me, y, my_color, font_size=8
                    )
                if their_feelings != RomanceLevel.PLATONIC:
                    self._add_rel_text(
                        their_feelings.name.title(), col_rom_them, y, their_color, font_size=8
                    )

                # Status label
                if rom.is_dating:
                    self._add_rel_text("Dating!", col_status, y, (210, 50, 90, 255), font_size=8, bold=True)
                elif rom.is_mutual_crush:
                    self._add_rel_text("Mutual crush", col_status, y, (220, 100, 140, 255), font_size=8)
                elif rom.is_unrequited:
                    crusher_id = sid if my_feelings > RomanceLevel.PLATONIC else other.student_id
                    label = "I like them" if crusher_id == sid else "They like me"
                    self._add_rel_text(label, col_status, y, (180, 120, 140, 200), font_size=8)

            y -= row_h

        if not others:
            self._add_rel_text("No other students.", il, y, _DIM_COLOR, font_size=8)

    # ------------------------------------------------------------------
    # Build helpers (profile tab)
    # ------------------------------------------------------------------

    def _add_text(self, text: str, x: float, y: float, color: tuple,
                  font_size: int = 9, bold: bool = False,
                  anchor_x: str = "left", anchor_y: str = "baseline",
                  width: int = 0, multiline: bool = False) -> None:
        kwargs: dict = dict(color=color, font_size=font_size, bold=bold,
                            anchor_x=anchor_x, anchor_y=anchor_y)
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
        self._bar_rects.append((bar_x, bar_x + _BAR_W, y - _BAR_H // 2, y + _BAR_H // 2, _BAR_BG))
        fill = int(_BAR_W * max(0.0, min(100.0, value)) / 100.0)
        if fill > 0:
            self._bar_rects.append((bar_x, bar_x + fill, y - _BAR_H // 2, y + _BAR_H // 2, color))
        self._add_text(f"{int(value)}", bar_x + _BAR_W + GAP + 2, y, _DIM_COLOR,
                       font_size=8, anchor_y="center")

    # ------------------------------------------------------------------
    # Build helpers (relationships tab)
    # ------------------------------------------------------------------

    def _add_rel_text(self, text: str, x: float, y: float, color: tuple,
                      font_size: int = 9, bold: bool = False) -> None:
        self._rel_texts.append(arcade.Text(
            text, x, y, color=color, font_size=font_size, bold=bold,
            anchor_y="center",
        ))

    def _rel_section_header(self, x: float, y: float, text: str) -> None:
        self._add_rel_text(text, x, y, _HEADER_COLOR, font_size=9, bold=True)
        inner_w = _COL1_W + 20 + _COL2_W + 20 + _COL3_W
        self._rel_lines.append((x, y - 13, x + inner_w, y - 13, (140, 120, 90, 180)))
