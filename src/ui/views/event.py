"""Event view -- modal overlay for campus events.

Displays event results (Basketball Game, Prom, Finals, etc.)
and dismisses on any keypress.
Stub for now; will be built out later.
"""

import arcade

from src.sim.engine import GameState
from src.ui.font import FONT_NAME


class EventView(arcade.View):
    """Modal screen showing a campus event. Any key dismisses."""

    def __init__(
        self,
        state: GameState,
        event_text: str,
        return_view: arcade.View,
    ) -> None:
        super().__init__()
        self._state = state
        self._event_text = event_text
        self._return_view = return_view
        self._title_text: arcade.Text | None = None
        self._hint_text: arcade.Text | None = None

    def on_show_view(self) -> None:
        cx = self.window.width // 2
        cy = self.window.height // 2
        self._title_text = arcade.Text(
            self._event_text, cx, cy,
            color=arcade.color.YELLOW, font_size=18,
            anchor_x="center", font_name=FONT_NAME,
        )
        self._hint_text = arcade.Text(
            "Press any key to continue", cx, cy - 40,
            color=arcade.color.GRAY, font_size=12,
            anchor_x="center", font_name=FONT_NAME,
        )

    def on_draw(self) -> None:
        self.clear()
        if self._title_text:
            self._title_text.draw()
        if self._hint_text:
            self._hint_text.draw()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)
