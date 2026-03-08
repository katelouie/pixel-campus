"""Student profile view -- detail panel for a selected student.

Shows stats, skills, journal entries, and preferences.
Stub for now; will be built out later.
"""

import arcade

from src.sim.engine import GameState
from src.sim.models import Student


class ProfileView(arcade.View):
    """Detail screen for one student. ESC returns to the previous view."""

    def __init__(
        self,
        state: GameState,
        student: Student,
        return_view: arcade.View,
    ) -> None:
        super().__init__()
        self._state = state
        self._student = student
        self._return_view = return_view

    def on_draw(self) -> None:
        self.clear()
        arcade.draw_text(
            f"Profile: {self._student.name} (stub)",
            x=self.window.width // 2,
            y=self.window.height // 2,
            color=arcade.color.WHITE,
            font_size=20,
            anchor_x="center",
        )
        arcade.draw_text(
            "Press ESC to go back",
            x=self.window.width // 2,
            y=self.window.height // 2 - 40,
            color=arcade.color.GRAY,
            font_size=12,
            anchor_x="center",
        )

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.ESCAPE:
            self.window.show_view(self._return_view)
