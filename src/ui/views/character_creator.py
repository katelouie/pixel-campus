"""Character creator view — customize a student's identity and appearance.

Shows a full-body animated sprite preview on the left with Randomize/Done
buttons stacked beneath it. The right side has:
- Editable first/last name fields
- Gender and zodiac sign selectors
- Attraction toggle buttons
- Year display (not editable)
- Trait selection (pick 1-2, respecting exclusions)
- Appearance selectors (skin, eyes, hairstyle, outfit, accessory)

Used from the pre-game landing screen and from the profile view mid-game.
"""

import json
from pathlib import Path

import arcade

from src.sim.defs import GameDefs
from src.sim.models import CharacterAppearance, Gender, Student, Year
from src.sim.personality import RomanceInterest, ZodiacSign
from src.sim.traits import Trait
from src.ui.bitmap_font import BitmapFont
from src.ui.character_composer import composite_sprite_sheet
from src.ui.font import COLOR_DIM, COLOR_HEADER, COLOR_LABEL
from src.ui.hud import _make_nine_slice_texture
from src.ui.sprites import CHAR_H, CHAR_W, FRAMES_PER_DIRECTION

# ── Layout ─────────────────────────────────────────────────────────

_PANEL_W = 920
_PANEL_H = 740
_BORDER = 36

_PREVIEW_SCALE = 3  # 48x96 → 144x288
_LEFT_COL_W = 220  # width for sprite + buttons column

# Right column
_RIGHT_X = _LEFT_COL_W + 30  # offset from panel left
_ROW_H = 38          # height per selector row
_ARROW_SIZE = 26
_LABEL_W = 120       # width reserved for labels

# Text input
_INPUT_W = 160
_INPUT_H = 26
_MAX_NAME_LEN = 12

# Trait/attraction toggle buttons
_TRAIT_ROW_H = 28
_TRAIT_COL_W = 150
_TRAIT_COLS = 3
_ATTRACT_BTN_W = 100

# Bottom buttons (stacked under sprite)
_BTN_W = 160
_BTN_H = 36
_BTN_GAP = 10

# ── Fonts ──────────────────────────────────────────────────────────

_FONT_LABEL = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_VALUE = BitmapFont(scale=2, color=(60, 50, 35, 255))
_FONT_ARROW = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_ARROW_HOVER = BitmapFont(scale=2, color=(30, 25, 15, 255))
_FONT_BTN = BitmapFont(scale=2, color=COLOR_LABEL)
_FONT_BTN_HOVER = BitmapFont(scale=2, color=(30, 25, 15, 255))
_FONT_DIM = BitmapFont(scale=2, color=COLOR_DIM)
_FONT_TAG = BitmapFont(scale=1, color=COLOR_LABEL)
_FONT_TAG_SEL = BitmapFont(scale=1, color=(30, 60, 20, 255))  # dark text on light green
_FONT_TAG_DIS = BitmapFont(scale=1, color=(160, 150, 135, 160))
_FONT_SECTION = BitmapFont(scale=2, color=(100, 85, 60, 200))

# Colors
_BTN_BG = (235, 225, 205, 230)
_BTN_HOVER_BG = (210, 200, 175, 245)
_BTN_BORDER = (180, 165, 140, 200)
_BTN_HOVER_BORDER = (140, 120, 90, 255)
_ARROW_BG = (215, 205, 185, 200)
_ARROW_HOVER_BG = (190, 180, 155, 240)
_INPUT_BG = (255, 255, 250, 200)
_INPUT_ACTIVE_BG = (255, 255, 240, 255)
_INPUT_BORDER = (180, 165, 140, 200)
_INPUT_ACTIVE_BORDER = (100, 80, 50, 255)
_TAG_BG = (225, 215, 195, 200)
_TAG_SEL_BG = (180, 210, 160, 240)     # soft green — selected
_TAG_SEL_BORDER = (120, 160, 100, 255)
_TAG_HOVER_BG = (210, 200, 180, 230)
_TAG_DIS_BG = (230, 225, 215, 120)

# ── Catalog ────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CATALOG_PATH = _PROJECT_ROOT / "src/data/character_catalog.json"

with open(_CATALOG_PATH) as f:
    _CATALOG = json.load(f)

_TRAIT_POOL: list[Trait] = []
_defs = GameDefs.load()
if _defs.traits:
    _TRAIT_POOL = _defs.traits


def _get_colors(component: str, style: int) -> list[int]:
    if component == "hairstyles":
        return _CATALOG["hairstyles"]["styles"].get(str(style), [1, 2, 3, 4, 5, 6, 7])
    elif component == "outfits":
        return _CATALOG["outfits"]["styles"].get(str(style), [1])
    elif component == "accessories":
        info = _CATALOG["accessories"]["styles"].get(str(style))
        return info["colors"] if info else [1]
    return [1]


def _accessory_name(style: int) -> str:
    info = _CATALOG["accessories"]["styles"].get(str(style))
    return info["name"].replace("_", " ") if info else f"Style {style}"


_COMPONENTS = [
    ("Skin Tone", "bodies", 9, False),
    ("Eyes", "eyes", 7, False),
    ("Hairstyle", "hairstyles", 29, True),
    ("Outfit", "outfits", 33, True),
    ("Accessory", "accessories", 19, True),
]

_ACCESSORY_IDS = [0] + sorted(int(k) for k in _CATALOG["accessories"]["styles"])

_GENDERS = list(Gender)
_ZODIAC_SIGNS = list(ZodiacSign)

_GENDER_LABELS = {Gender.MALE: "Male", Gender.FEMALE: "Female", Gender.NON_BINARY: "Non-Binary"}
_ZODIAC_LABELS = {z: z.value.capitalize() for z in ZodiacSign}
_YEAR_LABELS = {y: y.value.capitalize() for y in Year}
_RI_LABELS = {RomanceInterest.BOYS: "Boys", RomanceInterest.GIRLS: "Girls",
              RomanceInterest.NON_BINARY: "Enbies"}


class CharacterCreatorView(arcade.View):

    def __init__(self, student: Student, return_view: arcade.View,
                 on_done: callable = None) -> None:
        super().__init__()
        self._student = student
        self._return_view = return_view
        self._on_done = on_done

        if student.appearance is None:
            from src.ui.character_composer import random_appearance
            student.appearance = random_appearance(student.student_id)

        self._appearance = student.appearance
        self._panel_tex = _make_nine_slice_texture(_PANEL_W, _PANEL_H)
        self._screen_cam = arcade.Camera2D()

        # Preview
        self._preview_frames: list[arcade.Texture] = []
        self._preview_frame_idx: int = 0
        self._preview_timer: int = 0
        self._recomposite_preview()

        # Text input
        self._first_name: str = student.name
        self._last_name: str = student.last_name
        self._active_field: str = ""
        self._cursor_blink: int = 0

        # Traits
        self._selected_traits: list[str] = [t.name for t in student.traits]
        self._trait_by_name: dict[str, Trait] = {t.name: t for t in _TRAIT_POOL}

        # Romance interests
        self._attraction: set[RomanceInterest] = set(
            student.personality.romance_interest if student.personality else []
        )

        # Hover state
        self._hovered_arrow: tuple[str, str] | None = None
        self._hovered_button: str = ""
        self._hovered_trait: str = ""
        self._hovered_attract: str = ""

        # Rects (built in _rebuild_layout)
        self._panel_left = 0
        self._panel_bottom = 0
        self._arrow_rects: dict[tuple[str, str], tuple] = {}
        self._button_rects: dict[str, tuple] = {}
        self._input_rects: dict[str, tuple] = {}
        self._trait_rects: dict[str, tuple] = {}
        self._attract_rects: dict[str, tuple] = {}

    # ── Preview ────────────────────────────────────────────────────

    def _recomposite_preview(self) -> None:
        sheet = composite_sprite_sheet(self._appearance)
        start_col = 3 * FRAMES_PER_DIRECTION
        self._preview_frames = []
        for i in range(FRAMES_PER_DIRECTION):
            x = (start_col + i) * CHAR_W
            y = 1 * CHAR_H
            self._preview_frames.append(
                arcade.Texture(sheet.crop((x, y, x + CHAR_W, y + CHAR_H)))
            )
        self._preview_frame_idx = 0
        self._preview_timer = 0

    # ── Appearance helpers ─────────────────────────────────────────

    def _get_app_value(self, row):
        a = self._appearance
        return [a.body, a.eyes, a.hairstyle, a.outfit,
                a.accessory if a.accessory is not None else 0][row]

    def _get_app_color(self, row):
        a = self._appearance
        if row == 2: return a.hair_color
        if row == 3: return a.outfit_color
        if row == 4: return a.accessory_color if a.accessory_color is not None else 1
        return 1

    def _set_app_value(self, row, val):
        a = self._appearance
        if row == 0: a.body = val
        elif row == 1: a.eyes = val
        elif row == 2:
            a.hairstyle = val
            colors = _get_colors("hairstyles", val)
            if a.hair_color not in colors: a.hair_color = colors[0]
        elif row == 3:
            a.outfit = val
            colors = _get_colors("outfits", val)
            if a.outfit_color not in colors: a.outfit_color = colors[0]
        elif row == 4:
            if val == 0:
                a.accessory = None; a.accessory_color = None
            else:
                a.accessory = val
                colors = _get_colors("accessories", val)
                if a.accessory_color not in (colors or [1]):
                    a.accessory_color = colors[0] if colors else 1
        self._recomposite_preview()

    def _set_app_color(self, row, val):
        a = self._appearance
        if row == 2: a.hair_color = val
        elif row == 3: a.outfit_color = val
        elif row == 4 and a.accessory is not None: a.accessory_color = val
        self._recomposite_preview()

    def _cycle_app_value(self, row, direction):
        _, _, max_style, _ = _COMPONENTS[row]
        if row == 4:
            cur = self._get_app_value(row)
            idx = _ACCESSORY_IDS.index(cur) if cur in _ACCESSORY_IDS else 0
            self._set_app_value(row, _ACCESSORY_IDS[(idx + direction) % len(_ACCESSORY_IDS)])
        else:
            cur = self._get_app_value(row)
            self._set_app_value(row, ((cur - 1 + direction) % max_style) + 1)

    def _cycle_app_color(self, row, direction):
        _, cat_key, _, has_color = _COMPONENTS[row]
        if not has_color or (row == 4 and self._appearance.accessory is None):
            return
        colors = _get_colors(cat_key, self._get_app_value(row))
        if not colors: return
        cur = self._get_app_color(row)
        idx = colors.index(cur) if cur in colors else 0
        self._set_app_color(row, colors[(idx + direction) % len(colors)])

    # ── Identity cycling ───────────────────────────────────────────

    def _cycle_enum(self, key, direction):
        if key == "gender":
            idx = _GENDERS.index(self._student.gender)
            self._student.gender = _GENDERS[(idx + direction) % len(_GENDERS)]
        elif key == "zodiac" and self._student.personality:
            idx = _ZODIAC_SIGNS.index(self._student.personality.zodiac)
            self._student.personality.zodiac = _ZODIAC_SIGNS[(idx + direction) % len(_ZODIAC_SIGNS)]

    # ── Trait selection ────────────────────────────────────────────

    def _get_excluded_traits(self):
        excluded = set()
        for name in self._selected_traits:
            trait = self._trait_by_name.get(name)
            if trait:
                excluded.update(trait.excludes)
                for other in _TRAIT_POOL:
                    if name in other.excludes:
                        excluded.add(other.name)
        return excluded

    def _toggle_trait(self, name):
        if name in self._selected_traits:
            self._selected_traits.remove(name)
        else:
            if name in self._get_excluded_traits(): return
            if len(self._selected_traits) >= 2: return
            self._selected_traits.append(name)

    # ── Layout ─────────────────────────────────────────────────────

    def on_show_view(self):
        self.window.background_color = (58, 55, 62)
        self._rebuild_layout()

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self._rebuild_layout()

    def _rebuild_layout(self):
        w, h = self.window.width, self.window.height
        self._screen_cam.position = arcade.Vec2(w / 2, h / 2)

        pl = (w - _PANEL_W) // 2
        pb = (h - _PANEL_H) // 2
        self._panel_left = pl
        self._panel_bottom = pb

        # ── Left column: sprite + buttons ──────────────────────────
        left_cx = pl + _BORDER + _LEFT_COL_W // 2
        sprite_cy = pb + _PANEL_H // 2 + 100

        # Buttons stacked below sprite
        sprite_bottom = sprite_cy - (CHAR_H * _PREVIEW_SCALE) // 2
        btn_x1 = left_cx - _BTN_W // 2
        btn_x2 = left_cx + _BTN_W // 2

        self._button_rects = {}
        self._button_rects["randomize"] = (btn_x1, sprite_bottom - 50,
                                            btn_x2, sprite_bottom - 50 + _BTN_H)
        self._button_rects["done"] = (btn_x1, sprite_bottom - 50 - _BTN_GAP - _BTN_H,
                                       btn_x2, sprite_bottom - 50 - _BTN_GAP)

        self._sprite_cx = left_cx
        self._sprite_cy = sprite_cy

        # ── Right column ───────────────────────────────────────────
        rx = pl + _RIGHT_X  # right column start
        val_x = rx + _LABEL_W  # where values/arrows start
        y = pb + _PANEL_H - _BORDER - 20

        self._arrow_rects = {}
        self._input_rects = {}
        self._trait_rects = {}
        self._attract_rects = {}

        # Name fields
        self._name_y = y
        self._input_rects["first"] = (val_x, y - _INPUT_H // 2,
                                       val_x + _INPUT_W, y + _INPUT_H // 2)
        last_x = val_x + _INPUT_W + 80
        self._input_rects["last"] = (last_x, y - _INPUT_H // 2,
                                      last_x + _INPUT_W, y + _INPUT_H // 2)
        y -= 40

        # Gender
        self._gender_y = y
        self._arrow_rects[("gender", "left")] = (val_x, y - _ARROW_SIZE // 2,
                                                   val_x + _ARROW_SIZE, y + _ARROW_SIZE // 2)
        self._arrow_rects[("gender", "right")] = (val_x + 190, y - _ARROW_SIZE // 2,
                                                    val_x + 190 + _ARROW_SIZE, y + _ARROW_SIZE // 2)
        y -= _ROW_H

        # Zodiac
        self._zodiac_y = y
        self._arrow_rects[("zodiac", "left")] = (val_x, y - _ARROW_SIZE // 2,
                                                    val_x + _ARROW_SIZE, y + _ARROW_SIZE // 2)
        self._arrow_rects[("zodiac", "right")] = (val_x + 190, y - _ARROW_SIZE // 2,
                                                     val_x + 190 + _ARROW_SIZE, y + _ARROW_SIZE // 2)
        y -= _ROW_H

        # Attracted to (toggle buttons)
        self._attract_y = y
        for j, ri in enumerate(RomanceInterest):
            bx = val_x + j * (_ATTRACT_BTN_W + 6)
            self._attract_rects[ri.value] = (bx, y - 12, bx + _ATTRACT_BTN_W, y + 12)
        y -= _ROW_H

        # Year (display only)
        self._year_y = y
        y -= _ROW_H

        # Section: Traits
        y -= 4
        self._traits_label_y = y
        y -= 6
        for i, trait in enumerate(_TRAIT_POOL):
            col = i % _TRAIT_COLS
            row = i // _TRAIT_COLS
            tx = val_x + col * _TRAIT_COL_W
            ty = y - row * _TRAIT_ROW_H
            tw = _TRAIT_COL_W - 6
            self._trait_rects[trait.name] = (tx, ty - 12, tx + tw, ty + 12)

        trait_rows = (len(_TRAIT_POOL) + _TRAIT_COLS - 1) // _TRAIT_COLS
        y -= trait_rows * _TRAIT_ROW_H + 12

        # Section: Appearance
        self._app_label_y = y
        y -= 28  # extra gap so Skin Tone doesn't overlap the label
        for i, (_, _, _, has_color) in enumerate(_COMPONENTS):
            yc = y - i * _ROW_H
            ay1 = yc - _ARROW_SIZE // 2
            ay2 = yc + _ARROW_SIZE // 2

            self._arrow_rects[(f"app{i}", "left")] = (val_x, ay1, val_x + _ARROW_SIZE, ay2)
            self._arrow_rects[(f"app{i}", "right")] = (val_x + 190, ay1,
                                                         val_x + 190 + _ARROW_SIZE, ay2)
            if has_color:
                cx = val_x + 270
                self._arrow_rects[(f"app{i}", "cleft")] = (cx, ay1, cx + _ARROW_SIZE, ay2)
                self._arrow_rects[(f"app{i}", "cright")] = (cx + 150, ay1,
                                                              cx + 150 + _ARROW_SIZE, ay2)

        self._app_start_y = y

    # ── Drawing ────────────────────────────────────────────────────

    def on_draw(self):
        self.clear()
        with self._screen_cam.activate():
            pl, pb = self._panel_left, self._panel_bottom
            rx = pl + _RIGHT_X
            val_x = rx + _LABEL_W

            # Panel
            arcade.draw_texture_rect(
                self._panel_tex,
                arcade.XYWH(pl + _PANEL_W // 2, pb + _PANEL_H // 2, _PANEL_W, _PANEL_H))

            # ── Sprite preview ─────────────────────────────────────
            self._preview_timer += 1
            if self._preview_timer >= 8:
                self._preview_timer = 0
                self._preview_frame_idx = (self._preview_frame_idx + 1) % len(self._preview_frames)

            if self._preview_frames:
                tex = self._preview_frames[self._preview_frame_idx]
                arcade.draw_texture_rect(
                    tex, arcade.XYWH(self._sprite_cx, self._sprite_cy,
                                     CHAR_W * _PREVIEW_SCALE, CHAR_H * _PREVIEW_SCALE))

            # ── Left buttons ───────────────────────────────────────
            self._draw_button("randomize", "Randomize")
            self._draw_button("done", "Done")

            # ── Name fields ────────────────────────────────────────
            y = self._name_y
            self._draw_label_at("First:", rx, y)
            self._draw_input("first", self._first_name)
            self._draw_label_at("Last:", val_x + _INPUT_W + 10, y)
            self._draw_input("last", self._last_name)

            # ── Gender ─────────────────────────────────────────────
            y = self._gender_y
            self._draw_label_at("Gender:", rx, y)
            self._draw_arrow_pair("gender")
            self._draw_value_between("gender", _GENDER_LABELS.get(self._student.gender, "?"))

            # ── Zodiac ─────────────────────────────────────────────
            y = self._zodiac_y
            self._draw_label_at("Zodiac:", rx, y)
            self._draw_arrow_pair("zodiac")
            zod = self._student.personality.zodiac if self._student.personality else None
            self._draw_value_between("zodiac", _ZODIAC_LABELS.get(zod, "?"))

            # ── Attracted to ───────────────────────────────────────
            y = self._attract_y
            self._draw_label_at("Attracted:", rx, y)
            for ri in RomanceInterest:
                self._draw_attract_btn(ri)

            # ── Year (display only) ────────────────────────────────
            y = self._year_y
            self._draw_label_at("Year:", rx, y)
            yt = _FONT_VALUE.get_texture(_YEAR_LABELS.get(self._student.year, "?"))
            arcade.draw_texture_rect(yt, arcade.XYWH(val_x + yt.width // 2, y,
                                                      yt.width, yt.height))

            # ── Traits ─────────────────────────────────────────────
            st = _FONT_SECTION.get_texture("Traits")
            arcade.draw_texture_rect(st, arcade.XYWH(rx + st.width // 2,
                                                      self._traits_label_y,
                                                      st.width, st.height))
            st2 = _FONT_DIM.get_texture(f"({len(self._selected_traits)}/2)")
            arcade.draw_texture_rect(st2, arcade.XYWH(rx + st2.width // 2,
                                                       self._traits_label_y - 18,
                                                       st2.width, st2.height))

            excluded = self._get_excluded_traits()
            for trait in _TRAIT_POOL:
                if trait.name not in self._trait_rects: continue
                x1, y1, x2, y2 = self._trait_rects[trait.name]
                is_sel = trait.name in self._selected_traits
                is_dis = (trait.name in excluded and not is_sel) or \
                         (len(self._selected_traits) >= 2 and not is_sel)
                is_hov = self._hovered_trait == trait.name

                bg = _TAG_SEL_BG if is_sel else _TAG_DIS_BG if is_dis else \
                     _TAG_HOVER_BG if is_hov else _TAG_BG
                arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, bg)
                if is_sel:
                    arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2,
                                                       _TAG_SEL_BORDER, border_width=2)

                font = _FONT_TAG_SEL if is_sel else _FONT_TAG_DIS if is_dis else _FONT_TAG
                tt = font.get_texture(trait.name)
                arcade.draw_texture_rect(tt, arcade.XYWH((x1+x2)/2, (y1+y2)/2,
                                                          tt.width, tt.height))

            # ── Appearance ─────────────────────────────────────────
            at = _FONT_SECTION.get_texture("Appearance")
            arcade.draw_texture_rect(at, arcade.XYWH(rx + at.width // 2,
                                                      self._app_label_y,
                                                      at.width, at.height))

            for i, (label, cat_key, max_style, has_color) in enumerate(_COMPONENTS):
                yc = self._app_start_y - i * _ROW_H

                self._draw_label_at(label, rx, yc)
                self._draw_arrow_pair(f"app{i}")

                val = self._get_app_value(i)
                val_text = ("None" if val == 0 else _accessory_name(val)) if i == 4 \
                    else f"{val} / {max_style}"
                self._draw_value_between(f"app{i}", val_text)

                if has_color and not (i == 4 and val == 0):
                    self._draw_arrow_pair(f"app{i}", color=True)
                    color_val = self._get_app_color(i)
                    colors = _get_colors(cat_key, val if i != 4 else (val or 1))
                    self._draw_value_between(f"app{i}", f"Color {color_val}/{len(colors)}",
                                             color=True)

    # ── Draw helpers ───────────────────────────────────────────────

    def _draw_label_at(self, text, x, y):
        t = _FONT_LABEL.get_texture(text)
        arcade.draw_texture_rect(t, arcade.XYWH(x + t.width // 2, y, t.width, t.height))

    def _draw_input(self, field, value):
        if field not in self._input_rects: return
        x1, y1, x2, y2 = self._input_rects[field]
        active = self._active_field == field
        arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2,
                                           _INPUT_ACTIVE_BG if active else _INPUT_BG)
        arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2,
                                            _INPUT_ACTIVE_BORDER if active else _INPUT_BORDER,
                                            border_width=2)
        display = value
        if active:
            self._cursor_blink += 1
            if (self._cursor_blink // 20) % 2 == 0:
                display += "|"
        t = _FONT_VALUE.get_texture(display)
        arcade.draw_texture_rect(t, arcade.XYWH(x1 + 6 + t.width // 2, (y1+y2)/2,
                                                 t.width, t.height))

    def _draw_arrow_pair(self, section, color=False):
        left_key = (section, "cleft" if color else "left")
        right_key = (section, "cright" if color else "right")
        for key, sym in [(left_key, "<"), (right_key, ">")]:
            if key not in self._arrow_rects: continue
            x1, y1, x2, y2 = self._arrow_rects[key]
            hov = self._hovered_arrow == key
            arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2,
                                               _ARROW_HOVER_BG if hov else _ARROW_BG)
            font = _FONT_ARROW_HOVER if hov else _FONT_ARROW
            t = font.get_texture(sym)
            arcade.draw_texture_rect(t, arcade.XYWH((x1+x2)/2, (y1+y2)/2, t.width, t.height))

    def _draw_value_between(self, section, text, color=False):
        left_key = (section, "cleft" if color else "left")
        right_key = (section, "cright" if color else "right")
        if left_key not in self._arrow_rects or right_key not in self._arrow_rects:
            return
        lx2 = self._arrow_rects[left_key][2]
        rx1 = self._arrow_rects[right_key][0]
        cy = (self._arrow_rects[left_key][1] + self._arrow_rects[left_key][3]) / 2
        t = _FONT_VALUE.get_texture(text)
        arcade.draw_texture_rect(t, arcade.XYWH((lx2 + rx1) / 2, cy, t.width, t.height))

    def _draw_attract_btn(self, ri: RomanceInterest):
        key = ri.value
        if key not in self._attract_rects: return
        x1, y1, x2, y2 = self._attract_rects[key]
        is_sel = ri in self._attraction
        is_hov = self._hovered_attract == key

        bg = _TAG_SEL_BG if is_sel else _TAG_HOVER_BG if is_hov else _TAG_BG
        arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2, bg)
        if is_sel:
            arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2,
                                               _TAG_SEL_BORDER, border_width=2)

        font = _FONT_TAG_SEL if is_sel else _FONT_TAG
        t = font.get_texture(_RI_LABELS[ri])
        arcade.draw_texture_rect(t, arcade.XYWH((x1+x2)/2, (y1+y2)/2, t.width, t.height))

    def _draw_button(self, name, label):
        if name not in self._button_rects: return
        x1, y1, x2, y2 = self._button_rects[name]
        hov = self._hovered_button == name
        arcade.draw_lrbt_rectangle_filled(x1, x2, y1, y2,
                                           _BTN_HOVER_BG if hov else _BTN_BG)
        arcade.draw_lrbt_rectangle_outline(x1, x2, y1, y2,
                                            _BTN_HOVER_BORDER if hov else _BTN_BORDER,
                                            border_width=2)
        font = _FONT_BTN_HOVER if hov else _FONT_BTN
        t = font.get_texture(label)
        arcade.draw_texture_rect(t, arcade.XYWH((x1+x2)/2, (y1+y2)/2, t.width, t.height))

    # ── Input ──────────────────────────────────────────────────────

    def on_mouse_motion(self, x, y, dx, dy):
        self._hovered_arrow = None
        self._hovered_button = ""
        self._hovered_trait = ""
        self._hovered_attract = ""

        for key, rect in self._arrow_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._hovered_arrow = key; return
        for name, rect in self._button_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._hovered_button = name; return
        for name, rect in self._trait_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._hovered_trait = name; return
        for name, rect in self._attract_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._hovered_attract = name; return

    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT: return

        # Text fields
        clicked_field = False
        for field, rect in self._input_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._active_field = field
                self._cursor_blink = 0
                clicked_field = True; break
        if not clicked_field:
            self._active_field = ""

        # Arrows
        for key, rect in self._arrow_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                section, side = key
                direction = -1 if side in ("left", "cleft") else 1
                if section in ("gender", "zodiac"):
                    self._cycle_enum(section, direction)
                elif section.startswith("app"):
                    row = int(section[3:])
                    if side in ("left", "right"):
                        self._cycle_app_value(row, direction)
                    else:
                        self._cycle_app_color(row, direction)
                return

        # Traits
        for name, rect in self._trait_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                self._toggle_trait(name); return

        # Attraction toggles
        for key, rect in self._attract_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                ri = RomanceInterest(key)
                if ri in self._attraction:
                    self._attraction.discard(ri)
                else:
                    self._attraction.add(ri)
                return

        # Buttons
        for name, rect in self._button_rects.items():
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                if name == "done": self._finish()
                elif name == "randomize": self._randomize()
                return

    def on_text(self, text):
        if not self._active_field: return
        for ch in text:
            if ch.isprintable() and ord(ch) < 128:
                if self._active_field == "first" and len(self._first_name) < _MAX_NAME_LEN:
                    self._first_name += ch
                elif self._active_field == "last" and len(self._last_name) < _MAX_NAME_LEN:
                    self._last_name += ch

    def on_key_press(self, key, modifiers):
        if self._active_field:
            if key == arcade.key.BACKSPACE:
                if self._active_field == "first" and self._first_name:
                    self._first_name = self._first_name[:-1]
                elif self._active_field == "last" and self._last_name:
                    self._last_name = self._last_name[:-1]
                return
            elif key in (arcade.key.RETURN, arcade.key.TAB):
                self._active_field = "last" if self._active_field == "first" else ""
                return
            elif key == arcade.key.ESCAPE:
                self._active_field = ""; return

        if key == arcade.key.ESCAPE:
            self._finish()

    def _randomize(self):
        import random as _random
        from src.ui.character_composer import random_appearance
        new_app = random_appearance(_random.randint(0, 999999))
        a = self._appearance
        a.body = new_app.body; a.eyes = new_app.eyes
        a.hairstyle = new_app.hairstyle; a.hair_color = new_app.hair_color
        a.outfit = new_app.outfit; a.outfit_color = new_app.outfit_color
        a.accessory = new_app.accessory; a.accessory_color = new_app.accessory_color
        self._recomposite_preview()

    def _finish(self):
        if self._first_name.strip():
            self._student.name = self._first_name.strip()
        if self._last_name.strip():
            self._student.last_name = self._last_name.strip()

        self._student.traits = [
            self._trait_by_name[n] for n in self._selected_traits if n in self._trait_by_name
        ]

        if self._student.personality:
            self._student.personality.romance_interest = sorted(
                self._attraction, key=lambda ri: ri.value
            )

        if self._on_done:
            self._on_done(self._student)
        self.window.show_view(self._return_view)
