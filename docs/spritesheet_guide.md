# Spritesheet Animation Guide

## Character Pack

**Source:** `assets/packs/moderninteriors-win/2_Characters/Character_Generator/`

**Premade characters (48x48):**
`0_Premade_Characters/48x48/Premade_Character_48x48_01.png` through `_20.png`

Each sheet is **2688×1968px = 56 columns × 41 rows** at 48×48px per tile.

## Row Layout

| Row (0-indexed) | Animation | Directions | Frames per direction |
|-----------------|-----------|------------|----------------------|
| 0 | Default pose (static) | E-N-W-S | 1 |
| 1 | Idle animation | E-N-W-S | 6 |
| 2 | Walk | E-N-W-S | 6 |
| 3 | Sleep (head only) | — | 6 |
| 4 | **Sit A** — legs visible (bench, bleachers) | E-W only | 6 |
| 5 | **Sit B** — legs hidden (at desk) | E-W only | 6 |
| 6 | Phone idle | S only | 12 |
| 7 | Book reading | S only | 12 |
| 8 | Pushing cart | E-N-W-S | 6 (+ cart sprites at end of row) |
| 9 | Picking something up | E-N-W-S | 12 |
| 10 | Giving a gift | E-N-W-S | 10 |
| 11 | Lifting | E-N-W-S | 14 |
| 12 | Throwing | E-N-W-S | 14 |
| 13 | Hitting | E-N-W-S | 6 |
| 14 | Punching | E-N-W-S | 6 |
| 15 | Stabbing (knife) | E-N-W-S | 6 (+ knife sprites at end of row) |
| 16 | Grab gun | E-N-W-S | 4 |
| 17 | Gun idle | E-N-W-S | 6 |
| 18 | Shoot gun | E-N-W-S | 3 |
| 19 | Hurt (flashing red/white outline) | E-N-W-S | 3 |

## Direction Order

For animations with E-N-W-S directions, frames are laid out left-to-right:
`[East frames] [North frames] [West frames] [South frames]`

## Notes for Sit Points

- **Sit A** (row 4): Use for open seating — benches, bleachers, cafeteria chairs
- **Sit B** (row 5): Use for desk seating — legs hidden under furniture
- Both sit animations are **East and West facing only**
- Sit points with `facing=north` or `facing=south` should fall back to East or West

## Loading Example

```python
CHAR_BASE = "assets/packs/moderninteriors-win/2_Characters/Character_Generator/0_Premade_Characters/48x48"
sheet = arcade.load_spritesheet(f"{CHAR_BASE}/Premade_Character_48x48_01.png")

TILE_W, TILE_H = 48, 48
SHEET_COLS = 56

def get_row_frames(sheet, row, start_col, num_frames):
    return [
        sheet.get_texture(arcade.LBWH((start_col + i) * TILE_W, row * TILE_H, TILE_W, TILE_H))
        for i in range(num_frames)
    ]

# Walk animation (row 2): E=cols 0-5, N=6-11, W=12-17, S=18-23
walk_east  = get_row_frames(sheet, row=2, start_col=0,  num_frames=6)
walk_north = get_row_frames(sheet, row=2, start_col=6,  num_frames=6)
walk_west  = get_row_frames(sheet, row=2, start_col=12, num_frames=6)
walk_south = get_row_frames(sheet, row=2, start_col=18, num_frames=6)

# Sit B (row 5, at desk): E=cols 0-5, W=cols 6-11
sit_east = get_row_frames(sheet, row=5, start_col=0, num_frames=6)
sit_west = get_row_frames(sheet, row=5, start_col=6, num_frames=6)
```
