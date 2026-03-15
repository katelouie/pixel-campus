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

from src.sim.engine import GameState
from src.sim.models import StudentState
from src.ui.hud import HUD
from src.ui.sprites import StudentSprite

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TMX_PATH = str(_PROJECT_ROOT / "rooms" / "high_school_v0.tmx")
MAP_SCALE = 1.0
CAMERA_SPEED = 10.0

CHARACTER_SHEETS: list[str] = ["Adam", "Alex", "Amelia", "Bob"]

# Maps sit point type prefix → sim room name (must match DEFAULT_ROOMS names exactly)
_SIT_PREFIX_TO_ROOM: dict[str, str] = {
    "sit_desk": "Math Classroom",
    "sit_cafeteria": "Cafeteria",
    "sit_computer": "Computer Lab",
    "sit_library": "Library",
    "sit_gym": "Gym",
    "sit_stands": "Gym",
}


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
        self._sit_points: dict[str, tuple[float, float, str]] = {}
        for obj in self._tile_map.object_lists.get("Sit", []):
            facing = obj.properties.get("facing", "south") if obj.properties else "south"
            self._sit_points[obj.name] = (
                float(obj.shape[0]),
                float(obj.shape[1]),
                facing,
            )

        # --- Explicit room centers from a "RoomCenters" object layer ---
        self._explicit_room_centers: dict[str, tuple[float, float]] = {}
        for obj in self._tile_map.object_lists.get("RoomCenters", []):
            if obj.name:
                self._explicit_room_centers[obj.name] = (
                    float(obj.shape[0]),
                    float(obj.shape[1]),
                )

        # Room centers: explicit points win; fall back to sit point centroids
        self._room_centers: dict[str, tuple[float, float]] = (
            self._compute_room_centers()
        )
        print("Room centers loaded:", list(self._room_centers.keys()))

        # --- Students ---
        self._student_sprites: dict[int, StudentSprite] = {}
        self._sprite_list = arcade.SpriteList()
        self._name_labels: dict[int, arcade.Text] = {}
        self._mood_labels: dict[int, arcade.Text] = {}
        self._build_student_sprites(char_textures)

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
        self._hud.push_messages(
            ["Welcome to Pixel Campus! SPACE to advance time. Arrow keys to pan."]
        )

        self._selected_sprite: StudentSprite | None = None
        # Initialise to None so first sync fires for all students
        self._prev_destinations: dict[int, str | None] = {
            s.student_id: None for s in self._state.students
        }

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _compute_room_centers(self) -> dict[str, tuple[float, float]]:
        """Compute room centers: explicit RoomCenters points win, fall back to sit centroids."""
        by_room: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for name, (x, y, _) in self._sit_points.items():
            for prefix, room_name in _SIT_PREFIX_TO_ROOM.items():
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
        """Send every idle student to a room based on their favourite skill."""
        skill_to_room = {
            "academics": "Math Classroom",
            "athletics": "Gym",
            "creativity": "Art Room",
            "social": "Cafeteria",
            "music": "Music Room",
        }
        for student in self._state.students:
            room_name = skill_to_room.get(student.favorite_skill.value, "Quad")
            room = self._state.get_room_by_name(room_name)
            if room:
                self._state.assign_student(student, room)

    def _build_student_sprites(self, char_textures: dict[str, dict]) -> None:
        for i, student in enumerate(self._state.students):
            sheet_name = CHARACTER_SHEETS[i % len(CHARACTER_SHEETS)]
            sprite = StudentSprite(student, char_textures[sheet_name])

            sx, sy = self._spawn_points[i % len(self._spawn_points)]
            sprite.center_x = sx + random.uniform(-30, 30)
            sprite.center_y = sy + random.uniform(-20, 20)

            self._student_sprites[student.student_id] = sprite
            self._sprite_list.append(sprite)

            self._name_labels[student.student_id] = arcade.Text(
                student.name,
                x=sprite.center_x,
                y=sprite.top + 12,
                color=arcade.color.WHITE,
                font_size=9,
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

        # Camera panning with arrow keys
        cx, cy = self._camera.position
        if arcade.key.LEFT in self._camera_keys:
            cx -= CAMERA_SPEED
        if arcade.key.RIGHT in self._camera_keys:
            cx += CAMERA_SPEED
        if arcade.key.UP in self._camera_keys:
            cy += CAMERA_SPEED
        if arcade.key.DOWN in self._camera_keys:
            cy -= CAMERA_SPEED
        self._camera.position = arcade.Vec2(cx, cy)

    def on_draw(self) -> None:
        self.clear()
        with self._camera.activate():
            self._scene.draw()
            self._walls.draw()  # DEBUG: show collision boxes
            self._sprite_list.draw()
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

    def _draw_student_labels(self) -> None:
        for sid in self._student_sprites:
            self._name_labels[sid].draw()
            self._mood_labels[sid].draw()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        self._camera_keys.add(symbol)
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

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        self._camera_keys.discard(symbol)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        # Convert screen → world coordinates
        world_x = x + self._camera.position[0] - self.window.width / 2
        world_y = y + self._camera.position[1] - self.window.height / 2
        clicked = arcade.get_sprites_at_point((world_x, world_y), self._sprite_list)
        if clicked:
            self._selected_sprite = clicked[0]
            self._hud.push_messages(
                [f"Selected {self._selected_sprite.student.name}."]
            )
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
        print(f"A* {sc}→{dc}: {'path len=' + str(len(path)) if path else 'NO PATH'}")
        if path:
            sprite.set_path(path)
        else:
            sprite.set_target(*dest)

    def _sync_sprites_to_sim(self) -> None:
        for student in self._state.students:
            sprite = self._student_sprites[student.student_id]
            prev_dest = self._prev_destinations.get(student.student_id)
            curr_dest = student.destination.name if student.destination else None

            # Start walking as soon as destination is assigned (not when they arrive)
            if curr_dest and curr_dest != prev_dest:
                if curr_dest in self._room_centers:
                    cx, cy = self._room_centers[curr_dest]
                    dest = (cx + random.uniform(-30, 30), cy + random.uniform(-20, 20))
                    self._path_to(sprite, dest)
                else:
                    print(f"{student.name} → {curr_dest}: NO ROOM CENTER, not moving")

            if student.state == StudentState.IDLE and not sprite.is_walking:
                sprite.stop()

            self._prev_destinations[student.student_id] = curr_dest
