"""Pixel Campus -- main entry point for the Arcade frontend.

Run from the project root:
    python -m src.main_arcade
"""

from pathlib import Path

import arcade
from pyglet import gl

from src.sim.engine import GameState
from src.ui.sprites import load_character_textures
from src.ui.views.campus import CampusView

# Screen
SCREEN_WIDTH: int = 900
SCREEN_HEIGHT: int = 700
SCREEN_TITLE: str = "Pixel Campus"

# Asset paths (resolved relative to project root, not CWD)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ASSET_BASE = _PROJECT_ROOT / "assets" / "sprites" / "Modern tiles_Free"
ROOM_BUILDER_PATH = str(
    _ASSET_BASE / "Interiors_free" / "48x48" / "Room_Builder_free_48x48.png"
)
INTERIORS_PATH = str(
    _ASSET_BASE / "Interiors_free" / "48x48" / "Interiors_free_48x48.png"
)
CHAR_BASE = str(_ASSET_BASE / "Characters_free")
CHARACTER_SHEETS: list[str] = ["Adam", "Alex", "Amelia", "Bob"]


class PixelCampusWindow(arcade.Window):
    """Thin shell that owns the GL context, shared assets, and game state."""

    def __init__(self) -> None:
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.background_color = arcade.color.DARK_SLATE_BLUE

        # Pixel-art rendering -- MUST be set before any sprite creation
        arcade.SpriteList.DEFAULT_TEXTURE_FILTER = gl.GL_NEAREST, gl.GL_NEAREST

        # Create the simulation
        self.state = GameState.new_game(num_students=4)

        # Load shared spritesheets (expensive, do once)
        self.room_builder_sheet = arcade.load_spritesheet(ROOM_BUILDER_PATH)
        self.interiors_sheet = arcade.load_spritesheet(INTERIORS_PATH)

        # Load character textures for all available characters
        self.char_textures: dict[str, dict] = {
            name: load_character_textures(name, CHAR_BASE)
            for name in CHARACTER_SHEETS
        }

        # Launch the campus view
        campus = CampusView(
            state=self.state,
            room_builder_sheet=self.room_builder_sheet,
            interiors_sheet=self.interiors_sheet,
            char_textures=self.char_textures,
        )
        self.show_view(campus)


def main() -> None:
    PixelCampusWindow()
    arcade.run()


if __name__ == "__main__":
    main()
