"""Pixel Campus -- main entry point for the Arcade frontend.

Run from the project root:
    python -m src.main_arcade
"""

from pathlib import Path

import arcade
from pyglet import gl, image as pyglet_image

from src.sim.engine import GameState
from src.ui.sprites import load_premade_character_textures
from src.ui.views.campus import CHARACTER_SHEET_NUMS, CampusView

# Screen
SCREEN_WIDTH: int = 1280
SCREEN_HEIGHT: int = 800
SCREEN_TITLE: str = "Pixel Campus"

# Asset paths (resolved relative to project root, not CWD)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ICON_PATH = str(
    _PROJECT_ROOT / "assets/packs/Icons_Essential/v1.2/Icons/Book.png"
)
CHAR_BASE = str(
    _PROJECT_ROOT
    / "assets" / "packs" / "moderninteriors-win"
    / "2_Characters" / "Character_Generator"
    / "0_Premade_Characters" / "48x48"
)


class PixelCampusWindow(arcade.Window):
    """Thin shell that owns the GL context, shared assets, and game state."""

    def __init__(self) -> None:
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.background_color = arcade.color.DARK_SLATE_BLUE

        # Pixel-art rendering -- MUST be set before any sprite creation
        arcade.SpriteList.DEFAULT_TEXTURE_FILTER = gl.GL_NEAREST, gl.GL_NEAREST

        # Window icon
        self.set_icon(pyglet_image.load(_ICON_PATH))

        # Create the simulation
        self.state = GameState.new_game(num_students=20)

        # Load character textures for all premade characters in use
        self.char_textures: dict[int, dict] = {
            num: load_premade_character_textures(num, CHAR_BASE)
            for num in CHARACTER_SHEET_NUMS
        }

        # Launch the campus view
        campus = CampusView(state=self.state, char_textures=self.char_textures)
        self.show_view(campus)


def main() -> None:
    PixelCampusWindow()
    arcade.run()


if __name__ == "__main__":
    main()
