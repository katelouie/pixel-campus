"""Student profile view -- full detail panel for a selected student.

Shows portrait, identity, needs, skills, grades, personality preferences,
recent thoughts, and a scrollable journal. A second tab shows all relationships.
ESC returns to campus view.

The journal is the primary interface — it occupies the right 2/3 of the panel
and is scrollable via mouse wheel. Stats live in a compact left sidebar.

All text uses the pixel-perfect BitmapFont renderer for crisp display.
"""

from pathlib import Path

import arcade

from src.sim.academics import Subject
from src.sim.engine import GameState
from src.sim.models import FriendshipLevel, RomanceLevel, Skill, Student
from src.sim.needs import NeedType
from src.sim.personality import fmt_romance_interests
from src.ui.bitmap_font import BitmapFont
from src.ui.font import (
    COLOR_DIM, COLOR_HEADER, COLOR_JOURNAL, COLOR_LABEL, COLOR_SCROLL,
    COLOR_TIMESTAMP, COLOR_WHITE,
    FONT, FONT_DIM, FONT_HEADER, FONT_JOURNAL, FONT_SCROLL, FONT_TIMESTAMP,
)
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
_JOURNAL_X = _SIDEBAR_W + 20
_JOURNAL_W = _PANEL_W - _BORDER * 2 - _JOURNAL_X

# Sidebar sub-columns for needs+grades side by side
_NEEDS_W   = 170
_GRADES_X  = _NEEDS_W + 10

_BAR_W  = 80
_BAR_H  = 9
_BAR_SPACING = 16

_TAB_ACTIVE_BG = (220, 210, 190, 220)
_TAB_INACTIVE_COLOR = (120, 110, 90, 160)
_BAR_BG = (190, 180, 165, 200)

_NEED_COLORS: dict[NeedType, tuple] = {
    NeedType.REST:       ( 70, 130, 180, 255),
    NeedType.FUN:        (218, 165,  32, 255),
    NeedType.SOCIAL:     (219, 112, 147, 255),
    NeedType.ACADEMICS:  ( 60, 179, 113, 255),
    NeedType.CREATIVITY: (147, 112, 219, 255),
    NeedType.ATHLETICS:  (255, 140,   0, 255),
}

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

# Line height for bitmap font text
_LH = FONT.char_height  # 24px at scale 2


def _fmt(value: str) -> str:
    return value.replace("_", " ").replace("r and b", "R&B").title()


def _bmp_sprite(font: BitmapFont, text: str, x: float, y: float,
                color: tuple | None = None) -> arcade.Sprite:
    """Create a positioned sprite from a bitmap font texture. Anchored top-left."""
    tex = font.get_texture(text, color)
    sp = arcade.Sprite(tex)
    sp.left = x
    sp.top = y
    return sp


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

        # Animated portrait frames (talking animation, row 1 of portrait sheet)
        self._portrait_frames: list[arcade.Texture] = []
        self._portrait_anim_frame: int = 0
        self._portrait_anim_timer: int = 0
        if student.appearance:
            from src.ui.character_composer import composite_portrait_sheet
            sheet = composite_portrait_sheet(student.appearance)
            _CELL = 96
            for col in range(10):
                frame_img = sheet.crop((col * _CELL, 0, (col+1) * _CELL, _CELL))
                self._portrait_frames.append(arcade.Texture(frame_img))

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
        self._tab_sprites: dict[str, dict[str, arcade.Sprite]] = {}

        # Sidebar sprites (static)
        self._sidebar_sprites: list[arcade.Sprite] = []
        self._bar_rects: list[tuple] = []
        self._lines: list[tuple] = []

        # Unified hover tooltip system
        # Each hitbox: (x1, y1, x2, y2, tooltip_text, anchor="below"|"above", tab="profile"|"relationships")
        self._hover_hitboxes: list[tuple[float, float, float, float, str, str, str]] = []
        self._hover_active: bool = False
        self._hover_bg: tuple | None = None       # (x1, x2, y1, y2, color)
        self._hover_border: tuple | None = None    # (x1, x2, y1, y2, color)
        self._hover_sprites: list[arcade.Sprite] = []

        # Journal sprites (rebuilt on scroll)
        self._journal_sprites: list[arcade.Sprite] = []
        self._journal_lines: list[tuple] = []
        self._journal_scroll: int = 0
        self._journal_max_scroll: int = 0
        self._journal_area_top: float = 0
        self._journal_area_bottom: float = 0
        self._journal_area_left: float = 0

        # Relationships tab
        self._rel_sprites: list[arcade.Sprite] = []
        self._rel_bar_rects: list[tuple] = []
        self._rel_lines: list[tuple] = []
        # Animated portrait heads for relationship rows
        self._rel_portraits: list[tuple[list[arcade.Texture], float, float]] = []  # (frames, cx, cy)
        self._rel_anim_frame: int = 0
        self._rel_anim_timer: int = 0

        # Details tab
        self._det_sprites: list[arcade.Sprite] = []
        self._det_bar_rects: list[tuple] = []
        self._det_lines: list[tuple] = []

        # Close button
        self._close_btn: arcade.Sprite | None = None
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
        # Portrait: 96x96 composited head portrait (or 48x96 idle fallback)
        portrait_h = self._portrait_tex.height
        scale = 1.0 if portrait_h == 96 else 1.5  # head portrait vs full-body fallback
        self._portrait_sprite = arcade.Sprite(self._portrait_tex, scale=scale)
        self._portrait_sprite.center_x = il + 48
        self._portrait_sprite.center_y = it - _TAB_H - 52

        # Close button (nudged down a few px)
        btn_cx = self._panel_left + _PANEL_W - 22
        btn_cy = self._panel_bottom + _PANEL_H - 24
        self._close_btn = arcade.Sprite(
            self._close_btn_tex,
            scale=_CLOSE_BTN_SIZE / self._close_btn_tex.width,
        )
        self._close_btn.center_x = btn_cx
        self._close_btn.center_y = btn_cy
        half = _CLOSE_BTN_SIZE // 2
        self._close_rect = (btn_cx - half, btn_cy - half, btn_cx + half, btn_cy + half)
        # Bitmap "X" label on the button
        x_tex = FONT_HEADER.get_texture("X")
        self._close_x_sprite = arcade.Sprite(x_tex)
        self._close_x_sprite.center_x = btn_cx
        self._close_x_sprite.center_y = btn_cy

        # Tab strip (width based on label length + padding)
        tab_y = it - _TAB_H // 2
        tab_x = il
        tab_pad = 24  # horizontal padding inside each tab
        tab_gap = 10  # space between tabs
        for name, label in (("profile", "Profile"), ("relationships", "Relationships"), ("details", "Details")):
            label_tex = FONT_HEADER.get_texture(label)
            tab_w = label_tex.width + tab_pad
            self._tab_rects[name] = (tab_x, tab_y - 10, tab_x + tab_w, tab_y + 10)
            active_sp = _bmp_sprite(FONT_HEADER, label, tab_x + tab_pad // 2, tab_y + _LH // 2)
            inactive_sp = _bmp_sprite(
                BitmapFont(scale=2, color=_TAB_INACTIVE_COLOR), label, tab_x + tab_pad // 2, tab_y + _LH // 2,
            )
            self._tab_sprites[name] = {"active": active_sp, "inactive": inactive_sp}
            tab_x += tab_w + tab_gap

        # Journal area bounds
        ct = it - _TAB_H
        ib = self._panel_bottom + _BORDER
        self._journal_area_top = ct - 4
        self._journal_area_bottom = ib + 8
        self._journal_area_left = il + _JOURNAL_X

        # Build content
        self._sidebar_sprites.clear(); self._bar_rects.clear(); self._lines.clear()
        self._hover_hitboxes.clear()
        self._rel_sprites.clear(); self._rel_bar_rects.clear(); self._rel_lines.clear()
        self._det_sprites.clear(); self._det_bar_rects.clear(); self._det_lines.clear()
        self._build_sidebar(il, it)
        self._rebuild_journal()
        self._build_relationships_tab(il, it)
        self._build_details_tab(il, it)

    def on_draw(self) -> None:
        self._return_view.on_draw()
        with self._screen_cam.activate():
            arcade.draw_lrbt_rectangle_filled(
                0, self.window.width, 0, self.window.height, (0, 0, 0, 140),
            )
            if self._panel_sprite:
                arcade.draw_sprite(self._panel_sprite)

            # Tab strip
            for name, (x1, y1, x2, y2) in self._tab_rects.items():
                if name == self._active_tab:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, _TAB_ACTIVE_BG)
                key = "active" if name == self._active_tab else "inactive"
                arcade.draw_sprite(self._tab_sprites[name][key])

            if self._active_tab == "profile":
                if self._portrait_sprite:
                    # Animate talking portrait
                    if self._portrait_frames:
                        self._portrait_anim_timer += 1
                        if self._portrait_anim_timer >= 6:  # gentle pace
                            self._portrait_anim_timer = 0
                            self._portrait_anim_frame = (self._portrait_anim_frame + 1) % len(self._portrait_frames)
                        self._portrait_sprite.texture = self._portrait_frames[self._portrait_anim_frame]
                    arcade.draw_sprite(self._portrait_sprite)
                for x1, x2, y1, y2, color in self._bar_rects:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
                for x1, y1, x2, y2, color in self._lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for sp in self._sidebar_sprites:
                    arcade.draw_sprite(sp)
                # Hover tooltip (traits, needs, relationship bars)
                if self._hover_active and self._hover_bg:
                    bx1, bx2, by1, by2, bg_color = self._hover_bg
                    arcade.draw_lrbt_rectangle_filled(bx1, bx2, by1, by2, bg_color)
                    if self._hover_border:
                        ox1, ox2, oy1, oy2, border_color = self._hover_border
                        arcade.draw_lrbt_rectangle_outline(ox1, ox2, oy1, oy2, border_color, 2)
                    for sp in self._hover_sprites:
                        arcade.draw_sprite(sp)
                # Journal
                for x1, y1, x2, y2, color in self._journal_lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for sp in self._journal_sprites:
                    arcade.draw_sprite(sp)
            elif self._active_tab == "relationships":
                # Animate talking head portraits
                self._rel_anim_timer += 1
                if self._rel_anim_timer >= 8:
                    self._rel_anim_timer = 0
                    self._rel_anim_frame = (self._rel_anim_frame + 1) % 10
                for frames, pcx, pcy in self._rel_portraits:
                    if frames:
                        frame_idx = self._rel_anim_frame % len(frames)
                        arcade.draw_texture_rect(
                            frames[frame_idx],
                            arcade.XYWH(pcx, pcy, 44, 44),
                        )
                for x1, x2, y1, y2, color in self._rel_bar_rects:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
                for x1, y1, x2, y2, color in self._rel_lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for sp in self._rel_sprites:
                    arcade.draw_sprite(sp)
                # Hover tooltip on relationships tab too
                if self._hover_active and self._hover_bg:
                    bx1, bx2, by1, by2, bg_color = self._hover_bg
                    arcade.draw_lrbt_rectangle_filled(bx1, bx2, by1, by2, bg_color)
                    if self._hover_border:
                        ox1, ox2, oy1, oy2, border_color = self._hover_border
                        arcade.draw_lrbt_rectangle_outline(ox1, ox2, oy1, oy2, border_color, 2)
                    for sp in self._hover_sprites:
                        arcade.draw_sprite(sp)

            elif self._active_tab == "details":
                for x1, x2, y1, y2, color in self._det_bar_rects:
                    arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, color)
                for x1, y1, x2, y2, color in self._det_lines:
                    arcade.draw_line(x1, y1, x2, y2, color, 1)
                for sp in self._det_sprites:
                    arcade.draw_sprite(sp)
                if self._hover_active and self._hover_bg:
                    bx1, bx2, by1, by2, bg_color = self._hover_bg
                    arcade.draw_lrbt_rectangle_filled(bx1, bx2, by1, by2, bg_color)
                    if self._hover_border:
                        ox1, ox2, oy1, oy2, border_color = self._hover_border
                        arcade.draw_lrbt_rectangle_outline(ox1, ox2, oy1, oy2, border_color, 2)
                    for sp in self._hover_sprites:
                        arcade.draw_sprite(sp)

            if self._close_btn:
                arcade.draw_sprite(self._close_btn)
                arcade.draw_sprite(self._close_x_sprite)

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

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Update hover tooltip (unified for traits, needs, relationship bars)."""
        self._hover_active = False
        self._hover_bg = None
        self._hover_border = None
        self._hover_sprites.clear()

        for hx1, hy1, hx2, hy2, text, anchor, tab in self._hover_hitboxes:
            if tab != self._active_tab:
                continue
            if hx1 <= x <= hx2 and hy1 <= y <= hy2 and text:
                tooltip_font = BitmapFont(scale=2, color=(50, 40, 30, 255))
                lines = tooltip_font.wrap_lines(text, _SIDEBAR_W - 16)

                pad = 6
                line_h = tooltip_font.char_height
                total_h = len(lines) * line_h + pad * 2
                max_line_w = max(len(l) * tooltip_font.char_width for l in lines)
                total_w = max_line_w + pad * 2

                # Position: below or above the hitbox
                tx = hx1
                if anchor == "above":
                    ty = hy2 + total_h + 4
                else:
                    ty = hy1 - 4

                self._hover_bg = (tx - pad, tx + total_w - pad,
                                  ty - total_h, ty,
                                  (245, 235, 220, 245))
                self._hover_border = (tx - pad, tx + total_w - pad,
                                      ty - total_h, ty,
                                      (160, 130, 100, 200))

                line_y = ty - pad
                for line in lines:
                    sp = _bmp_sprite(tooltip_font, line, tx, line_y)
                    self._hover_sprites.append(sp)
                    line_y -= line_h

                self._hover_active = True
                break

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        if self._active_tab != "profile":
            return
        old = self._journal_scroll
        self._journal_scroll = max(0, min(self._journal_max_scroll,
                                          self._journal_scroll - int(scroll_y)))
        if self._journal_scroll != old:
            self._rebuild_journal()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _add_sp(self, font: BitmapFont, text: str, x: float, y: float,
                color: tuple | None = None) -> None:
        """Add a bitmap text sprite to the sidebar list."""
        self._sidebar_sprites.append(_bmp_sprite(font, text, x, y, color))

    def _build_sidebar(self, il: float, it: float) -> None:
        ib = self._panel_bottom + _BORDER
        ct = it - _TAB_H
        identity_bottom = self._build_identity(il, ct)
        self._build_needs_and_grades(il, identity_bottom - 8)
        self._build_thoughts(il, ib)

    # Trait link color (teal-ish, looks like a clickable link)
    _TRAIT_LINK_COLOR = (60, 120, 140, 255)

    def _build_identity(self, il: float, it: float) -> float:
        """Build identity + traits section. Returns the y position of the bottom."""
        s = self._student
        x = il + 100
        y = it - 8

        self._add_sp(FONT_HEADER, s.full_name, x, y)
        y -= _LH + 2

        # Year and age
        self._add_sp(FONT, f"{s.year.value.capitalize()} - Age {s.age}", x, y)
        y -= _LH

        # Gender
        self._add_sp(FONT, s.gender.value.replace("_", " ").title(), x, y)
        y -= _LH

        # Sun sign
        if s.personality:
            self._add_sp(FONT_DIM, s.personality.zodiac.value.capitalize(), x, y)
            y -= _LH

        # Mood
        self._add_sp(FONT, f"{s.mood.name.capitalize()} ({int(s.mood_value)})", x, y)
        y -= _LH

        # Extra gap before traits so they don't overlap portrait bottom
        y -= 10

        # Traits as comma-separated, word-wrapped line with hover descriptions
        if s.traits:
            # Build the display string and track each trait's character position
            trait_parts: list[tuple[str, str, int]] = []  # (name, description, char_offset)
            display = ""
            for i, trait in enumerate(s.traits):
                offset = len(display)
                display += trait.name
                trait_parts.append((trait.name, trait.description, offset))
                if i < len(s.traits) - 1:
                    display += ", "

            # Word-wrap the full string
            cw = FONT.char_width
            max_chars = max(1, (_SIDEBAR_W) // cw)
            # Render as one string in link color
            lines = FONT.wrap_lines(display, _SIDEBAR_W)
            char_pos = 0
            for line in lines:
                sp = _bmp_sprite(FONT, line, il, y, self._TRAIT_LINK_COLOR)
                self._sidebar_sprites.append(sp)

                # Register hitboxes for each trait name that appears on this line
                for name, desc, trait_offset in trait_parts:
                    trait_end = trait_offset + len(name)
                    # Check if this trait overlaps with this line's character range
                    line_start = char_pos
                    line_end = char_pos + len(line)
                    if trait_offset >= line_start and trait_offset < line_end:
                        # Trait starts on this line
                        local_start = trait_offset - line_start
                        local_end = min(local_start + len(name), len(line))
                        hx1 = il + local_start * cw
                        hx2 = il + local_end * cw
                        hy_top = y
                        hy_bot = y - _LH
                        # Underline
                        self._lines.append((hx1, hy_bot + 2, hx2, hy_bot + 2, self._TRAIT_LINK_COLOR))
                        # Hover hitbox
                        self._hover_hitboxes.append((hx1, hy_bot, hx2, hy_top, desc, "below", "profile"))

                char_pos += len(line)
                # Account for the space that was removed by word-wrap
                if char_pos < len(display) and display[char_pos] == " ":
                    char_pos += 1
                y -= _LH
            y -= 4

        return y

    # Subject display names (PE needs to stay uppercase)
    _SUBJECT_NAMES = {
        "math": "Math", "english": "English", "science": "Science",
        "art": "Art", "pe": "PE", "music": "Music",
    }

    def _build_needs_and_grades(self, il: float, top: float) -> None:
        s = self._student

        # ── Needs (left side — full labels, no numbers, wider bars, hover for value) ──
        self._add_sp(FONT_HEADER, "NEEDS", il, top)
        self._lines.append((il, top - _LH + 4, il + 160, top - _LH + 4, (140, 120, 90, 180)))
        y = top - _LH - 4
        _NEED_LABELS = {
            NeedType.REST: "Rest", NeedType.FUN: "Fun", NeedType.SOCIAL: "Social",
            NeedType.ACADEMICS: "Academics", NeedType.CREATIVITY: "Creative",
            NeedType.ATHLETICS: "Athletics",
        }
        label_w = 110  # space for full label text
        need_bar_w = 50
        for need_type, color in _NEED_COLORS.items():
            label = _NEED_LABELS.get(need_type, need_type.value.capitalize())
            val = s.needs[need_type].value
            self._add_sp(FONT_DIM, label, il, y)
            bar_x = il + label_w
            cy = y - _LH // 2
            self._bar_rects.append((bar_x, bar_x + need_bar_w, cy - _BAR_H // 2, cy + _BAR_H // 2, _BAR_BG))
            fill = int(need_bar_w * max(0.0, min(100.0, val)) / 100.0)
            if fill > 0:
                self._bar_rects.append((bar_x, bar_x + fill, cy - _BAR_H // 2, cy + _BAR_H // 2, color))
            # Hover hitbox over the bar → shows numeric value
            self._hover_hitboxes.append((
                bar_x, cy - _BAR_H // 2 - 2, bar_x + need_bar_w, cy + _BAR_H // 2 + 2,
                f"{label}: {int(val)}/100", "above", "profile",
            ))
            y -= _BAR_SPACING

        # ── Grades (right side, compact) ──
        gx = il + 185
        self._add_sp(FONT_HEADER, "GRADES", gx, top)
        self._lines.append((gx, top - _LH + 4, gx + 130, top - _LH + 4, (140, 120, 90, 180)))
        gy = top - _LH - 4
        for subj in Subject:
            if subj not in s.grades:
                continue
            grade = s.grades[subj]
            letter = grade.letter_full
            gc = _GRADE_COLORS.get(letter[0], COLOR_LABEL)
            display_name = self._SUBJECT_NAMES.get(subj.value, subj.value.capitalize())
            self._add_sp(FONT_DIM, display_name, gx, gy)
            self._sidebar_sprites.append(_bmp_sprite(FONT, letter, gx + 90, gy, gc))
            gy -= _LH

    def _build_thoughts(self, il: float, ib: float) -> None:
        s = self._student
        top = ib + 100
        self._add_sp(FONT_HEADER, "THOUGHTS", il, top)
        self._lines.append((il, top - _LH + 4, il + 140, top - _LH + 4, (140, 120, 90, 180)))
        y = top - _LH - 4
        shown = 0
        for thought in reversed(s.thoughts):
            if shown >= 4:
                break
            sign = "+" if thought.mood_effect >= 0 else ""
            label = thought.label
            if len(label) > 35:
                label = label[:32] + "..."
            self._add_sp(FONT, f"{sign}{thought.mood_effect:.0f} {label}", il, y)
            y -= _LH
            shown += 1
        if not s.thoughts:
            self._add_sp(FONT_DIM, "Nothing on their mind.", il, y)

    # ------------------------------------------------------------------
    # Journal (scrollable)
    # ------------------------------------------------------------------

    def _rebuild_journal(self) -> None:
        self._journal_sprites.clear()
        self._journal_lines.clear()

        s = self._student
        jx = self._journal_area_left
        jw = _JOURNAL_W
        top = self._journal_area_top
        bottom = self._journal_area_bottom

        # Header
        self._journal_sprites.append(_bmp_sprite(FONT_HEADER, "JOURNAL", jx, top))
        self._journal_lines.append((jx, top - _LH + 4, jx + jw, top - _LH + 4, (140, 120, 90, 180)))

        content_top = top - _LH - 4
        content_h = content_top - bottom

        # Pre-compute all entries as rendered line groups
        entries = list(reversed(s.journal))
        total = len(entries)

        if not entries:
            self._journal_sprites.append(_bmp_sprite(FONT_DIM, "No journal entries yet.", jx, content_top))
            self._journal_max_scroll = 0
            return

        # Build line data for all entries: list of (timestamp_str, wrapped_text_lines)
        entry_data: list[tuple[str, list[str]]] = []
        for entry in entries:
            ts = f"Day {entry.day} - {entry.time_label}"
            lines = FONT_JOURNAL.wrap_lines(entry.text, jw)
            entry_data.append((ts, lines))

        # Calculate height per entry (timestamp line + text lines + gap)
        def _entry_height(data: tuple[str, list[str]]) -> int:
            return _LH + len(data[1]) * _LH + 6  # timestamp + text lines + gap

        # Find how many entries fit from scroll position
        self._journal_max_scroll = max(0, total - 1)

        y = content_top
        shown = 0
        for i in range(self._journal_scroll, total):
            data = entry_data[i]
            h = _entry_height(data)
            if y - h < bottom and shown > 0:
                break

            # Timestamp
            self._journal_sprites.append(_bmp_sprite(FONT_TIMESTAMP, data[0], jx, y))
            y -= _LH

            # Text lines
            for line in data[1]:
                self._journal_sprites.append(_bmp_sprite(FONT_JOURNAL, line, jx, y))
                y -= _LH

            y -= 6  # gap between entries
            shown += 1

        # Update max scroll based on how many didn't fit
        remaining = total - self._journal_scroll - shown
        if remaining <= 0:
            self._journal_max_scroll = self._journal_scroll
        else:
            self._journal_max_scroll = total - shown

        # Scroll hints
        if self._journal_scroll > 0:
            self._journal_sprites.append(_bmp_sprite(FONT_SCROLL, "^ newer", jx + jw - 80, top - 4))
        if self._journal_scroll < self._journal_max_scroll:
            self._journal_sprites.append(_bmp_sprite(FONT_SCROLL, "v older", jx + jw - 80, bottom + _LH))

    # ------------------------------------------------------------------
    # Relationships tab
    # ------------------------------------------------------------------

    def _add_rel_sp(self, font: BitmapFont, text: str, x: float, y: float,
                    color: tuple | None = None) -> None:
        self._rel_sprites.append(_bmp_sprite(font, text, x, y, color))

    def _build_relationships_tab(self, il: float, it: float) -> None:
        s   = self._student
        ct  = it - _TAB_H - 8
        ib  = self._panel_bottom + _BORDER
        sid = s.student_id

        from src.ui.character_composer import composite_portrait_sheet

        inner_w = _PANEL_W - _BORDER * 2
        portrait_size = 44  # display size for talking heads
        _CELL = 96  # native portrait cell size
        col_portrait = il + 4
        col_name   = il + portrait_size + 14
        col_friend = il + portrait_size + 120
        col_bar    = il + portrait_size + 270
        col_rom_me = il + portrait_size + 370
        col_rom_them = il + portrait_size + 500
        col_status = il + portrait_size + 640
        bar_w = 60

        self._rel_portraits.clear()

        self._add_rel_sp(FONT_HEADER, "RELATIONSHIPS", il, ct)
        self._rel_lines.append((il, ct - _LH + 4, il + inner_w, ct - _LH + 4, (140, 120, 90, 180)))
        y = ct - _LH - 4

        for text, x in (
            ("NAME",       col_name),
            ("FRIENDSHIP", col_friend),
            ("I FEEL",     col_rom_me),
            ("THEY FEEL",  col_rom_them),
            ("STATUS",     col_status),
        ):
            self._add_rel_sp(FONT_DIM, text, x, y)
        y -= _LH
        self._rel_lines.append((il, y + 4, il + inner_w, y + 4, (140, 120, 90, 140)))
        y -= 8

        others = [st for st in self._state.students if st.student_id != sid]

        def _sort_key(other: Student) -> tuple:
            key = (min(sid, other.student_id), max(sid, other.student_id))
            rom = self._state.romances.get(key)
            fri = self._state.friendships.get(key)
            rom_score = 0
            if rom:
                if rom.is_dating: rom_score = 3
                elif rom.is_mutual_crush: rom_score = 2
                elif rom.is_unrequited: rom_score = 1
            fri_level = fri.level if fri else FriendshipLevel.STRANGER
            return (-rom_score, -int(fri_level), other.name)

        others.sort(key=_sort_key)

        row_h = portrait_size + 6  # row height = portrait + padding
        for other in others:
            key = (min(sid, other.student_id), max(sid, other.student_id))
            fri = self._state.friendships.get(key)
            rom = self._state.romances.get(key)

            fri_level    = fri.level    if fri else FriendshipLevel.STRANGER
            fri_affinity = fri.affinity if fri else 0
            fri_color    = _FRIENDSHIP_COLORS.get(fri_level, COLOR_DIM)

            # Build talking head frames for this student
            if other.appearance:
                sheet = composite_portrait_sheet(other.appearance)
                frames = []
                for fc in range(10):
                    frame_img = sheet.crop((fc * _CELL, 0, (fc + 1) * _CELL, _CELL))
                    frames.append(arcade.Texture(frame_img))
                portrait_cx = col_portrait + portrait_size // 2
                portrait_cy = y - portrait_size // 2
                self._rel_portraits.append((frames, portrait_cx, portrait_cy))

            # Text baseline aligned to portrait center
            text_y = y - portrait_size // 2 + _LH // 2

            self._add_rel_sp(FONT, other.name, col_name, text_y)

            fri_label = fri_level.name.replace("_", " ").title()
            self._rel_sprites.append(_bmp_sprite(FONT, fri_label, col_friend, text_y, fri_color))

            # Friendship bar
            cy = text_y - _LH // 2
            self._rel_bar_rects.append((col_bar, col_bar + bar_w, cy - 4, cy + 4, _BAR_BG))
            fill = int(bar_w * min(100, fri_affinity) / 100)
            if fill > 0:
                self._rel_bar_rects.append((col_bar, col_bar + fill, cy - 4, cy + 4, fri_color))
            self._hover_hitboxes.append((
                col_bar, cy - 6, col_bar + bar_w, cy + 6,
                f"{fri_label}: {fri_affinity}/100", "above", "relationships",
            ))

            if rom:
                my_feelings   = rom.feelings_of(sid)
                their_feelings = rom.feelings_of(other.student_id)
                my_color   = _ROMANCE_COLORS.get(my_feelings, COLOR_DIM)
                their_color = _ROMANCE_COLORS.get(their_feelings, COLOR_DIM)

                if my_feelings != RomanceLevel.PLATONIC:
                    self._rel_sprites.append(
                        _bmp_sprite(FONT, my_feelings.name.title(), col_rom_me, text_y, my_color)
                    )
                if their_feelings != RomanceLevel.PLATONIC:
                    self._rel_sprites.append(
                        _bmp_sprite(FONT, their_feelings.name.title(), col_rom_them, text_y, their_color)
                    )

                if rom.is_dating:
                    self._rel_sprites.append(
                        _bmp_sprite(FONT, "Dating!", col_status, text_y, (210, 50, 90, 255))
                    )
                elif rom.is_mutual_crush:
                    self._rel_sprites.append(
                        _bmp_sprite(FONT, "Mutual crush", col_status, text_y, (220, 100, 140, 255))
                    )
                elif rom.is_unrequited:
                    crusher_id = sid if my_feelings > RomanceLevel.PLATONIC else other.student_id
                    label = "I like them" if crusher_id == sid else "They like me"
                    self._rel_sprites.append(
                        _bmp_sprite(FONT, label, col_status, text_y, (180, 120, 140, 200))
                    )

            y -= row_h

        if not others:
            self._add_rel_sp(FONT_DIM, "No other students.", il, y)

    # ------------------------------------------------------------------
    # Details tab
    # ------------------------------------------------------------------

    _SKILL_COLORS: dict[str, tuple] = {
        "academics":  ( 60, 179, 113, 255),
        "athletics":  (255, 140,   0, 255),
        "creativity": (147, 112, 219, 255),
        "social":     (219, 112, 147, 255),
        "music":      ( 70, 130, 180, 255),
    }

    def _add_det_sp(self, font: BitmapFont, text: str, x: float, y: float,
                    color: tuple | None = None) -> None:
        self._det_sprites.append(_bmp_sprite(font, text, x, y, color))

    def _build_details_tab(self, il: float, it: float) -> None:
        """Build the details tab: skills, preferences, attraction."""
        s = self._student
        ct = it - _TAB_H
        y = ct - 8
        content_w = _PANEL_W - _BORDER * 2

        # ── Skills ─────────────────────────────────────────────────
        self._add_det_sp(FONT_HEADER, "SKILLS", il, y)
        self._det_lines.append((il, y - _LH + 4, il + 160, y - _LH + 4, (140, 120, 90, 180)))
        y -= _LH + 4

        # Core skills only (not party/protest/flirt — those are hidden mechanics)
        _DISPLAY_SKILLS = [Skill.ACADEMICS, Skill.ATHLETICS, Skill.CREATIVITY, Skill.SOCIAL, Skill.MUSIC]
        fav = s.favorite_skill
        dread = s.dreaded_skill
        label_w = 120
        bar_w = 140
        bar_h = 12
        skill_spacing = 22

        for skill in _DISPLAY_SKILLS:
            val = s.skills.get(skill, 0.0)
            label = skill.value.capitalize()
            color = self._SKILL_COLORS.get(skill.value, COLOR_LABEL)

            self._add_det_sp(FONT, label, il, y)

            # Bar
            bar_x = il + label_w
            cy = y - _LH // 2
            self._det_bar_rects.append((bar_x, bar_x + bar_w, cy - bar_h // 2, cy + bar_h // 2, _BAR_BG))
            fill = int(bar_w * max(0.0, min(100.0, val)) / 100.0)
            if fill > 0:
                self._det_bar_rects.append((bar_x, bar_x + fill, cy - bar_h // 2, cy + bar_h // 2, color))

            # Value text right of bar
            val_x = bar_x + bar_w + 8
            self._det_sprites.append(
                _bmp_sprite(FONT_DIM, f"{int(val)}", val_x, y)
            )

            # Favorite/dreaded indicator after the number
            indicator_x = val_x + 40
            if skill == fav:
                self._add_det_sp(FONT, "(Fav)", indicator_x, y, (60, 140, 80, 255))
            elif skill == dread:
                self._add_det_sp(FONT_DIM, "(Weak)", indicator_x, y)

            # Hover for skill description
            self._hover_hitboxes.append((
                bar_x, cy - bar_h // 2 - 2, bar_x + bar_w, cy + bar_h // 2 + 2,
                f"{skill.value.capitalize()}: {int(val)}/100", "below", "details",
            ))

            y -= skill_spacing

        y -= 10

        # ── Preferences ───────────────────────────────────────────
        self._add_det_sp(FONT_HEADER, "PREFERENCES", il, y)
        self._det_lines.append((il, y - _LH + 4, il + 200, y - _LH + 4, (140, 120, 90, 180)))
        y -= _LH + 4

        if s.personality:
            p = s.personality
            prefs = [
                ("Zodiac", p.zodiac.value.capitalize()),
                ("Music", p.music_genre.value.replace("_", " ").replace("r and b", "R&B").title()),
                ("Movies", p.movie_genre.value.replace("_", " ").title()),
                ("Time", p.time_of_day.value.capitalize()),
                ("Weather", p.weather.value.capitalize()),
                ("Worldview", p.worldview.value.capitalize()),
                ("Attracted", fmt_romance_interests(p.romance_interest)),
            ]
            for label, value in prefs:
                self._add_det_sp(FONT_DIM, f"{label}:", il, y)
                self._add_det_sp(FONT, value, il + 120, y)
                y -= _LH
        else:
            self._add_det_sp(FONT_DIM, "No personality data.", il, y)
