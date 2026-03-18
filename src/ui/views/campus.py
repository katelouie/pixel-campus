"""Campus view -- the main gameplay screen.

Renders the high_school TMX map, student sprites, and handles interaction.
The sim GameState lives on the Window; this View reads and drives it.
"""

import heapq
import math
import random
from collections import defaultdict
from pathlib import Path

import arcade
from PIL import Image as _PILImage

from src.sim.engine import GameState
from src.sim.models import StudentState
from src.ui.hud import HUD
from src.ui.sprites import SIT_TYPE_BY_PREFIX, StudentSprite

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TMX_PATH = str(_PROJECT_ROOT / "rooms" / "high_school_v0.tmx")

_EMOTES_PATH = (
    _PROJECT_ROOT
    / "assets/packs/moderninteriors-win/4_user_interface_elements"
    / "UI_thinking_emotes_animation_48x48.png"
)
_EMOTE_TILE = 48
_BUBBLE_SCALE = 0.6   # renders at ~29px — comfortable above name label

# Timing constants for bubble animation phases
_DOTS_FRAME_DUR = 0.07   # seconds per dots frame (~14fps)
_GROW_FRAME_DUR = 0.10   # seconds per grow frame (~10fps)
_PULSE_DUR      = 0.6    # seconds per pulse frame (slow relaxed swap)

# activity → (even_col, row); odd_col = even_col + 1 is the alternate pulse frame
_ACTIVITY_ICON: dict[str, tuple[int, int]] = {
    "classwork": (2, 6),  # yellow ? — thinking/learning
    "basketball": (0, 4), # yellow !
    "music":      (6, 6), # musical note
}


class _BubbleAnim:
    """Per-student bubble animation state machine."""
    __slots__ = ("phase", "frame_idx", "timer", "activity", "pulse_phase")

    def __init__(self) -> None:
        self.phase: str = "hidden"  # "hidden" | "dots" | "grow" | "pulse"
        self.frame_idx: int = 0
        self.timer: float = 0.0
        self.activity: str = ""
        self.pulse_phase: bool = False

    def start(self, activity: str) -> None:
        self.phase = "dots"
        self.frame_idx = 0
        self.timer = 0.0
        self.activity = activity
        self.pulse_phase = False

    def stop(self) -> None:
        self.phase = "hidden"


def _load_bubble_textures() -> dict:
    """Load dots/grow animation frames and per-activity icon pairs from the emotes sheet."""
    src = _PILImage.open(_EMOTES_PATH)
    ts = _EMOTE_TILE

    def crop(col: int, row: int) -> arcade.Texture:
        return arcade.Texture(src.crop((col * ts, row * ts, col * ts + ts, row * ts + ts)))

    return {
        "dots": [crop(col, 1) for col in range(6)],       # row 1, cols 0-5
        "grow": [crop(col, 2) for col in range(4)],       # row 2, cols 0-3
        "icons": {
            activity: [crop(col, row), crop(col + 1, row)]
            for activity, (col, row) in _ACTIVITY_ICON.items()
        },
    }
MAP_SCALE = 1.0
CAMERA_SPEED = 10.0
ZOOM_STEP = 0.1
ZOOM_MIN = 0.3
ZOOM_MAX = 3.0
AUTO_RUN_INTERVAL = 12.0  # seconds between auto ticks

# Premade character sheet numbers to use (1-20 available)
CHARACTER_SHEET_NUMS: list[int] = list(range(1, 21))

# _SIT_PREFIX_TO_ROOM is built dynamically from state.rooms in CampusView.__init__
# (each Room has a sit_prefixes list loaded from rooms.json)


class CampusView(arcade.View):
    """Main gameplay view showing the campus map with students."""

    def __init__(self, state: GameState, char_textures: dict[str, dict]) -> None:
        super().__init__()
        self._state = state

        # --- Load tilemap ---
        # Arcade 3: TiledObject is a named tuple with (shape, properties, name, type).
        # Rectangles have shape = [(x,y), (x,y), (x,y), (x,y)] (4 corners, already
        # in Arcade coords — Y-flip applied by the loader).
        # Points have shape = (x, y).
        self._tile_map = arcade.load_tilemap(TMX_PATH, scaling=MAP_SCALE)
        self._scene = arcade.Scene.from_tilemap(self._tile_map)

        # --- Collision walls (stored for future A* pathfinding grid) ---
        self._walls = arcade.SpriteList(use_spatial_hash=True)
        for obj in self._tile_map.object_lists.get("Collision", []):
            xs = [p[0] for p in obj.shape]
            ys = [p[1] for p in obj.shape]
            w = max(1, int(max(xs) - min(xs)))
            h = max(1, int(max(ys) - min(ys)))
            wall = arcade.SpriteSolidColor(w, h, color=(255, 0, 0, 80))
            wall.center_x = (min(xs) + max(xs)) / 2
            wall.center_y = (min(ys) + max(ys)) / 2
            self._walls.append(wall)

        # --- Spawn points (shape is a single (x, y) tuple for point objects) ---
        self._spawn_points: list[tuple[float, float]] = []
        for obj in self._tile_map.object_lists.get("Spawn", []):
            self._spawn_points.append((float(obj.shape[0]), float(obj.shape[1])))
        if not self._spawn_points:
            self._spawn_points = [(400.0, 400.0)]

        # --- Sit points: name → (x, y, facing) ---
        # Stand points share the same layer but use idle animation instead of sitting.
        # Detected by "stand" in the object name or class/type field.
        self._sit_points: dict[str, tuple[float, float, str]] = {}
        self._stand_point_names: set[str] = set()
        for obj in self._tile_map.object_lists.get("Sit", []):
            facing = obj.properties.get("facing", "south") if obj.properties else "south"
            self._sit_points[obj.name] = (
                float(obj.shape[0]),
                float(obj.shape[1]),
                facing,
            )
            obj_class = (obj.type or "") if hasattr(obj, "type") else ""
            if "stand_" in obj.name.lower() or "stand_" in obj_class.lower():
                self._stand_point_names.add(obj.name)

        # --- Explicit room centers from a "RoomCenters" object layer ---
        self._explicit_room_centers: dict[str, tuple[float, float]] = {}
        for obj in self._tile_map.object_lists.get("RoomCenters", []):
            if obj.name:
                self._explicit_room_centers[obj.name] = (
                    float(obj.shape[0]),
                    float(obj.shape[1]),
                )

        # --- Room boundary rectangles (from "Rooms" object layer) ---
        # Used for spatial containment: derive room name from object position.
        self._room_bounds: dict[str, tuple[float, float, float, float]] = {}
        for obj in self._tile_map.object_lists.get("Rooms", []):
            if obj.name and isinstance(obj.shape, list) and len(obj.shape) >= 3:
                xs = [p[0] for p in obj.shape]
                ys = [p[1] for p in obj.shape]
                self._room_bounds[obj.name] = (min(xs), max(xs), min(ys), max(ys))

        # Fast name → Room lookup for click-to-send
        self._room_by_name: dict[str, object] = {r.name: r for r in self._state.rooms}

        # Build sit prefix → room name map from the sim's loaded room data
        self._sit_prefix_to_room: dict[str, str] = {
            prefix: room.name
            for room in self._state.rooms
            for prefix in room.sit_prefixes
        }

        # Room centers: explicit points win; fall back to sit point centroids
        self._room_centers: dict[str, tuple[float, float]] = (
            self._compute_room_centers()
        )

        # Sit point management: room → sit point names, and per-student assignments
        self._room_sit_points: dict[str, list[str]] = self._build_room_sit_points()

        # --- Interactables layer: tile objects with class=action_spot ---
        # Stores explicit pose/facing/activity props for new-style tile objects.
        self._action_spot_props: dict[str, dict] = {}
        _counter: dict[str, int] = {}
        def _register_action_spot(name_hint: str, ox: float, oy: float, props: dict) -> None:
            pose     = props.get("pose", "sit")
            facing   = props.get("facing", "south")
            activity = props.get("activity", "")
            room_name = self._room_containing(ox, oy)
            if room_name is None:
                return
            sp_name = props.get("name") or name_hint or f"iact_{int(ox)}_{int(oy)}"
            if sp_name in self._sit_points:
                _counter[sp_name] = _counter.get(sp_name, 0) + 1
                sp_name = f"{sp_name}_{_counter[sp_name]}"
            # Sit-pose tile objects: nudge the navigation target so the student
            # lands on the seat rather than at the tile center.
            # Y: chair seats sit above the tile center; offset up slightly.
            # X: avoid chair backs — west-facing sits nudge left, east-facing nudge right.
            SIT_Y_OFFSET = 16   # pixels up; tune if student looks too high/low
            SIT_X_OFFSET = 10   # pixels; tune if student clips chair back
            if pose == "sit":
                adjusted_y = oy + SIT_Y_OFFSET
                if facing == "west":
                    adjusted_x = ox - SIT_X_OFFSET
                elif facing == "east":
                    adjusted_x = ox + SIT_X_OFFSET
                else:
                    adjusted_x = ox
            else:
                adjusted_x, adjusted_y = ox, oy
            self._sit_points[sp_name] = (adjusted_x, adjusted_y, facing)
            self._action_spot_props[sp_name] = {"pose": pose, "facing": facing, "activity": activity}
            if pose == "stand":
                self._stand_point_names.add(sp_name)
            if room_name not in self._room_sit_points:
                self._room_sit_points[room_name] = []
            self._room_sit_points[room_name].append(sp_name)

        # Tile objects → sprite_lists (Arcade splits these from shape objects)
        for _sp in self._tile_map.sprite_lists.get("Interactables", arcade.SpriteList()):
            _props = getattr(_sp, "properties", None) or {}
            if _props.get("class") == "action_spot":
                _register_action_spot(_props.get("name", ""), _sp.center_x, _sp.center_y, _props)

        # Point/shape objects → object_lists
        for obj in self._tile_map.object_lists.get("Interactables", []):
            obj_type = (obj.type or "") if hasattr(obj, "type") else ""
            if obj_type != "action_spot":
                continue
            if not isinstance(obj.shape, (tuple, list)) or len(obj.shape) < 2:
                continue
            if isinstance(obj.shape[0], (int, float)):
                ox, oy = float(obj.shape[0]), float(obj.shape[1])
            elif hasattr(obj.shape[0], "__len__"):
                xs = [p[0] for p in obj.shape]; ys = [p[1] for p in obj.shape]
                ox, oy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            else:
                continue
            _register_action_spot(obj.name or "", ox, oy, obj.properties or {})

        self._claimed_sit_points: dict[str, int | None] = {
            name: None for name in self._sit_points
        }
        self._student_sit_point: dict[int, str | None] = {}

        # --- Students ---
        self._student_sprites: dict[int, StudentSprite] = {}
        self._sprite_list = arcade.SpriteList()
        self._name_labels: dict[int, arcade.Text] = {}
        self._mood_labels: dict[int, arcade.Text] = {}
        self._build_student_sprites(char_textures)

        # --- Activity bubbles ---
        self._bubble_textures = _load_bubble_textures()
        self._bubble_sprites: dict[int, arcade.Sprite] = {}
        self._bubble_anims: dict[int, _BubbleAnim] = {}
        self._bubble_sprite_list = arcade.SpriteList()
        _empty_bubble = arcade.Texture(_PILImage.new("RGBA", (1, 1), (0, 0, 0, 0)))
        for student in self._state.students:
            bubble = arcade.Sprite(_empty_bubble, scale=_BUBBLE_SCALE)
            bubble.visible = False
            self._bubble_sprites[student.student_id] = bubble
            self._bubble_anims[student.student_id] = _BubbleAnim()
            self._bubble_sprite_list.append(bubble)

        # One physics engine per student so each gets wall collision
        self._physics_engines: dict[int, arcade.PhysicsEngineSimple] = {
            sid: arcade.PhysicsEngineSimple(sprite, walls=self._walls)
            for sid, sprite in self._student_sprites.items()
        }

        # Shared A* barrier list — built once from wall sprites.
        # Use a 1×1 dummy sprite so walls aren't inflated by the student's size,
        # which would seal off corridors at 48px grid resolution.
        map_w_px = int(self._tile_map.width * self._tile_map.tile_width * MAP_SCALE)
        map_h_px = int(self._tile_map.height * self._tile_map.tile_height * MAP_SCALE)
        _pathfind_dummy = arcade.SpriteSolidColor(1, 1, color=(0, 0, 0, 0))
        self._barrier_list = arcade.AStarBarrierList(
            moving_sprite=_pathfind_dummy,
            blocking_sprites=self._walls,
            grid_size=int(48 * MAP_SCALE),
            left=0,
            right=map_w_px,
            bottom=0,
            top=map_h_px,
        )

        # --- Camera ---
        self._camera = arcade.Camera2D()
        # Start camera looking at the first spawn point
        if self._spawn_points:
            sx, sy = self._spawn_points[0]
            self._camera.position = arcade.Vec2(sx, sy)
        self._camera_keys: set[int] = set()

        # --- Morning dispatch: send every student somewhere at startup ---
        self._dispatch_morning()

        # --- HUD ---
        self._hud = HUD(self.window.width, self.window.height)
        self._hud.set_student_names({s.name for s in self._state.students})
        self._hud.push_messages(
            ["Welcome to Pixel Campus! SPACE: tick | P: auto-run | +/-: zoom | arrows: pan"]
        )

        self._selected_sprite: StudentSprite | None = None
        self._context_menu: dict | None = None  # {x, y, target, items}
        # Initialise to None so first sync fires for all students
        self._prev_destinations: dict[int, str | None] = {
            s.student_id: None for s in self._state.students
        }

        # Auto-run
        self._auto_run: bool = False
        self._auto_run_timer: float = 0.0

        # --- Selection mini-card (bottom-right, screen-space) ---
        from src.ui.hud import _make_nine_slice_texture, _make_banner_texture
        _CARD_W, _CARD_H = 192, 284
        _CARD_MARGIN = 8
        _card_left   = self.window.width  - _CARD_W - _CARD_MARGIN
        _card_bottom = _CARD_MARGIN

        self._card_screen_cam = arcade.Camera2D()
        self._card_screen_cam.position = arcade.Vec2(
            self.window.width / 2, self.window.height / 2
        )
        card_panel_tex = _make_nine_slice_texture(_CARD_W, _CARD_H)
        self._card_panel_sprite = arcade.Sprite(card_panel_tex)
        self._card_panel_sprite.center_x = _card_left + _CARD_W // 2
        self._card_panel_sprite.center_y = _card_bottom + _CARD_H // 2

        # Portrait sprite — texture swapped on selection change
        _empty_portrait = arcade.Texture(_PILImage.new("RGBA", (48, 96), (0, 0, 0, 0)))
        self._card_portrait_sprite = arcade.Sprite(_empty_portrait, scale=1.5)
        self._card_portrait_sprite.center_x = _card_left + _CARD_W // 2
        # Portrait center: just inside top border, 72px from top inner edge (144/2)
        self._card_portrait_sprite.center_y = _card_bottom + _CARD_H - 32 - 72

        # "View Profile" button banner
        _BTN_W = 128
        _btn_left   = _card_left + (_CARD_W - _BTN_W) // 2
        _btn_bottom = _card_bottom + 32       # sits just inside bottom border
        _btn_top    = _btn_bottom + 32
        btn_tex = _make_banner_texture(_BTN_W)
        self._card_btn_sprite = arcade.Sprite(btn_tex)
        self._card_btn_sprite.center_x = _btn_left + _BTN_W // 2
        self._card_btn_sprite.center_y = (_btn_bottom + _btn_top) // 2
        # Stored for click-hit testing (screen coords)
        self._card_btn_bounds = (_btn_left, _btn_left + _BTN_W, _btn_bottom, _btn_top)

        # Pre-built Text objects for the mini-card (text updated on selection change)
        _portrait_bottom = self._card_portrait_sprite.center_y - 72  # 96*1.5/2
        _cx = _card_left + _CARD_W // 2
        self._card_name_text = arcade.Text(
            "", _cx, _portrait_bottom - 16,
            color=(40, 30, 20, 255), font_size=10, bold=True,
            anchor_x="center", anchor_y="center",
        )
        self._card_mood_text = arcade.Text(
            "", _cx, _portrait_bottom - 32,
            color=(60, 50, 40, 255), font_size=9,
            anchor_x="center", anchor_y="center",
        )
        self._card_state_text = arcade.Text(
            "", _cx, _portrait_bottom - 48,
            color=(80, 70, 55, 200), font_size=8,
            anchor_x="center", anchor_y="center",
        )
        self._card_btn_text = arcade.Text(
            "View Profile",
            self._card_btn_sprite.center_x, self._card_btn_sprite.center_y,
            color=(40, 30, 20, 255), font_size=8,
            anchor_x="center", anchor_y="center",
        )

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _build_room_sit_points(self) -> dict[str, list[str]]:
        """Group sit point names by room, using the same prefix mapping as _SIT_PREFIX_TO_ROOM."""
        by_room: dict[str, list[str]] = defaultdict(list)
        for name in self._sit_points:
            for prefix, room_name in self._sit_prefix_to_room.items():
                if name.startswith(prefix):
                    by_room[room_name].append(name)
                    break
        return dict(by_room)

    def _pick_sit_point(self, room_name: str, student_id: int) -> str | None:
        """Claim and return a random available sit point in the given room, or None if full."""
        available = [
            sp for sp in self._room_sit_points.get(room_name, [])
            if self._claimed_sit_points.get(sp) is None
        ]
        if not available:
            return None
        sp_name = random.choice(available)
        self._claimed_sit_points[sp_name] = student_id
        return sp_name

    def _release_sit_point(self, student_id: int) -> None:
        """Release whatever sit point this student currently holds."""
        sp = self._student_sit_point.pop(student_id, None)
        if sp and self._claimed_sit_points.get(sp) == student_id:
            self._claimed_sit_points[sp] = None

    def _room_containing(self, x: float, y: float) -> str | None:
        """Return the name of the room whose bounding rect contains (x, y), or None."""
        for name, (left, right, bottom, top) in self._room_bounds.items():
            if left <= x <= right and bottom <= y <= top:
                return name
        return None

    def _compute_room_centers(self) -> dict[str, tuple[float, float]]:
        """Compute room centers: explicit RoomCenters points win, fall back to sit centroids."""
        by_room: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for name, (x, y, _) in self._sit_points.items():
            for prefix, room_name in self._sit_prefix_to_room.items():
                if name.startswith(prefix):
                    by_room[room_name].append((x, y))
                    break
        centers = {
            room: (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )
            for room, pts in by_room.items()
        }
        # Explicit points override centroids, and fill in rooms with no sit points
        centers.update(self._explicit_room_centers)
        return centers

    def _dispatch_morning(self) -> None:
        """Send every idle student to a random room that boosts their favourite skill."""
        from src.sim.models import Skill

        for student in self._state.students:
            skill = student.favorite_skill
            # Flirt students prefer social rooms (Quad, Cafeteria)
            if skill == Skill.FLIRT:
                skill = Skill.SOCIAL

            candidates = [r for r in self._state.rooms if r.skill_boost == skill]
            if not candidates:
                candidates = self._state.rooms  # last resort: any room
            room = random.choice(candidates)
            self._state.assign_student(student, room)

    def _build_student_sprites(self, char_textures: dict[int, dict]) -> None:
        for i, student in enumerate(self._state.students):
            sheet_num = CHARACTER_SHEET_NUMS[i % len(CHARACTER_SHEET_NUMS)]
            sprite = StudentSprite(student, char_textures[sheet_num])

            sx, sy = self._spawn_points[i % len(self._spawn_points)]
            sprite.center_x = sx + random.uniform(-12, 12)
            sprite.center_y = sy + random.uniform(-8, 8)

            self._student_sprites[student.student_id] = sprite
            self._sprite_list.append(sprite)

            self._name_labels[student.student_id] = arcade.Text(
                student.name,
                x=sprite.center_x,
                y=sprite.top + 12,
                color=arcade.color.BLACK,
                font_size=9,
                font_name="Monaco",
                anchor_x="center",
            )
            self._mood_labels[student.student_id] = arcade.Text(
                student.mood.icon,
                x=sprite.center_x,
                y=sprite.top + 2,
                color=arcade.color.WHITE,
                font_size=10,
                anchor_x="center",
            )

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------

    def on_update(self, delta_time: float) -> None:
        self._scene.update_animation(delta_time)

        for sid, sprite in self._student_sprites.items():
            sprite.update_movement()
            self._physics_engines[sid].update()
            self._name_labels[sid].x = sprite.center_x
            self._name_labels[sid].y = sprite.top + 12
            self._mood_labels[sid].x = sprite.center_x
            self._mood_labels[sid].y = sprite.top + 2
            new_icon = sprite.student.mood.icon
            if self._mood_labels[sid].text != new_icon:
                self._mood_labels[sid].text = new_icon

            # Trigger sit/stand animation when student arrives at their assigned point
            if not sprite.is_walking and not sprite.is_stationed:
                sp_name = self._student_sit_point.get(sid)
                if sp_name:
                    _, _, facing = self._sit_points[sp_name]
                    ap = self._action_spot_props.get(sp_name, {})
                    pose     = ap.get("pose", "stand" if sp_name in self._stand_point_names else "sit")
                    activity = ap.get("activity", "")
                    if pose == "stand" and activity in ("throw", "basketball"):
                        sprite.set_throwing(facing)
                    elif pose == "stand" or sp_name in self._stand_point_names:
                        sprite.set_standing_at(facing)
                    else:
                        sit_type = ap.get("sit_type") or next(
                            (t for prefix, t in SIT_TYPE_BY_PREFIX.items() if sp_name.startswith(prefix)),
                            "b",
                        )
                        sprite.set_sitting(facing, sit_type)

            # Activity bubble: pop-in animation then pulsing icon when stationed
            bubble = self._bubble_sprites[sid]
            anim = self._bubble_anims[sid]
            if sprite.is_stationed:
                sp_name = self._student_sit_point.get(sid)
                ap = self._action_spot_props.get(sp_name, {}) if sp_name else {}
                activity = ap.get("activity", "")
                # Only show bubble for spots with a known activity icon
                if activity in self._bubble_textures["icons"]:
                    if anim.phase == "hidden":
                        anim.start(activity)
                        bubble.visible = True
                    # Advance animation
                    anim.timer += delta_time
                    if anim.phase == "dots":
                        if anim.timer >= _DOTS_FRAME_DUR:
                            anim.timer -= _DOTS_FRAME_DUR
                            anim.frame_idx += 1
                            if anim.frame_idx >= len(self._bubble_textures["dots"]):
                                anim.phase = "grow"
                                anim.frame_idx = 0
                        bubble.texture = self._bubble_textures["dots"][min(anim.frame_idx, len(self._bubble_textures["dots"]) - 1)]
                    elif anim.phase == "grow":
                        if anim.timer >= _GROW_FRAME_DUR:
                            anim.timer -= _GROW_FRAME_DUR
                            anim.frame_idx += 1
                            if anim.frame_idx >= len(self._bubble_textures["grow"]):
                                anim.phase = "pulse"
                                anim.frame_idx = 0
                                anim.timer = 0.0
                        bubble.texture = self._bubble_textures["grow"][min(anim.frame_idx, len(self._bubble_textures["grow"]) - 1)]
                    elif anim.phase == "pulse":
                        if anim.timer >= _PULSE_DUR:
                            anim.timer -= _PULSE_DUR
                            anim.pulse_phase = not anim.pulse_phase
                        icon_frames = self._bubble_textures["icons"][anim.activity]
                        bubble.texture = icon_frames[1 if anim.pulse_phase else 0]
                    bubble.scale = _BUBBLE_SCALE
                    bubble.center_x = sprite.center_x
                    bubble.center_y = sprite.top + bubble.height // 2 + 18
                else:
                    bubble.visible = False
            else:
                if anim.phase != "hidden":
                    anim.stop()
                    bubble.visible = False

        # Camera panning with arrow keys
        pan = CAMERA_SPEED / self._camera.zoom  # pan speed adjusts with zoom
        cx, cy = self._camera.position
        if arcade.key.LEFT in self._camera_keys:
            cx -= pan
        if arcade.key.RIGHT in self._camera_keys:
            cx += pan
        if arcade.key.UP in self._camera_keys:
            cy += pan
        if arcade.key.DOWN in self._camera_keys:
            cy -= pan
        self._camera.position = arcade.Vec2(cx, cy)

        # Auto-run: advance sim on a timer
        if self._auto_run:
            self._auto_run_timer += delta_time
            if self._auto_run_timer >= AUTO_RUN_INTERVAL:
                self._auto_run_timer = 0.0
                logs = self._state.tick()
                self._hud.push_messages(logs)
                self._sync_sprites_to_sim()

    def on_draw(self) -> None:
        self.clear()
        with self._camera.activate():
            self._scene.draw()
            self._sprite_list.draw()
            self._bubble_sprite_list.draw()
            self._draw_student_labels()
            if self._selected_sprite:
                arcade.draw_circle_outline(
                    self._selected_sprite.center_x,
                    self._selected_sprite.center_y,
                    30,
                    arcade.color.YELLOW,
                    border_width=2,
                )
        self._hud.draw(self._state)
        if self._selected_sprite:
            self._draw_selection_card()
        if self._context_menu:
            self._draw_context_menu()

    def _draw_selection_card(self) -> None:
        """Draw the bottom-right mini info card for the selected student."""
        sprite  = self._selected_sprite
        student = sprite.student

        self._card_portrait_sprite.texture = sprite.idle_textures["down"]

        self._card_name_text.text  = student.name
        self._card_mood_text.text  = f"{student.mood.icon} {student.mood.name.capitalize()}"
        self._card_state_text.text = student.state.value.capitalize()

        with self._card_screen_cam.activate():
            arcade.draw_sprite(self._card_panel_sprite)
            arcade.draw_sprite(self._card_portrait_sprite)
            arcade.draw_sprite(self._card_btn_sprite)
            self._card_name_text.draw()
            self._card_mood_text.draw()
            self._card_state_text.draw()
            self._card_btn_text.draw()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    _MENU_W    = 188
    _ITEM_H    = 26
    _MENU_PAD  = 6

    # Maps room skill_boost → activity verb for context menu labels
    _ACTIVITY_VERB: dict = {}  # populated lazily below

    def _build_context_menu(
        self, sx: int, sy: int, target: "Student", room: "Room | None" = None
    ) -> dict:
        """Build a context menu for acting on `target` relative to the selected student.

        If `room` is provided (cursor was inside a room's Tiled bounds), a
        room-specific activity option is appended to the menu.
        """
        from src.sim.thoughts import add_thought, thought_encouraged
        a = self._selected_sprite.student
        b = target

        def _introduce():
            dest = a.location or self._room_by_name.get("Cafeteria")
            if dest is None:
                dest = next(iter(self._room_by_name.values()))
            self._hud.push_messages([
                f"Introducing {a.name} and {b.name}...",
                self._state.assign_student(a, dest),
                self._state.assign_student(b, dest),
            ])
            self._sync_sprites_to_sim()

        def _separate():
            others = [r for r in self._room_by_name.values() if r != a.location]
            if others:
                dest = random.choice(others)
                self._hud.push_messages([
                    f"Separating {b.name} from {a.name}.",
                    self._state.assign_student(b, dest),
                ])
                self._sync_sprites_to_sim()

        def _encourage():
            add_thought(b.thoughts, thought_encouraged(), bus=self._state.bus)
            self._hud.push_messages([f"{a.name} encourages {b.name}."])

        items = [
            (f"Introduce {a.name} & {b.name}", _introduce),
            (f"Separate {b.name}",              _separate),
            (f"Encourage {b.name}",             _encourage),
        ]

        # Room-specific activity option when cursor is inside a room
        if room is not None:
            from src.sim.models import SKILL_TO_ACTIVITY, StudentState
            _verbs = {
                StudentState.STUDYING:    "Study",
                StudentState.EXERCISING:  "Train",
                StudentState.CREATING:    "Create",
                StudentState.SOCIALIZING: "Hang out",
            }
            activity_state = SKILL_TO_ACTIVITY.get(room.skill_boost)
            verb = _verbs.get(activity_state, "Go") if activity_state else "Go"

            def _send_to_room(r=room):
                self._hud.push_messages([self._state.assign_student(b, r)])
                self._sync_sprites_to_sim()

            items.append((f"{verb} in {room.name}", _send_to_room))

        # Nudge menu left/up if it would go off-screen
        mx = min(sx, self.window.width  - self._MENU_W - 4)
        my = min(sy, self.window.height - len(items) * self._ITEM_H - self._MENU_PAD * 2 - 4)
        return {"x": mx, "y": my, "target": b, "items": items}

    def _context_menu_item_at(self, sx: int, sy: int) -> int | None:
        """Return the index of the menu item under (sx, sy), or None."""
        if not self._context_menu:
            return None
        mx, my = self._context_menu["x"], self._context_menu["y"]
        items  = self._context_menu["items"]
        for i in range(len(items)):
            ib = my + self._MENU_PAD + i * self._ITEM_H
            it = ib + self._ITEM_H
            if mx <= sx <= mx + self._MENU_W and ib <= sy <= it:
                return i
        return None

    def _draw_context_menu(self) -> None:
        """Draw the right-click context menu in screen space."""
        if not self._context_menu:
            return
        mx, my   = self._context_menu["x"], self._context_menu["y"]
        items    = self._context_menu["items"]
        total_h  = len(items) * self._ITEM_H + self._MENU_PAD * 2

        with self._card_screen_cam.activate():
            # Background panel
            arcade.draw_lrbt_rectangle_filled(
                mx, mx + self._MENU_W, my, my + total_h,
                (20, 20, 35, 220),
            )
            arcade.draw_lrbt_rectangle_outline(
                mx, mx + self._MENU_W, my, my + total_h,
                (100, 100, 140, 200), border_width=1,
            )
            # Items
            for i, (label, _) in enumerate(items):
                text_y = my + self._MENU_PAD + i * self._ITEM_H + 6
                arcade.draw_text(
                    label, mx + 10, text_y,
                    arcade.color.WHITE, font_size=11,
                )

    def _draw_student_labels(self) -> None:
        for sid in self._student_sprites:
            self._name_labels[sid].draw()
            self._mood_labels[sid].draw()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def on_show_view(self) -> None:
        """Clear held camera keys so nothing is stuck after returning from another view."""
        self._camera_keys.clear()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        self._camera_keys.add(symbol)
        if symbol == arcade.key.ESCAPE:
            self._selected_sprite = None
            return
        if symbol == arcade.key.SPACE:
            logs = self._state.tick()
            self._hud.push_messages(logs)
            self._sync_sprites_to_sim()
        elif symbol == arcade.key.H:
            all_logs: list[str] = []
            for _ in range(6):
                all_logs.extend(self._state.tick())
            self._hud.push_messages(all_logs)
            self._sync_sprites_to_sim()
        elif symbol == arcade.key.P:
            self._auto_run = not self._auto_run
            self._auto_run_timer = 0.0
            self._hud.push_messages(
                [f"Auto-run {'ON' if self._auto_run else 'OFF'} (P to toggle)"]
            )
        elif symbol in (arcade.key.EQUAL, arcade.key.NUM_ADD):
            self._camera.zoom = min(ZOOM_MAX, round(self._camera.zoom + ZOOM_STEP, 2))
        elif symbol in (arcade.key.MINUS, arcade.key.NUM_SUBTRACT):
            self._camera.zoom = max(ZOOM_MIN, round(self._camera.zoom - ZOOM_STEP, 2))

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        self._camera_keys.discard(symbol)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        from src.ui.hud import _PANEL_W, _PANEL_H
        if x <= _PANEL_W and y <= _PANEL_H:
            # Scroll wheel over log panel: scroll history (up = back in time)
            self._hud.scroll(-int(scroll_y))
        else:
            self._camera.zoom = max(
                ZOOM_MIN, min(ZOOM_MAX, round(self._camera.zoom + scroll_y * ZOOM_STEP, 2))
            )

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        # Context menu: any click dismisses it; left-click on an item executes it
        if self._context_menu:
            if button == arcade.MOUSE_BUTTON_LEFT:
                i = self._context_menu_item_at(x, y)
                if i is not None:
                    _, action = self._context_menu["items"][i]
                    action()
            self._context_menu = None
            return

        # Right-click on a student while another is selected → context menu
        if button == arcade.MOUSE_BUTTON_RIGHT:
            if self._selected_sprite is not None:
                zoom = self._camera.zoom
                wx = (x - self.window.width  / 2) / zoom + self._camera.position[0]
                wy = (y - self.window.height / 2) / zoom + self._camera.position[1]
                clicked = arcade.get_sprites_at_point((wx, wy), self._sprite_list)
                room_name = self._room_containing(wx, wy)
                room = self._room_by_name.get(room_name) if room_name else None
                if clicked and clicked[0] is not self._selected_sprite:
                    self._context_menu = self._build_context_menu(
                        x, y, clicked[0].student, room=room
                    )
            return

        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        # Check log panel for clickable student names
        from src.ui.hud import _PANEL_W, _PANEL_H
        if x <= _PANEL_W and y <= _PANEL_H:
            name = self._hud.check_name_click(x, y)
            if name:
                student = self._state.get_student_by_name(name)
                if student:
                    sprite = self._student_sprites.get(student.student_id)
                    if sprite:
                        self._camera.position = arcade.Vec2(sprite.center_x, sprite.center_y)
                        self._hud.push_messages([f"Camera → {name}"])
                return

        # Check mini-card "View Profile" button first (screen-space, no transform needed)
        if self._selected_sprite is not None:
            bl, br, bb, bt = self._card_btn_bounds
            if bl <= x <= br and bb <= y <= bt:
                from src.ui.views.profile import ProfileView
                self.window.show_view(ProfileView(
                    self._state,
                    self._selected_sprite.student,
                    self._selected_sprite.idle_textures["down"],
                    self,
                ))
                return
        # Convert screen → world coordinates (account for zoom)
        zoom = self._camera.zoom
        world_x = (x - self.window.width  / 2) / zoom + self._camera.position[0]
        world_y = (y - self.window.height / 2) / zoom + self._camera.position[1]
        clicked = arcade.get_sprites_at_point((world_x, world_y), self._sprite_list)
        if clicked:
            self._selected_sprite = clicked[0]
            self._hud.push_messages(
                [f"Selected {self._selected_sprite.student.name}."]
            )
        elif self._selected_sprite is not None:
            # Click on empty space while a student is selected → send to room if inside one
            room_name = self._room_containing(world_x, world_y)
            room = self._room_by_name.get(room_name) if room_name else None
            if room is not None:
                msg = self._state.assign_student(self._selected_sprite.student, room)
                self._hud.push_messages([msg])
                self._sync_sprites_to_sim()
        else:
            self._selected_sprite = None

    # ------------------------------------------------------------------
    # Sim ↔ sprite sync
    # ------------------------------------------------------------------

    def _astar(
        self, start_px: tuple[float, float], end_px: tuple[float, float]
    ) -> list[tuple[float, float]] | None:
        """A* on the barrier grid with no iteration limit (Arcade's built-in caps at 500).

        AStarBarrierList stores .left/.right/.bottom/.top in grid coordinates (not pixels),
        and .barrier_list as a list of grid-coord tuples.
        """
        gs = self._barrier_list.grid_size
        # Raw blocked: used to validate start/end (sprite is physically there — it's valid)
        raw_blocked: set = set(self._barrier_list.barrier_list)
        # Padded blocked: diagonal-only padding smooths corners without sealing corridors
        blocked: set = set(raw_blocked)
        for bx, by in raw_blocked:
            for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                blocked.add((bx + dx, by + dy))
        left = self._barrier_list.left
        right = self._barrier_list.right
        bottom = self._barrier_list.bottom
        top = self._barrier_list.top

        start = (int(start_px[0] // gs), int(start_px[1] // gs))
        end = (int(end_px[0] // gs), int(end_px[1] // gs))

        # Reject only if physically inside a wall — not just near one
        if start in raw_blocked or end in raw_blocked:
            return None
        # Unblock start/end in padded set so the search can begin and end there
        blocked.discard(start)
        blocked.discard(end)

        def h(a: tuple, b: tuple) -> float:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        g: dict[tuple, float] = {start: 0.0}
        came_from: dict[tuple, tuple] = {}
        heap: list = [(h(start, end), start)]

        while heap:
            _, cur = heapq.heappop(heap)
            if cur == end:
                path = []
                while cur in came_from:
                    cx, cy = cur
                    path.append((cx * gs + gs // 2, cy * gs + gs // 2))
                    cur = came_from[cur]
                path.reverse()
                path.append((end[0] * gs + gs // 2, end[1] * gs + gs // 2))
                return path
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (cur[0] + dx, cur[1] + dy)
                if nb[0] < left or nb[0] > right or nb[1] < bottom or nb[1] > top:
                    continue
                if nb in blocked:
                    continue
                ng = g[cur] + 1.0
                if ng < g.get(nb, math.inf):
                    g[nb] = ng
                    came_from[nb] = cur
                    heapq.heappush(heap, (ng + h(nb, end), nb))
        return None

    def _path_to(self, sprite: StudentSprite, dest: tuple[float, float]) -> None:
        """Send a sprite to dest via A* pathfinding, falling back to direct if no path."""
        start = (sprite.center_x, sprite.center_y)
        gs = self._barrier_list.grid_size
        sc = (int(start[0] // gs), int(start[1] // gs))
        dc = (int(dest[0] // gs), int(dest[1] // gs))
        path = self._astar(start, dest)
        if path:
            sprite.set_path(path)
        else:
            sprite.set_target(*dest)

    def _sync_sprites_to_sim(self) -> None:
        for student in self._state.students:
            sprite = self._student_sprites[student.student_id]
            sid = student.student_id
            prev_dest = self._prev_destinations.get(sid)
            curr_dest = student.destination.name if student.destination else None

            # Start walking as soon as destination is assigned (not when they arrive)
            if curr_dest and curr_dest != prev_dest:
                self._release_sit_point(sid)
                sp_name = self._pick_sit_point(curr_dest, sid)
                if sp_name:
                    self._student_sit_point[sid] = sp_name
                    sx, sy, _ = self._sit_points[sp_name]
                    self._path_to(sprite, (sx, sy))
                elif curr_dest in self._room_centers:
                    # Room is full — walk to center and stand
                    cx, cy = self._room_centers[curr_dest]
                    self._path_to(sprite, (cx + random.uniform(-30, 30), cy + random.uniform(-20, 20)))

            if student.state == StudentState.IDLE and not sprite.is_walking and not sprite.is_stationed:
                sprite.stop()

            self._prev_destinations[sid] = curr_dest
