"""Student profile view -- full detail panel for a selected student.

Shows portrait, identity, needs, skills, grades, personality preferences,
recent thoughts, and a scrollable journal. A second tab shows all relationships.
ESC returns to campus view.

The journal is the primary interface — it occupies the right 2/3 of the panel
and is scrollable via mouse wheel. Stats live in a compact left sidebar.
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
_CLOSE_BTN_SIZE = 28

_PANEL_W = 1020
_PANEL_H = 620
_BORDER  = 36
_TAB_H   = 26

# Layout: left sidebar for stats, right area for journal
_SIDEBAR_W = 340
_JOURNAL_X = _SIDEBAR_W + 20   # journal starts after sidebar + gap
_JOURNAL_W = _PANEL_W - _BORDER * 2 - _JOURNAL_X  # fills remaining width

# Sidebar sub-columns for needs+grades side by side
_NEEDS_W   = 170
_GRADES_X  = _NEEDS_W + 10

_BAR_W  = 80
_BAR_H  = 9
_BAR_SPACING = 16

_LABEL_COLOR  = (40,  30,  20,  255)
_DIM_COLOR    = (80,  70,  55,  200)
_HEADER_COLOR = (30,  20,  10,  255)
_BAR_BG       = (190, 180, 165, 200)
_TAB_ACTIVE_BG = (220, 210, 190, 220)
_TAB_INACTIVE  = (120, 110,  90, 160)
_JOURNAL_TIMESTAMP = (110, 90, 65, 200)
_JOURNAL_TEXT      = (45, 35, 25, 255)
_SCROLL_HINT       = (140, 120, 90, 160)

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

# Journal entry height (timestamp line + text line + spacing)
_JOURNAL_ENTRY_H = 38


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
        self._active_tab: str = "profile"
        self._tab_rects: dict[str, tuple] = {}
        self._tab_labels: dict[str, list[arcade.Text]] = {}

        # Profile tab render data (sidebar)
        self._texts:     list[arcade.Text] = []
        self._bar_rects: list[tuple]       = []
        self._lines:     list[tuple]       = []

        # Journal render data (rebuilt on scroll)
        self._journal_texts: list[arcade.Text] = []
        self._journal_lines: list[tuple]       = []
        self._journal_scroll: int = 0  # 0 = newest entries visible at top
        self._journal_max_scroll: int = 0
        self._journal_area_top: float = 0
        self._journal_area_bottom: float = 0
        self._journal_area_left: float = 0

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

        # Portrait
        self._portrait_sprite = arcade.Sprite(self._portrait_tex, scale=1.5)
        self._portrait_sprite.center_x = il + 48
        self._portrait_sprite.center_y = it - _TAB_H - 48

        # Close button
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

        # Tab strip
        tab_y_center = it - _TAB_H // 2
        tab_w = 110
        tab_x = il
        display = {"profile": "Profile", "relationships": "Relationships"}
        for name in ("profile", "relationships"):
            self._tab_rects[name] = (tab_x, tab_y_center - 10, tab_x + tab_w, tab_y_center + 10)
            cx = tab_x + tab_w // 2
            self._tab_labels[name] = [
                arcade.Text(display[name], cx, tab_y_center,
                            color=_HEADER_COLOR, font_size=8, bold=True,
                            anchor_x="center", anchor_y="center"),
                arcade.Text(display[name], cx, tab_y_center,
                            color=_TAB_INACTIVE, font_size=8, bold=False,
                            anchor_x="center", anchor_y="center"),
            ]
            tab_x += tab_w + 8

        # Store journal area bounds for scroll rebuilds
        ct = it - _TAB_H
        ib = self._panel_bottom + _BORDER
        self._journal_area_top = ct - 4
        self._journal_area_bottom = ib + 8
        self._journal_area_left = il + _JOURNAL_X

        # Build content
        self._texts.clear();     self._bar_rects.clear();     self._lines.clear()
        self._rel_texts.clear(); self._rel_bar_rects.clear(); self._rel_lines.clear()
        self._build_sidebar(il, it)
        self._rebuild_journal()
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
                # Journal (separate list, rebuilt on scroll)
                for x1, y1, x2, y2, color in self._journal_lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for t in self._journal_texts:
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
        x1, y1, x2, y2 = self._close_rect
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.window.show_view(self._return_view)
            return
        for name, (tx1, ty1, tx2, ty2) in self._tab_rects.items():
            if tx1 <= x <= tx2 and ty1 <= y <= ty2:
                self._active_tab = name
                return

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        """Scroll journal entries. scroll_y > 0 = scroll up (older), < 0 = scroll down (newer)."""
        if self._active_tab != "profile":
            return
        old = self._journal_scroll
        self._journal_scroll = max(0, min(self._journal_max_scroll,
                                          self._journal_scroll - int(scroll_y)))
        if self._journal_scroll != old:
            self._rebuild_journal()

    # ------------------------------------------------------------------
    # Sidebar (left column: portrait, identity, traits, needs, grades, thoughts)
    # ------------------------------------------------------------------

    def _build_sidebar(self, il: float, it: float) -> None:
        ib = self._panel_bottom + _BORDER
        ct = it - _TAB_H

        self._build_identity(il, ct)
        self._build_traits(il, ct - 110)
        self._build_needs_and_grades(il, ct - 220)
        self._build_thoughts(il, ib)

    def _build_identity(self, il: float, it: float) -> None:
        s  = self._student
        x  = il + 100  # right of portrait
        y  = it - 10

        self._add_text(s.name, x, y, _HEADER_COLOR, font_size=13, bold=True,
                       anchor_y="top")
        y -= 20

        meta = [
            f"{s.year.value.capitalize()} · Age {s.age} · {s.gender.value.replace('_', ' ').title()}",
            s.personality.zodiac.value.capitalize() if s.personality else "—",
            f"{s.mood.icon} {s.mood.name.capitalize()} ({int(s.mood_value)})",
        ]
        for line in meta:
            self._add_text(line, x, y, _LABEL_COLOR, font_size=8, anchor_y="top")
            y -= 14

        # Traits inline
        if s.traits:
            trait_str = " · ".join(t.name for t in s.traits)
            self._add_text(trait_str, x, y, _DIM_COLOR, font_size=8, anchor_y="top")

    def _build_traits(self, il: float, top: float) -> None:
        traits = self._student.traits
        if not traits:
            return
        y = top
        for trait in traits:
            if trait.description:
                self._add_text(f"{trait.name}: {trait.description}", il, y, _DIM_COLOR,
                               font_size=7, anchor_y="top", width=_SIDEBAR_W, multiline=True)
                y -= 22

    def _build_needs_and_grades(self, il: float, top: float) -> None:
        s = self._student

        # Needs (left sub-column)
        self._section_header(il, top, "NEEDS")
        y = top - 18
        for need_type, color in _NEED_COLORS.items():
            self._compact_bar(il, y, need_type.value[:4].upper(),
                              s.needs[need_type].value, color)
            y -= _BAR_SPACING

        # Grades (right sub-column, same top)
        gx = il + _GRADES_X
        self._section_header(gx, top, "GRADES")
        gy = top - 18
        for subj in Subject:
            if subj not in s.grades:
                continue
            grade  = s.grades[subj]
            letter = grade.letter_full
            color  = _GRADE_COLORS.get(letter[0], _LABEL_COLOR)
            self._add_text(f"{subj.value[:6].capitalize()}", gx, gy, _DIM_COLOR,
                           font_size=8, anchor_y="center")
            self._add_text(letter, gx + 55, gy, color,
                           font_size=9, bold=True, anchor_y="center")
            gy -= 15

    def _build_thoughts(self, il: float, ib: float) -> None:
        s = self._student
        top = ib + 90
        self._section_header(il, top, "THOUGHTS")
        y = top - 18
        shown = 0
        for thought in reversed(s.thoughts):
            if shown >= 4:
                break
            sign = "+" if thought.mood_effect >= 0 else ""
            label = thought.label
            if len(label) > 45:
                label = label[:42] + "..."
            self._add_text(f"{sign}{thought.mood_effect:.0f}  {label}",
                           il, y, _LABEL_COLOR, font_size=7, anchor_y="center")
            y -= 13
            shown += 1
        if not s.thoughts:
            self._add_text("Nothing on their mind.", il, y, _DIM_COLOR,
                           font_size=7, anchor_y="center")

    # ------------------------------------------------------------------
    # Journal (right panel, scrollable)
    # ------------------------------------------------------------------

    def _rebuild_journal(self) -> None:
        """Rebuild visible journal Text objects based on current scroll offset."""
        self._journal_texts.clear()
        self._journal_lines.clear()

        s = self._student
        jx = self._journal_area_left
        jw = _JOURNAL_W
        top = self._journal_area_top
        bottom = self._journal_area_bottom
        available_h = top - bottom

        # Header
        self._journal_texts.append(arcade.Text(
            "JOURNAL", jx, top, color=_HEADER_COLOR,
            font_size=10, bold=True, anchor_y="top",
        ))
        self._journal_lines.append((jx, top - 14, jx + jw, top - 14, (140, 120, 90, 180)))

        content_top = top - 20
        content_h = content_top - bottom

        # How many entries can fit?
        visible_count = max(1, int(content_h / _JOURNAL_ENTRY_H))

        # Entries are newest-first
        entries = list(reversed(s.journal))
        total = len(entries)
        self._journal_max_scroll = max(0, total - visible_count)

        if not entries:
            self._journal_texts.append(arcade.Text(
                "No journal entries yet.", jx, content_top - 10,
                color=_DIM_COLOR, font_size=9, anchor_y="top",
            ))
            return

        # Slice visible entries based on scroll
        start = self._journal_scroll
        end = min(start + visible_count, total)
        visible = entries[start:end]

        y = content_top
        for entry in visible:
            # Timestamp line
            timestamp = f"Day {entry.day} — {entry.time_label}"
            self._journal_texts.append(arcade.Text(
                timestamp, jx, y, color=_JOURNAL_TIMESTAMP,
                font_size=7, anchor_y="top",
            ))
            y -= 12

            # Entry text (word-wrapped)
            text = entry.text
            self._journal_texts.append(arcade.Text(
                text, jx, y, color=_JOURNAL_TEXT,
                font_size=8, anchor_y="top",
                width=jw, multiline=True,
            ))
            y -= 24  # base entry text height

            # Light separator
            y -= 2

        # Scroll hints
        if self._journal_scroll > 0:
            self._journal_texts.append(arcade.Text(
                "▲ newer", jx + jw - 50, top - 6,
                color=_SCROLL_HINT, font_size=7, anchor_y="top",
            ))
        if self._journal_scroll < self._journal_max_scroll:
            self._journal_texts.append(arcade.Text(
                "▼ older", jx + jw - 50, bottom + 2,
                color=_SCROLL_HINT, font_size=7, anchor_y="bottom",
            ))

    # ------------------------------------------------------------------
    # Relationships tab build
    # ------------------------------------------------------------------

    def _build_relationships_tab(self, il: float, it: float) -> None:
        s   = self._student
        ct  = it - _TAB_H - 8
        ib  = self._panel_bottom + _BORDER
        sid = s.student_id

        inner_w = _PANEL_W - _BORDER * 2
        col_name   = il
        col_friend = il + 145
        col_rom_me = il + 330
        col_rom_them = il + 460
        col_status = il + 590

        self._rel_section_header(il, ct, "RELATIONSHIPS")
        y = ct - 22

        for text, x in (
            ("NAME",        col_name),
            ("FRIENDSHIP",  col_friend),
            ("MY FEELINGS", col_rom_me),
            ("THEIR FEELINGS", col_rom_them),
            ("STATUS",      col_status),
        ):
            self._add_rel_text(text, x, y, _DIM_COLOR, font_size=7, bold=True)
        y -= 4
        self._rel_lines.append((il, y, il + inner_w, y, (140, 120, 90, 140)))
        y -= 12

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

            self._add_rel_text(other.name, col_name, y, _LABEL_COLOR, font_size=9)

            fri_label = fri_level.name.replace("_", " ").title()
            self._add_rel_text(fri_label, col_friend, y, fri_color, font_size=8)
            bar_x = col_friend + 90
            bar_w = 50
            self._rel_bar_rects.append((bar_x, bar_x + bar_w, y - 4, y + 4, _BAR_BG))
            fill = int(bar_w * min(100, fri_affinity) / 100)
            if fill > 0:
                self._rel_bar_rects.append((bar_x, bar_x + fill, y - 4, y + 4, fri_color))

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
    # Build helpers (sidebar)
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
        self._add_text(text, x, y, _HEADER_COLOR, font_size=8, bold=True, anchor_y="top")
        self._lines.append((x, y - 11, x + 140, y - 11, (140, 120, 90, 180)))

    def _compact_bar(self, x: float, y: float, label: str, value: float, color: tuple) -> None:
        """Compact bar: short label + thin bar + value number."""
        LABEL_W = 35
        GAP = 3
        bar_x = x + LABEL_W + GAP
        self._add_text(label, bar_x - GAP, y, _DIM_COLOR, font_size=7,
                       anchor_x="right", anchor_y="center")
        self._bar_rects.append((bar_x, bar_x + _BAR_W, y - _BAR_H // 2, y + _BAR_H // 2, _BAR_BG))
        fill = int(_BAR_W * max(0.0, min(100.0, value)) / 100.0)
        if fill > 0:
            self._bar_rects.append((bar_x, bar_x + fill, y - _BAR_H // 2, y + _BAR_H // 2, color))
        self._add_text(f"{int(value)}", bar_x + _BAR_W + GAP + 2, y, _DIM_COLOR,
                       font_size=7, anchor_y="center")

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
        inner_w = _PANEL_W - _BORDER * 2
        self._rel_lines.append((x, y - 13, x + inner_w, y - 13, (140, 120, 90, 180)))
