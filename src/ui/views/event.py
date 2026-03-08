"""Event view -- modal overlay for campus events.

Displays event results (Basketball Game, Prom, Finals, etc.)
and dismisses on any keypress.
Stub for now; will be built out later.
"""

import arcade

from src.sim.engine import GameState


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

    def on_draw(self) -> None:
        self.clear()
        arcade.draw_text(
            self._event_text,
            x=self.window.width // 2,
            y=self.window.height // 2,
            color=arcade.color.YELLOW,
            font_size=18,
            anchor_x="center",
        )
        arcade.draw_text(
            "Press any key to continue",
            x=self.window.width // 2,
            y=self.window.height // 2 - 40,
            color=arcade.color.GRAY,
            font_size=12,
            anchor_x="center",
        )

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        self.window.show_view(self._return_view)
