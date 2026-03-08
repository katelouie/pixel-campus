"""Campus view -- the main gameplay screen.

Renders tiled rooms, student sprites, and handles player interaction.
The sim GameState lives on the Window; this View reads and drives it.
"""

import random
from dataclasses import dataclass

import arcade

from src.sim.engine import GameState
from src.sim.models import Room, StudentState
from src.ui.hud import HUD
from src.ui.sprites import (
    TILE,
    StudentSprite,
    build_room_sprites,
    tile_texture,
)

CHARACTER_SHEETS: list[str] = ["Adam", "Alex", "Amelia", "Bob"]


@dataclass
class RoomLayout:
    """Screen-space description of a room. UI-layer only."""

    x: int  # left edge (pixels)
    y: int  # bottom edge (pixels)
    w: int  # width (tiles)
    h: int  # height (tiles)
    floor_col: int  # column in Room Builder tileset
    floor_row: int  # row in Room Builder tileset

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w * TILE / 2, self.y + self.h * TILE / 2)


# Visual layout for each sim room, keyed by Room.name.
ROOM_LAYOUTS: dict[str, RoomLayout] = {
    "Library": RoomLayout(x=30, y=380, w=5, h=3, floor_col=11, floor_row=6),
    "Art Room": RoomLayout(x=310, y=380, w=5, h=3, floor_col=11, floor_row=7),
    "Gym": RoomLayout(x=30, y=150, w=5, h=3, floor_col=11, floor_row=3),
    "Cafeteria": RoomLayout(x=310, y=150, w=5, h=3, floor_col=11, floor_row=4),
}


class CampusView(arcade.View):
    """Main gameplay view showing the campus with tiled rooms and students."""

    def __init__(
        self,
        state: GameState,
        room_builder_sheet: arcade.SpriteSheet,
        interiors_sheet: arcade.SpriteSheet,
        char_textures: dict[str, dict],
    ) -> None:
        super().__init__()
        self._state = state

        # Build visual layers
        self._room_floor_sprites: dict[str, arcade.SpriteList] = {}
        self._room_labels: list[arcade.Text] = []
        self._build_rooms(room_builder_sheet)

        self._furniture_list = arcade.SpriteList()
        self._place_furniture(interiors_sheet)

        self._student_sprites: dict[int, StudentSprite] = {}
        self._sprite_list = arcade.SpriteList()
        self._build_student_sprites(char_textures)

        # HUD
        self._hud = HUD(self.window.width, self.window.height)
        self._hud.push_messages(
            ["Welcome to Pixel Campus! SPACE to advance time."]
        )

        # Interaction state
        self._selected_sprite: StudentSprite | None = None
        self._prev_locations: dict[int, str | None] = {
            s.student_id: (s.location.name if s.location else None)
            for s in self._state.students
        }

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _build_rooms(self, sheet: arcade.SpriteSheet) -> None:
        """Create floor tile sprites and labels for every room."""
        for room in self._state.rooms:
            layout = ROOM_LAYOUTS.get(room.name)
            if not layout:
                continue

            room_sl = build_room_sprites(
                sheet,
                floor_col=layout.floor_col,
                floor_row=layout.floor_row,
                screen_x=layout.x,
                screen_y=layout.y,
                width_tiles=layout.w,
                height_tiles=layout.h,
            )
            self._room_floor_sprites[room.name] = room_sl

            cx, cy = layout.center
            label = arcade.Text(
                room.name,
                x=cx,
                y=layout.y + layout.h * TILE + 8,
                color=arcade.color.WHITE,
                font_size=12,
                anchor_x="center",
            )
            self._room_labels.append(label)

    def _place_furniture(self, sheet: arcade.SpriteSheet) -> None:
        """Add furniture sprites to rooms."""
        # Library bookshelf
        lib = ROOM_LAYOUTS.get("Library")
        if lib:
            bookshelf_tex = tile_texture(sheet, col=14, row=0)
            shelf = arcade.Sprite(bookshelf_tex)
            shelf.center_x = lib.x + 3 * TILE
            shelf.center_y = lib.y + 1.5 * TILE
            self._furniture_list.append(shelf)

    def _build_student_sprites(self, char_textures: dict[str, dict]) -> None:
        """Create a StudentSprite and name/mood Text objects for each student."""
        self._name_labels: dict[int, arcade.Text] = {}
        self._mood_labels: dict[int, arcade.Text] = {}

        for i, student in enumerate(self._state.students):
            sheet_name = CHARACTER_SHEETS[i % len(CHARACTER_SHEETS)]
            textures = char_textures[sheet_name]
            sprite = StudentSprite(student, textures)

            # Place at starting room with a small random offset
            if student.location and student.location.name in ROOM_LAYOUTS:
                cx, cy = ROOM_LAYOUTS[student.location.name].center
                sprite.center_x = cx + random.uniform(-25, 25)
                sprite.center_y = cy + random.uniform(-20, 20)
            else:
                sprite.center_x = self.window.width // 2
                sprite.center_y = self.window.height // 2

            self._student_sprites[student.student_id] = sprite
            self._sprite_list.append(sprite)

            # Pre-create Text objects for name and mood (avoids draw_text)
            self._name_labels[student.student_id] = arcade.Text(
                student.name,
                x=sprite.center_x,
                y=sprite.top + 12,
                color=arcade.color.WHITE,
                font_size=9,
                anchor_x="center",
            )
            self._mood_labels[student.student_id] = arcade.Text(
                student.mood.icon,
                x=sprite.center_x,
                y=sprite.top + 2,
                color=arcade.color.WHITE,
                font_size=10,
                anchor_x="center",
            )

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------

    def on_update(self, delta_time: float) -> None:
        for sid, sprite in self._student_sprites.items():
            sprite.update_movement()

            # Track labels to sprite position
            self._name_labels[sid].x = sprite.center_x
            self._name_labels[sid].y = sprite.top + 12
            self._mood_labels[sid].x = sprite.center_x
            self._mood_labels[sid].y = sprite.top + 2

            # Update mood icon if it changed
            new_icon = sprite.student.mood.icon
            if self._mood_labels[sid].text != new_icon:
                self._mood_labels[sid].text = new_icon

    def on_draw(self) -> None:
        self.clear()

        # Layer 1: Room floors
        for room_sl in self._room_floor_sprites.values():
            room_sl.draw()

        # Layer 2: Room borders
        for room in self._state.rooms:
            layout = ROOM_LAYOUTS.get(room.name)
            if not layout:
                continue
            arcade.draw_rect_outline(
                arcade.rect.LBWH(
                    layout.x, layout.y, layout.w * TILE, layout.h * TILE
                ),
                color=arcade.color.DIM_GRAY,
                border_width=3,
            )

        # Layer 3: Furniture
        self._furniture_list.draw()

        # Layer 4: Room labels
        for label in self._room_labels:
            label.draw()

        # Layer 5: Students
        self._sprite_list.draw()

        # Layer 6: Student names + mood icons
        self._draw_student_labels()

        # Layer 7: Selection ring
        if self._selected_sprite:
            arcade.draw_circle_outline(
                self._selected_sprite.center_x,
                self._selected_sprite.center_y,
                30,
                arcade.color.YELLOW,
                border_width=2,
            )

        # Layer 8: HUD
        self._hud.draw(self._state)

    def _draw_student_labels(self) -> None:
        """Draw pre-created name and mood Text objects above each sprite."""
        for sid, sprite in self._student_sprites.items():
            self._name_labels[sid].draw()
            self._mood_labels[sid].draw()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.SPACE:
            logs = self._state.tick()
            self._hud.push_messages(logs)
            self._sync_sprites_to_sim()
        elif symbol == arcade.key.H:
            all_logs: list[str] = []
            for _ in range(6):
                all_logs.extend(self._state.tick())
            self._hud.push_messages(all_logs)
            self._sync_sprites_to_sim()

    def on_mouse_press(
        self, x: int, y: int, button: int, modifiers: int
    ) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return

        # Check if we clicked a student sprite
        clicked = arcade.get_sprites_at_point((x, y), self._sprite_list)
        if clicked:
            self._selected_sprite = clicked[0]
            name = self._selected_sprite.student.name
            self._hud.push_messages(
                [f"Selected {name}. Click a room to assign."]
            )
            return

        # If a student is selected, try to assign them to a clicked room
        if self._selected_sprite:
            room = self._room_at(x, y)
            if room:
                result = self._state.assign_student(
                    self._selected_sprite.student, room
                )
                self._hud.push_messages([result])
                self._sync_sprites_to_sim()
                self._selected_sprite = None
                return

        # Click on empty space: deselect
        self._selected_sprite = None

    # ------------------------------------------------------------------
    # Sim ↔ sprite sync
    # ------------------------------------------------------------------

    def _room_at(self, x: float, y: float) -> Room | None:
        """Return the sim Room at a screen point, or None."""
        for room in self._state.rooms:
            layout = ROOM_LAYOUTS.get(room.name)
            if not layout:
                continue
            if (
                layout.x <= x <= layout.x + layout.w * TILE
                and layout.y <= y <= layout.y + layout.h * TILE
            ):
                return room
        return None

    def _sync_sprites_to_sim(self) -> None:
        """After a sim tick, move sprites to match student locations."""
        for student in self._state.students:
            sprite = self._student_sprites[student.student_id]
            prev_room = self._prev_locations.get(student.student_id)
            curr_room = student.location.name if student.location else None

            # Student changed rooms → walk to new room center
            if (
                curr_room
                and curr_room != prev_room
                and curr_room in ROOM_LAYOUTS
            ):
                cx, cy = ROOM_LAYOUTS[curr_room].center
                sprite.set_target(
                    cx + random.uniform(-25, 25),
                    cy + random.uniform(-20, 20),
                )

            # Student is idle and done walking → show idle pose
            if student.state == StudentState.IDLE and not sprite.is_walking:
                sprite.stop()

            self._prev_locations[student.student_id] = curr_room
