"""HUD overlay for Pixel Campus.

Draws the clock/points bar at top, message log, and control hints.
Reads from GameState but never writes to it.
"""

import arcade

from src.sim.engine import GameState


class HUD:
    """Heads-up display drawn on top of the game view."""

    MAX_MESSAGES = 8

    def __init__(self, screen_width: int, screen_height: int) -> None:
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._messages: list[str] = []

        self._clock_text = arcade.Text(
            "",
            x=screen_width // 2,
            y=screen_height - 25,
            color=arcade.color.WHITE,
            font_size=16,
            anchor_x="center",
            bold=True,
        )

        self._controls_text = arcade.Text(
            "SPACE = tick  |  H = hour  |  Click student \u2192 room to assign",
            x=screen_width // 2,
            y=10,
            color=arcade.color.GRAY,
            font_size=10,
            anchor_x="center",
        )

        # Pre-allocate message log Text objects (6 visible lines)
        self._msg_lines: list[arcade.Text] = []
        for i in range(6):
            line = arcade.Text(
                "",
                x=10,
                y=90 - i * 14,
                color=arcade.color.LIGHT_GRAY,
                font_size=9,
            )
            self._msg_lines.append(line)

    def push_messages(self, messages: list[str]) -> None:
        """Add new log lines, keeping only the most recent."""
        self._messages = (self._messages + messages)[-self.MAX_MESSAGES :]

    def draw(self, state: GameState) -> None:
        """Update and draw all HUD elements."""
        # Clock / points bar
        self._clock_text.text = (
            f"Day {state.clock.day}  |  {state.clock.time_str}  |  "
            f"Points: {state.total_points}/{state.graduation_target}"
        )
        self._clock_text.draw()

        # Message log (bottom-left, newest at top)
        recent = list(reversed(self._messages[-6:]))
        for i, line_text in enumerate(self._msg_lines):
            if i < len(recent):
                line_text.text = recent[i]
            else:
                line_text.text = ""
            line_text.draw()

        # Controls hint
        self._controls_text.draw()
