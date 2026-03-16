"""Pixel-perfect bitmap font renderer using monogram-bitmap.json.

Each character is 12 rows × 5 columns, stored as 5-bit row bitmasks.
Bit 0 = leftmost column, bit 4 = rightmost column.
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

    All textures are cached by string, so each unique string is only rendered once.
    """

    def __init__(self, scale: int = 2, color: tuple[int, int, int, int] = (30, 30, 30, 255)) -> None:
        self.scale = scale
        self.color = color
        with open(_JSON_PATH) as f:
            self._data: dict[str, list[int]] = json.load(f)
        self._cache: dict[str, arcade.Texture] = {}

    @property
    def char_height(self) -> int:
        """Height in pixels of a rendered character (includes top/bottom padding rows)."""
        return _CHAR_H * self.scale

    @property
    def line_spacing(self) -> int:
        """Suggested line spacing in pixels."""
        return _CHAR_H * self.scale

    def _render(self, text: str) -> arcade.Texture:
        s = self.scale
        char_w = _CHAR_W * s
        char_h = _CHAR_H * s
        gap    = _GAP * s

        if not text:
            return arcade.Texture(_PILImage.new("RGBA", (1, char_h), (0, 0, 0, 0)))

        total_w = len(text) * (char_w + gap) - gap
        img = _PILImage.new("RGBA", (total_w, char_h), (0, 0, 0, 0))
        pixels = img.load()

        x = 0
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
                                    pixels[px, py] = self.color
            x += char_w + gap

        return arcade.Texture(img)

    def get_texture(self, text: str) -> arcade.Texture:
        """Return a cached texture for the given text string."""
        if text not in self._cache:
            self._cache[text] = self._render(text)
        return self._cache[text]
