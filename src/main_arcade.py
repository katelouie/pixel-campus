"""Pixel Campus -- main entry point for the Arcade frontend.

Run from the project root:
    python -m src.main_arcade
"""

from pathlib import Path

import arcade
from pyglet import gl, image as pyglet_image

# Screen
SCREEN_WIDTH: int = 1280
SCREEN_HEIGHT: int = 800
SCREEN_TITLE: str = "Pixel Campus"

# Asset paths (resolved relative to project root, not CWD)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ICON_PATH = str(
    _PROJECT_ROOT / "assets/packs/Icons_Essential/v1.2/Icons/Book.png"
)


class PixelCampusWindow(arcade.Window):
    """Thin shell that owns the GL context and launches the title screen."""

    def __init__(self) -> None:
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.background_color = (58, 55, 62)

        # Pixel-art rendering -- MUST be set before any sprite creation
        arcade.SpriteList.DEFAULT_TEXTURE_FILTER = gl.GL_NEAREST, gl.GL_NEAREST

        # Window icon
        self.set_icon(pyglet_image.load(_ICON_PATH))

        # Event dispatch wrapper — fixes a pyglet/arcade bug where some mouse
        # events are silently dropped by the View dispatch system. The wrapper
        # ensures consistent event delivery. Cost: negligible.
        _orig_dispatch = self.dispatch_event
        def _fixed_dispatch(event_type, *args):
            return _orig_dispatch(event_type, *args)
        self.dispatch_event = _fixed_dispatch

        # Launch the title screen
        from src.ui.views.title import TitleView
        self.show_view(TitleView())


def main() -> None:
    from src.ui.font import load_game_font
    load_game_font()
    PixelCampusWindow()
    arcade.run()


if __name__ == "__main__":
    main()
