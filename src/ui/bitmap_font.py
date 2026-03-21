"""Pixel-perfect bitmap font renderer using monogram-bitmap.json.

Each character is 12 rows x 5 columns, stored as 5-bit row bitmasks.
Bit 0 = leftmost column, bit 4 = rightmost column.

Supports:
- Single-line rendering (cached by string)
- Word-wrapping into lines given a pixel width
- Multiple color presets via color parameter
"""

import json
from pathlib import Path

import arcade
from PIL import Image as _PILImage

_JSON_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "assets/fonts/monogram-bitmap.json"
)

_CHAR_W = 5   # pixels wide per character (pre-scale)
_CHAR_H = 12  # pixels tall per character (pre-scale)
_GAP    = 1   # pixels between characters (pre-scale)


class BitmapFont:
    """Renders text strings to arcade.Texture objects using the monogram bitmap font.

    All textures are cached by (string, color), so each unique combination
    is only rendered once.
    """

    def __init__(self, scale: int = 2, color: tuple[int, int, int, int] = (30, 30, 30, 255)) -> None:
        self.scale = scale
        self.default_color = color
        with open(_JSON_PATH) as f:
            self._data: dict[str, list[int]] = json.load(f)
        self._cache: dict[tuple[str, tuple], arcade.Texture] = {}

    @property
    def char_width(self) -> int:
        """Width in pixels of a single rendered character (including gap)."""
        return (_CHAR_W + _GAP) * self.scale

    @property
    def char_height(self) -> int:
        """Height in pixels of a rendered character."""
        return _CHAR_H * self.scale

    @property
    def line_spacing(self) -> int:
        """Suggested line spacing in pixels."""
        return _CHAR_H * self.scale

    def _render(self, text: str, color: tuple[int, int, int, int]) -> arcade.Texture:
        s = self.scale
        char_w = _CHAR_W * s
        char_h = _CHAR_H * s
        gap    = _GAP * s

        if not text:
            return arcade.Texture(_PILImage.new("RGBA", (1, char_h), (0, 0, 0, 0)))

        total_w = len(text) * (char_w + gap) - gap + s  # +s padding on left to prevent clipping
        img = _PILImage.new("RGBA", (total_w, char_h), (0, 0, 0, 0))
        pixels = img.load()

        x = s  # start after left padding
        for ch in text:
            rows = self._data.get(ch, self._data.get("?", [0] * _CHAR_H))
            for row_i, mask in enumerate(rows):
                for col in range(_CHAR_W):
                    if mask & (1 << col):
                        for dy in range(s):
                            for dx in range(s):
                                px = x + col * s + dx
                                py = row_i * s + dy
                                if 0 <= px < total_w and 0 <= py < char_h:
                                    pixels[px, py] = color
            x += char_w + gap

        return arcade.Texture(img)

    def get_texture(self, text: str, color: tuple[int, int, int, int] | None = None) -> arcade.Texture:
        """Return a cached texture for the given text string and color."""
        c = color or self.default_color
        key = (text, c)
        if key not in self._cache:
            self._cache[key] = self._render(text, c)
        return self._cache[key]

    def wrap_lines(self, text: str, max_width_px: int) -> list[str]:
        """Word-wrap text into lines that fit within max_width_px.

        Uses monospace character math: each char is (CHAR_W + GAP) * scale pixels.
        Wraps at word boundaries when possible, hard-breaks long words.
        """
        max_chars = max(1, max_width_px // self.char_width)
        words = text.split(" ")
        lines: list[str] = []
        current_line = ""

        for word in words:
            # Handle words longer than max_chars — hard break
            if len(word) > max_chars:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                while len(word) > max_chars:
                    lines.append(word[:max_chars])
                    word = word[max_chars:]
                if word:
                    current_line = word
                continue

            # Normal word — check if it fits on current line
            if not current_line:
                current_line = word
            elif len(current_line) + 1 + len(word) <= max_chars:
                current_line += " " + word
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines if lines else [""]

    def get_wrapped_textures(
        self, text: str, max_width_px: int,
        color: tuple[int, int, int, int] | None = None,
    ) -> list[arcade.Texture]:
        """Word-wrap text and return a list of textures, one per line."""
        lines = self.wrap_lines(text, max_width_px)
        c = color or self.default_color
        return [self.get_texture(line, c) for line in lines]
