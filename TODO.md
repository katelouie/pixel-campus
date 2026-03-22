# Pixel Campus — TODO

Organized by priority tier. Quick wins first — most of these are 1–20 lines and transform the feel of the game.
Each item links to the audit doc that describes it in detail (`planning/audit/`).

---

## Tier 1: Quick Wins (trivial → low complexity, high impact)

These should be done before anything else. Each is fast and meaningfully improves the game.

- [x] **Mood → skill gain multiplier** (`behaviors.py:_process_activity`)
  `mood_mult = 0.5 + (student.mood_value / 100.0)` — one line that unlocks the cascade engine.
  Bad mood → slower growth → worse grades → worse thoughts → worse mood. Happy students learn faster.

- [x] **Student count: 20 → 10** (`data/scenarios/high_school.json`)
  45 relationship pairs the player can track vs. 190 they can't. Single highest-ROI change.

- [x] **Mood → conversation snapping** (`conversation.py:resolve_conversation`)
  Students with mood < 25 have 30% chance to snap (NEUTRAL → CONFLICT). Bad days feel real.

- [x] **Fix `favorite_skill` non-determinism** (`models.py`)
  Traitless students now seed from `student_id` via `random.Random(student_id).choice(...)` — stable across calls.

- [x] **Fix overnight recovery ignoring trait modifiers** (`engine.py`)
  Now passes `traits=student.traits` to all overnight `satisfy_need()` calls.

- [x] **Fix Music Room activity state mapping** (`models.py`)
  Added `Skill.MUSIC: StudentState.CREATING` to `SKILL_TO_ACTIVITY`.

- [x] **Fix HUD message history cap** (`hud.py`)
  Raised `MAX_MESSAGES` from 12 to 200.

- [x] **Fix duplicate FRIENDSHIP_LEVEL_THRESHOLDS** (`conversation.py`)
  Now imports from `social.py` instead of redefining.

- [x] **Named weekdays** (`clock.py` / `hud.py`)
  Added `weekday_str` and `day_time_str` properties to `GameClock`. HUD now shows "Mon 9:35a".

---

## EventBus (do before Tier 2 — foundation for all reactive systems)

Build this after Tier 1, before building Storyteller, Sound, Day Summary, or Drama Events.
All Tier 2 reactive systems plug into the bus cleanly once it exists.
See `planning/event_bus_design.md` for full design.

- [x] **Create `src/sim/game_events.py`**
  `GameEventType` enum, `GameEvent` dataclass, `GameEventBus` class.

- [x] **Add `bus: GameEventBus` to `GameState`** (`engine.py`)
  `bus: GameEventBus = field(default_factory=GameEventBus)` — no subscribers wired yet.

- [x] **Thread `bus` through emit sites** (additive changes, no behavior change)
  - `thoughts.py:add_thought(thoughts, thought, bus=None)` — emit THOUGHT_ADDED for |mood_effect| ≥ 3
  - `conversation.py:resolve_conversation(..., bus=None)` — emit FRIENDSHIP_LEVEL_UP, CHAT_CONFLICT, CHAT_MATCH
  - `social.py:maybe_romance(..., bus=None)` — emit ROMANCE_SPARK, ROMANCE_DATING
  - `social.py:maybe_interact(..., bus=None)` — thread bus into resolve_conversation
  - `engine.py:_start_chat()` — pass `self.bus` to maybe_interact and maybe_romance
  - `engine.py:_report_card()` — emit GRADE_FAILED directly
  - `engine.py:_end_of_day()` — emit DAY_ENDED
  - `behaviors.py` — pass `state.bus` to add_thought calls

---

## Tier 2: High Impact (medium complexity, substantial gameplay effect)

- [x] **Jealousy system** (`thoughts.py` + `engine.py:_start_chat`)
  Global trigger (not same-room only): when A chats with B, any student C with a crush on A or B fires `thought_jealous`
  if the chat partner is a gender C is attracted to. Same-room = 90% chance, different room = 25% ("somehow you just know").
  → See `technical_implementation.md §1c`, `conversation_log.md §1b`

- [ ] **Rumor mill** (new `src/sim/rumors.py`)
  EventBus subscriber that propagates drama through the friendship graph with delay and decay.
  Subscribes to ROMANCE_DATING, ROMANCE_SPARK, CHAT_CONFLICT, CHAT_MATCH. Rumors travel student-to-student
  weighted by friendship level — close friends spread news fast, strangers rarely pass it on.
  Fires jealousy (and other drama thoughts) when a rumor *arrives* at the target, replacing the
  probabilistic distance penalty with tracked propagation chains. Distortion optional: rumors could
  arrive slightly wrong ("I heard they're dating" before they actually are).
  Pairs with and eventually supersedes the current 25%-chance global jealousy trigger.

- [x] **Journal system overhaul** (`journal.py` + `models.py` + `engine.py`)
  Three-part enhancement that makes the journal the emotional core of the game.
  → See `planning/journal_design.md` for full design.
  - **JournalEntry dataclass**: promote from plain strings to `JournalEntry(text, day, tick, trigger)` — enables "Day 5 — afternoon" timestamps in profile view.
  - **Trait-voiced entries**: `_TRAIT_VOICE` dict with per-trait templates for each situation (dating, conflict, friendship levelup, happy, sad). 50% chance before generic fallback. Each student sounds like themselves — Bookworm terse, Class Clown performatively casual, Anxious hedging, Rebel dismissive-but-honest.
  - **Prospective entries** (start-of-day): student looks forward based on active thoughts. "I kind of hope Marcus is in the art room again today."
  - **Event-triggered mid-day entries**: EventBus subscriber fires journal entries on ROMANCE_DATING (100%), ROMANCE_SPARK (75%), FRIENDSHIP_LEVEL_UP (45-80%), CHAT_CONFLICT (65%), GRADE_FAILED (85%), etc. Permanent record of the moments that matter.
  - **Note**: template writing is the main labor — 8 traits × ~5 situations each. See `journal_design.md` for the template writing guide and existing templates for Bookworm, Class Clown, Anxious, Rebel, Empath, Overachiever, Artist, Loner.

- [x] **Friend-seeking + crush-seeking autonomous decisions** (`behaviors.py:_autonomous_decision`)
  Room scoring system: need satisfaction (20 primary/10 secondary) + social pull (best friend 15, close friend 10, friend 5, crush 12, dating 20) + random jitter. Students drift toward people they care about without sacrificing critical needs. Creates visible clique formation and crush-following behavior.

- [ ] **Fight system** (`src/sim/fights.py` + `engine.py`)
  Students can get into fights based on: incompatible traits, jealousy buildup, repeated chat conflicts,
  low mood + provocation. Fights damage friendship affinity, create strong negative thoughts for both
  participants (and witnesses), drain social/fun needs, and generate dramatic journal entries. Fights
  could escalate (verbal → shoving → full fight) or be broken up by the player (right-click "Break it up").
  Rebel and Class Clown more likely to instigate. Anxious and Empath more affected as witnesses.
  Feeds into the rumor mill. The Big Drama Generator.

- [ ] **Sprite mood tinting** (`campus.py:on_update`)
  Blue-grey tint for mood < 30, full brightness for mood > 75. Glanceable emotional state without clicking.
  → See `technical_implementation.md §3a`

- [ ] **Storyteller pacing module** (new `src/sim/storyteller.py`)
  Lightweight drama director: tracks tension (0-100), phases (CALM → RISING → CLIMAX → FALLING).
  Multiplies social encounter rates by phase. Creates breathing room after drama.
  → See `technical_implementation.md §2`, `design_philosophy.md §5`

- [ ] **Day summary screen** (new `src/ui/views/day_summary.py`)
  Pause between days with: points gained (and why), weather, student activity summary, skill gains, relationship changes, conversations, notable events. The "one more day" hook.
  → See `technical_implementation.md §5b`

---

## Tier 2b: Event System Rework (design shift, high impact)

These belong together — they form a cohesive redesign of how events work, transforming the player from spectator to social architect.

- [x] **Player-driven event system** (`events.py` + `views/event_menu.py` + `views/event_results.py`)
  Complete rewrite: 7 events, player schedules from menu, pays point cost, countdown timer, team-total resolution. The Big Party has special invitation mechanics. Event menu accessible from HUD. Results modal on completion.
  → See `planning/events_revamp.md`

- [x] **Points as currency** — events cost points to schedule. Cancel for 50% refund.

- [ ] **Graduation ceremony + year cycling** (`views/graduation.py`)
  Complete X/7 events → unlock graduation. Superlative slides from game data, senior archival to yearbook, year promotion, new freshman generation via character creator. Event completion resets for new year.
  → See `planning/events_revamp.md`

- [ ] **Yearbook** — persistent archive of graduated classes. Viewable from title screen + campus HUD.

- [ ] **Personality system wiring** (`behaviors.py:_autonomous_decision`)
  - [x] Weather preference: daily weather roll fires mood thoughts based on student preference match/mismatch/storm. (`engine.py:_end_of_day`)
  - [x] Wire `time_of_day` preference into autonomous decisions: morning people push through tiredness in first half (rest threshold 15), tire easily in second half (threshold 35). Night owls opposite. Creates visible social texture — early-risers active at 8am, night owls dragging.
  → See `clicky_design_thoughts.md §The Personality System Is Your Best Underused Asset`

---

- [ ] **Dates as an activity** (`engine.py` + new activity type)
  When two students are DATING and share a room, small chance to trigger a "date" activity: special flavor text, big mood boost, social need satisfaction, flirt skill gain. The thing players will wait all week to see happen.
  → Pairs naturally with the day summary screen (\"Alex and Riley went on a date yesterday!\")

---

## Tier 3: Meaningful Features (more involved, high fun factor)

- [x] **Right-click social context menu** (`campus.py`)
  Select A, right-click B: "Introduce A & B", "Separate B", "Encourage B", + room-specific activity
  option when cursor is inside a Tiled room bounds ("Study in Library", "Train in Gym", etc.).
  → See `technical_implementation.md §2a`, `avatar_high_comparison.md §1`

- [ ] **Expanded activity bubbles** (`campus.py:_ACTIVITY_ICON`)
  Add icons for: art (palette), book/study, chat/social, heart (crush context), angry (post-conflict), zzz (resting).
  → See `technical_implementation.md §3c`, `review_polish.md §8`

- [ ] **Walking speed reflects energy** (`sprites.py`)
  `speed = base_speed * (0.5 + rest_need / 200.0)`. Tired students drag visually.
  → See `technical_implementation.md §3d`

- [ ] **Live narrative status on mini-card** (`campus.py` selection card)
  Replace "Socializing" with "Chatting with Marcus about hip-hop". Data already in the sim.
  → See `avatar_high_comparison.md §3`

- [ ] **School-wide stat sidebar** (`campus.py` / new sidebar widget)
  Persistent bars: Academics, Athletics, Creativity, Social Health, Happiness — school-level aggregates.
  → See `avatar_high_comparison.md §4`

- [ ] **Sound system skeleton** (new `src/ui/sounds.py`)
  Lazy-loading SoundManager + pattern-match log messages → play: friendship_up, heartbeat, record_scratch, bell, sparkle.
  ~6 .wav files from kenney.nl. Highest emotional payoff per line of any feature.
  → See `technical_implementation.md §6`

- [x] **Save/load: full serialization** (`serialization.py`)
  Full round-trip serialization of all game state: students (needs, skills, grades, thoughts, journal, personality, traits), friendships, romances, clock, weather, points. Rooms and traits reloaded from data files, matched by name. Save format version 1 with migration support. 34KB for a 3-day/5-student game.
  → See `src/sim/serialization.py`

- [ ] **Trait-flavored conversation text** (`conversation.py:_make_text`)
  Trait-conditional template variants: Class Clown + MATCH → "did their impression". Loner + CONFLICT → "just walked away".
  → See `technical_implementation.md §4c`

---

## Tier 4: Polish

- [ ] **Name label backgrounds** (`campus.py`)
  Semi-transparent rounded rect behind floating name labels. Currently invisible on dark floors.
  → See `review_polish.md §3`

- [ ] **Speed controls** (1x / 2x / 3x / pause buttons)
  Currently: SPACE, H, P. Add visible speed buttons. Display speed in top bar.
  → See `review_polish.md §6`

- [ ] **Log panel color-coding**
  Events: gold. Romance: pink. Friendship: green. System: gray. Timestamps per message.
  → See `review_polish.md §7`

- [ ] **Camera follow selected student** (`campus.py`)
  Soft-track camera to selected student's position. Arrow keys temporarily override.
  → See `review_polish.md §5`

- [x] **Day/night visual treatment + seasons** (`campus.py:on_draw` + `clock.py`)
  Fullscreen color overlay shifting with time of day AND season. Winter sunsets at 2pm, summer stays bright all day. 40-day school year: Fall → Winter → Spring → Summer. Weather weighted by season.
  → See `review_polish.md §10`

- [ ] **Pulsing selection indicator** (`campus.py`)
  Sine-wave radius pulse on the selection circle (28-32px over ~1 second).
  → See `review_polish.md §4`

- [ ] **Profile: relationship column wording**
  "MY FEELINGS" / "THEIR FEELINGS" → "How I feel" / "How they feel"
  → See `review_polish.md §11`

- [x] **Animated talking heads on Relationships tab** — 44×44 portraits per row
- [x] **Details tab on profile** — skills bars, personality preferences
- [x] **Responsive tab widths** — tab strip sizes to label length

- [ ] **Graduation epilogue + yearbook** (new view)
  CRPG-style ending slides — one per graduating senior. Portrait, two narrative sentences based on who they became (relationship states, grades, events attended, journal history). Fade to black between each slide.
  Then: a class superlatives screen. Superlatives are computed from sim state:
  - **Most Popular** — highest avg friendship affinity across all pairs
  - **Most Likely to Succeed** — highest grades + academics skill
  - **Biggest Heartbreaker** — most students with unrequited crush on them
  - **Class Couple** — DATING pair with highest combined affinity
  - **Most Improved** — largest skill gain delta from sim start to graduation
  The yearbook screen. Not a score — a story.
  → See `clicky_design_thoughts.md §Graduation Has to Be a Story Ending`

---

## Tier 5: Architecture (refactors that enable future growth)

These don't change gameplay but make the codebase much easier to work with.

- [ ] **Fix global module state** (`social.py:TEXT_TEMPLATES`, `events.py:EVENTS`)
  Move onto `GameState` as a `GameDefs` instance. Two-game safety, testability.
  → See `review_fixes.md §3`, `review_refactors.md §3`

- [ ] **Fix `_start_chat` interrupting non-idle activities** (`engine.py:372-403`)
  Only initiate chat for IDLE/SOCIALIZING students, or properly award partial credit on interrupt.
  → See `review_fixes.md §4`

- [ ] **Fix chat zombie bug** (`behaviors.py:206-238`)
  `_process_chatting` only decrements timer for lower-ID student. If lower-ID is freed, higher-ID gets stuck.
  → See `review_fixes.md §5`

- [ ] **Unify social encounter pipeline** (`engine.py:_start_chat`)
  Friendship and romance run in parallel and don't share context. One `SocialEncounter` object that applies both.
  → See `review_refactors.md §6`

- [ ] **Decouple sim tick rate from UI tick rate** (`campus.py`)
  Sprite interpolation between positions so fast-forward doesn't cause teleporting.
  → See `review_refactors.md §4`

- [ ] **Consolidate Room ↔ Skill ↔ Activity mappings**
  Three separate places define how rooms, skills, activities relate. Unify into `ActivityType` dataclass.
  → See `review_refactors.md §2`

- [ ] **Type-safe room definitions** (`defs.py`)
  Parse `needs_satisfied` strings to `NeedType` and `skill_boost` strings to `Skill` at load time.
  → See `review_refactors.md §7`

- [ ] **Extract `_process_activity` thought logic** (`behaviors.py`)
  50-line function interleaves mechanics + mood. Extract `_generate_activity_thoughts(student, room)`.
  → See `review_refactors.md §8`

- [ ] **A* iteration cap** (`campus.py`)
  Add 5000-iteration limit with fallback to direct movement.
  → See `review_fixes.md §12`

---

## Out of Scope (for now)

These are good ideas that are a bigger scope shift. Track here, don't plan yet.

- Player character / first-person mode (different game entirely)
- Extracurricular clubs system
- Gift / item shop
- Reputation / social standing system
- Student goals / aspirations system
- Schedule system (class periods)
- Scenario / mod system
- Replay / history timeline
- Relationship web visualization (graph view)

---

*Last updated: 2026-03-21. Audit source: `planning/audit/`.*
