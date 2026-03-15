"""Room builder for Pixel Campus.

Generates .tmx Tiled map files from a RoomPalette of tile references.
Output files can be opened in the Tiled GUI for editing, and loaded
by arcade.tilemap in the game.

Usage:
    builder = RoomBuilder(assets_root)
    builder.build_tmx(
        PALETTE_HOME_WOOD,
        width=14, height=13,
        output_path=Path("rooms/home.tmx"),
    )

Room anatomy (W tiles wide, H tiles tall):

    col:  0    1    2    3  ...  W-3  W-2  W-1
    r0:   ext  ext  TLc  WAL  ..  WAL  TRc  ext   ← back wall row 0
    r1:   ext  ext  TLc  WAL  ..  WAL  TRc  ext   ← back wall row 1
    r2:   BOR  BOR  SdL  FLR  ..  FLR  SdR  ext   ← side walls + floor
    ...   BOR  BOR  SdL  FLR  ..  FLR  SdR  ext
    rH-2: BOR  BOR  SdL  FLR  ..  FLR  SdR  ext
    rH-1: THR  THR  ENL  FLR  ..  FLR  ENR  THR   ← entrance row

    ext = empty  TLc/TRc = 3D corner  WAL = wall strip
    SdL/SdR = 3D side straight  FLR = floor fill
    BOR = border trim  THR = threshold  ENL/ENR = entrance corner
"""

from __future__ import annotations

import base64
import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

TILE_SIZE = 48

# Sheet name → filename inside Room_Builder_subfiles_48x48/
_SUBFILE_FILES: dict[str, str] = {
    "floors":     "Room_Builder_Floors_48x48.png",
    "walls":      "Room_Builder_Walls_48x48.png",
    "3d_walls":   "Room_Builder_3d_walls_48x48.png",
    "borders":    "Room_Builder_borders_48x48.png",
    "arches":     "Room_Builder_Arched_Entryways_48x48.png",
    "connectors": "Room_Builder_Floor_Connectors_48x48.png",
}
_FULL_SHEET_NAME = "full"
_FULL_SHEET_FILE = "Room_Builder_48x48.png"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TileRef:
    """A reference to one tile by sheet name and grid position.

    Col/row indices match the 16×16 grid coordinates documented in
    ROOM_GRAMMAR_16x16.md — the 48×48 sheets use the same grid layout,
    just with larger pixels per tile.
    """
    sheet: str   # key in _SUBFILE_FILES, or "full" for the combined sheet
    col: int
    row: int


@dataclass
class RoomPalette:
    """Tile assignments for each structural role in a room.

    Built-in instances: PALETTE_HOME_WOOD, PALETTE_MUSEUM_GRAY.

    Floor shadow rules (derived from Kate's corrected example):
      - Row 2 (below back wall)  → floor_shadow / floor_l_edge_shadow
      - Col 3 (beside left 3D wall) → floor_l_edge / floor_l_edge_shadow
      - All other interior cells  → floor
    """
    # ── Floor tiles ────────────────────────────────────────────────────
    floor: TileRef                          # plain fill (everywhere)
    floor_shadow: Optional[TileRef] = None  # row 2, cols 4+ (top-wall shadow)
    floor_l_edge: Optional[TileRef] = None  # col 3, rows 3+ (side-wall shadow)
    floor_l_edge_shadow: Optional[TileRef] = None  # col 3, row 2 (both shadows)

    # ── Back wall (rows 0–1) ───────────────────────────────────────────
    wall_top: Optional[TileRef] = None   # upper strip tile
    wall_low: Optional[TileRef] = None   # lower strip tile
    corner_tl: Optional[list[TileRef]] = None   # [row0, row1] top-left corner
    corner_tr: Optional[list[TileRef]] = None   # [row0, row1] top-right corner

    # ── Side walls (rows 2 to H-3) ────────────────────────────────────
    side_l: Optional[TileRef] = None
    side_r: Optional[TileRef] = None

    # ── Front wall (row H-2) ──────────────────────────────────────────
    front_wall_l_corner: Optional[TileRef] = None  # 3D_1005  left end
    front_wall_r_corner: Optional[TileRef] = None  # 3D_1305  right end
    front_wall_fill:     Optional[TileRef] = None  # 3D_1205  horizontal fill

    # ── Doorway cut-through (rows H-2 and H-1) ────────────────────────
    doorway_l:      Optional[TileRef] = None  # 3D_0904  left corner overlay
    doorway_r:      Optional[TileRef] = None  # 3D_1404  right corner overlay
    doorway_l_base: Optional[TileRef] = None  # 3D_0905  left base (row H-1)
    doorway_r_base: Optional[TileRef] = None  # 3D_1405  right base (row H-1)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class RoomBuilder:
    """Generates .tmx files from a RoomPalette and tile dimensions.

    Tilesets in the output .tmx are referenced by path relative to the
    output file, so the file is portable as long as the relative structure
    is preserved.
    """

    def __init__(self, assets_root: Path) -> None:
        """
        Args:
            assets_root: Root of the pixel-campus assets tree
                         (the directory that contains ``packs/``).
        """
        base = assets_root / "packs/moderninteriors-win/1_Interiors/48x48"
        self._subfiles_dir = base / "Room_Builder_subfiles_48x48"
        self._full_sheet   = base / _FULL_SHEET_FILE

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sheet_path(self, sheet: str) -> Path:
        if sheet == _FULL_SHEET_NAME:
            return self._full_sheet
        return self._subfiles_dir / _SUBFILE_FILES[sheet]

    def _sheet_dims(self, sheet: str) -> tuple[int, int]:
        """Return (cols, rows) tile count for a sheet."""
        with Image.open(self._sheet_path(sheet)) as img:
            w, h = img.size
        return w // TILE_SIZE, h // TILE_SIZE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_tmx(
        self,
        palette: RoomPalette,
        width: int,
        height: int,
        output_path: Path,
        doorway_center: int = -1,
        doorway_width: int = 3,
    ) -> None:
        """Write a .tmx file for a room of the given tile dimensions.

        Room anatomy (rows):
          0–1      back wall (3D corners + WAL strips)
          2–H-3    interior  (side walls + floor)
          H-2      front wall row (with doorway cut-through)
          H-1      doorway base row (wall pieces flanking the opening)

        Args:
            palette:        Tile selections for each structural role.
            width:          Room width in tiles (minimum 9).
            height:         Room height in tiles (minimum 6).
            output_path:    Destination .tmx file path.
            doorway_center: Centre column of the doorway opening.
                            Defaults to ``width // 2``.
            doorway_width:  Number of open tiles in the doorway (default 3).
        """
        if width < 9 or height < 6:
            raise ValueError(
                f"Room must be at least 9×6 tiles, got {width}×{height}"
            )

        # Doorway geometry
        if doorway_center < 0:
            doorway_center = width // 2
        open_start = doorway_center - doorway_width // 2   # first open column
        open_end   = open_start + doorway_width - 1        # last open column
        dw_l = open_start - 1   # doorway_l corner column
        dw_r = open_end   + 1   # doorway_r corner column

        # Discover which sheets this palette uses, in encounter order
        used_sheets = _collect_sheets(palette)

        # Read each sheet's tile grid dimensions and assign firstgids
        sheet_cols: dict[str, int] = {}
        sheet_rows: dict[str, int] = {}
        firstgids:  dict[str, int] = {}
        next_gid = 1
        for sheet in used_sheets:
            cols, rows = self._sheet_dims(sheet)
            sheet_cols[sheet] = cols
            sheet_rows[sheet] = rows
            firstgids[sheet] = next_gid
            next_gid += cols * rows

        def gid(ref: TileRef | None) -> int:
            """TileRef → TMX GID (0 = empty)."""
            if ref is None:
                return 0
            return firstgids[ref.sheet] + ref.row * sheet_cols[ref.sheet] + ref.col

        # Allocate grids (0 = empty tile)
        floors = [[0] * width for _ in range(height)]
        walls  = [[0] * width for _ in range(height)]

        # ── Floor fill ──────────────────────────────────────────────────
        # Interior rows 2 to H-3: four floor tile variants by position.
        for r in range(2, height - 2):
            for c in range(3, width - 2):
                shadow_row = (r == 2)
                left_col   = (c == 3)
                if shadow_row and left_col:
                    ref = palette.floor_l_edge_shadow or palette.floor_shadow or palette.floor
                elif shadow_row:
                    ref = palette.floor_shadow or palette.floor
                elif left_col:
                    ref = palette.floor_l_edge or palette.floor
                else:
                    ref = palette.floor
                floors[r][c] = gid(ref)

        # Front wall row (H-2): floor only under the doorway span.
        # dw_l column gets the left-edge shadow tile (it's the leftmost floor
        # tile in this row, adjacent to the doorway-l wall piece).
        for c in range(dw_l, dw_r + 1):
            ref = palette.floor_l_edge or palette.floor if c == dw_l else palette.floor
            floors[height - 2][c] = gid(ref)

        # Passthrough row (H-1): floor in the open doorway only.
        # Leftmost open column gets the left-edge shadow if available.
        for c in range(open_start, open_end + 1):
            ref = palette.floor_l_edge or palette.floor if c == open_start else palette.floor
            floors[height - 1][c] = gid(ref)

        # ── Back wall corners (rows 0–1) ────────────────────────────────
        if palette.corner_tl:
            for i in range(min(2, len(palette.corner_tl))):
                walls[i][2] = gid(palette.corner_tl[i])
        if palette.corner_tr:
            for i in range(min(2, len(palette.corner_tr))):
                walls[i][width - 2] = gid(palette.corner_tr[i])

        # ── Back wall strips (rows 0–1, cols 3 to W-3) ─────────────────
        if palette.wall_top and palette.wall_low:
            for c in range(3, width - 2):
                walls[0][c] = gid(palette.wall_top)
                walls[1][c] = gid(palette.wall_low)

        # ── Side-wall straights (rows 2 to H-3) ─────────────────────────
        if palette.side_l and palette.side_r:
            for r in range(2, height - 2):
                walls[r][2]         = gid(palette.side_l)
                walls[r][width - 2] = gid(palette.side_r)

        # ── Front wall (row H-2) ─────────────────────────────────────────
        if palette.front_wall_l_corner:
            walls[height - 2][2] = gid(palette.front_wall_l_corner)
        if palette.front_wall_r_corner:
            walls[height - 2][width - 2] = gid(palette.front_wall_r_corner)
        if palette.front_wall_fill:
            for c in range(3, dw_l):
                walls[height - 2][c] = gid(palette.front_wall_fill)
            for c in range(dw_r + 1, width - 2):
                walls[height - 2][c] = gid(palette.front_wall_fill)

        # ── Doorway corners (row H-2) ────────────────────────────────────
        if palette.doorway_l:
            walls[height - 2][dw_l] = gid(palette.doorway_l)
        if palette.doorway_r:
            walls[height - 2][dw_r] = gid(palette.doorway_r)

        # ── Doorway base (row H-1) ───────────────────────────────────────
        if palette.doorway_l_base:
            walls[height - 1][dw_l] = gid(palette.doorway_l_base)
        if palette.doorway_r_base:
            walls[height - 1][dw_r] = gid(palette.doorway_r_base)

        # ── Emit tsx + tmx ─────────────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write a .tsx file per sheet (next to the .tmx) so Tiled can load
        # the tileset image.  Reuses existing tsx files if already present.
        tsx_sources: list[str] = []
        for sheet in used_sheets:
            tsx_name = f"{sheet}.tsx"
            tsx_path = output_path.parent / tsx_name
            if not tsx_path.exists():
                _write_tsx(
                    tsx_path=tsx_path,
                    name=sheet,
                    cols=sheet_cols[sheet],
                    rows=sheet_rows[sheet],
                    image_path=self._sheet_path(sheet),
                )
            tsx_sources.append(tsx_name)

        _write_tmx(
            output_path=output_path,
            width=width,
            height=height,
            tilesets=[
                {"firstgid": firstgids[sheet], "source": tsx_sources[i]}
                for i, sheet in enumerate(used_sheets)
            ],
            layers=[("Floors", floors), ("Walls", walls)],
        )

        print(f"Written: {output_path}  ({width}×{height} tiles, {len(used_sheets)} sheet(s))")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sheets(palette: RoomPalette) -> list[str]:
    """Return the unique sheet names used by palette, in first-encounter order."""
    seen: set[str] = set()
    order: list[str] = []
    refs: list[TileRef | None] = [
        palette.floor, palette.floor_shadow,
        palette.floor_l_edge, palette.floor_l_edge_shadow,
        palette.wall_top, palette.wall_low,
        *(palette.corner_tl or []), *(palette.corner_tr or []),
        palette.side_l, palette.side_r,
        palette.front_wall_l_corner, palette.front_wall_r_corner,
        palette.front_wall_fill,
        palette.doorway_l, palette.doorway_r,
        palette.doorway_l_base, palette.doorway_r_base,
    ]
    for ref in refs:
        if ref is not None and ref.sheet not in seen:
            seen.add(ref.sheet)
            order.append(ref.sheet)
    return order


def _encode_layer(grid: list[list[int]]) -> str:
    """Pack a GID grid into Tiled's base64+zlib layer data format.

    Each GID is stored as a little-endian 32-bit unsigned int, the byte
    array is zlib-compressed, then base64-encoded — identical to what
    Tiled itself writes when saving with base64+zlib encoding.
    """
    flat = [gid for row in grid for gid in row]
    raw = struct.pack(f"<{len(flat)}I", *flat)
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def _write_tsx(
    tsx_path: Path,
    name: str,
    cols: int,
    rows: int,
    image_path: Path,
) -> None:
    """Write a Tiled external tileset (.tsx) file."""
    img_src = _relpath(tsx_path.parent, image_path)
    tilecount = cols * rows
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<tileset version="1.10" tiledversion="1.11.2"'
        f' name="{name}" tilewidth="{TILE_SIZE}" tileheight="{TILE_SIZE}"'
        f' tilecount="{tilecount}" columns="{cols}">',
        f' <image source="{img_src}"'
        f' width="{cols * TILE_SIZE}" height="{rows * TILE_SIZE}"/>',
        "</tileset>",
    ]
    tsx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  tsx: {tsx_path.name}  ({cols}×{rows} = {tilecount} tiles)")


def _write_tmx(
    output_path: Path,
    width: int,
    height: int,
    tilesets: list[dict],
    layers: list[tuple[str, list[list[int]]]],
) -> None:
    """Write a .tmx file referencing external .tsx tilesets."""
    lines: list[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<map version="1.10" tiledversion="1.11.2" orientation="orthogonal"'
        f' renderorder="right-down" width="{width}" height="{height}"'
        f' tilewidth="{TILE_SIZE}" tileheight="{TILE_SIZE}"'
        f' infinite="0" nextlayerid="{len(layers) + 1}" nextobjectid="1">'
    )

    for ts in tilesets:
        lines.append(
            f' <tileset firstgid="{ts["firstgid"]}" source="{ts["source"]}"/>'
        )

    for layer_id, (name, grid) in enumerate(layers, start=1):
        lines.append(
            f' <layer id="{layer_id}" name="{name}"'
            f' width="{width}" height="{height}">'
        )
        encoded = _encode_layer(grid)
        lines.append('  <data encoding="base64" compression="zlib">')
        lines.append(f"   {encoded}")
        lines.append("  </data>")
        lines.append(" </layer>")

    lines.append("</map>")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _relpath(from_dir: Path, to_file: Path) -> str:
    """Relative path string from from_dir to to_file (forward slashes)."""
    try:
        return str(to_file.relative_to(from_dir)).replace("\\", "/")
    except ValueError:
        return os.path.relpath(to_file, from_dir).replace("\\", "/")


# ---------------------------------------------------------------------------
# Built-in palettes
# ---------------------------------------------------------------------------
# Tile IDs from ROOM_GRAMMAR_16x16.md (same grid coords for 48×48 sheets).
# Format: TileRef("sheet", col, row)  where ID = CCRRR → col=CC, row=RR

PALETTE_HOME_WOOD = RoomPalette(
    # Floor — FLO0131 plain, FLO0130 top-shadow, FLO0031/0030 left-edge variants
    floor               = TileRef("floors",  1, 31),   # FLO0131
    floor_shadow        = TileRef("floors",  1, 30),   # FLO0130 — below back wall
    floor_l_edge        = TileRef("floors",  0, 31),   # FLO0031 — beside left 3D wall
    floor_l_edge_shadow = TileRef("floors",  0, 30),   # FLO0030 — corner (both shadows)
    # Back wall strip
    wall_top   = TileRef("walls",    1,  4),            # WAL0104
    wall_low   = TileRef("walls",    1,  5),            # WAL0105
    # 3D back-wall corners
    corner_tl  = [TileRef("3d_walls", 10, 0), TileRef("3d_walls", 10, 1)],  # 3D_1000, 3D_1001
    corner_tr  = [TileRef("3d_walls", 13, 0), TileRef("3d_walls", 12, 1)],  # 3D_1300, 3D_1201
    # 3D side straights
    side_l     = TileRef("3d_walls", 10, 2),            # 3D_1002
    side_r     = TileRef("3d_walls", 13, 2),            # 3D_1302
    # Front wall
    front_wall_l_corner = TileRef("3d_walls", 10, 5),  # 3D_1005
    front_wall_r_corner = TileRef("3d_walls", 13, 5),  # 3D_1305
    front_wall_fill     = TileRef("3d_walls", 12, 5),  # 3D_1205
    # Doorway cut-through
    doorway_l      = TileRef("3d_walls",  9, 4),        # 3D_0904
    doorway_r      = TileRef("3d_walls", 14, 4),        # 3D_1404
    doorway_l_base = TileRef("3d_walls",  9, 5),        # 3D_0905
    doorway_r_base = TileRef("3d_walls", 14, 5),        # 3D_1405
)

PALETTE_MUSEUM_GRAY = RoomPalette(
    # Gray tile floor
    floor               = TileRef("floors",  9, 37),    # FLO0937 — plain fill
    floor_shadow        = TileRef("floors",  9, 36),    # FLO0936 — below back wall
    floor_l_edge        = TileRef("floors", 12, 35),    # FLO1235 — beside left 3D wall
    floor_l_edge_shadow = TileRef("floors", 12, 34),    # FLO1234 — corner (both shadows)
    # Same 3D wall structure
    wall_top   = TileRef("walls",    1,  4),
    wall_low   = TileRef("walls",    1,  5),
    corner_tl  = [TileRef("3d_walls", 10, 0), TileRef("3d_walls", 10, 1)],
    corner_tr  = [TileRef("3d_walls", 13, 0), TileRef("3d_walls", 12, 1)],
    side_l     = TileRef("3d_walls", 10, 2),
    side_r     = TileRef("3d_walls", 13, 2),
    front_wall_l_corner = TileRef("3d_walls", 10, 5),
    front_wall_r_corner = TileRef("3d_walls", 13, 5),
    front_wall_fill     = TileRef("3d_walls", 12, 5),
    doorway_l      = TileRef("3d_walls",  9, 4),
    doorway_r      = TileRef("3d_walls", 14, 4),
    doorway_l_base = TileRef("3d_walls",  9, 5),
    doorway_r_base = TileRef("3d_walls", 14, 5),
)
