"""Sprite classes and texture-loading utilities for Pixel Campus.

Pure Arcade layer -- no sim logic, no game state manipulation.
StudentSprite holds a back-reference to a sim Student for reading state only.
"""

import math

import arcade

from src.sim.models import Student

# Tile / sprite dimensions
TILE: int = 48
SPRITE_WIDTH: int = 16
SPRITE_HEIGHT: int = 32
SPRITE_SCALE: float = 2.5

# Movement
MOVEMENT_SPEED: float = 2.0
ARRIVAL_DISTANCE: float = 5.0

# Animation
ANIMATION_SPEED: int = 8  # game frames per animation frame
FRAMES_PER_DIRECTION: int = 6

# Direction frame order in the spritesheets (Kate's remapped order)
FRAME_ORDER: dict[str, int] = {"down": 3, "left": 2, "right": 0, "up": 1}


def tile_texture(
    sheet: arcade.SpriteSheet, col: int, row: int
) -> arcade.Texture:
    """Grab one TILE×TILE tile from a spritesheet by grid position."""
    return sheet.get_texture(arcade.LBWH(col * TILE, row * TILE, TILE, TILE))


def build_room_sprites(
    sheet: arcade.SpriteSheet,
    floor_col: int,
    floor_row: int,
    screen_x: float,
    screen_y: float,
    width_tiles: int,
    height_tiles: int,
) -> arcade.SpriteList:
    """Build a grid of floor tiles and return them as a SpriteList.

    Args:
        sheet: The Room Builder spritesheet.
        floor_col: Column of the floor tile in the tileset.
        floor_row: Row of the floor tile in the tileset.
        screen_x: Left edge of the room on screen (pixels).
        screen_y: Bottom edge of the room on screen (pixels).
        width_tiles: Room width in tiles.
        height_tiles: Room height in tiles.
    """
    sprites = arcade.SpriteList()
    floor_tex = tile_texture(sheet, floor_col, floor_row)

    for tx in range(width_tiles):
        for ty in range(height_tiles):
            sprite = arcade.Sprite(floor_tex)
            sprite.center_x = screen_x + TILE // 2 + tx * TILE
            sprite.center_y = screen_y + TILE // 2 + ty * TILE
            sprites.append(sprite)

    return sprites


def load_character_textures(name: str, char_base: str) -> dict:
    """Load idle + run textures for one character.

    Returns {"idle": {direction: Texture}, "run": {direction: [Texture x6]}}.
    """
    idle_sheet = arcade.load_spritesheet(f"{char_base}/{name}_idle_16x16.png")
    idle = {
        direction: idle_sheet.get_texture(
            arcade.LBWH(order * SPRITE_WIDTH, 0, SPRITE_WIDTH, SPRITE_HEIGHT)
        )
        for direction, order in FRAME_ORDER.items()
    }

    run_sheet = arcade.load_spritesheet(f"{char_base}/{name}_run_16x16.png")
    all_run = run_sheet.get_texture_grid(
        size=(SPRITE_WIDTH, SPRITE_HEIGHT), columns=24, count=24
    )
    run = {
        direction: all_run[order * 6 : (order + 1) * 6]
        for direction, order in FRAME_ORDER.items()
    }

    return {"idle": idle, "run": run}


class StudentSprite(arcade.Sprite):
    """A sprite that wraps a sim Student and handles walk animation."""

    def __init__(
        self, student: Student, textures: dict, scale: float = SPRITE_SCALE
    ) -> None:
        super().__init__(textures["idle"]["down"], scale=scale)
        self.student = student
        self.idle_textures = textures["idle"]
        self.run_textures = textures["run"]

        # Movement
        self.target_x: float | None = None
        self.target_y: float | None = None
        self.direction = "down"
        self.is_walking = False

        # Animation
        self.anim_timer = 0
        self.anim_frame = 0

    def set_target(self, x: float, y: float) -> None:
        """Start walking toward a screen position."""
        self.target_x = x
        self.target_y = y
        self.is_walking = True
        self.anim_timer = 0
        self.anim_frame = 0

    def stop(self) -> None:
        """Stop walking and show the idle texture."""
        self.is_walking = False
        self.target_x = None
        self.target_y = None
        self.texture = self.idle_textures[self.direction]

    def update_movement(self) -> None:
        """Move toward target and animate. Called every frame by the view."""
        if not self.is_walking or self.target_x is None or self.target_y is None:
            return

        dx = self.target_x - self.center_x
        dy = self.target_y - self.center_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < ARRIVAL_DISTANCE:
            self.stop()
            return

        # Normalized direction × speed
        self.center_x += (dx / distance) * MOVEMENT_SPEED
        self.center_y += (dy / distance) * MOVEMENT_SPEED

        # Face the dominant axis
        if abs(dx) > abs(dy):
            self.direction = "right" if dx > 0 else "left"
        else:
            self.direction = "up" if dy > 0 else "down"

        # Advance animation frame
        self.anim_timer += 1
        if self.anim_timer >= ANIMATION_SPEED:
            self.anim_timer = 0
            self.anim_frame = (self.anim_frame + 1) % FRAMES_PER_DIRECTION
            self.texture = self.run_textures[self.direction][self.anim_frame]
