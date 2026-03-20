"""Character sprite compositor — layers body, eyes, outfit, hair into unique characters.

Takes a CharacterAppearance and produces a composited PIL spritesheet
identical in format to the premade character sheets. The result plugs
directly into the existing StudentSprite animation system.

Compositing order (from CHARACTER_GENERATOR.txt):
  1. Body (skin tone)
  2. Eyes
  3. Outfit
  4. Hairstyle
  5. Accessory (optional)
"""

import json
import random
from pathlib import Path

from PIL import Image

from src.sim.models import CharacterAppearance

# ── Asset paths ─────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SPRITE_BASE = _PROJECT_ROOT / "assets/packs/moderninteriors-win/2_Characters/Character_Generator"
_PORTRAIT_BASE = _PROJECT_ROOT / "assets/packs/modernuserinterface-win/48x48/Portrait_Generator_48x48"
_CATALOG_PATH = _PROJECT_ROOT / "src/data/character_catalog.json"
_SIZE = "48x48"

# Target sheet width (body sheets are wider, need cropping)
_TARGET_W = 2688

# ── Catalog ─────────────────────────────────────────────────────────

with open(_CATALOG_PATH) as f:
    _CATALOG = json.load(f)


def _outfit_max_color(style: int) -> int:
    """Max color variant for a given outfit style."""
    colors = _CATALOG["outfits"]["styles"].get(str(style), [])
    return max(colors) if colors else 1


def _hair_max_color(style: int) -> int:
    """Max color variant for a given hairstyle."""
    colors = _CATALOG["hairstyles"]["styles"].get(str(style), [])
    return max(colors) if colors else 7


def _accessory_info(style: int) -> dict | None:
    """Get accessory name and colors, or None if style doesn't exist."""
    return _CATALOG["accessories"]["styles"].get(str(style))


# ── Path builders ───────────────────────────────────────────────────


def _sprite_path(component: str, style: int, color: int | None = None) -> Path:
    """Build path to a sprite component sheet."""
    if component == "Body":
        return _SPRITE_BASE / "Bodies" / _SIZE / f"Body_{_SIZE}_{style:02d}.png"
    elif component == "Eyes":
        return _SPRITE_BASE / "Eyes" / _SIZE / f"Eyes_{_SIZE}_{style:02d}.png"
    elif component == "Outfit":
        return _SPRITE_BASE / "Outfits" / _SIZE / f"Outfit_{style:02d}_{_SIZE}_{color:02d}.png"
    elif component == "Hairstyle":
        return _SPRITE_BASE / "Hairstyles" / _SIZE / f"Hairstyle_{style:02d}_{_SIZE}_{color:02d}.png"
    elif component == "Accessory":
        info = _accessory_info(style)
        if info is None:
            raise FileNotFoundError(f"No accessory style {style}")
        name = info["name"]
        return _SPRITE_BASE / "Accessories" / _SIZE / f"Accessory_{style:02d}_{name}_{_SIZE}_{color:02d}.png"
    raise ValueError(f"Unknown component: {component}")


def _portrait_path(component: str, style: int, color: int | None = None) -> Path:
    """Build path to a portrait component sheet. Color numbers NOT zero-padded."""
    if component == "Skin":
        return _PORTRAIT_BASE / "Skins_48x48" / f"PG_Skin_48x48_{style}.png"
    elif component == "Eyes":
        return _PORTRAIT_BASE / "Eyes_48x48" / f"PG_Eyes_48x48_{style:02d}.png"
    elif component == "Hairstyle":
        return _PORTRAIT_BASE / "Hairstyles_48x48" / f"PG_Hairstyle_{style:02d}_48x48_{color}.png"
    elif component == "Accessory":
        info = _accessory_info(style)
        if info is None:
            raise FileNotFoundError(f"No accessory style {style}")
        name = info["name"]
        return _PORTRAIT_BASE / "Accessories_48x48" / f"PG_Accessory_{style:02d}_{name}_48x48_{color}.png"
    raise ValueError(f"Unknown portrait component: {component}")


# ── Compositing ─────────────────────────────────────────────────────


def composite_sprite_sheet(appearance: CharacterAppearance) -> Image.Image:
    """Composite a full character spritesheet from layered components.

    Returns a PIL Image identical in format to premade character sheets
    (2688x1968 RGBA). Can be fed directly into the sprite texture loader.
    """
    # 1. Body (crop to target width)
    body = Image.open(_sprite_path("Body", appearance.body)).convert("RGBA")
    if body.size[0] > _TARGET_W:
        body = body.crop((0, 0, _TARGET_W, body.size[1]))

    result = body.copy()

    # 2. Eyes
    result.alpha_composite(Image.open(_sprite_path("Eyes", appearance.eyes)))

    # 3. Outfit
    result.alpha_composite(
        Image.open(_sprite_path("Outfit", appearance.outfit, appearance.outfit_color))
    )

    # 4. Hairstyle
    result.alpha_composite(
        Image.open(_sprite_path("Hairstyle", appearance.hairstyle, appearance.hair_color))
    )

    # 5. Accessory (optional)
    if appearance.accessory is not None and appearance.accessory_color is not None:
        acc_path = _sprite_path("Accessory", appearance.accessory, appearance.accessory_color)
        if acc_path.exists():
            result.alpha_composite(Image.open(acc_path))

    return result


def composite_portrait_sheet(appearance: CharacterAppearance) -> Image.Image:
    """Composite a portrait sheet from layered components.

    Returns a PIL Image (960x288 RGBA) — the head portrait grid.
    Portraits don't include outfits (head only).
    """
    # 1. Skin (maps to body number)
    skin = Image.open(_portrait_path("Skin", appearance.body)).convert("RGBA")
    result = skin.copy()

    # 2. Eyes
    result.alpha_composite(Image.open(_portrait_path("Eyes", appearance.eyes)))

    # 3. Hairstyle
    result.alpha_composite(
        Image.open(_portrait_path("Hairstyle", appearance.hairstyle, appearance.hair_color))
    )

    # 4. Accessory (optional)
    if appearance.accessory is not None and appearance.accessory_color is not None:
        acc_path = _portrait_path("Accessory", appearance.accessory, appearance.accessory_color)
        if acc_path.exists():
            result.alpha_composite(Image.open(acc_path))

    return result


# ── Random appearance generation ────────────────────────────────────


# ── Portrait extraction ──────────────────────────────────────────────

# Portrait grid: 10 columns × 3 rows of 96×96 cells
# Row 0 = neutral, Row 1 = happy, Row 2 = alternate
# Col 1 = front-facing
_PORTRAIT_CELL = 96
_PORTRAIT_FRONT_COL = 1
_PORTRAIT_NEUTRAL_ROW = 0


def extract_portrait(appearance: CharacterAppearance, row: int = 0) -> Image.Image:
    """Extract a single front-facing portrait from a composited portrait sheet.

    Args:
        appearance: The character's visual identity.
        row: 0=neutral, 1=happy, 2=alternate expression.

    Returns:
        A 96×96 RGBA PIL Image of the character's face.
    """
    sheet = composite_portrait_sheet(appearance)
    x = _PORTRAIT_FRONT_COL * _PORTRAIT_CELL
    y = row * _PORTRAIT_CELL
    return sheet.crop((x, y, x + _PORTRAIT_CELL, y + _PORTRAIT_CELL))


def extract_portrait_texture(appearance: CharacterAppearance, row: int = 0) -> "arcade.Texture":
    """Extract a front-facing portrait as an arcade Texture, ready for display."""
    import arcade
    portrait_img = extract_portrait(appearance, row)
    return arcade.Texture(portrait_img)


# ── Random appearance generation ────────────────────────────────────


def random_appearance(student_id: int) -> CharacterAppearance:
    """Generate a random CharacterAppearance, seeded by student_id for determinism."""
    rng = random.Random(student_id + 1000)  # offset to avoid collision with other seeded randoms

    body = rng.randint(1, 9)
    eyes = rng.randint(1, 7)
    hairstyle = rng.randint(1, 29)
    hair_color = rng.randint(1, _hair_max_color(hairstyle))
    outfit = rng.randint(1, 33)
    outfit_color = rng.randint(1, _outfit_max_color(outfit))

    # 25% chance of accessory (skip combat/weird ones, prefer school-appropriate)
    _SCHOOL_ACCESSORIES = [3, 4, 5, 11, 15]  # Backpack, Snapback, Dino_Snapback, Beanie, Glasses
    accessory = None
    accessory_color = None
    if rng.random() < 0.25:
        acc_style = rng.choice(_SCHOOL_ACCESSORIES)
        info = _accessory_info(acc_style)
        if info:
            accessory = acc_style
            accessory_color = rng.choice(info["colors"])

    return CharacterAppearance(
        body=body,
        eyes=eyes,
        outfit=outfit,
        outfit_color=outfit_color,
        hairstyle=hairstyle,
        hair_color=hair_color,
        accessory=accessory,
        accessory_color=accessory_color,
    )
