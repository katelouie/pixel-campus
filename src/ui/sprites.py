"""Sprite classes and texture-loading utilities for Pixel Campus.

Pure Arcade layer -- no sim logic, no game state manipulation.
StudentSprite holds a back-reference to a sim Student for reading state only.
"""

import math

import arcade

from src.sim.models import Student

# Map tile size
TILE: int = 48
# Character sprite dimensions (48 wide, 96 tall — two tiles high)
CHAR_W: int = 48
CHAR_H: int = 96
SPRITE_SCALE: float = 1.0

# Movement
MOVEMENT_SPEED: float = 6.0
ARRIVAL_DISTANCE: float = 24.0

# Animation
ANIMATION_SPEED: int = 8  # game frames per animation frame
FRAMES_PER_DIRECTION: int = 6

# New spritesheet layout (moderninteriors premade characters, 48x48)
# Directions in sheet order: East, North, West, South (left to right)
# Internal direction names: right=East, up=North, left=West, down=South
_SHEET_DIR_COL: dict[str, int] = {"right": 0, "up": 1, "left": 2, "down": 3}

# Sit animations are East/West only; map all facings to a valid sit direction
_SIT_DIR_COL: dict[str, int] = {"right": 0, "left": 1}

# Tiled facing property → internal direction name
_FACING_MAP: dict[str, str] = {
    "east": "right", "west": "left", "north": "up", "south": "down",
    "right": "right", "left": "left", "up": "up", "down": "down",
}

# Sit type → sheet row (0-indexed)
_SIT_ROW: dict[str, int] = {"a": 4, "b": 5}

# Throw animation: row 12 (0-indexed), 14 frames per direction, all 4 directions
_THROW_ROW    = 12
THROW_FRAMES  = 14

# Sit point prefix → sit type ("a"=legs visible, "b"=legs under desk)
SIT_TYPE_BY_PREFIX: dict[str, str] = {
    "sit_desk":      "b",
    "sit_computer":  "b",
    "sit_library":   "b",
    "sit_piano":     "b",
    "sit_drums":     "a",
    "sit_guitar":    "a",
    "sit_easel":     "a",
    "sit_cafeteria": "a",
    "sit_gym":       "a",
    "sit_stands":    "a",
    "sit_quad":      "a",
}


def load_premade_character_textures(sheet_num: int, char_base: str) -> dict:
    """Load idle, walk, and sit textures from a moderninteriors premade character sheet.

    Args:
        sheet_num: Character number 1-20.
        char_base: Path to the 48x48 premade characters directory.

    Returns:
        {
            "idle": {direction: Texture},          # static pose, all 4 directions
            "run":  {direction: [Texture x6]},     # walk animation, all 4 directions
            "sit_a": {direction: [Texture x6]},    # sit A (legs visible), east/west only
            "sit_b": {direction: [Texture x6]},    # sit B (legs hidden), east/west only
        }
    """
    path = f"{char_base}/Premade_Character_48x48_{sheet_num:02d}.png"
    sheet = arcade.load_spritesheet(path)

    def row_frames(row: int, start_col: int, n: int) -> list[arcade.Texture]:
        return [
            sheet.get_texture(arcade.LBWH((start_col + i) * CHAR_W, row * CHAR_H, CHAR_W, CHAR_H))
            for i in range(n)
        ]

    # Row 0: default static pose, 1 frame per direction (used as fallback only)
    idle_static = {
        direction: sheet.get_texture(arcade.LBWH(col * CHAR_W, 0, CHAR_W, CHAR_H))
        for direction, col in _SHEET_DIR_COL.items()
    }

    # Row 1: idle animation, 6 frames per direction
    idle_anim = {
        direction: row_frames(1, col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SHEET_DIR_COL.items()
    }

    # Row 2: walk animation, 6 frames per direction
    run = {
        direction: row_frames(2, col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SHEET_DIR_COL.items()
    }

    # Rows 4 & 5: sit A and sit B, 6 frames, east (col 0) and west (col 1) only
    sit_a = {
        direction: row_frames(_SIT_ROW["a"], col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SIT_DIR_COL.items()
    }
    sit_b = {
        direction: row_frames(_SIT_ROW["b"], col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SIT_DIR_COL.items()
    }

    # Row 12: throw animation, 14 frames per direction, all 4 directions
    throw = {
        direction: row_frames(_THROW_ROW, col * THROW_FRAMES, THROW_FRAMES)
        for direction, col in _SHEET_DIR_COL.items()
    }

    return {"idle": idle_static, "idle_anim": idle_anim, "run": run, "sit_a": sit_a, "sit_b": sit_b, "throw": throw}


def load_composited_character_textures(pil_image: "PIL.Image.Image") -> dict:
    """Load character textures from a composited PIL image (same format as premade sheets).

    The PIL image should be 2688x1968 RGBA — identical to a premade character sheet.
    Uses the same frame layout as load_premade_character_textures.
    """
    sheet = arcade.SpriteSheet(image=pil_image)

    def row_frames(row: int, start_col: int, n: int) -> list[arcade.Texture]:
        return [
            sheet.get_texture(arcade.LBWH((start_col + i) * CHAR_W, row * CHAR_H, CHAR_W, CHAR_H))
            for i in range(n)
        ]

    idle_static = {
        direction: sheet.get_texture(arcade.LBWH(col * CHAR_W, 0, CHAR_W, CHAR_H))
        for direction, col in _SHEET_DIR_COL.items()
    }
    idle_anim = {
        direction: row_frames(1, col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SHEET_DIR_COL.items()
    }
    run = {
        direction: row_frames(2, col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SHEET_DIR_COL.items()
    }
    sit_a = {
        direction: row_frames(_SIT_ROW["a"], col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SIT_DIR_COL.items()
    }
    sit_b = {
        direction: row_frames(_SIT_ROW["b"], col * FRAMES_PER_DIRECTION, FRAMES_PER_DIRECTION)
        for direction, col in _SIT_DIR_COL.items()
    }
    throw = {
        direction: row_frames(_THROW_ROW, col * THROW_FRAMES, THROW_FRAMES)
        for direction, col in _SHEET_DIR_COL.items()
    }

    return {"idle": idle_static, "idle_anim": idle_anim, "run": run, "sit_a": sit_a, "sit_b": sit_b, "throw": throw}


def build_room_sprites(
    sheet: arcade.SpriteSheet,
    floor_col: int,
    floor_row: int,
    screen_x: float,
    screen_y: float,
    width_tiles: int,
    height_tiles: int,
) -> arcade.SpriteList:
    """Build a grid of floor tiles and return them as a SpriteList."""
    sprites = arcade.SpriteList()
    floor_tex = sheet.get_texture(arcade.LBWH(floor_col * TILE, floor_row * TILE, TILE, TILE))

    for tx in range(width_tiles):
        for ty in range(height_tiles):
            sprite = arcade.Sprite(floor_tex)
            sprite.center_x = screen_x + TILE // 2 + tx * TILE
            sprite.center_y = screen_y + TILE // 2 + ty * TILE
            sprites.append(sprite)

    return sprites


class StudentSprite(arcade.Sprite):
    """A sprite that wraps a sim Student and handles walk and sit animations."""

    def __init__(
        self, student: Student, textures: dict, scale: float = SPRITE_SCALE
    ) -> None:
        super().__init__(textures["idle"]["down"], scale=scale,
                         hit_box_algorithm=arcade.hitbox.algo_bounding_box)
        self.student = student
        self.idle_textures = textures["idle"]
        self.idle_anim_textures = textures["idle_anim"]
        self.run_textures = textures["run"]
        self.sit_a_textures = textures["sit_a"]
        self.sit_b_textures = textures["sit_b"]
        self.throw_textures = textures["throw"]

        # Movement
        self.target_x: float | None = None
        self.target_y: float | None = None
        self.path: list[tuple[float, float]] = []
        self.direction = "down"
        self.is_walking = False
        self.is_sitting = False
        self.is_stationed = False  # True when arrived at sit OR stand point
        self._sit_type: str = "b"
        self._is_throwing: bool = False
        self._anim_length: int = FRAMES_PER_DIRECTION

        # Stuck detection
        self._stuck_timer: int = 0
        self._last_pos: tuple[float, float] = (0.0, 0.0)

        # Animation
        self.anim_timer = 0
        self.anim_frame = 0

    def set_target(self, x: float, y: float) -> None:
        """Start walking directly to a position (no pathfinding — use set_path instead)."""
        self.is_sitting = False
        self.is_stationed = False
        self._is_throwing = False
        self.path = []
        self.target_x = x
        self.target_y = y
        self.is_walking = True
        self.anim_timer = 0
        self.anim_frame = 0
        self._anim_length = FRAMES_PER_DIRECTION

    def set_path(self, waypoints: list[tuple[float, float]]) -> None:
        """Walk along a sequence of waypoints (e.g. from A* pathfinding)."""
        if not waypoints:
            self.stop()
            return
        self.is_sitting = False
        self.is_stationed = False
        self._is_throwing = False
        self.path = list(waypoints)
        first = self.path.pop(0)
        self.target_x, self.target_y = first
        self.is_walking = True
        self.anim_timer = 0
        self.anim_frame = 0
        self._anim_length = FRAMES_PER_DIRECTION

    def stop(self) -> None:
        """Stop walking; idle animation will take over in update_movement."""
        self.is_walking = False
        self.path = []
        self.target_x = None
        self.target_y = None
        self.change_x = 0.0
        self.change_y = 0.0
        self.anim_timer = 0
        self.anim_frame = 0
        self._is_throwing = False
        self._anim_length = FRAMES_PER_DIRECTION

    def set_standing_at(self, facing: str) -> None:
        """Stop walking and idle-animate facing a specific direction (e.g. at a whiteboard)."""
        self.stop()
        self.is_sitting = False
        self.is_stationed = True
        direction = _FACING_MAP.get(facing, "down")
        self.direction = direction
        self.anim_frame = 0
        self.anim_timer = 0
        self._is_throwing = False
        self._anim_length = FRAMES_PER_DIRECTION

    def set_sitting(self, facing: str, sit_type: str = "b") -> None:
        """Switch to a sitting pose.

        Args:
            facing: Tiled facing property value ("east"/"west"/"north"/"south" etc.)
            sit_type: "a" (legs visible) or "b" (legs hidden under desk).
        """
        self.stop()
        self.is_sitting = True

        direction = _FACING_MAP.get(facing, "right")
        # Sit animations only exist for east/west — north/south sit sidesaddle
        sit_dir = direction if direction in _SIT_DIR_COL else "right"
        self.direction = sit_dir
        self._sit_type = sit_type
        self.is_stationed = True
        self.anim_frame = 0
        self.anim_timer = 0
        self._is_throwing = False
        self._anim_length = FRAMES_PER_DIRECTION

    def set_throwing(self, facing: str) -> None:
        """Play the throw animation, looping (e.g. basketball)."""
        self.stop()
        self.is_sitting = False
        self.is_stationed = True
        self._is_throwing = True
        self._anim_length = THROW_FRAMES
        self.direction = _FACING_MAP.get(facing, "down")
        self.anim_frame = 0
        self.anim_timer = 0

    def _advance_anim(self) -> None:
        """Tick the animation timer and advance frame if ready."""
        self.anim_timer += 1
        if self.anim_timer >= ANIMATION_SPEED:
            self.anim_timer = 0
            self.anim_frame = (self.anim_frame + 1) % self._anim_length

    def update_movement(self) -> None:
        """Set change_x/change_y toward target. PhysicsEngineSimple applies the move."""
        if not self.is_walking or self.target_x is None or self.target_y is None:
            self.change_x = 0.0
            self.change_y = 0.0
            # Animate sitting or idle in place
            self._advance_anim()
            if self.is_sitting:
                sit_textures = self.sit_b_textures if self._sit_type == "b" else self.sit_a_textures
                self.texture = sit_textures[self.direction][self.anim_frame]
            elif self._is_throwing:
                self.texture = self.throw_textures[self.direction][self.anim_frame]
            else:
                self.texture = self.idle_anim_textures[self.direction][self.anim_frame]
            return

        dx = self.target_x - self.center_x
        dy = self.target_y - self.center_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < ARRIVAL_DISTANCE:
            if self.path:
                self.target_x, self.target_y = self.path.pop(0)
            else:
                self.stop()
            self._stuck_timer = 0
            return

        # Stuck detection: if barely moved in 30 frames, skip to next waypoint
        moved = math.sqrt(
            (self.center_x - self._last_pos[0]) ** 2
            + (self.center_y - self._last_pos[1]) ** 2
        )
        if moved < 0.5:
            self._stuck_timer += 1
            if self._stuck_timer > 30:
                self._stuck_timer = 0
                if self.path:
                    self.target_x, self.target_y = self.path.pop(0)
                else:
                    self.stop()
                return
        else:
            self._stuck_timer = 0
        self._last_pos = (self.center_x, self.center_y)

        # Normalized direction × speed — physics engine applies the actual move
        self.change_x = (dx / distance) * MOVEMENT_SPEED
        self.change_y = (dy / distance) * MOVEMENT_SPEED

        # Face the dominant axis
        if abs(dx) > abs(dy):
            self.direction = "right" if dx > 0 else "left"
        else:
            self.direction = "up" if dy > 0 else "down"

        # Advance walk animation frame
        self._advance_anim()
        self.texture = self.run_textures[self.direction][self.anim_frame]
