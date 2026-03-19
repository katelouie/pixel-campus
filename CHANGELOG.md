# Changelog

All notable changes to Pixel Campus are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased — 2026-03-18]

### Added
- **Journal system overhaul** — the journal is now the emotional core of the game.
  - **JournalEntry dataclass** (`models.py`): promoted from `tuple[int, str]` to `JournalEntry(text, day, tick, trigger)` with `time_label` ("2:30 PM") and `period_label` ("afternoon") properties.
  - **Trait-voiced entries** (`src/data/journal_templates.json`): all 15 traits voiced across 13 situations each (~500+ unique template strings). Templates live in a separate JSON data file — `journal.py` is pure logic. Each student sounds like themselves: Bookworm terse, Class Clown performatively casual, Anxious hedging, Rebel dismissive-but-honest.
  - **Three generation modes** (`journal.py`): end-of-day retrospective (50% trait voice → thought-driven → generic mood → zodiac flavor), start-of-day prospective (50% chance, forward-looking), event-triggered mid-day (EventBus subscriber).
  - **19 trigger types**: end_of_day, start_of_day, boring_day, dating, crush, friendship_levelup, conflict, match, grade_failed, grade_milestone, skill_milestone, jealous, encouraged, mood_happy, mood_sad, mood_crisis, loneliness, new_room, activity_fav/dread/neutral/improving.
  - **Activity reflection** (~18% per activity completion): interacts with favorite/dreaded skill. "Art just poured out of me today" vs "Why am I doing academics. Why."
  - **Mood threshold crossing**: fires journal entries when mood crosses happy (70+), sad (<35), or crisis (<20) thresholds. Crisis entries are trait-voiced ("My chest won't stop. My brain won't stop. Everything is spiraling." — Anxious).
  - **Guaranteed minimum**: if a student has zero entries for the day, a trait-voiced "boring day" entry always fires. "Quiet day. Good." — Loner. "LITERALLY nothing happened today. I am so bored I could scream." — Social Butterfly.
  - **Daily cap of 6** entries per student per day prevents any one student from flooding.
  - **Frequency budget**: quiet days 1-2 entries, normal days 2-3, dramatic days 4-6. Average ~2.8 per student per day in testing.
  - **Design doc**: `planning/journal_design.md`

- **Profile view redesign** (`profile.py`): journal is now the primary interface.
  - Journal occupies the right 2/3 of the panel, scrollable via mouse wheel, with "Day N — time" timestamps.
  - Stats compressed into a left sidebar: portrait, identity, traits, needs bars, grades, thoughts.
  - Traits displayed as teal "link" text with underlines; hover shows description in a tooltip with papernote-themed background.
  - Need bars show full labels (Rest, Fun, Social, Academics, Creative, Athletics); numeric values appear on hover.
  - Grade subjects use proper display names (PE stays uppercase).
  - Relationship tab columns respaced; friendship affinity values appear on hover.
  - All profile text uses pixel-perfect BitmapFont renderer.

- **Unified hover tooltip system** (`profile.py`): traits, need bars, and relationship bars all share one tooltip renderer with cream background and brown border. Each hitbox tagged with its tab to prevent cross-tab phantom hovers.

- **Bitmap font system** (`bitmap_font.py`, `font.py`): enhanced BitmapFont with word wrapping (`wrap_lines`, `get_wrapped_textures`), color parameter, shared font instances with named presets (FONT_HEADER, FONT_DIM, FONT_TIMESTAMP, FONT_JOURNAL, etc.).

- **Global font configuration** (`src/ui/font.py`): single source of truth for game fonts. Change font/scale in one file to restyle the entire game (e.g., dyslexia-accessible font swap).

- **Animated minicard portrait** (`campus.py`): selected student's portrait in the minicard now runs the idle animation loop at a gentle pace. The little bob is very cute.

- **Student name labels below sprites** (`campus.py`): names now appear centered below each student sprite instead of above, with mood emoji removed for cleaner visual.

- **Full save/load system** (`src/sim/serialization.py`): complete round-trip serialization of all game state.
  - Students: needs, skills, grades (per-subject), thoughts, journal entries (all 19 trigger types preserved), personality (zodiac, preferences, romance interest), traits (saved by name, re-matched from data files on load).
  - Friendships: level, affinity, history per pair.
  - Romances: directed feelings + affinity per student per pair, history.
  - Clock: day, tick, ticks_per_day.
  - Game state: points, graduation target, weather.
  - Rooms and traits NOT serialized — reloaded from data files. Trait balance changes in `traits.json` automatically apply to existing saves.
  - Save format version 1 with migration field for future format changes.
  - ~34KB for a 3-day/5-student game. Journal text is the bulk of the size (which is the good stuff).
  - Loaded games continue correctly: JournalSubscriber re-wired, EventBus re-subscribed, social text reloaded, students dispatched on next tick.

- **Friend-seeking + crush-seeking** (`behaviors.py`): students autonomously drift toward rooms where friends, crushes, or dating partners are present. Room scoring: primary need match (20) + secondary need (10) + social pull (best friend 15, close friend 10, friend 5, crush 12, dating partner 20) + random jitter. Creates visible clique formation — Hugo follows Jasper to every room in the school.

- **Minimap** (`campus.py`): 160x120px semi-transparent overlay in the top-right corner.
  - Mood-colored dots: green (happy), yellow (neutral), blue (sad), grey (tired). Glanceable emotional state for all students at once.
  - Selected student highlighted with larger dot + yellow ring.
  - Camera viewport outline shows what part of the map you're currently viewing.
  - Drawn with primitives only (no sprites, no click interference).

- **Time-of-day autonomous behavior** (`behaviors.py`): morning people push through tiredness in the first half of the day (rest threshold 15 vs base 25), tire easily in the evening (threshold 35). Night owls opposite. Creates visible daily rhythms — early-risers active at 8am, night owls dragging until afternoon.

- **Weather display in HUD** (`hud.py`): current weather now shown in the top banner: `Mon 9:35a | Sunny | Points: 0/800`. Weather was already simulated and affecting mood thoughts — now the player can see it.

- **Student separation + spread spawning** (`campus.py`): students no longer overlap.
  - Spawn distribution: students spread in a circle around spawn points (radius 30px, 20px per ring) instead of piling on the same pixel.
  - Soft separation force: every frame, walking students closer than 28px gently push apart (1.2px/frame, scaled by overlap). Sitting students exempt. Boid-style separation — cheap, natural-looking, no hard collision needed.

### Changed
- **Minicard rendering** (`campus.py`): all minicard elements (panel, portrait, button, text) now drawn via `arcade.draw_texture_rect` instead of `arcade.Sprite` to avoid polluting arcade's global spatial hash, which was causing mouse event interception.
- **Profile tab labels**: "MY FEELINGS"/"THEIR FEELINGS" shortened to "I FEEL"/"THEY FEEL".
- **Student sprite hitbox** (`sprites.py`): switched to `algo_bounding_box` for full-rectangle click detection instead of the default detailed algorithm that traces non-transparent pixels (which made tiny clickable areas on pixel art characters).
- Journal end-of-day generation probability raised from 60% to 70%.
- Encourage action now fires a journal entry (80% probability) in addition to the mood thought.
- Jealousy system now fires journal entries (45% probability) alongside jealousy thoughts.
- Skill milestones (25/50/75) now fire journal entries (55% probability).

### Fixed
- **Critical: mouse event dispatch bug** (`main_arcade.py`): wrapping `Window.dispatch_event` with a pass-through function fixes a pyglet/arcade bug where mouse click events were silently dropped before reaching `on_mouse_press`. The wrapper is semantically a no-op (`def f(*a): return orig(*a)`) but changes the method binding in a way that bypasses whatever internal caching was filtering events. Cause unknown; fix is stable and zero-cost. Without this wrapper, ~70% of mouse clicks were silently lost.
- **Sprite-as-text click interference**: bitmap font `arcade.Sprite` objects drawn in world space (name labels below students) were registering in arcade's global spatial hash and intercepting click detection even though they weren't in any `SpriteList`. Fix: world-space text labels use `arcade.Text` (which doesn't participate in hit testing); all other bitmap text uses `arcade.Sprite` safely (profile view, context menus) since those are screen-space overlays.
- **Context menu draw_text performance warning**: all `arcade.draw_text()` calls replaced with pre-built `arcade.Text` objects or bitmap font sprites.
- Introduce action now forces immediate conversation (`maybe_interact` + `maybe_romance` called directly).
- Encourage action now adds +5 friendship affinity and checks for level-up threshold crossing.

### Removed
- Mood emoji floating above student sprites (replaced by name-below-sprite layout).
- `draw_text` calls throughout UI (replaced with Text objects or bitmap font).

---

## [Previous Unreleased]

### Added
- **Right-click context menu** (`campus.py`): select student A, right-click student B to get a social action menu.
  - **Introduce A & B**: sends both to A's current room (or Cafeteria as neutral ground)
  - **Separate B**: sends B to a random room away from A
  - **Encourage B**: fires `thought_encouraged()` (+5 mood, 24 ticks) — "Someone believed in me today"
  - **Room-specific activity** (conditional): if the cursor is inside a room's Tiled bounds, a fourth option appears — "Study in Library", "Train in Gym", "Create in Music Room", "Hang out in Cafeteria", etc. Verb derived from the room's `skill_boost` via `SKILL_TO_ACTIVITY`.
  - Menu nudges away from screen edges; any click dismisses it; clicking outside executes nothing.
- **Jealousy system** (`thoughts.py` + `engine.py`): global trigger — when A chats with B, any student C
  with a crush on A or B fires `thought_jealous` if the chat partner is a gender C is attracted to.
  Same-room = 90% chance; different room = 25% ("somehow you just know"). Mood effect: -4, 12 ticks.
  Creates the cascade: spark → jealousy → bad mood → conflict → more drama.
- **Simulation harness** (`tools/simulate.py`): headless Monte Carlo tool for tuning magic numbers. Runs N games × T days and reports per-day distributions: mood, romance, friendship, grades, skills, critical need pressure. `python -m tools.simulate --days 14 --runs 100`
- **EventBus** (`src/sim/game_events.py`): `GameEventType`, `GameEvent`, `GameEventBus`. Synchronous pub/sub system for simulation events. `GameState` gains a `bus` field. Emit sites wired across `thoughts.py`, `conversation.py`, `social.py`, `engine.py`, `behaviors.py`. No subscribers yet — foundation for Storyteller, Sound, Day Summary, Drama Events.
  - Events emitted: `THOUGHT_ADDED` (|mood_effect| ≥ 3), `FRIENDSHIP_LEVEL_UP`, `CHAT_CONFLICT`, `CHAT_MATCH`, `ROMANCE_SPARK`, `ROMANCE_DATING`, `GRADE_FAILED`, `DAY_ENDED`
- Named weekdays in HUD banner: "Mon 9:35a" replaces "Day 1 | 9:35 AM". `GameClock` gains `weekday_str` and `day_time_str` properties.

### Changed
- **Need decay retuning** (three-pass calibration against actual room satisfaction amounts):
  - Key insight: `NeedType.FUN` maps to social rooms, so FUN/SOCIAL auto-satisfy via cafeteria. ACADEMICS/CREATIVITY/ATHLETICS need explicit player direction → lower decay so they pressure slowly rather than crash.
  - Final rates: REST 0.60, SOCIAL 0.50, FUN 0.55, ACADEMICS 0.28, CREATIVITY 0.25, ATHLETICS 0.30
  - Idle REST recovery: `1.0 → 0.3` per tick (was too generous — kept REST permanently at 100)
  - Idle FUN recovery: `0.3 → 0.5` per tick (being idle is mildly fun)
  - Overnight: `fun_recovery [8,14]`, `social_recovery [5,10]`, `minor_recovery [4,8]`
  - Result: mood stable at 58-70, ACADEMICS orbits 40-47 (real but not punishing), ~32% critical pressure by day 14 without player guidance
- **Romance tuning** (was effectively broken — expected days to first crush was 1,143):
  - `base_threshold`: `0.05 → 0.70` (sparks fly; high schoolers catch feelings fast)
  - `slow_burn` threshold: `0.15 → 0.90`
  - CRUSH affinity threshold: `25 → 5`
  - DATING affinity threshold: `50 → 20`
  - Affinity gain per spark: removed compat penalty (`randint(3, 8)` instead of `int(uniform(3,8) * compat)`)
  - Dating gate: `compat > 0.6` → `compat > 0.2` (0.6 was impossible — max realistic compat is ~0.5)
  - Dating probability per encounter: `0.10 → 0.35`
  - Romance interest generation: weights `[65, 28, 7]` → `[15, 45, 40]` (more students interested in multiple genders); nobody rate `10% → 5%`
  - Result: ~30% crush rate by day 2, ~32% dating by day 14
- **Friendship tuning** (was taking ~88 days to become friends):
  - FRIEND threshold: `35 → 10`
  - CLOSE_FRIEND threshold: `55 → 25`
  - BEST_FRIEND threshold: `75 → 45`
  - Result: ~45% of pairs at FRIEND+ by day 14
- Student count: 20 → 10 (`high_school.json`). 45 trackable relationship pairs vs. 190.
- Skill gain now scaled by mood: `mood_mult = 0.5 + (mood_value / 100.0)`. Unhappy students learn slower; happy students learn faster. Unlocks the primary cascade loop.
- Mood → conversation snapping: students with mood < 25 have a 30% chance to turn a NEUTRAL conversation CONFLICT. Bad days feel real.
- Overnight need recovery now respects trait satisfaction multipliers (was ignoring traits).
- HUD log history cap raised: 12 → 200 message groups (was silently dropping earlier messages on busy ticks).

### Fixed
- `favorite_skill` / `dreaded_skill` non-determinism: traitless students now seed from `student_id` via `random.Random`, returning a stable value across multiple calls in the same tick.
- Music Room activity state: `Skill.MUSIC` now maps to `StudentState.CREATING` in `SKILL_TO_ACTIVITY` (was falling back to SOCIALIZING).
- Duplicate `FRIENDSHIP_LEVEL_THRESHOLDS`: `conversation.py` now imports the canonical copy from `social.py`.
- **Grade system overhaul** (`academics.py`): grades were flat C-range for all 14 days. Root causes: drift rate too aggressive, skill-to-grade multiplier too small, and Music Room never visited autonomously.
  - `DRIFT_RATE`: `0.01 → 0.003` (~4-day half-life for gains; was ~18 hours)
  - `SKILL_TO_GRADE`: `0.15 → 0.30` (2× bigger per-session gains — studying visibly moves the needle)
  - Added **baseline creep**: when `grade.value > baseline + 5`, baseline rises at 0.002/tick. Sustained effort raises your floor, not just your ceiling.
  - Added **grade inertia / sticky zones**: drift runs at 25% strength in the 4 points above each base letter threshold (90/80/70/60). Earned letter grades defend themselves — a student with a B doesn't drop to C just because they spent two days on the party event.
  - Result: grades climb C → B- range over 14 days of autonomous play; player-directed studying reaches B/B+ territory.
- **Music Room routing** (`behaviors.py`): Music Room was never visited autonomously because `NEED_TO_SKILL` only mapped `CREATIVITY → Skill.CREATIVITY` (Art Room). Renamed to `NEED_TO_SKILLS` with list values; CREATIVITY now routes to both Art Room and Music Room. Music grades now climb (C → C+ over 14 days) instead of sitting flat.

### Planned
See `planning/TODO.md` for prioritized upcoming work.

---

## [0.1.0] — 2026-03-17

### Core Simulation Engine

- Student dataclass with needs, skills, grades, traits, personality, thoughts, journal, romance
- Need system: 6 need types (REST, FUN, SOCIAL, ACADEMICS, ATHLETICS, CREATIVITY) with decay, satisfaction, and trait modifiers
- Mood system: computed from active thoughts + needs baseline
- Thought system: timed mood modifiers with stacking/expiry, categories, source deduplication
- Trait system: 15 traits loaded from JSON (`traits.json`), mutual exclusion enforcement, `has_trait()` helper
- Friendship system: directed affinity per pair, 5 levels (Stranger → Best Friend) with thresholds
- Romance system: directed feelings per student per pair (Platonic / Crush / Dating), compatibility scoring, `feelings_of()` / `affinity_of()` accessors
- Conversation system: topic-driven interactions (Music, Movies, Athletics, Art, Academics, Worldview), outcome evaluation (Match / Neutral / Conflict), affinity/skill/social need effects, flavor text templates
  - First conversation immediately moves Stranger → Acquaintance
- Academic system: per-subject grades with trait baselines, drift toward mean, skill correlation, report cards
- Journal system: end-of-day entry generation with mood-based templates, zodiac flavor (40% chance), 60% generation rate
- Scenario config: JSON-driven (`high_school.json`) — student count, room setup, event schedule, lunch period, ticks-per-day
- Clock: tick-based, 48 ticks = 1 school day (8 AM–4 PM), 12-hour display

### Behaviors

- Activity processing: skill gain with trait multipliers, need satisfaction, grade application, thought generation on completion
- Thought firing: `thought_lonely` (SOCIAL < 20), `thought_academic_pressure` (ACADEMICS < 15), `thought_skill_milestone` at 25/50/75/100 crossings
- Chatting behavior: two-student chat sessions with `resolve_conversation()` wiring
- Autonomous decision-making: idle students route to room satisfying lowest need (6% chance per tick, suppressed during lunch)
- Lunch period: all students dispatched to Cafeteria at tick 24 (noon); `thought_lunch_social` fired for cafeteria students at lunch end; idle students nudged out with `_autonomous_decision`

### Traits (15 total)

Bookworm, Social Butterfly, Loner, Class Clown, Overachiever, Slacker, Jock, Artist, Flirt, Musician, Attractive, Anxious, Empath, Rebel, Perfectionist — with grade baseline modifiers, need multipliers, skill multipliers, thought multipliers, and mutual exclusion rules

### Romance

- `_romance_interest_compatible()`: checks `list[RomanceInterest]` (BOYS / GIRLS / NON_BINARY) against gender
- Spark probability: base × avg flirt skill × location boost × Attractive trait boost (1.5×)
- `thought_crush` fires on CRUSH level-up; `thought_dating` fires on DATING transition
- Flirt near Attractive student → `thought_charmed_by`

### Events

- Basketball Game, Art Show, Finals, Prom — triggered on fixed-day schedule
- Skill-check resolution with flavor text and point rewards

### Arcade UI

- `CampusView`: TMX map (Modern Interiors tileset), A* pathfinding (custom, no iteration cap), student sprites with directional animation (8 directions, sit/stand states), activity bubbles (classwork / basketball / music), camera pan/zoom, click-to-select, click-to-assign
- `ProfileView`: Two-tab layout (Profile / Relationships), portrait, mood emoji, needs bars, grades, traits, thoughts (up to 6), journal entries (up to 4), ✕ close button, clickable tab strip with pre-built arcade.Text labels
  - Relationships tab: full student list sorted by romance status → friendship → name; directed "My feelings" / "Their feelings" columns; color-coded affinity bars; status labels (Dating!, Mutual crush, I like them, They like me)
- HUD: scrollable log panel (bitmap font), top banner (day/time/points), clickable student names in log
- Window icon: `Book.png` set via `pyglet.image`

### Bug Fixes (build history)

- Fixed `arcade.Text` positional args (was using kwargs `start_x=`, `start_y=`) — profile view text now renders
- Fixed GL context error: texture loading deferred to `__init__` (not module level)
- Fixed camera drift: `on_show_view` calls `_camera_keys.clear()` to prevent stuck key state after ProfileView return
- Fixed click accuracy at non-1.0 zoom: world transform now `(x - w/2) / zoom + cam.x`
- Fixed `arcade.draw_text()` PerformanceWarning in tab labels: replaced with pre-built arcade.Text objects
- Fixed `IntEnum` issues in student state comparisons
- Fixed animation `IndexError` on sprite initialization
- ESC in CampusView clears student selection

---

## [0.0.1] — 2026-02 (pre-history)

### Foundation

- Project scaffold: Python 3.11, Arcade 3.x, pytest, ruff
- Data-driven rooms, traits, scenarios (JSON)
- Tiled map integration (`.tmx` with collision, sit/stand/action object layers)
- A* pathfinding with custom implementation
- CLI entry point (`main_cli.py`) for headless simulation testing
- Basic student generation with name pools from `names.json`
