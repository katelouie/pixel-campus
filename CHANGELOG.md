# Changelog

All notable changes to Pixel Campus are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Named weekdays in HUD banner: "Mon 9:35a" replaces "Day 1 | 9:35 AM". `GameClock` gains `weekday_str` and `day_time_str` properties.

### Changed
- Student count: 20 → 10 (`high_school.json`). 45 trackable relationship pairs vs. 190.
- Skill gain now scaled by mood: `mood_mult = 0.5 + (mood_value / 100.0)`. Unhappy students learn slower; happy students learn faster. Unlocks the primary cascade loop.
- Mood → conversation snapping: students with mood < 25 have a 30% chance to turn a NEUTRAL conversation CONFLICT. Bad days feel real.
- Overnight need recovery now respects trait satisfaction multipliers (was ignoring traits).
- HUD log history cap raised: 12 → 200 message groups (was silently dropping earlier messages on busy ticks).

### Fixed
- `favorite_skill` / `dreaded_skill` non-determinism: traitless students now seed from `student_id` via `random.Random`, returning a stable value across multiple calls in the same tick.
- Music Room activity state: `Skill.MUSIC` now maps to `StudentState.CREATING` in `SKILL_TO_ACTIVITY` (was falling back to SOCIALIZING).
- Duplicate `FRIENDSHIP_LEVEL_THRESHOLDS`: `conversation.py` now imports the canonical copy from `social.py`.

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
